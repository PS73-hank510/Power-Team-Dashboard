"""Application settings — persistence and APP_ROOT detection.

APP_ROOT is the single location from which all runtime paths are derived.
It resolves correctly whether the app runs as a Python script (development)
or as a PyInstaller-frozen .exe (deployment).

Never hardcode any path outside this module.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from src.core.models import LimitPair

# ---------------------------------------------------------------------------
# APP_ROOT detection — the foundation of all portability
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # Running as a PyInstaller .exe — keep data beside the executable
    APP_ROOT: Path = Path(sys.executable).parent
else:
    # Running as a Python script — project root is 2 levels above this file
    # (src/config/settings_manager.py  →  src/config  →  src  →  project root)
    APP_ROOT = Path(__file__).resolve().parents[2]

CONFIG_FILE: Path = APP_ROOT / "config.json"
LOGS_DIR: Path = APP_ROOT / "logs"

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "psu_visa_strings": [""],        # list of PSU VISA addresses (≥1)
    "load_visa_strings": [""],       # list of Load VISA addresses (rows preserved even in PSU-only)
    "no_load_mode": False,           # True = PSU-only test; load rows hidden but VISA strings kept
    "poll_rate_hz": 1.0,
    "teams_webhook_url": "",
    "log_directory": str(LOGS_DIR),
    "control_psu_output": False,
    "control_load_input": False,
    "last_load_mode": "CC",
    "graph_window_seconds": 60,
    "limits": {},  # key: "PSU_voltage" → {"min": null, "max": null}
    # Serial-port settings (apply to ASRL/COM-port resources; ignored for USB-TMC/GPIB/LAN)
    "serial_baud_rate": 9600,
    "serial_write_termination": "\n",   # LF — change to "\r\n" or "\r" for some instruments
    "serial_read_termination": "\n",
    "visa_timeout_ms": 5000,
    # Optional command sent immediately after port open, before any SCPI query.
    # e.g. "ADR 10" for TDK-Lambda GENESYS/GEN series (address = unit's RS-232 address).
    "connect_preamble": "",
}

# Valid poll rate options (Hz)
POLL_RATE_OPTIONS: list[float] = [0.5, 1.0, 2.0, 5.0, 10.0]

# Graph window options (seconds; 0 means "All")
GRAPH_WINDOW_OPTIONS: list[int] = [10, 30, 60, 120, 0]


class SettingsManager:
    """Loads and saves application settings to config.json.

    All settings are stored as typed attributes. Call load() on startup
    and save() whenever a value changes.

    Usage:
        settings = SettingsManager()
        settings.load()
        settings.teams_webhook_url = "https://..."
        settings.save()
    """

    def __init__(self) -> None:
        # Instrument connection — lists support multiple instruments
        self.psu_visa_strings: list[str] = _DEFAULTS["psu_visa_strings"][:]
        self.load_visa_strings: list[str] = _DEFAULTS["load_visa_strings"][:]
        # PSU-only mode flag: load rows are hidden but VISA strings are preserved
        self.no_load_mode: bool = _DEFAULTS["no_load_mode"]

        # Polling
        self.poll_rate_hz: float = _DEFAULTS["poll_rate_hz"]

        # Notifications
        self.teams_webhook_url: str = _DEFAULTS["teams_webhook_url"]

        # Logging
        self.log_directory: str = _DEFAULTS["log_directory"]

        # Instrument control flags
        self.control_psu_output: bool = _DEFAULTS["control_psu_output"]
        self.control_load_input: bool = _DEFAULTS["control_load_input"]

        # Load configuration
        self.last_load_mode: str = _DEFAULTS["last_load_mode"]

        # Graph display
        self.graph_window_seconds: int = _DEFAULTS["graph_window_seconds"]

        # Limits: maps parameter key (e.g. "PSU_voltage") to LimitPair
        self.limits: dict[str, LimitPair] = {}

        # Serial-port / VISA session settings
        self.serial_baud_rate: int = _DEFAULTS["serial_baud_rate"]
        self.serial_write_termination: str = _DEFAULTS["serial_write_termination"]
        self.serial_read_termination: str = _DEFAULTS["serial_read_termination"]
        self.visa_timeout_ms: int = _DEFAULTS["visa_timeout_ms"]
        self.connect_preamble: str = _DEFAULTS["connect_preamble"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load settings from config.json. Creates the file with defaults if absent."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        if not CONFIG_FILE.exists():
            self._apply_defaults()
            self.save()
            return

        try:
            raw: dict = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable config — fall back to defaults
            self._apply_defaults()
            self.save()
            return

        # -- PSU and Load VISA strings (with migration from old single-value fields) --
        self.psu_visa_strings = self._migrate_visa_strings(
            raw, "psu_visa_strings", "psu_visa_string", _DEFAULTS["psu_visa_strings"]
        )
        self.load_visa_strings = self._migrate_visa_strings(
            raw, "load_visa_strings", "load_visa_string", _DEFAULTS["load_visa_strings"],
            strip_empty_singular=True,
        )

        # -- No-load mode (added in v2) --
        self.no_load_mode = bool(raw.get("no_load_mode", False))
        # Backward compat: old configs recorded PSU-only as load_visa_strings=[]
        if not self.no_load_mode and "no_load_mode" not in raw and self.load_visa_strings == []:
            self.no_load_mode = True

        self.poll_rate_hz = float(raw.get("poll_rate_hz", _DEFAULTS["poll_rate_hz"]))
        self.teams_webhook_url = raw.get("teams_webhook_url", _DEFAULTS["teams_webhook_url"])
        self.log_directory = raw.get("log_directory", _DEFAULTS["log_directory"])
        self.control_psu_output = bool(raw.get("control_psu_output", _DEFAULTS["control_psu_output"]))
        self.control_load_input = bool(raw.get("control_load_input", _DEFAULTS["control_load_input"]))
        self.last_load_mode = raw.get("last_load_mode", _DEFAULTS["last_load_mode"])
        self.graph_window_seconds = int(raw.get("graph_window_seconds", _DEFAULTS["graph_window_seconds"]))
        self.serial_baud_rate = int(raw.get("serial_baud_rate", _DEFAULTS["serial_baud_rate"]))
        self.serial_write_termination = raw.get("serial_write_termination", _DEFAULTS["serial_write_termination"])
        self.serial_read_termination = raw.get("serial_read_termination", _DEFAULTS["serial_read_termination"])
        self.visa_timeout_ms = int(raw.get("visa_timeout_ms", _DEFAULTS["visa_timeout_ms"]))
        self.connect_preamble = raw.get("connect_preamble", _DEFAULTS["connect_preamble"])

        raw_limits: dict = raw.get("limits", {})
        self.limits = {
            key: LimitPair.from_dict(val)
            for key, val in raw_limits.items()
            if isinstance(val, dict)
        }

        # Ensure log directory exists (user may have changed it)
        self._ensure_log_dir()

    def save(self) -> None:
        """Atomically write current settings to config.json."""
        data = {
            "psu_visa_strings": self.psu_visa_strings,
            "load_visa_strings": self.load_visa_strings,
            "no_load_mode": self.no_load_mode,
            "poll_rate_hz": self.poll_rate_hz,
            "teams_webhook_url": self.teams_webhook_url,
            "log_directory": self.log_directory,
            "control_psu_output": self.control_psu_output,
            "control_load_input": self.control_load_input,
            "last_load_mode": self.last_load_mode,
            "graph_window_seconds": self.graph_window_seconds,
            "limits": {key: pair.to_dict() for key, pair in self.limits.items()},
            "serial_baud_rate": self.serial_baud_rate,
            "serial_write_termination": self.serial_write_termination,
            "serial_read_termination": self.serial_read_termination,
            "visa_timeout_ms": self.visa_timeout_ms,
            "connect_preamble": self.connect_preamble,
        }

        # Atomic write: write to temp file, then rename
        tmp = CONFIG_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(CONFIG_FILE)
            # Restrict config.json to the current user — it contains the Teams
            # webhook bearer token.  On Windows os.chmod only controls the
            # read-only attribute; for stronger protection use icacls manually.
            os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Clean up temp file so the credential isn't left on disk unmanaged
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            # Non-fatal — settings simply won't persist this round

    def get_log_dir(self) -> Path:
        """Return the configured log directory as a Path, creating it if needed."""
        p = Path(self.log_directory)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_defaults(self) -> None:
        """Reset all fields to their default values."""
        self.psu_visa_strings = _DEFAULTS["psu_visa_strings"][:]
        self.load_visa_strings = _DEFAULTS["load_visa_strings"][:]
        self.no_load_mode = _DEFAULTS["no_load_mode"]
        self.poll_rate_hz = _DEFAULTS["poll_rate_hz"]
        self.teams_webhook_url = _DEFAULTS["teams_webhook_url"]
        self.log_directory = _DEFAULTS["log_directory"]
        self.control_psu_output = _DEFAULTS["control_psu_output"]
        self.control_load_input = _DEFAULTS["control_load_input"]
        self.last_load_mode = _DEFAULTS["last_load_mode"]
        self.graph_window_seconds = _DEFAULTS["graph_window_seconds"]
        self.limits = {}
        self.serial_baud_rate = _DEFAULTS["serial_baud_rate"]
        self.serial_write_termination = _DEFAULTS["serial_write_termination"]
        self.serial_read_termination = _DEFAULTS["serial_read_termination"]
        self.visa_timeout_ms = _DEFAULTS["visa_timeout_ms"]
        self.connect_preamble = _DEFAULTS["connect_preamble"]

    @staticmethod
    def _migrate_visa_strings(
        raw: dict,
        plural_key: str,
        singular_key: str,
        default: list,
        strip_empty_singular: bool = False,
    ) -> list:
        """Return a VISA string list from *raw*, migrating old single-string keys.

        Args:
            plural_key:           New-style list key (e.g. "psu_visa_strings").
            singular_key:         Old-style single-string key (e.g. "psu_visa_string").
            default:              Fallback list when neither key is present.
            strip_empty_singular: If True, an empty/whitespace singular value yields []
                                  rather than [''] (used for Load which supports no-load mode).
        """
        if plural_key in raw:
            val = raw[plural_key]
            return val if isinstance(val, list) else [str(val)]
        if singular_key in raw:
            val = raw[singular_key]
            if strip_empty_singular and not val.strip():
                return []
            return [val]
        return default[:]

    def _ensure_log_dir(self) -> None:
        """Create the log directory if it doesn't exist."""
        try:
            Path(self.log_directory).mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fall back to default if configured path is inaccessible
            self.log_directory = str(LOGS_DIR)
            LOGS_DIR.mkdir(parents=True, exist_ok=True)

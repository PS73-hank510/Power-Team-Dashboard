"""Tests for SettingsManager — config persistence and APP_ROOT detection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.core.models import LimitPair


def _make_manager(tmp_path: Path) -> "SettingsManager":
    """Return a SettingsManager whose CONFIG_FILE and LOGS_DIR live in tmp_path."""
    import src.config.settings_manager as sm_module

    # Patch module-level paths to use tmp_path
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    from src.config.settings_manager import SettingsManager
    return SettingsManager()


def test_fresh_load_creates_config(tmp_path):
    """Loading with no config.json creates the file with defaults."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()

    assert (tmp_path / "config.json").exists()
    assert mgr.poll_rate_hz == 1.0
    assert mgr.last_load_mode == "CC"
    assert mgr.control_psu_output is False
    assert mgr.control_load_input is False


def test_fresh_load_creates_logs_dir(tmp_path):
    """Loading creates the logs directory if absent."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()

    assert (tmp_path / "logs").is_dir()


def test_round_trip_save_load(tmp_path):
    """Values survive a save → load round trip."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    from src.config.settings_manager import SettingsManager

    mgr = SettingsManager()
    mgr.load()
    mgr.psu_visa_strings = ["USB0::0x1234::INSTR", "GPIB0::5::INSTR"]
    mgr.load_visa_strings = ["USB0::0xABCD::INSTR"]
    mgr.poll_rate_hz = 5.0
    mgr.teams_webhook_url = "https://example.com/webhook"
    mgr.control_psu_output = True
    mgr.last_load_mode = "CV"
    mgr.limits = {"PSU_voltage": LimitPair(min=9.0, max=15.0)}
    mgr.save()

    mgr2 = SettingsManager()
    mgr2.load()
    assert mgr2.psu_visa_strings == ["USB0::0x1234::INSTR", "GPIB0::5::INSTR"]
    assert mgr2.load_visa_strings == ["USB0::0xABCD::INSTR"]
    assert mgr2.poll_rate_hz == 5.0
    assert mgr2.teams_webhook_url == "https://example.com/webhook"
    assert mgr2.control_psu_output is True
    assert mgr2.last_load_mode == "CV"
    assert mgr2.limits["PSU_voltage"].min == 9.0
    assert mgr2.limits["PSU_voltage"].max == 15.0


def test_corrupt_config_falls_back_to_defaults(tmp_path):
    """Corrupt JSON in config.json falls back to defaults without crashing."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    (tmp_path / "config.json").write_text("NOT VALID JSON", encoding="utf-8")

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()

    assert mgr.poll_rate_hz == 1.0
    assert mgr.psu_visa_strings == [""]


def test_migration_from_old_single_visa_fields(tmp_path):
    """Old config.json with single-string visa fields is migrated to lists."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    # Write a v1-style config with singular field names
    old_config = {
        "psu_visa_string": "USB0::0x0957::INSTR",
        "load_visa_string": "USB0::0x2A45::INSTR",
        "poll_rate_hz": 2.0,
    }
    (tmp_path / "config.json").write_text(json.dumps(old_config), encoding="utf-8")

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()

    assert mgr.psu_visa_strings == ["USB0::0x0957::INSTR"]
    assert mgr.load_visa_strings == ["USB0::0x2A45::INSTR"]
    assert mgr.poll_rate_hz == 2.0


def test_migration_empty_load_visa_string_becomes_no_load_mode(tmp_path):
    """Old config with an empty load_visa_string migrates to no_load_mode=True."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    old_config = {
        "psu_visa_string": "USB0::0x0957::INSTR",
        "load_visa_string": "",   # user had no load configured
        "poll_rate_hz": 1.0,
    }
    (tmp_path / "config.json").write_text(json.dumps(old_config), encoding="utf-8")

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()

    assert mgr.psu_visa_strings == ["USB0::0x0957::INSTR"]
    assert mgr.load_visa_strings == []
    assert mgr.no_load_mode is True


def test_psu_only_mode_saves_and_restores(tmp_path):
    """PSU-only mode: no_load_mode flag and load VISA strings both round-trip."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()
    mgr.psu_visa_strings = ["USB0::0x0957::INSTR"]
    mgr.load_visa_strings = ["USB0::0x2A45::INSTR"]  # VISA string preserved even in PSU-only
    mgr.no_load_mode = True
    mgr.save()

    mgr2 = SettingsManager()
    mgr2.load()
    assert mgr2.psu_visa_strings == ["USB0::0x0957::INSTR"]
    assert mgr2.no_load_mode is True
    assert mgr2.load_visa_strings == ["USB0::0x2A45::INSTR"]  # not discarded


def test_backward_compat_empty_load_visas_implies_no_load_mode(tmp_path):
    """Old configs with load_visa_strings=[] are auto-migrated to no_load_mode=True."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    (tmp_path / "config.json").write_text(
        json.dumps({"load_visa_strings": [], "poll_rate_hz": 1.0}), encoding="utf-8"
    )

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()
    assert mgr.no_load_mode is True


def test_unknown_keys_ignored(tmp_path):
    """Unknown keys in config.json are silently ignored."""
    import src.config.settings_manager as sm_module
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    (tmp_path / "config.json").write_text(
        json.dumps({"poll_rate_hz": 2.0, "future_unknown_key": "value"}),
        encoding="utf-8",
    )

    from src.config.settings_manager import SettingsManager
    mgr = SettingsManager()
    mgr.load()  # Must not raise

    assert mgr.poll_rate_hz == 2.0


def test_app_root_is_not_user_profile():
    """APP_ROOT must not resolve to a user-profile path."""
    from src.config.settings_manager import APP_ROOT

    root_str = str(APP_ROOT).lower()
    assert "users" not in root_str or "power_team_dashboard" in root_str.lower(), (
        f"APP_ROOT looks like a user profile path: {APP_ROOT}"
    )


def test_app_root_frozen_mode(tmp_path, monkeypatch):
    """In frozen mode, APP_ROOT resolves to the directory of sys.executable."""
    fake_exe = tmp_path / "PowerTeamDashboard.exe"
    fake_exe.touch()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    # Re-import to trigger re-evaluation of APP_ROOT
    import importlib
    import src.config.settings_manager as sm_module
    importlib.reload(sm_module)

    assert sm_module.APP_ROOT == tmp_path

    # Restore
    monkeypatch.delattr(sys, "frozen", raising=False)
    importlib.reload(sm_module)

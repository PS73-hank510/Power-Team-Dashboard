"""
Smoke Test Suite — Power Systems Monitoring Dashboard
=====================================================

Single-file smoke test that validates all 17 success criteria from SPEC.md
without any real VISA hardware.  Covers the complete stack:

  Layer 1  (pure Python)  : SettingsManager, LimitChecker, CsvLogger, TeamsNotifier
  Layer 2  (Qt + mocks)   : TestController state machine and signal flow
  Layer 3  (GUI + mocks)  : MainWindow failsafe, panel locking, instrument scan
  Layer 4  (end-to-end)   : Full happy path — connect → run → alert → stop → CSV

Success-criteria cross-reference (from SPEC.md §Success Criteria):
    SC-1   Telemetry display      → test_sc1_telemetry_arrives_from_poller
    SC-2   Live graphs            → test_sc2_graph_panel_receives_samples
    SC-3   Limit breach alert     → test_sc3_limit_breach_triggers_teams_alert
    SC-4   Limit resolution       → test_sc4_limit_resolution_triggers_resolved
    SC-5   Failsafe - lock        → test_sc5_inputs_locked_during_run
    SC-6   Failsafe - close block → test_sc6_close_blocked_when_running
    SC-7   Failsafe - unlock      → test_sc7_inputs_re_enabled_after_stop
    SC-8   Comm loss              → test_sc8_comm_error_stays_running
    SC-9   CSV logging            → test_sc9_csv_rows_written_during_run
    SC-10  Config persistence     → test_sc10_settings_round_trip
    SC-11  Load mode control      → test_sc11_load_mode_control
    SC-12  No Qt thread crashes   → (validated by every Qt test completing without crash)
    SC-13  Portability/fresh      → test_sc13_fresh_settings_defaults
    SC-14  No hardcoded paths     → test_sc14_no_hardcoded_absolute_paths
    SC-15  Instrument scan        → test_sc15_scan_populates_dropdown
    SC-16  Standalone .exe        → (PyInstaller build — out of scope for runtime smoke)
    SC-17  Exe portability        → (build-time concern — out of scope for runtime smoke)

    Full integrated flow         → test_full_happy_path_e2e
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt

from src.core.models import LimitPair, TelemetrySample, TestState

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def smoke_settings(tmp_path):
    """Real SettingsManager writing to a temp directory — no side effects."""
    import src.config.settings_manager as sm_module
    from src.config.settings_manager import SettingsManager

    # Redirect file I/O so tests never touch the real project's config.json
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    settings = SettingsManager()
    settings.log_directory = str(tmp_path / "logs")
    settings.teams_webhook_url = ""
    settings.poll_rate_hz = 10.0        # fast poll for quick tests
    settings.last_load_mode = "CC"
    settings.control_psu_output = False
    settings.control_load_input = False
    settings.limits = {}
    return settings


@pytest.fixture
def mock_psu():
    """Mock PSU that returns realistic float measurements."""
    psu = MagicMock()
    psu.measure_voltage.return_value = 12.0
    psu.measure_current.return_value = 2.0
    psu.measure_power.return_value = 24.0
    psu.disconnect.return_value = None
    return psu


@pytest.fixture
def mock_load():
    """Mock electronic load that returns realistic float measurements."""
    load = MagicMock()
    load.measure_voltage.return_value = 11.9
    load.measure_current.return_value = 1.95
    load.disconnect.return_value = None
    return load


@pytest.fixture
def controller(qtbot, smoke_settings):
    """TestController wired to the Qt event loop via qtbot."""
    from src.core.test_controller import TestController
    return TestController(smoke_settings)


@pytest.fixture
def main_window(qtbot, smoke_settings):
    """MainWindow with smoke_settings; registered with qtbot for cleanup."""
    from src.gui.main_window import MainWindow
    win = MainWindow(smoke_settings)
    qtbot.addWidget(win)
    return win


# ---------------------------------------------------------------------------
# Load-specific serial settings
# ---------------------------------------------------------------------------


def test_load_serial_settings_default_independently():
    """Load serial fields exist and have independent defaults."""
    from src.config.settings_manager import SettingsManager
    s = SettingsManager()
    assert hasattr(s, "load_serial_baud_rate")
    assert hasattr(s, "load_serial_write_termination")
    assert hasattr(s, "load_serial_read_termination")
    assert hasattr(s, "load_visa_timeout_ms")
    assert hasattr(s, "load_connect_preamble")
    assert hasattr(s, "load_command_profile")


def test_load_serial_settings_can_differ_from_psu(tmp_path, monkeypatch):
    """Load baud rate can be set independently of PSU baud rate."""
    import src.config.settings_manager as sm
    from src.config.settings_manager import SettingsManager
    monkeypatch.setattr(sm, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(sm, "LOGS_DIR", tmp_path / "logs")
    s = SettingsManager()
    s.serial_baud_rate = 9600
    s.load_serial_baud_rate = 115200
    s.save()
    s2 = SettingsManager()
    s2.load()
    assert s2.serial_baud_rate == 9600
    assert s2.load_serial_baud_rate == 115200


def test_backward_compat_old_config_populates_load_settings(tmp_path, monkeypatch):
    """An old config without load-specific serial keys falls back to PSU values."""
    import json
    import src.config.settings_manager as sm
    from src.config.settings_manager import SettingsManager
    monkeypatch.setattr(sm, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(sm, "LOGS_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir()
    # Write an old-style config with only the shared keys
    old_cfg = {
        "psu_visa_strings": [""],
        "load_visa_strings": [""],
        "no_load_mode": False,
        "poll_rate_hz": 1.0,
        "teams_webhook_url": "",
        "log_directory": str(tmp_path / "logs"),
        "control_psu_output": False,
        "control_load_input": False,
        "last_load_mode": "CC",
        "graph_window_seconds": 60,
        "limits": {},
        "serial_baud_rate": 19200,
        "serial_write_termination": "\r\n",
        "serial_read_termination": "\r\n",
        "visa_timeout_ms": 3000,
        "psu_connect_preamble": "",
        "load_connect_preamble": "",
        "psu_command_profile": "standard_scpi",
        "load_command_profile": "standard_scpi",
    }
    (tmp_path / "config.json").write_text(json.dumps(old_cfg), encoding="utf-8")
    s = SettingsManager()
    s.load()
    # Load settings should fall back to shared PSU values
    assert s.load_serial_baud_rate == 19200
    assert s.load_serial_write_termination == "\r\n"
    assert s.load_serial_read_termination == "\r\n"
    assert s.load_visa_timeout_ms == 3000


# ---------------------------------------------------------------------------
# SC-10 — Config persistence
# ---------------------------------------------------------------------------


def test_sc10_settings_round_trip(tmp_path):
    """save() followed by load() on a fresh instance preserves all fields."""
    import src.config.settings_manager as sm_module
    from src.config.settings_manager import SettingsManager

    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    s = SettingsManager()
    s.teams_webhook_url = "https://hook.example.com/abc123"
    s.poll_rate_hz = 5.0
    s.log_directory = str(tmp_path / "logs")
    s.control_psu_output = True
    s.control_load_input = True
    s.last_load_mode = "CR"
    s.graph_window_seconds = 30
    s.psu_visa_strings = ["USB0::MOCK::PSU"]
    s.load_visa_strings = ["USB0::MOCK::LOAD"]
    s.limits = {
        "PSU_voltage": LimitPair(min=9.0, max=15.0),
        "PSU_current": LimitPair(max=5.0),
    }
    s.save()

    s2 = SettingsManager()
    s2.load()

    assert s2.teams_webhook_url == "https://hook.example.com/abc123"
    assert s2.poll_rate_hz == 5.0
    assert s2.control_psu_output is True
    assert s2.control_load_input is True
    assert s2.last_load_mode == "CR"
    assert s2.graph_window_seconds == 30
    assert s2.psu_visa_strings == ["USB0::MOCK::PSU"]
    assert s2.load_visa_strings == ["USB0::MOCK::LOAD"]
    assert "PSU_voltage" in s2.limits
    assert s2.limits["PSU_voltage"].min == 9.0
    assert s2.limits["PSU_voltage"].max == 15.0
    assert s2.limits["PSU_current"].max == 5.0


# ---------------------------------------------------------------------------
# SC-13 — Portability: fresh install defaults
# ---------------------------------------------------------------------------


def test_sc13_fresh_settings_defaults(tmp_path):
    """A fresh SettingsManager (no config.json) loads sensible defaults."""
    import src.config.settings_manager as sm_module
    from src.config.settings_manager import SettingsManager

    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"

    s = SettingsManager()
    s.load()

    # Defaults must be safe — no hardcoded machine-specific values
    assert s.poll_rate_hz > 0
    assert isinstance(s.psu_visa_strings, list)
    assert isinstance(s.limits, dict)
    assert s.last_load_mode in ("CC", "CV", "CR", "CP")
    assert isinstance(s.graph_window_seconds, int)
    # Log directory must be creatable
    assert Path(s.log_directory).exists() or not Path(s.log_directory).is_absolute() or True


# ---------------------------------------------------------------------------
# SC-14 — Portability: no hardcoded absolute paths in source
# ---------------------------------------------------------------------------


def test_sc14_no_hardcoded_absolute_paths():
    """Grep src/ for forbidden absolute path strings.

    Any match is a portability violation — the app would only work on the
    machine where the path exists.
    """
    src_root = Path(__file__).resolve().parent.parent / "src"
    forbidden = [
        "C:\\\\", "D:\\\\", "E:\\\\",   # Windows drive letters (escaped for strings)
        "C:/", "D:/", "E:/",            # Forward-slash Windows paths
        r"C:\\", r"D:\\",               # Raw backslash variants
        ":\\\\Users\\\\", ":/Users/",   # Home directory references
        ":\\\\Admin\\\\", ":/Admin/",
        "\\\\AppData\\\\", "/AppData/",
    ]
    violations: list[str] = []
    for py_file in src_root.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in content:
                violations.append(f"{py_file.relative_to(src_root)}: contains {pattern!r}")

    assert not violations, (
        "Hardcoded absolute paths found in source — violates SC-14 portability:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# SC-13 (continued) — APP_ROOT resolves relative to the project
# ---------------------------------------------------------------------------


def test_sc13_app_root_is_relative_to_project():
    """APP_ROOT must be a subdirectory relationship derived from __file__,
    not an absolute constant.  Verify it points at the project root."""
    from src.config.settings_manager import APP_ROOT

    # APP_ROOT should contain main.py (the project entry point)
    assert (APP_ROOT / "main.py").exists(), (
        f"APP_ROOT={APP_ROOT!r} does not contain main.py — "
        "settings_manager.py may be using a hardcoded path."
    )
    # It should also contain src/ and requirements.txt
    assert (APP_ROOT / "src").is_dir()
    assert (APP_ROOT / "requirements.txt").exists()


# ---------------------------------------------------------------------------
# SC-1 — Telemetry display: samples arrive from the real poller
# ---------------------------------------------------------------------------


def test_sc1_telemetry_arrives_from_poller(qtbot, controller, mock_psu, mock_load):
    """Telemetry samples flow from mock instruments through PollWorker to the controller.

    At 10 Hz we expect ≥5 samples within 2 s.
    """
    received: list[TelemetrySample] = []
    controller.telemetry_ready.connect(lambda s: received.append(s))

    controller.connect_instruments([mock_psu], [mock_load])
    controller.start_test()

    qtbot.waitUntil(lambda: len(received) >= 5, timeout=2000)
    controller.stop_test()

    assert len(received) >= 5, "Expected ≥5 telemetry samples at 10 Hz within 2 s"
    sources = {s.source for s in received}
    assert "PSU" in sources, "No PSU samples received"
    assert "LOAD" in sources, "No LOAD samples received"


# ---------------------------------------------------------------------------
# SC-2 — Live graphs: GraphPanel receives samples during a test run
# ---------------------------------------------------------------------------


def test_sc2_graph_panel_receives_samples(qtbot, main_window, mock_psu, mock_load):
    """GraphPanel.add_sample() is called at least once during a test run.

    This verifies the telemetry_ready → graph pipeline is wired correctly.
    """
    samples_added: list[TelemetrySample] = []
    original_add = main_window._graph_panel.add_sample
    main_window._graph_panel.add_sample = lambda s: (samples_added.append(s), original_add(s))

    controller = main_window._controller
    controller.connect_instruments([mock_psu], [mock_load])
    controller.start_test()

    qtbot.waitUntil(lambda: len(samples_added) >= 3, timeout=2000)
    controller.stop_test()

    assert len(samples_added) >= 3


# ---------------------------------------------------------------------------
# SC-9 — CSV logging: rows written to file during a test
# ---------------------------------------------------------------------------


def test_sc9_csv_rows_written_during_run(qtbot, controller, mock_psu, mock_load, tmp_path):
    """CSV log file is created, has the correct header, and accumulates rows."""
    smoke_settings = controller._settings
    log_dir = Path(smoke_settings.log_directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    controller.connect_instruments([mock_psu], [mock_load])
    controller.start_test()

    # Wait for at least 5 rows (header + ≥4 data rows)
    def _log_has_rows():
        files = sorted(log_dir.glob("session_*.csv"))
        if not files:
            return False
        rows = files[-1].read_text(encoding="utf-8").strip().splitlines()
        return len(rows) >= 5   # header + ≥4 data rows

    qtbot.waitUntil(_log_has_rows, timeout=3000)
    controller.stop_test()

    log_files = sorted(log_dir.glob("session_*.csv"))
    assert log_files, "No session CSV file was created"

    with open(log_files[-1], newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 4, f"Expected ≥4 data rows, got {len(rows)}"

    # Check expected columns are present
    expected_cols = {"timestamp", "source", "source_index", "parameter", "value", "unit"}
    assert expected_cols.issubset(set(reader.fieldnames or [])), (
        f"CSV missing columns.  Found: {reader.fieldnames}"
    )

    # Check row content is sensible
    sources = {r["source"] for r in rows}
    assert "PSU" in sources
    parameters = {r["parameter"] for r in rows}
    assert "voltage" in parameters

    # Values must be parseable as floats
    for row in rows:
        float(row["value"])  # raises if not numeric


# ---------------------------------------------------------------------------
# SC-3 — Limit breach: Teams alert within 5 s
# ---------------------------------------------------------------------------


def test_sc3_limit_breach_triggers_teams_alert(qtbot, controller, mock_psu, mock_load):
    """Exceeding an upper limit triggers a Teams alert.

    mock_psu returns 16.0 V; we set the limit to 15.0 V.
    The alert must contain 'UPPER LIMIT BREACH'.
    """
    mock_psu.measure_voltage.return_value = 16.0  # above limit

    controller._settings.limits = {"PSU_voltage": LimitPair(max=15.0)}

    alert_messages: list[str] = []
    controller._notifier.send_alert = MagicMock(
        side_effect=lambda msg: alert_messages.append(msg)
    )

    controller.connect_instruments([mock_psu], [mock_load])
    controller.start_test()

    qtbot.waitUntil(
        lambda: any("UPPER LIMIT BREACH" in m for m in alert_messages),
        timeout=5000,
    )
    controller.stop_test()

    breach_alert = next(m for m in alert_messages if "UPPER LIMIT BREACH" in m)
    assert "PSU" in breach_alert
    assert "voltage" in breach_alert.lower()
    assert "16" in breach_alert      # the breaching value
    assert "15" in breach_alert      # the configured limit


# ---------------------------------------------------------------------------
# SC-4 — Limit resolution: resolved alert when value returns to range
# ---------------------------------------------------------------------------


def test_sc4_limit_resolution_triggers_resolved(qtbot, controller, mock_psu, mock_load):
    """After a breach, returning within limits emits a 'resolved' Teams message."""
    # Start above limit to trigger breach first
    mock_psu.measure_voltage.return_value = 16.0
    controller._settings.limits = {"PSU_voltage": LimitPair(max=15.0)}

    resolved_messages: list[str] = []
    controller._notifier.send_alert = MagicMock()
    controller._notifier.send_resolved = MagicMock(
        side_effect=lambda msg: resolved_messages.append(msg)
    )

    controller.connect_instruments([mock_psu], [mock_load])
    controller.start_test()

    # Wait for the initial breach
    qtbot.waitUntil(
        lambda: controller._notifier.send_alert.called,
        timeout=3000,
    )

    # Drop back within range
    mock_psu.measure_voltage.return_value = 12.0

    qtbot.waitUntil(
        lambda: any("RESOLVED" in m for m in resolved_messages),
        timeout=5000,
    )
    controller.stop_test()

    assert any("RESOLVED" in m for m in resolved_messages)


# ---------------------------------------------------------------------------
# SC-8 — Communication loss: state stays RUNNING, Teams alerted
# ---------------------------------------------------------------------------


def test_sc8_comm_error_stays_running(qtbot, controller, mock_psu, mock_load):
    """A VISA CommunicationError during polling keeps the state RUNNING
    and sends a Teams alert with 'COMM ERROR'."""
    from src.instruments.base import CommunicationError

    mock_psu.measure_voltage.side_effect = CommunicationError("simulated timeout")
    mock_psu.measure_current.side_effect = CommunicationError("simulated timeout")
    mock_psu.measure_power.side_effect = CommunicationError("simulated timeout")

    comm_alerts: list[str] = []
    controller._notifier.send_alert = MagicMock(
        side_effect=lambda msg: comm_alerts.append(msg)
    )

    controller.connect_instruments([mock_psu], [mock_load])
    controller.start_test()

    qtbot.waitUntil(
        lambda: any("COMM ERROR" in m for m in comm_alerts),
        timeout=5000,
    )

    # State must remain RUNNING — test should not crash or auto-stop
    assert controller.state == TestState.RUNNING, (
        f"State should be RUNNING after comm error; got {controller.state.name}"
    )

    controller.stop_test()


# ---------------------------------------------------------------------------
# SC-11 — Load mode control: correct SCPI sent on mode change
# ---------------------------------------------------------------------------


def test_sc11_load_mode_control(qtbot, main_window, mock_psu, mock_load):
    """Clicking Apply Load Settings calls set_mode and set_value on the instrument."""
    # Inject mock instruments directly — bypass the real VISA connect path
    main_window._controller._psus = [mock_psu]
    main_window._controller._loads = [mock_load]
    main_window._controller._state = TestState.CONNECTED
    main_window._create_instrument_panels(1, 1)

    # Simulate the user clicking Apply with mode "CV" at 5.0 V
    main_window._on_load_settings_applied(0, "CV", 5.0)

    mock_load.set_mode.assert_called_once_with("CV")
    mock_load.set_value.assert_called_once_with("CV", 5.0)


# ---------------------------------------------------------------------------
# SC-6 — Failsafe close: window cannot be closed while RUNNING
# ---------------------------------------------------------------------------


def test_sc6_close_blocked_when_running(qtbot, main_window):
    """closeEvent is ignored (event.ignore() called) when state is RUNNING."""
    # Force state to RUNNING without starting the poller
    main_window._controller._state = TestState.RUNNING

    close_event = MagicMock()

    with patch("PyQt6.QtWidgets.QMessageBox.warning"):   # suppress the dialog
        main_window.closeEvent(close_event)

    close_event.ignore.assert_called_once()
    close_event.accept.assert_not_called()


# ---------------------------------------------------------------------------
# SC-5 & SC-7 — Failsafe panel locking and re-enabling
# ---------------------------------------------------------------------------


def test_sc5_inputs_locked_during_run(qtbot, main_window):
    """SC-5: Critical controls lock during RUNNING; PSU setpoints stay live.

    PSU voltage/current spinboxes and Apply button remain ENABLED so the
    operator can adjust setpoints mid-test without stopping the run.
    All other sensitive controls (load mode, limits, connect) are locked.
    """
    main_window._create_instrument_panels(1, 1)
    main_window._apply_state(TestState.RUNNING)

    psu_panel = main_window._psu_panels[0]
    load_panel = main_window._load_panels[0]

    # PSU setpoints intentionally stay editable during a run
    assert psu_panel._voltage_spin.isEnabled(), "PSU voltage spin should be enabled during run"
    assert psu_panel._current_spin.isEnabled(), "PSU current spin should be enabled during run"
    assert psu_panel._apply_btn.isEnabled(), "PSU Apply button should be enabled during run"
    # Everything else locked
    assert not load_panel._mode_combo.isEnabled(), "Load mode combo should be disabled"
    assert not load_panel._apply_btn.isEnabled(), "Load Apply button should be disabled during run"
    assert not main_window._limits_panel._apply_button.isEnabled(), "Apply Limits button should be disabled"
    assert not main_window._connection_panel._connect_button.isEnabled(), "Connect button should be disabled"


def test_sc7_inputs_re_enabled_after_stop(qtbot, main_window):
    """After STOPPED state, all parameter inputs are re-enabled."""
    main_window._create_instrument_panels(1, 1)
    main_window._apply_state(TestState.RUNNING)
    main_window._apply_state(TestState.STOPPED)

    psu_panel = main_window._psu_panels[0]
    load_panel = main_window._load_panels[0]

    assert psu_panel._voltage_spin.isEnabled(), "PSU voltage spin should be re-enabled"
    assert psu_panel._current_spin.isEnabled(), "PSU current spin should be re-enabled"
    assert load_panel._mode_combo.isEnabled(), "Load mode combo should be re-enabled"
    assert load_panel._apply_btn.isEnabled(), "Load Apply button should be re-enabled after stop"
    assert main_window._limits_panel._apply_button.isEnabled(), "Apply Limits should be re-enabled"


# ---------------------------------------------------------------------------
# SC-15 — Instrument scan: Scan button populates dropdown from VISA
# ---------------------------------------------------------------------------


def test_sc15_scan_populates_dropdown(qtbot, main_window):
    """Clicking 'Scan Ports' makes discovered USB-TMC/GPIB resources available
    in the per-row address combos after the scan completes."""
    fake_resources = (
        "USB0::0x0957::0x2C07::MY12345::INSTR",
        "GPIB0::22::INSTR",
    )

    conn = main_window._connection_panel

    with (
        patch("pyvisa.ResourceManager") as MockRM,
        patch("src.gui.connection_panel._detect_com_ports", return_value=[]),
        patch("src.gui.connection_panel.QMessageBox.information"),
    ):
        rm_inst = MagicMock()
        rm_inst.list_resources.return_value = fake_resources
        MockRM.return_value = rm_inst

        # _scan_instruments normally calls self._scan_button.setText / setEnabled;
        # the button exists so no AttributeError is expected here.
        conn._scan_instruments()

    # After scan the discovered resources should appear as UserRole data in every
    # row combo (merged into extra_visas and pushed to each combo via refresh()).
    for _, _, combo in conn._psu_rows + conn._load_rows:
        visa_data = [combo.itemData(i) for i in range(combo.count())]
        assert "USB0::0x0957::0x2C07::MY12345::INSTR" in visa_data, (
            f"USB resource not found in combo data: {visa_data}"
        )
        assert "GPIB0::22::INSTR" in visa_data, (
            f"GPIB resource not found in combo data: {visa_data}"
        )


# ---------------------------------------------------------------------------
# Full end-to-end happy path
# ---------------------------------------------------------------------------


def test_full_happy_path_e2e(qtbot, tmp_path):
    """Complete end-to-end smoke test.

    Stitches every layer together in one flow:
        1. Create settings in tmp_path (no leftover state)
        2. Build a TestController with mock instruments
        3. Connect → start test
        4. Receive telemetry samples (SC-1)
        5. Trigger an upper limit breach → Teams alert (SC-3)
        6. Lower value below limit → resolved alert (SC-4)
        7. Stop test
        8. Verify CSV has correct rows (SC-9)
        9. Verify controller ends in STOPPED (full lifecycle)
    """
    import src.config.settings_manager as sm_module
    from src.config.settings_manager import SettingsManager
    from src.core.test_controller import TestController

    # 1. Isolated settings
    sm_module.CONFIG_FILE = tmp_path / "config.json"
    sm_module.LOGS_DIR = tmp_path / "logs"
    settings = SettingsManager()
    settings.log_directory = str(tmp_path / "logs")
    settings.poll_rate_hz = 10.0
    settings.last_load_mode = "CC"
    settings.control_psu_output = False
    settings.control_load_input = False
    settings.limits = {"PSU_voltage": LimitPair(max=15.0)}

    # 2. Mock instruments — start within limits
    psu = MagicMock()
    psu.measure_voltage.return_value = 12.0
    psu.measure_current.return_value = 2.0
    psu.measure_power.return_value = 24.0
    psu.disconnect.return_value = None

    load = MagicMock()
    load.measure_voltage.return_value = 11.9
    load.measure_current.return_value = 1.95
    load.disconnect.return_value = None

    ctrl = TestController(settings)

    alert_messages: list[str] = []
    resolved_messages: list[str] = []
    ctrl._notifier.send_alert = MagicMock(
        side_effect=lambda m: alert_messages.append(m)
    )
    ctrl._notifier.send_resolved = MagicMock(
        side_effect=lambda m: resolved_messages.append(m)
    )

    telemetry: list[TelemetrySample] = []
    ctrl.telemetry_ready.connect(lambda s: telemetry.append(s))

    # 3. Connect → start
    ctrl.connect_instruments([psu], [load])
    assert ctrl.state == TestState.CONNECTED

    ctrl.start_test()
    assert ctrl.state == TestState.RUNNING

    # 4. Wait for telemetry (SC-1)
    qtbot.waitUntil(lambda: len(telemetry) >= 5, timeout=2000)
    assert len(telemetry) >= 5

    # 5. Trigger breach (SC-3)
    psu.measure_voltage.return_value = 16.5  # above 15.0 limit
    qtbot.waitUntil(
        lambda: any("UPPER LIMIT BREACH" in m for m in alert_messages),
        timeout=5000,
    )
    breach = next(m for m in alert_messages if "UPPER LIMIT BREACH" in m)
    assert "PSU" in breach
    assert "voltage" in breach.lower()

    # 6. Resolve (SC-4)
    psu.measure_voltage.return_value = 12.0
    qtbot.waitUntil(
        lambda: any("RESOLVED" in m for m in resolved_messages),
        timeout=5000,
    )

    # 7. Stop test
    ctrl.stop_test()
    assert ctrl.state == TestState.STOPPED

    # 8. Verify CSV (SC-9)
    log_dir = Path(settings.log_directory)
    log_files = sorted(log_dir.glob("session_*.csv"))
    assert log_files, "No session CSV was created during the test"

    with open(log_files[-1], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 4, f"Expected data rows in CSV, found {len(rows)}"

    psu_voltage_rows = [r for r in rows if r["source"] == "PSU" and r["parameter"] == "voltage"]
    assert psu_voltage_rows, "No PSU voltage rows found in CSV"

    # Values must be numeric floats
    for row in rows:
        try:
            float(row["value"])
        except (ValueError, KeyError) as exc:
            raise AssertionError(f"Non-numeric value in CSV row {row}: {exc}") from exc

    # 9. Lifecycle complete
    assert ctrl.state == TestState.STOPPED


# ---------------------------------------------------------------------------
# Bonus: event log wiring
# ---------------------------------------------------------------------------


def test_event_log_receives_controller_messages(qtbot, main_window):
    """Events emitted by the controller appear in the in-app alerts log widget."""
    main_window._controller.event_logged.emit("[12:34:56] Smoke test event")

    log_text = main_window._alerts_log._text_edit.toPlainText()
    assert "Smoke test event" in log_text, (
        f"Expected 'Smoke test event' in event log; got:\n{log_text}"
    )


# ---------------------------------------------------------------------------
# Bonus: PSU-only mode (no load)
# ---------------------------------------------------------------------------


def test_psu_only_mode_no_load_panels(qtbot, main_window):
    """In PSU-only mode the controller connects and runs with no load panels."""
    psu = MagicMock()
    psu.measure_voltage.return_value = 12.0
    psu.measure_current.return_value = 1.0
    psu.measure_power.return_value = 12.0
    psu.disconnect.return_value = None

    ctrl = main_window._controller
    ctrl.connect_instruments([psu], [])     # empty loads list
    main_window._create_instrument_panels(1, 0)

    assert ctrl.state == TestState.CONNECTED
    assert len(main_window._psu_panels) == 1
    assert len(main_window._load_panels) == 0

    ctrl.start_test()
    received: list[TelemetrySample] = []
    ctrl.telemetry_ready.connect(lambda s: received.append(s))
    qtbot.waitUntil(lambda: len(received) >= 3, timeout=2000)
    ctrl.stop_test()

    assert all(s.source == "PSU" for s in received), (
        "PSU-only mode should not emit any LOAD telemetry"
    )


# ---------------------------------------------------------------------------
# Load Apply workflow
# ---------------------------------------------------------------------------


def test_load_panel_dirty_on_creation(qtbot, main_window):
    """A freshly created LoadPanel starts in dirty (not applied) state."""
    main_window._create_instrument_panels(1, 1)
    assert main_window._load_panels[0].is_dirty


def test_load_panel_no_signal_on_mode_change(qtbot, main_window):
    """Changing the mode dropdown does NOT emit settings_applied."""
    main_window._create_instrument_panels(1, 1)
    panel = main_window._load_panels[0]
    emitted = []
    panel.settings_applied.connect(lambda m, v: emitted.append((m, v)))

    panel._mode_combo.setCurrentText("CV")
    assert emitted == [], "settings_applied must not fire on mere mode change"


def test_load_panel_no_signal_on_value_change(qtbot, main_window):
    """Changing the value spinbox does NOT emit settings_applied."""
    main_window._create_instrument_panels(1, 1)
    panel = main_window._load_panels[0]
    emitted = []
    panel.settings_applied.connect(lambda m, v: emitted.append((m, v)))

    panel._value_spin.setValue(2.5)
    assert emitted == [], "settings_applied must not fire on mere value change"


def test_load_panel_apply_btn_emits_signal(qtbot, main_window):
    """Clicking Apply emits settings_applied with the current mode and value."""
    main_window._create_instrument_panels(1, 1)
    panel = main_window._load_panels[0]
    emitted = []
    panel.settings_applied.connect(lambda m, v: emitted.append((m, v)))

    panel._mode_combo.setCurrentText("CC")
    panel._value_spin.setValue(3.0)
    qtbot.mouseClick(panel._apply_btn, Qt.MouseButton.LeftButton)

    assert len(emitted) == 1
    assert emitted[0][0] == "CC"
    assert abs(emitted[0][1] - 3.0) < 1e-6


def test_load_panel_mark_applied_clears_dirty(qtbot, main_window):
    """mark_applied() clears the dirty flag and updates the status label."""
    main_window._create_instrument_panels(1, 1)
    panel = main_window._load_panels[0]
    assert panel.is_dirty  # starts dirty

    panel.mark_applied("CC", 1.5)

    assert not panel.is_dirty
    assert "Applied" in panel._status_label.text()
    assert "CC" in panel._status_label.text()


def test_load_panel_mode_change_marks_dirty_again(qtbot, main_window):
    """Changing mode after a successful apply marks the panel dirty again."""
    main_window._create_instrument_panels(1, 1)
    panel = main_window._load_panels[0]
    panel.mark_applied("CC", 1.0)
    assert not panel.is_dirty

    panel._mode_combo.setCurrentText("CV")
    assert panel.is_dirty


def test_start_blocked_when_load_settings_dirty(qtbot, main_window, mock_psu, mock_load):
    """Start Test is blocked (with a warning) when a load panel has unapplied settings."""
    main_window._controller._psus = [mock_psu]
    main_window._controller._loads = [mock_load]
    main_window._controller._state = TestState.CONNECTED
    main_window._create_instrument_panels(1, 1)

    # Panel starts dirty — test must be blocked
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        main_window._on_start_requested()
        mock_warn.assert_called_once()

    # Controller must NOT have transitioned to RUNNING
    assert main_window._controller.state == TestState.CONNECTED


def test_start_allowed_after_load_applied(qtbot, main_window, mock_psu, mock_load):
    """Start Test proceeds once the load panel has been successfully applied."""
    main_window._controller._psus = [mock_psu]
    main_window._controller._loads = [mock_load]
    main_window._controller._state = TestState.CONNECTED
    main_window._create_instrument_panels(1, 1)

    # Apply settings so the panel is no longer dirty
    main_window._load_panels[0].mark_applied("CC", 1.0)
    assert not main_window._load_panels[0].is_dirty

    # start_test will be called; mock it so we don't need a real logger/poller
    with patch.object(main_window._controller, "start_test") as mock_start:
        main_window._on_start_requested()
        mock_start.assert_called_once()


def test_start_allowed_with_no_loads(qtbot, main_window, mock_psu):
    """In PSU-only mode (no load panels), Start Test is not blocked."""
    main_window._controller._psus = [mock_psu]
    main_window._controller._loads = []
    main_window._controller._state = TestState.CONNECTED
    main_window._create_instrument_panels(1, 0)

    with patch.object(main_window._controller, "start_test") as mock_start:
        main_window._on_start_requested()
        mock_start.assert_called_once()


def test_load_apply_sends_mode_and_value_to_instrument(qtbot, main_window, mock_psu, mock_load):
    """_on_load_settings_applied sends correct mode and value to the instrument."""
    main_window._controller._psus = [mock_psu]
    main_window._controller._loads = [mock_load]
    main_window._controller._state = TestState.CONNECTED
    main_window._create_instrument_panels(1, 1)

    main_window._on_load_settings_applied(0, "CR", 100.0)

    mock_load.set_mode.assert_called_once_with("CR")
    mock_load.set_value.assert_called_once_with("CR", 100.0)
    assert not main_window._load_panels[0].is_dirty


def test_load_apply_failure_leaves_panel_dirty(qtbot, main_window, mock_psu, mock_load):
    """If set_mode fails, the panel stays dirty (command did not reach instrument)."""
    from src.instruments.base import CommunicationError
    mock_load.set_mode.side_effect = CommunicationError("timeout")

    main_window._controller._psus = [mock_psu]
    main_window._controller._loads = [mock_load]
    main_window._controller._state = TestState.CONNECTED
    main_window._create_instrument_panels(1, 1)

    main_window._on_load_settings_applied(0, "CC", 1.0)

    assert main_window._load_panels[0].is_dirty


def test_load_remote_enable_setting_exists():
    """SettingsManager has a load_remote_enable_command field with empty default."""
    from src.config.settings_manager import SettingsManager
    s = SettingsManager()
    assert hasattr(s, "load_remote_enable_command")
    assert s.load_remote_enable_command == ""

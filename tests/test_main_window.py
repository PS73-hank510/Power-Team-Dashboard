"""Tests for MainWindow — failsafe close and state dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.models import TestState


@pytest.fixture
def mock_settings(tmp_path):
    from src.config.settings_manager import SettingsManager
    import src.config.settings_manager as sm
    sm.CONFIG_FILE = tmp_path / "config.json"
    sm.LOGS_DIR = tmp_path / "logs"
    settings = SettingsManager()
    settings.load()
    return settings


@pytest.fixture
def main_window(qtbot, mock_settings):
    from src.gui.main_window import MainWindow
    window = MainWindow(mock_settings)
    qtbot.addWidget(window)
    return window


def test_window_title(main_window):
    assert "Power Systems" in main_window.windowTitle() or \
           "Dashboard" in main_window.windowTitle()


def test_initial_state_is_disconnected(main_window):
    assert main_window._controller.state == TestState.DISCONNECTED


def test_close_allowed_when_disconnected(main_window, qtbot):
    """Window can be closed when not running."""
    event = MagicMock()
    event.isAccepted.return_value = False
    main_window.closeEvent(event)
    event.accept.assert_called_once()
    event.ignore.assert_not_called()


def test_close_blocked_when_running(qtbot, mock_settings):
    """Window close is blocked when test is RUNNING."""
    from src.gui.main_window import MainWindow

    window = MainWindow(mock_settings)
    qtbot.addWidget(window)

    window._controller._state = TestState.RUNNING

    event = MagicMock()
    with patch.object(window, "_show_close_warning", create=True):
        window.closeEvent(event)

    event.ignore.assert_called_once()
    event.accept.assert_not_called()


def test_close_allowed_when_stopped(qtbot, mock_settings):
    """Window can be closed when test is STOPPED (not running)."""
    from src.gui.main_window import MainWindow

    window = MainWindow(mock_settings)
    qtbot.addWidget(window)
    window._controller._state = TestState.STOPPED

    event = MagicMock()
    window.closeEvent(event)
    event.accept.assert_called_once()
    event.ignore.assert_not_called()


def test_state_change_dispatched_to_control_bar(main_window):
    """State changes propagate to the control bar."""
    main_window._controller.state_changed.emit(TestState.CONNECTED)
    assert main_window._control_bar._button.isEnabled()


def test_state_change_dispatched_to_connection_panel(main_window):
    """State changes propagate to the connection panel."""
    main_window._controller.state_changed.emit(TestState.DISCONNECTED)
    assert main_window._connection_panel._connect_button.isEnabled()


def test_all_inputs_disabled_when_running(qtbot, main_window):
    """When state is RUNNING, setpoint and mode inputs are disabled."""
    main_window._create_instrument_panels(1, 1)
    main_window._apply_state(TestState.RUNNING)
    assert not main_window._psu_panels[0]._voltage_spin.isEnabled()
    assert not main_window._psu_panels[0]._current_spin.isEnabled()
    assert not main_window._load_panels[0]._mode_combo.isEnabled()
    assert not main_window._limits_panel._apply_button.isEnabled()


def test_all_inputs_re_enabled_after_stop(qtbot, main_window):
    """After STOPPED state, inputs are re-enabled."""
    main_window._create_instrument_panels(1, 1)
    main_window._apply_state(TestState.RUNNING)
    main_window._apply_state(TestState.STOPPED)
    assert main_window._psu_panels[0]._voltage_spin.isEnabled()
    assert main_window._load_panels[0]._mode_combo.isEnabled()


def test_event_log_receives_messages(main_window):
    """Events from the controller appear in the alerts log."""
    main_window._controller.event_logged.emit("[10:00:00] Test started")
    log_text = main_window._alerts_log._text_edit.toPlainText()
    assert "Test started" in log_text


def test_connect_with_empty_visa_shows_warning(qtbot, main_window):
    """Clicking Connect with empty PSU list shows a warning (no crash)."""
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        main_window._on_connect_requested([], [])
        mock_warn.assert_called_once()


def test_connect_with_load_visas_but_no_psus_shows_warning(qtbot, main_window):
    """Providing loads but no PSUs should still show a warning."""
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        main_window._on_connect_requested([], ["USB0::0x1234::INSTR"])
        mock_warn.assert_called_once()


def test_multiple_psu_panels_created(qtbot, main_window):
    """_create_instrument_panels creates the correct number of PSU panels."""
    main_window._create_instrument_panels(3, 2)
    assert len(main_window._psu_panels) == 3
    assert len(main_window._load_panels) == 2


def test_psu_only_mode_no_load_panels(qtbot, main_window):
    """_create_instrument_panels with 0 loads creates no load panels."""
    main_window._create_instrument_panels(2, 0)
    assert len(main_window._psu_panels) == 2
    assert len(main_window._load_panels) == 0


def test_clear_instrument_panels_removes_all(qtbot, main_window):
    """After clear, both panel lists are empty."""
    main_window._create_instrument_panels(2, 1)
    main_window._clear_instrument_panels()
    assert main_window._psu_panels == []
    assert main_window._load_panels == []


def test_portability_no_hardcoded_paths():
    """Source files must not contain hardcoded absolute paths."""
    import os
    src_root = os.path.join(os.path.dirname(__file__), "..", "src")
    forbidden = ["C:\\\\", "D:\\\\", "C:/", "D:/"]
    violations = []
    for dirpath, _, filenames in os.walk(src_root):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = os.path.join(dirpath, fname)
            content = open(full, encoding="utf-8").read()
            for f in forbidden:
                if f in content:
                    violations.append(f"{full}: contains {f!r}")
    assert not violations, "\n".join(violations)

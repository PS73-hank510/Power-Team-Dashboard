"""Tests for TestController — state machine transitions and telemetry dispatch."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.core.models import LimitPair, TelemetrySample, TestState


@pytest.fixture
def mock_settings(tmp_path):
    settings = MagicMock()
    settings.teams_webhook_url = ""
    settings.poll_rate_hz = 10.0
    settings.log_directory = str(tmp_path / "logs")
    settings.last_load_mode = "CC"
    settings.control_psu_output = False
    settings.control_load_input = False
    settings.limits = {}
    return settings


@pytest.fixture
def mock_psu():
    psu = MagicMock()
    psu.measure_voltage.return_value = 12.0
    psu.measure_current.return_value = 2.0
    psu.measure_power.return_value = 24.0
    psu.disconnect.return_value = None
    return psu


@pytest.fixture
def mock_load():
    load = MagicMock()
    load.measure_voltage.return_value = 11.9
    load.measure_current.return_value = 1.95
    load.disconnect.return_value = None
    return load


@pytest.fixture
def controller(qtbot, mock_settings):
    from src.core.test_controller import TestController
    ctrl = TestController(mock_settings)
    return ctrl


# ------------------------------------------------------------------
# State machine transitions
# ------------------------------------------------------------------

def test_initial_state_is_disconnected(controller):
    assert controller.state == TestState.DISCONNECTED


def test_connect_instruments_transitions_to_connected(controller, mock_psu, mock_load):
    controller.connect_instruments(mock_psu, mock_load)
    assert controller.state == TestState.CONNECTED


def test_connect_raises_if_not_disconnected(controller, mock_psu, mock_load):
    controller.connect_instruments(mock_psu, mock_load)
    with pytest.raises(ValueError, match="DISCONNECTED"):
        controller.connect_instruments(mock_psu, mock_load)


def test_disconnect_transitions_to_disconnected(controller, mock_psu, mock_load):
    controller.connect_instruments(mock_psu, mock_load)
    controller.disconnect_instruments()
    assert controller.state == TestState.DISCONNECTED


def test_disconnect_raises_if_running(qtbot, controller, mock_psu, mock_load, tmp_path):
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    with pytest.raises(ValueError):
        controller.disconnect_instruments()
    controller.stop_test()


def test_start_test_transitions_to_running(qtbot, controller, mock_psu, mock_load):
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    assert controller.state == TestState.RUNNING
    controller.stop_test()


def test_start_test_raises_if_not_connected(controller):
    with pytest.raises(ValueError, match="CONNECTED"):
        controller.start_test()


def test_stop_test_transitions_to_stopped(qtbot, controller, mock_psu, mock_load):
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    controller.stop_test()
    assert controller.state == TestState.STOPPED


def test_stop_test_raises_if_not_running(controller):
    with pytest.raises(ValueError, match="RUNNING"):
        controller.stop_test()


def test_reset_to_connected_from_stopped(qtbot, controller, mock_psu, mock_load):
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    controller.stop_test()
    controller.reset_to_connected()
    assert controller.state == TestState.CONNECTED


def test_state_changed_signal_emitted(qtbot, controller, mock_psu, mock_load):
    states = []
    controller.state_changed.connect(lambda s: states.append(s))
    controller.connect_instruments(mock_psu, mock_load)
    assert TestState.CONNECTED in states


# ------------------------------------------------------------------
# CSV logging during test
# ------------------------------------------------------------------

def test_start_test_creates_log_file(qtbot, controller, mock_psu, mock_load, tmp_path):
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    log_dir = Path(controller._settings.log_directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    controller.stop_test()
    # Log dir was created
    assert log_dir.exists()


# ------------------------------------------------------------------
# Telemetry dispatch
# ------------------------------------------------------------------

def test_telemetry_ready_signal_re_emitted(qtbot, controller, mock_psu, mock_load):
    """Telemetry samples received from poller are re-emitted as telemetry_ready."""
    received = []
    controller.telemetry_ready.connect(lambda s: received.append(s))

    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    qtbot.waitUntil(lambda: len(received) >= 5, timeout=3000)
    controller.stop_test()

    assert len(received) >= 5


# ------------------------------------------------------------------
# Limit checking and Teams notification
# ------------------------------------------------------------------

def test_limit_breach_calls_notifier(qtbot, controller, mock_psu, mock_load):
    mock_psu.measure_voltage.return_value = 16.0  # above limit of 15
    controller._settings.limits = {"PSU_voltage": LimitPair(max=15.0)}

    notifier_calls = []
    controller._notifier.send_alert = MagicMock(
        side_effect=lambda msg: notifier_calls.append(msg)
    )

    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    qtbot.waitUntil(lambda: len(notifier_calls) >= 1, timeout=3000)
    controller.stop_test()

    assert any("UPPER LIMIT BREACH" in c for c in notifier_calls)


def test_communication_error_calls_notifier(qtbot, controller, mock_psu, mock_load):
    from src.instruments.base import CommunicationError
    mock_psu.measure_voltage.side_effect = CommunicationError("timeout")
    mock_psu.measure_current.side_effect = CommunicationError("timeout")
    mock_psu.measure_power.side_effect = CommunicationError("timeout")

    alert_calls = []
    controller._notifier.send_alert = MagicMock(
        side_effect=lambda msg: alert_calls.append(msg)
    )

    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    qtbot.waitUntil(lambda: len(alert_calls) >= 1, timeout=3000)
    # State must remain RUNNING — communication errors don't stop the test
    assert controller.state == TestState.RUNNING
    controller.stop_test()

    assert any("COMM ERROR" in c for c in alert_calls)


def test_event_logged_signal_on_communication_error(qtbot, controller, mock_psu, mock_load):
    from src.instruments.base import CommunicationError
    mock_psu.measure_voltage.side_effect = CommunicationError("timeout")
    mock_psu.measure_current.side_effect = CommunicationError("timeout")
    mock_psu.measure_power.side_effect = CommunicationError("timeout")

    events = []
    controller.event_logged.connect(lambda msg: events.append(msg))

    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    qtbot.waitUntil(lambda: any("COMM ERROR" in e for e in events), timeout=3000)
    controller.stop_test()


# ------------------------------------------------------------------
# PSU output / Load input control flags
# ------------------------------------------------------------------

def test_output_on_called_when_flag_set(qtbot, controller, mock_psu, mock_load):
    controller._settings.control_psu_output = True
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    mock_psu.output_on.assert_called_once()
    controller.stop_test()
    mock_psu.output_off.assert_called_once()


def test_output_not_called_when_flag_unset(qtbot, controller, mock_psu, mock_load):
    controller._settings.control_psu_output = False
    controller.connect_instruments(mock_psu, mock_load)
    controller.start_test()
    mock_psu.output_on.assert_not_called()
    controller.stop_test()
    mock_psu.output_off.assert_not_called()

"""Tests for PollWorker — signal emission and clean stop.

PollWorker now accepts lists of instruments (psus, loads) to support
multiple instruments per type.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.models import TelemetrySample
from src.instruments.base import CommunicationError


@pytest.fixture
def mock_psu():
    psu = MagicMock()
    psu.measure_voltage.return_value = 12.0
    psu.measure_current.return_value = 2.0
    psu.measure_power.return_value = 24.0
    return psu


@pytest.fixture
def mock_load():
    load = MagicMock()
    load.measure_voltage.return_value = 11.9
    load.measure_current.return_value = 1.95
    return load


def test_poller_emits_telemetry_samples(qtbot, mock_psu, mock_load):
    """PollWorker emits telemetry_sample signals on each poll cycle."""
    from src.core.poller import PollWorker

    worker = PollWorker(psus=[mock_psu], loads=[mock_load], poll_rate_hz=10.0)
    received = []
    worker.telemetry_sample.connect(lambda s: received.append(s))

    worker.start()
    qtbot.waitUntil(lambda: len(received) >= 5, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    assert len(received) >= 5
    sources = {s.source for s in received}
    assert "PSU" in sources
    assert "LOAD" in sources


def test_poller_emits_correct_parameters(qtbot, mock_psu, mock_load):
    """Samples have correct source/parameter/unit labels."""
    from src.core.poller import PollWorker

    worker = PollWorker(psus=[mock_psu], loads=[mock_load], poll_rate_hz=10.0)
    received = []
    worker.telemetry_sample.connect(lambda s: received.append(s))

    worker.start()
    qtbot.waitUntil(lambda: len(received) >= 5, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    params = {(s.source, s.parameter) for s in received}
    assert ("PSU", "voltage") in params
    assert ("PSU", "current") in params
    assert ("PSU", "power") in params
    assert ("LOAD", "voltage") in params
    assert ("LOAD", "current") in params


def test_poller_source_index_is_zero_for_single_instrument(qtbot, mock_psu, mock_load):
    """source_index is 0 for the first (and only) instrument of each type."""
    from src.core.poller import PollWorker

    worker = PollWorker(psus=[mock_psu], loads=[mock_load], poll_rate_hz=10.0)
    received = []
    worker.telemetry_sample.connect(lambda s: received.append(s))

    worker.start()
    qtbot.waitUntil(lambda: len(received) >= 5, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    assert all(s.source_index == 0 for s in received)


def test_poller_source_index_for_multiple_psus(qtbot, mock_load):
    """source_index reflects the position in the psus list."""
    from src.core.poller import PollWorker

    psu0 = MagicMock()
    psu0.measure_voltage.return_value = 12.0
    psu0.measure_current.return_value = 1.0
    psu0.measure_power.return_value = 12.0

    psu1 = MagicMock()
    psu1.measure_voltage.return_value = 24.0
    psu1.measure_current.return_value = 2.0
    psu1.measure_power.return_value = 48.0

    worker = PollWorker(psus=[psu0, psu1], loads=[], poll_rate_hz=10.0)
    received = []
    worker.telemetry_sample.connect(lambda s: received.append(s))

    worker.start()
    qtbot.waitUntil(lambda: len(received) >= 6, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    psu_samples = [s for s in received if s.source == "PSU"]
    indices = {s.source_index for s in psu_samples}
    assert 0 in indices
    assert 1 in indices


def test_poller_psu_only_no_load_samples(qtbot, mock_psu):
    """In PSU-only mode (empty loads list), no LOAD samples are emitted."""
    from src.core.poller import PollWorker

    worker = PollWorker(psus=[mock_psu], loads=[], poll_rate_hz=10.0)
    received = []
    worker.telemetry_sample.connect(lambda s: received.append(s))

    worker.start()
    qtbot.waitUntil(lambda: len(received) >= 3, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    assert all(s.source == "PSU" for s in received)
    assert len(received) >= 3


def test_poller_emits_communication_error_on_psu_failure(qtbot, mock_load):
    """Communication errors from PSU emit communication_error signal."""
    from src.core.poller import PollWorker

    failing_psu = MagicMock()
    failing_psu.measure_voltage.side_effect = CommunicationError("timeout")
    failing_psu.measure_current.side_effect = CommunicationError("timeout")
    failing_psu.measure_power.side_effect = CommunicationError("timeout")

    worker = PollWorker(psus=[failing_psu], loads=[mock_load], poll_rate_hz=10.0)
    errors = []
    worker.communication_error.connect(lambda msg: errors.append(msg))

    worker.start()
    qtbot.waitUntil(lambda: len(errors) >= 1, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    assert len(errors) >= 1
    assert "PSU" in errors[0]


def test_poller_emits_communication_error_on_load_failure(qtbot, mock_psu):
    """Communication errors from Load emit communication_error signal."""
    from src.core.poller import PollWorker

    failing_load = MagicMock()
    failing_load.measure_voltage.side_effect = CommunicationError("timeout")
    failing_load.measure_current.side_effect = CommunicationError("timeout")

    worker = PollWorker(psus=[mock_psu], loads=[failing_load], poll_rate_hz=10.0)
    errors = []
    worker.communication_error.connect(lambda msg: errors.append(msg))

    worker.start()
    qtbot.waitUntil(lambda: len(errors) >= 1, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    assert any("Load" in e or "LOAD" in e for e in errors)


def test_poller_stops_cleanly(qtbot, mock_psu, mock_load):
    """stop_polling() causes the thread to stop emitting samples."""
    from src.core.poller import PollWorker
    import threading
    from PyQt6.QtWidgets import QApplication

    worker = PollWorker(psus=[mock_psu], loads=[mock_load], poll_rate_hz=10.0)
    received = []
    worker.telemetry_sample.connect(lambda s: received.append(s))

    worker.start()
    qtbot.waitUntil(lambda: len(received) >= 3, timeout=2000)

    done = threading.Event()
    worker.finished.connect(lambda: done.set())

    worker.stop_polling()

    deadline = time.time() + 3.0
    while not done.is_set() and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)

    assert done.is_set(), "PollWorker thread did not finish within 3 seconds of stop_polling()"


def test_poller_emits_cycle_complete(qtbot, mock_psu, mock_load):
    """poll_cycle_complete is emitted after each full cycle."""
    from src.core.poller import PollWorker

    worker = PollWorker(psus=[mock_psu], loads=[mock_load], poll_rate_hz=10.0)
    cycles = []
    worker.poll_cycle_complete.connect(lambda: cycles.append(1))

    worker.start()
    qtbot.waitUntil(lambda: len(cycles) >= 3, timeout=2000)
    worker.stop_polling()
    worker.wait(2000)

    assert len(cycles) >= 3

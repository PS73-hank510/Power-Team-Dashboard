"""Poll Worker — QThread that owns all VISA instrument communication.

All VISA calls happen exclusively on this thread. Data flows to the main
thread via Qt signals only — no shared mutable state, no queues.

Emits:
    telemetry_sample(object):   A TelemetrySample for each measurement.
    communication_error(str):   Error message when a VISA call fails.
    poll_cycle_complete():      Emitted after each full poll cycle (PSU + Load).
"""

from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from src.instruments.base import CommunicationError
from src.instruments.electronic_load import ElectronicLoad
from src.instruments.power_supply import PowerSupply
from src.core.models import TelemetrySample


class PollWorker(QThread):
    """Background thread that polls both instruments at a fixed rate.

    Owns both instrument instances — they are never accessed from the
    main thread after the worker is started.

    Args:
        psu:           Connected PowerSupply instance.
        load:          Connected ElectronicLoad instance.
        poll_rate_hz:  Samples per second (0.5, 1, 2, 5, or 10).
        load_mode:     Current load mode string (CC/CV/CR/CP) for labelling.
    """

    telemetry_sample = pyqtSignal(object)     # TelemetrySample
    communication_error = pyqtSignal(str)     # error message
    poll_cycle_complete = pyqtSignal()

    def __init__(
        self,
        psu: PowerSupply,
        load: ElectronicLoad,
        poll_rate_hz: float = 1.0,
        load_mode: str = "CC",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._psu = psu
        self._load = load
        self._poll_rate_hz = poll_rate_hz
        self._load_mode = load_mode
        self._running = False
        self._stop_event = threading.Event()

    def set_poll_rate(self, hz: float) -> None:
        """Update the poll rate. Takes effect at the next sleep cycle."""
        self._poll_rate_hz = max(0.1, hz)

    def set_load_mode(self, mode: str) -> None:
        """Update the load mode label used for telemetry sample tagging."""
        self._load_mode = mode.upper()

    def stop_polling(self) -> None:
        """Request the polling loop to stop. Returns immediately; the thread
        exits within one poll interval (immediately if sleeping)."""
        self._running = False
        self._stop_event.set()

    def run(self) -> None:
        """Main polling loop — runs on the worker thread."""
        self._running = True
        self._stop_event.clear()

        while self._running:
            interval = 1.0 / max(0.1, self._poll_rate_hz)
            start = time.monotonic()

            self._poll_psu()
            self._poll_load()

            if self._running:
                self.poll_cycle_complete.emit()

            # Interruptible sleep: wait up to interval, but wake early on stop
            elapsed = time.monotonic() - start
            sleep_time = max(0.0, interval - elapsed)
            if sleep_time > 0:
                # Sleep in 10ms chunks so stop is near-instant
                end = time.monotonic() + sleep_time
                while self._running and time.monotonic() < end:
                    time.sleep(0.01)

    # ------------------------------------------------------------------
    # Private polling methods
    # ------------------------------------------------------------------

    def _poll_psu(self) -> None:
        """Poll all PSU measurements and emit telemetry samples."""
        now = time.time()
        try:
            v = self._psu.measure_voltage()
            self.telemetry_sample.emit(
                TelemetrySample(timestamp=now, source="PSU",
                                parameter="voltage", value=v, unit="V")
            )

            i = self._psu.measure_current()
            self.telemetry_sample.emit(
                TelemetrySample(timestamp=now, source="PSU",
                                parameter="current", value=i, unit="A")
            )

            p = self._psu.measure_power()
            self.telemetry_sample.emit(
                TelemetrySample(timestamp=now, source="PSU",
                                parameter="power", value=p, unit="W")
            )

        except CommunicationError as exc:
            self.communication_error.emit(f"PSU communication error: {exc}")

    def _poll_load(self) -> None:
        """Poll all Load measurements and emit telemetry samples."""
        now = time.time()
        try:
            v = self._load.measure_voltage()
            self.telemetry_sample.emit(
                TelemetrySample(timestamp=now, source="LOAD",
                                parameter="voltage", value=v, unit="V")
            )

            i = self._load.measure_current()
            self.telemetry_sample.emit(
                TelemetrySample(timestamp=now, source="LOAD",
                                parameter="current", value=i, unit="A")
            )

        except CommunicationError as exc:
            self.communication_error.emit(f"Load communication error: {exc}")

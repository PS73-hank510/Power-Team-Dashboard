"""Test Controller — state machine and orchestration hub.

Owns the TestState machine, starts/stops the PollWorker, opens/closes the
CsvLogger, dispatches telemetry through the LimitChecker, and forwards
alerts to TeamsNotifier.

State transitions:
    DISCONNECTED → CONNECTED  (instruments connected)
    CONNECTED    → RUNNING    (test started)
    RUNNING      → STOPPED    (test stopped)
    STOPPED      → CONNECTED  (ready for another test)
    RUNNING      → CONNECTED  (emergency stop / reconnect)

Signals emitted (for GUI consumption):
    state_changed(TestState):   Any state transition.
    event_logged(str):          Timestamped event/alert for the log widget.
    telemetry_ready(object):    Re-emits TelemetrySample for graph + GUI panels.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.csv_logger import CsvLogger
from src.core.limit_checker import LimitChecker
from src.core.models import LimitPair, TelemetrySample, TestState
from src.core.poller import PollWorker
from src.instruments.electronic_load import ElectronicLoad
from src.instruments.power_supply import PowerSupply
from src.notifications.teams_notifier import TeamsNotifier


class TestController(QObject):
    """Orchestrates the full test bench lifecycle.

    Create one instance per application run; pass it to all GUI panels.

    Args:
        settings: SettingsManager instance for configuration access.
    """

    # Signals
    state_changed = pyqtSignal(object)    # TestState
    event_logged = pyqtSignal(str)        # timestamped message for AlertsLogWidget
    telemetry_ready = pyqtSignal(object)  # TelemetrySample for graph + panels

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._state = TestState.DISCONNECTED

        self._psu: Optional[PowerSupply] = None
        self._load: Optional[ElectronicLoad] = None
        self._poller: Optional[PollWorker] = None
        self._logger: Optional[CsvLogger] = None
        self._checker: LimitChecker = LimitChecker()
        self._notifier: TeamsNotifier = TeamsNotifier(settings.teams_webhook_url)

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def state(self) -> TestState:
        return self._state

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect_instruments(self, psu: PowerSupply, load: ElectronicLoad) -> None:
        """Transition DISCONNECTED → CONNECTED with the given instruments.

        Raises ValueError if not in DISCONNECTED state.
        """
        self._require_state(TestState.DISCONNECTED)
        self._psu = psu
        self._load = load
        self._transition(TestState.CONNECTED)
        self._log("Instruments connected.")

    def disconnect_instruments(self) -> None:
        """Disconnect from instruments. Must be in CONNECTED or STOPPED state."""
        if self._state not in (TestState.CONNECTED, TestState.STOPPED):
            raise ValueError(
                f"Cannot disconnect in state {self._state.name}. "
                "Stop the test first."
            )
        if self._psu:
            self._psu.disconnect()
        if self._load:
            self._load.disconnect()
        self._psu = None
        self._load = None
        self._transition(TestState.DISCONNECTED)
        self._log("Instruments disconnected.")

    # ------------------------------------------------------------------
    # Test lifecycle
    # ------------------------------------------------------------------

    def start_test(self) -> None:
        """Transition CONNECTED → RUNNING.

        Opens a new CSV log file, refreshes limits and notifier from settings,
        starts the PollWorker, and optionally enables PSU output / Load input.

        Raises ValueError if not in CONNECTED state.
        """
        self._require_state(TestState.CONNECTED)

        # Refresh notifier URL (user may have changed it in Settings)
        self._notifier.update_webhook_url(self._settings.teams_webhook_url)

        # Start CSV logger
        log_dir = Path(self._settings.log_directory)
        self._logger = CsvLogger(log_dir)
        log_path = self._logger.start()

        # Rebuild limit checker from current settings
        self._checker = LimitChecker(dict(self._settings.limits))

        # Optionally control instrument output/input state
        if self._settings.control_psu_output and self._psu:
            try:
                self._psu.output_on()
            except Exception as exc:
                self._log(f"Warning: Could not enable PSU output: {exc}")

        if self._settings.control_load_input and self._load:
            try:
                self._load.input_on()
            except Exception as exc:
                self._log(f"Warning: Could not enable Load input: {exc}")

        # Start poller
        self._poller = PollWorker(
            psu=self._psu,
            load=self._load,
            poll_rate_hz=self._settings.poll_rate_hz,
            load_mode=self._settings.last_load_mode,
        )
        self._poller.telemetry_sample.connect(self._on_telemetry_sample)
        self._poller.communication_error.connect(self._on_communication_error)
        self._poller.start()

        self._transition(TestState.RUNNING)
        self._log(f"Test started. Logging to: {log_path.name}")

    def stop_test(self) -> None:
        """Transition RUNNING → STOPPED.

        Stops the PollWorker, closes the CSV log file, optionally disables
        PSU output / Load input, and resets the limit checker.

        Raises ValueError if not in RUNNING state.
        """
        self._require_state(TestState.RUNNING)

        # Stop poller
        if self._poller:
            self._poller.stop_polling()
            self._poller.wait(3000)  # up to 3s for clean exit
            self._poller = None

        # Optionally control instrument output/input state
        if self._settings.control_load_input and self._load:
            try:
                self._load.input_off()
            except Exception as exc:
                self._log(f"Warning: Could not disable Load input: {exc}")

        if self._settings.control_psu_output and self._psu:
            try:
                self._psu.output_off()
            except Exception as exc:
                self._log(f"Warning: Could not disable PSU output: {exc}")

        # Close logger
        if self._logger:
            self._logger.stop()
            self._logger = None

        # Reset limit state
        self._checker.reset()

        self._transition(TestState.STOPPED)
        self._log("Test stopped.")

    def reset_to_connected(self) -> None:
        """Transition STOPPED → CONNECTED (ready to start another test)."""
        self._require_state(TestState.STOPPED)
        self._transition(TestState.CONNECTED)
        self._log("Ready for new test.")

    # ------------------------------------------------------------------
    # Settings update (called by SettingsDialog)
    # ------------------------------------------------------------------

    def update_limits(self, limits: dict[str, LimitPair]) -> None:
        """Replace the active limit set. Safe to call while RUNNING."""
        self._settings.limits = limits
        self._settings.save()
        self._checker.update_limits(limits)
        self._log("Limits updated.")

    def update_poll_rate(self, hz: float) -> None:
        """Update poll rate. Takes effect immediately if running."""
        self._settings.poll_rate_hz = hz
        self._settings.save()
        if self._poller:
            self._poller.set_poll_rate(hz)

    def update_notifier_url(self, url: str) -> None:
        """Update Teams webhook URL immediately."""
        self._settings.teams_webhook_url = url
        self._settings.save()
        self._notifier.update_webhook_url(url)

    # ------------------------------------------------------------------
    # Signal handlers (called from main thread via signal/slot)
    # ------------------------------------------------------------------

    def _on_telemetry_sample(self, sample: TelemetrySample) -> None:
        """Receive a sample from PollWorker: log, check limits, re-emit."""
        # Write to CSV
        if self._logger and self._logger.is_open:
            try:
                self._logger.write(sample)
            except Exception as exc:
                self._log(f"Log write error: {exc}")

        # Check limits
        alerts = self._checker.check(sample)
        for alert in alerts:
            self._log(alert)
            if "BREACH" in alert:
                self._notifier.send_alert(alert)
            elif "RESOLVED" in alert:
                self._notifier.send_resolved(alert)

        # Re-emit for graph and display panels
        self.telemetry_ready.emit(sample)

    def _on_communication_error(self, message: str) -> None:
        """Handle a VISA communication error from PollWorker."""
        full_msg = f"COMM ERROR: {message}"
        self._log(full_msg)
        # Alert Teams — test state stays RUNNING as per spec
        self._notifier.send_alert(full_msg)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _transition(self, new_state: TestState) -> None:
        self._state = new_state
        self.state_changed.emit(new_state)

    def _log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.event_logged.emit(f"[{ts}] {message}")

    def _require_state(self, expected: TestState) -> None:
        if self._state != expected:
            raise ValueError(
                f"Operation requires state {expected.name}, "
                f"but current state is {self._state.name}."
            )

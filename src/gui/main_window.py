"""Main application window.

Owns the TestController, lays out all panels, wires all signals/slots,
and enforces the failsafe close behaviour.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState
from src.core.test_controller import TestController
from src.gui.alerts_log_widget import AlertsLogWidget
from src.gui.connection_panel import ConnectionPanel
from src.gui.control_bar import ControlBar
from src.gui.graph_panel import GraphPanel
from src.gui.limits_panel import LimitsPanel
from src.gui.load_panel import LoadPanel
from src.gui.psu_panel import PsuPanel
from src.gui.settings_dialog import SettingsDialog
from src.instruments.electronic_load import ElectronicLoad
from src.instruments.power_supply import PowerSupply
from src.instruments.base import CommunicationError


class MainWindow(QMainWindow):
    """Top-level application window.

    Responsibilities:
    - Create and own all panels + controller
    - Connect every signal/slot
    - Enforce failsafe: block close while RUNNING
    - Dispatch state changes to all panels
    """

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._controller = TestController(settings, parent=self)

        self.setWindowTitle("Power Systems Monitoring Dashboard")
        self.setMinimumSize(1200, 800)

        self._build_panels()
        self._build_layout()
        self._connect_signals()
        self._build_menu()

        # Apply initial state
        self._apply_state(TestState.DISCONNECTED)

    # ------------------------------------------------------------------
    # Failsafe close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Block close while a test is running."""
        if self._controller.state == TestState.RUNNING:
            QMessageBox.warning(
                self,
                "Test Running",
                "A test is currently running.\n\n"
                "Please click STOP TEST before closing the application.",
            )
            event.ignore()
            return
        event.accept()

    # ------------------------------------------------------------------
    # Panel construction
    # ------------------------------------------------------------------

    def _build_panels(self) -> None:
        self._connection_panel = ConnectionPanel(self._settings)
        self._psu_panel = PsuPanel(self._settings)
        self._load_panel = LoadPanel(self._settings)
        self._limits_panel = LimitsPanel(self._settings)
        self._control_bar = ControlBar()
        self._graph_panel = GraphPanel()
        self._alerts_log = AlertsLogWidget()

    def _build_layout(self) -> None:
        # Left column: connection + psu + load + limits + control bar
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addWidget(self._connection_panel)
        left_layout.addWidget(self._psu_panel)
        left_layout.addWidget(self._load_panel)
        left_layout.addWidget(self._limits_panel)
        left_layout.addWidget(self._control_bar)
        left_layout.addStretch()
        left_widget.setLayout(left_layout)

        # Right column: graphs + alert log
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.addWidget(self._graph_panel, 3)
        right_layout.addWidget(self._alerts_log, 1)
        right_widget.setLayout(right_layout)

        # Splitter between left and right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([380, 820])

        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # Settings menu
        settings_menu = menu_bar.addMenu("Settings")
        settings_action = settings_menu.addAction("Open Settings…")
        settings_action.triggered.connect(self._open_settings)

        # Help menu
        help_menu = menu_bar.addMenu("Help")
        teams_action = help_menu.addAction("Teams Webhook Setup…")
        teams_action.triggered.connect(self._show_teams_help)
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._show_about)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Controller → UI
        self._controller.state_changed.connect(self._apply_state)
        self._controller.event_logged.connect(self._alerts_log.append_entry)
        self._controller.telemetry_ready.connect(self._on_telemetry_ready)

        # Connection panel → controller
        self._connection_panel.connect_requested.connect(self._on_connect_requested)
        self._connection_panel.disconnect_requested.connect(self._on_disconnect_requested)

        # Control bar → controller
        self._control_bar.start_requested.connect(self._on_start_requested)
        self._control_bar.stop_requested.connect(self._on_stop_requested)

        # Limits panel → controller
        self._limits_panel.limits_applied.connect(self._on_limits_applied)

        # Load panel → controller (mode changes when not running)
        self._load_panel.mode_changed.connect(self._on_load_mode_changed)

        # PSU panel → controller (setpoint changes when not running)
        self._psu_panel.setpoint_changed.connect(self._on_psu_setpoint_changed)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _apply_state(self, state: TestState) -> None:
        """Dispatch state to all panels that need enable/disable behaviour."""
        self._connection_panel.apply_state(state)
        self._psu_panel.apply_state(state)
        self._load_panel.apply_state(state)
        self._limits_panel.apply_state(state)
        self._control_bar.apply_state(state)

    # ------------------------------------------------------------------
    # Slot implementations
    # ------------------------------------------------------------------

    def _on_connect_requested(self, psu_visa: str, load_visa: str) -> None:
        if not psu_visa or not load_visa:
            QMessageBox.warning(
                self, "Missing VISA Address",
                "Please enter VISA resource strings for both the PSU and Load."
            )
            return

        psu = PowerSupply(psu_visa)
        load = ElectronicLoad(load_visa)
        try:
            psu.connect()
        except CommunicationError as exc:
            QMessageBox.critical(self, "PSU Connection Failed", str(exc))
            return
        try:
            load.connect()
        except CommunicationError as exc:
            psu.disconnect()
            QMessageBox.critical(self, "Load Connection Failed", str(exc))
            return

        self._controller.connect_instruments(psu, load)

    def _on_disconnect_requested(self) -> None:
        try:
            self._controller.disconnect_instruments()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Disconnect", str(exc))

    def _on_start_requested(self) -> None:
        try:
            self._controller.start_test()
        except Exception as exc:
            QMessageBox.critical(self, "Start Failed", str(exc))

    def _on_stop_requested(self) -> None:
        try:
            self._controller.stop_test()
        except Exception as exc:
            QMessageBox.critical(self, "Stop Failed", str(exc))

    def _on_limits_applied(self, limits: dict) -> None:
        self._controller.update_limits(limits)
        self._graph_panel.update_limits(limits)

    def _on_load_mode_changed(self, mode: str, value: float) -> None:
        """Send mode + value to the load instrument (if connected and not running)."""
        if self._controller.state not in (TestState.CONNECTED, TestState.STOPPED):
            return
        if self._controller._load:
            try:
                self._controller._load.set_mode(mode)
                self._controller._load.set_value(mode, value)
            except CommunicationError as exc:
                self._alerts_log.append_entry(f"[Load] Mode set error: {exc}")

    def _on_psu_setpoint_changed(self, voltage: float, current: float) -> None:
        """Send setpoint changes to the PSU (if connected and not running)."""
        if self._controller.state not in (TestState.CONNECTED, TestState.STOPPED):
            return
        if self._controller._psu:
            try:
                self._controller._psu.set_voltage(voltage)
                self._controller._psu.set_current(current)
            except CommunicationError as exc:
                self._alerts_log.append_entry(f"[PSU] Setpoint error: {exc}")

    def _on_telemetry_ready(self, sample) -> None:
        """Route telemetry to graph and live reading displays."""
        self._graph_panel.add_sample(sample)

        if sample.source == "PSU":
            # Accumulate PSU readings; update display panel when we have all three
            self._update_psu_display(sample)
        elif sample.source == "LOAD":
            self._update_load_display(sample)

    # ------------------------------------------------------------------
    # Telemetry display helpers
    # ------------------------------------------------------------------

    def __init_psu_cache(self) -> None:
        if not hasattr(self, "_psu_cache"):
            self._psu_cache = {"voltage": 0.0, "current": 0.0, "power": 0.0}

    def __init_load_cache(self) -> None:
        if not hasattr(self, "_load_cache"):
            self._load_cache = {"voltage": 0.0, "current": 0.0}

    def _update_psu_display(self, sample) -> None:
        self.__init_psu_cache()
        self._psu_cache[sample.parameter] = sample.value
        self._psu_panel.update_readings(
            self._psu_cache.get("voltage", 0.0),
            self._psu_cache.get("current", 0.0),
            self._psu_cache.get("power", 0.0),
        )

    def _update_load_display(self, sample) -> None:
        self.__init_load_cache()
        self._load_cache[sample.parameter] = sample.value
        self._load_panel.update_readings(
            self._load_cache.get("voltage", 0.0),
            self._load_cache.get("current", 0.0),
        )

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec():
            # Apply changed poll rate to running controller
            self._controller.update_poll_rate(self._settings.poll_rate_hz)
            self._controller.update_notifier_url(self._settings.teams_webhook_url)

    def _show_teams_help(self) -> None:
        QMessageBox.information(
            self,
            "Teams Webhook Setup",
            "<b>Setting up Microsoft Teams Notifications:</b><br><br>"
            "1. Open the target Teams channel<br>"
            "2. Click <b>...</b> → <b>Workflows</b><br>"
            "3. Search for <i>\"Post to a channel when a webhook request is received\"</i><br>"
            "4. Complete the setup wizard and copy the webhook URL<br>"
            "5. Paste the URL into <b>Settings → Webhook URL</b><br><br>"
            "<small>Note: This uses Microsoft Power Automate Workflows, "
            "not the deprecated Office 365 Connectors.</small>",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            "<b>Power Systems Monitoring Dashboard</b><br><br>"
            "Real-time VISA instrument monitoring and control.<br>"
            "Supports any SCPI-compliant power supply and electronic load.<br><br>"
            "<small>Built with Python, PyQt6, pyqtgraph, and pyvisa.</small>",
        )

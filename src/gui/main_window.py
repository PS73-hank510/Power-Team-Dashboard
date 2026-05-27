"""Main application window.

Owns the TestController, lays out all panels, wires all signals/slots,
and enforces the failsafe close behaviour.

Instrument panels (PsuPanel, LoadPanel) are created dynamically after
instruments are connected, and removed on disconnect.  This supports
any number of power supplies and an optional electronic load.
"""

from __future__ import annotations

import logging
from typing import List

from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)
from PyQt6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TelemetrySample, TestState
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
    - Manage dynamic PSU / Load panels
    """

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._controller = TestController(settings, parent=self)

        # Dynamic instrument panels (populated on connect, cleared on disconnect)
        self._psu_panels: List[PsuPanel] = []
        self._load_panels: List[LoadPanel] = []

        # Per-instrument telemetry caches for the live reading labels
        self._psu_caches: dict[int, dict] = {}
        self._load_caches: dict[int, dict] = {}

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
        self._limits_panel = LimitsPanel(self._settings)
        self._control_bar = ControlBar()
        self._graph_panel = GraphPanel()
        self._alerts_log = AlertsLogWidget()

    def _build_layout(self) -> None:
        # ── Left column ───────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setSpacing(4)

        # Connection panel (always visible)
        left_layout.addWidget(self._connection_panel)

        # Scrollable area for dynamic instrument panels
        self._instrument_panels_widget = QWidget()
        self._instrument_panels_layout = QVBoxLayout()
        self._instrument_panels_layout.setContentsMargins(0, 0, 0, 0)
        self._instrument_panels_layout.setSpacing(4)
        self._instrument_panels_layout.addStretch()  # pushes panels to the top
        self._instrument_panels_widget.setLayout(self._instrument_panels_layout)

        instr_scroll = QScrollArea()
        instr_scroll.setWidget(self._instrument_panels_widget)
        instr_scroll.setWidgetResizable(True)
        instr_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        left_layout.addWidget(instr_scroll, 1)

        # Fixed panels at the bottom of the left column
        left_layout.addWidget(self._limits_panel)
        left_layout.addWidget(self._control_bar)

        left_widget.setLayout(left_layout)

        # ── Right column ──────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.addWidget(self._graph_panel, 3)
        right_layout.addWidget(self._alerts_log, 1)
        right_widget.setLayout(right_layout)

        # ── Splitter ──────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 800])

        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        settings_menu = menu_bar.addMenu("Settings")
        settings_action = settings_menu.addAction("Open Settings…")
        settings_action.triggered.connect(self._open_settings)

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

        # Connection panel → main window
        self._connection_panel.connect_requested.connect(self._on_connect_requested)
        self._connection_panel.disconnect_requested.connect(
            self._on_disconnect_requested
        )

        # Control bar → controller
        self._control_bar.start_requested.connect(self._on_start_requested)
        self._control_bar.stop_requested.connect(self._on_stop_requested)

        # Limits panel → controller + graph
        self._limits_panel.limits_applied.connect(self._on_limits_applied)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _apply_state(self, state: TestState) -> None:
        """Dispatch state to all panels."""
        self._connection_panel.apply_state(state)
        for panel in self._psu_panels:
            panel.apply_state(state)
        for panel in self._load_panels:
            panel.apply_state(state)
        self._limits_panel.apply_state(state)
        self._control_bar.apply_state(state)

    # ------------------------------------------------------------------
    # Dynamic instrument panels
    # ------------------------------------------------------------------

    def _create_instrument_panels(self, num_psus: int, num_loads: int) -> None:
        """Create PSU and Load display panels after a successful connection."""
        self._clear_instrument_panels()

        # Insert before the trailing stretch (last item in the layout)
        stretch_idx = self._instrument_panels_layout.count() - 1

        for i in range(num_psus):
            panel = PsuPanel(self._settings, index=i)
            panel.setpoint_changed.connect(
                lambda v, c, idx=i: self._on_psu_setpoint_changed(idx, v, c)
            )
            self._instrument_panels_layout.insertWidget(stretch_idx + i, panel)
            self._psu_panels.append(panel)

        for j in range(num_loads):
            panel = LoadPanel(self._settings, index=j)
            panel.mode_changed.connect(
                lambda m, v, idx=j: self._on_load_mode_changed(idx, m, v)
            )
            self._instrument_panels_layout.insertWidget(
                stretch_idx + num_psus + j, panel
            )
            self._load_panels.append(panel)

        # Apply current state so newly-created panels are in the right enabled state
        self._apply_state(self._controller.state)

    def _clear_instrument_panels(self) -> None:
        """Destroy all dynamic instrument panels and reset caches."""
        for panel in list(self._psu_panels) + list(self._load_panels):
            self._instrument_panels_layout.removeWidget(panel)
            panel.hide()
            panel.deleteLater()
        self._psu_panels = []
        self._load_panels = []
        self._psu_caches = {}
        self._load_caches = {}

    # ------------------------------------------------------------------
    # Slot implementations
    # ------------------------------------------------------------------

    def _on_connect_requested(
        self, psu_visas: list[str], load_visas: list[str]
    ) -> None:
        if not psu_visas:
            QMessageBox.warning(
                self,
                "Missing VISA Address",
                "Please enter at least one VISA resource string for a Power Supply.",
            )
            return

        # Connect all PSUs
        psus: list[PowerSupply] = []
        for visa in psu_visas:
            psu = PowerSupply(visa)
            try:
                psu.connect()
                psus.append(psu)
            except CommunicationError as exc:
                logger.error("PSU connection failed for %s: %s", visa, exc)
                for p in psus:
                    p.disconnect()
                QMessageBox.critical(
                    self, "PSU Connection Failed",
                    f"Could not connect to PSU at:\n{visa}\n\n"
                    "Check that the instrument is powered on and the VISA address is correct.",
                )
                return

        # Connect all loads (may be empty for PSU-only)
        loads: list[ElectronicLoad] = []
        for visa in load_visas:
            load = ElectronicLoad(visa)
            try:
                load.connect()
                loads.append(load)
            except CommunicationError as exc:
                logger.error("Load connection failed for %s: %s", visa, exc)
                for p in psus:
                    p.disconnect()
                for ld in loads:
                    ld.disconnect()
                QMessageBox.critical(
                    self, "Load Connection Failed",
                    f"Could not connect to Load at:\n{visa}\n\n"
                    "Check that the instrument is powered on and the VISA address is correct.",
                )
                return

        try:
            self._controller.connect_instruments(psus, loads)
        except Exception as exc:
            # Defensive: clean up already-opened VISA connections before surfacing
            # the error (e.g. rapid double-click where state is no longer DISCONNECTED)
            for p in psus:
                try:
                    p.disconnect()
                except Exception:
                    pass
            for ld in loads:
                try:
                    ld.disconnect()
                except Exception:
                    pass
            QMessageBox.critical(self, "Connection Failed", str(exc))
            return
        self._create_instrument_panels(len(psus), len(loads))

    def _on_disconnect_requested(self) -> None:
        try:
            self._controller.disconnect_instruments()
            self._clear_instrument_panels()
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

    def _on_load_mode_changed(self, idx: int, mode: str, value: float) -> None:
        """Send mode + value to the indexed load instrument (if connected)."""
        if self._controller.state not in (TestState.CONNECTED, TestState.STOPPED):
            return
        if idx < len(self._controller._loads):
            try:
                load = self._controller._loads[idx]
                load.set_mode(mode)
                load.set_value(mode, value)
            except CommunicationError as exc:
                self._alerts_log.append_entry(f"[Load-{idx}] Mode set error: {exc}")

    def _on_psu_setpoint_changed(
        self, idx: int, voltage: float, current: float
    ) -> None:
        """Send setpoint changes to the indexed PSU (if connected)."""
        if self._controller.state not in (TestState.CONNECTED, TestState.STOPPED):
            return
        if idx < len(self._controller._psus):
            try:
                psu = self._controller._psus[idx]
                psu.set_voltage(voltage)
                psu.set_current(current)
            except CommunicationError as exc:
                self._alerts_log.append_entry(f"[PSU-{idx}] Setpoint error: {exc}")

    def _on_telemetry_ready(self, sample: TelemetrySample) -> None:
        """Route telemetry to graph and live reading displays."""
        self._graph_panel.add_sample(sample)

        idx = sample.source_index
        if sample.source == "PSU" and idx < len(self._psu_panels):
            self._update_psu_display(sample, idx)
        elif sample.source == "LOAD" and idx < len(self._load_panels):
            self._update_load_display(sample, idx)

    # ------------------------------------------------------------------
    # Telemetry display helpers
    # ------------------------------------------------------------------

    def _update_psu_display(self, sample: TelemetrySample, idx: int) -> None:
        cache = self._psu_caches.setdefault(idx, {"voltage": 0.0, "current": 0.0, "power": 0.0})
        cache[sample.parameter] = sample.value
        self._psu_panels[idx].update_readings(
            cache["voltage"], cache["current"], cache["power"]
        )

    def _update_load_display(self, sample: TelemetrySample, idx: int) -> None:
        cache = self._load_caches.setdefault(idx, {"voltage": 0.0, "current": 0.0})
        cache[sample.parameter] = sample.value
        self._load_panels[idx].update_readings(cache["voltage"], cache["current"])

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec():
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
            "Supports any SCPI-compliant power supply and electronic load.<br>"
            "Multiple instruments of each type are supported.<br><br>"
            "<small>Built with Python, PyQt6, pyqtgraph, and pyvisa.</small>",
        )

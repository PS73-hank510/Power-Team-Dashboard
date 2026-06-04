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
from src.instruments.electronic_load import (
    LOAD_PROFILES,
    ElectronicLoad,
    ProdigitBothChannelsLoad,
    ProdigitCh1Load,
    ProdigitCh2Load,
    ProdigitDualChannelLoad,
)
from src.instruments.power_supply import PSU_PROFILES, PowerSupply
from src.instruments.base import CommunicationError


# ---------------------------------------------------------------------------
# Operating Manual — HTML content for Help → Operating Manual
# ---------------------------------------------------------------------------

_OPERATING_MANUAL_HTML = """
<h2>Power Systems Monitoring Dashboard — Operating Manual</h2>

<h3>Overview</h3>
<p>The dashboard connects to SCPI-compliant power supplies (PSUs) and electronic
loads via VISA (USB-TMC, GPIB, LAN) or serial (RS-232 / USB-CDC) interfaces.
It provides real-time telemetry, limit monitoring, Teams alerts, and direct
instrument control.</p>

<h3>Connecting Instruments</h3>
<ol>
  <li>Enter the VISA resource strings in the Connection panel
      (e.g. <code>ASRL3::INSTR</code> for COM3, <code>USB0::0x0ABC::0x0001::INSTR</code>
      for USB-TMC).</li>
  <li>Open <b>Settings</b> and configure serial baud rate, termination, profile,
      and (for Prodigit loads) the channel selector.</li>
  <li>Click <b>Connect</b>.</li>
</ol>

<h3>Power Supply Control</h3>
<ul>
  <li>Enter voltage and current setpoints in the PSU panel and click
      <b>Apply Setpoints</b>.  Setpoints are sent immediately.</li>
  <li>Use <b>Output ON / OFF</b> to enable or disable the PSU output.</li>
  <li>The measured voltage, current, and power update at the configured poll rate.</li>
</ul>

<h3>Electronic Load — General (Standard SCPI / Short SCPI profiles)</h3>
<ol>
  <li>Select mode (CC / CV / CR / CP) and set value in the Load panel.</li>
  <li>Click <b>Apply Load Settings</b> to send the mode and value to the instrument.</li>
  <li>Use the load&rsquo;s front panel or the <b>Load ON / OFF</b> buttons to enable
      the load input.</li>
</ol>

<h3>Electronic Load — Prodigit 3302G / 3330F</h3>
<p>The Prodigit uses a <em>select-then-command</em> protocol: a channel-select
command (<code>CHAN1</code> or <code>CHAN2</code>) is always sent first,
followed by bare commands with no per-command prefix.</p>

<h4>Protocol sequence</h4>
<pre>
CHAN1          (select channel 1)
LOAD OFF       (disable input — safety before mode change)
CC 0.0         (reset current setpoint to 0)
MODE CC        (set operating mode)
CC 5.0         (set setpoint; format: &lt;MODE&gt; &lt;value&gt;)
LOAD ON        (enable input)
VOLT?          (measure terminal voltage)
CURR?          (measure load current)
</pre>

<h4>Recommended operating sequence</h4>
<ol>
  <li><b>Select channel</b> in the Load panel (CH1 / CH2 / Both).
      Reconnect if you change the channel selection.</li>
  <li><b>Apply Load Settings</b> — sends LOAD OFF → CC 0 → MODE → setpoint.</li>
  <li><b>Load ON</b> — enables the load input.</li>
  <li>To change mode: click <b>Load OFF</b>, change mode/value,
      click <b>Apply</b>, then <b>Load ON</b> again.</li>
  <li>Click <b>Load OFF</b> before disconnecting.</li>
</ol>

<h4>Safety notes</h4>
<ul>
  <li>Always send <b>Load OFF</b> before changing the operating mode.
      The driver does this automatically on Apply, but manual OFF first is safer.</li>
  <li><b>CP mode</b> may not engage if a residual current setpoint is left from
      a previous mode. Cycling LOAD OFF → Apply → Load ON resolves this.</li>
  <li>The <b>Both CH1+CH2</b> mode locks both channels to the same setpoint.
      It sleeps ≈ 700 ms per mode change (hardware firmware requirement).</li>
  <li><b>Numeric MODE? response</b>: the 3330F sometimes returns
      <code>0</code>=CC, <code>1</code>=CR, <code>2</code>=CV, <code>3</code>=CP.
      The driver normalises these automatically.</li>
</ul>

<h4>Typical baud rate</h4>
<p>COM3 or COM4 at <b>115200 baud</b>, write/read termination <code>\\r\\n</code>.</p>

<h3>Running a Test</h3>
<ol>
  <li>Connect instruments and apply load settings.</li>
  <li>Optionally configure limits in the Limits panel.</li>
  <li>Click <b>Start Test</b>.  The test runs at the configured poll rate.</li>
  <li>Click <b>Stop Test</b> to end.  The dashboard remains connected.</li>
</ol>
<p><b>Note:</b> Start Test is blocked until all connected load panels show
<em>&ldquo;Applied&rdquo;</em> status.  Click <b>Apply Load Settings</b>
on each load panel first.</p>

<h3>Limit Monitoring</h3>
<p>Set min/max limits for any measured parameter in the Limits panel.
When a limit is violated, an alert is logged and a Teams notification is sent
(if a webhook URL is configured in Settings).</p>

<h3>Settings Reference</h3>
<table border="1" cellpadding="4" cellspacing="0">
  <tr><th>Setting</th><th>Description</th></tr>
  <tr><td>PSU Profile</td><td>SCPI command set for the power supply</td></tr>
  <tr><td>Load Profile</td><td>SCPI command set for the electronic load</td></tr>
  <tr><td>Load Channel</td><td>CH1 / CH2 / Both — Prodigit only; reconnect to apply</td></tr>
  <tr><td>Baud Rate</td><td>Serial baud rate (e.g. 9600, 115200)</td></tr>
  <tr><td>Write / Read Termination</td><td>Line ending sent/expected (LF, CR+LF, CR)</td></tr>
  <tr><td>VISA Timeout</td><td>Query timeout in milliseconds</td></tr>
  <tr><td>Connect Preamble</td><td>Command sent once on connect (e.g. ADR 10 for TDK-Lambda)</td></tr>
  <tr><td>Remote Enable</td><td>Command to put instrument in remote mode (e.g. SYST:REM)</td></tr>
  <tr><td>Poll Rate</td><td>Measurement frequency (0.5 – 10 Hz)</td></tr>
</table>
"""


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
        # ── Top bar — status + Start/Stop (spans full window width) ──
        # The ControlBar has: [status label] [stretch] [START/STOP button]
        self._control_bar.setStyleSheet(
            "QWidget { background-color: #1e1e2e; border-bottom: 1px solid #333; }"
        )
        self._control_bar.setFixedHeight(52)

        # ── Left column: Connection panel + scrollable instrument panels ──
        # Connection panel is always visible at the top.
        # PSU and Load panels are added/removed dynamically below it.
        self._instrument_panels_widget = QWidget()
        self._instrument_panels_layout = QVBoxLayout()
        self._instrument_panels_layout.setContentsMargins(0, 0, 0, 0)
        self._instrument_panels_layout.setSpacing(6)
        self._instrument_panels_layout.addStretch()  # panels pinned to top
        self._instrument_panels_widget.setLayout(self._instrument_panels_layout)

        instr_scroll = QScrollArea()
        instr_scroll.setWidget(self._instrument_panels_widget)
        instr_scroll.setWidgetResizable(True)
        instr_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setSpacing(4)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(self._connection_panel)
        left_layout.addWidget(instr_scroll, 1)   # PSU + Load panels fill remaining height
        left_widget.setLayout(left_layout)

        # ── Right column: Limits bar (top) + Graph + Alerts ──────────
        # Safety-limits bar is a compact horizontal strip at the very top.
        # The graph and alerts log share the remaining space below it.
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)
        right_layout.addWidget(self._limits_panel)      # compact horizontal limits
        right_layout.addWidget(self._graph_panel, 3)    # graph gets most of the space
        right_layout.addWidget(self._alerts_log, 1)     # alerts log below graph
        right_widget.setLayout(right_layout)

        # ── 2-pane horizontal splitter ────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)    # Connection + instrument panels
        splitter.addWidget(right_widget)   # Limits + Graph + Alerts
        splitter.setSizes([420, 780])

        # ── Central widget: top bar + splitter ────────────────────────
        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._control_bar)   # full-width top bar
        main_layout.addWidget(splitter, 1)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        settings_menu = menu_bar.addMenu("Settings")
        settings_action = settings_menu.addAction("Open Settings…")
        settings_action.triggered.connect(self._open_settings)

        help_menu = menu_bar.addMenu("Help")
        manual_action = help_menu.addAction("Operating Manual…")
        manual_action.triggered.connect(self._show_operating_manual)
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
        """Create PSU and Load display panels after a successful connection.

        Panels are stacked vertically in the left scrollable area:
        PSU panels first, then Load panels.  All panels are inserted before
        the trailing stretch so they stay pinned to the top.
        """
        self._clear_instrument_panels()

        # Insert before the trailing stretch (last item in the layout)
        stretch_idx = self._instrument_panels_layout.count() - 1

        for i in range(num_psus):
            panel = PsuPanel(self._settings, index=i)
            panel.setpoint_changed.connect(
                lambda v, c, idx=i: self._on_psu_setpoint_changed(idx, v, c)
            )
            panel.output_requested.connect(
                lambda on, idx=i: self._on_psu_output_requested(idx, on)
            )
            self._instrument_panels_layout.insertWidget(stretch_idx + i, panel)
            self._psu_panels.append(panel)

        for j in range(num_loads):
            panel = LoadPanel(self._settings, index=j)
            panel.settings_applied.connect(
                lambda m, v, idx=j: self._on_load_settings_applied(idx, m, v)
            )
            panel.input_requested.connect(
                lambda on, idx=j: self._on_load_input_requested(idx, on)
            )
            panel.status_requested.connect(
                lambda idx=j: self._on_load_status_requested(idx)
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

        # PSU serial / VISA session params from settings
        baud = self._settings.serial_baud_rate
        write_term = self._settings.serial_write_termination
        read_term = self._settings.serial_read_termination
        timeout_ms = self._settings.visa_timeout_ms

        # Load serial/VISA settings — independent from PSU
        load_baud      = self._settings.load_serial_baud_rate
        load_write_term = self._settings.load_serial_write_termination
        load_read_term  = self._settings.load_serial_read_termination
        load_timeout_ms = self._settings.load_visa_timeout_ms

        # Per-instrument preambles and profiles
        psu_preamble = self._settings.psu_connect_preamble
        load_preamble   = self._settings.load_connect_preamble

        PSUClass = PSU_PROFILES.get(self._settings.psu_command_profile, PowerSupply)
        LoadClass = LOAD_PROFILES.get(self._settings.load_command_profile, ElectronicLoad)

        # For Prodigit profiles, the channel-mode setting (ch1/ch2/both) overrides
        # whichever specific ch1/ch2 variant was stored in load_command_profile.
        # This lets the user change channels via the LoadPanel dropdown without
        # editing the profile key manually.
        if issubclass(LoadClass, ProdigitDualChannelLoad):
            channel_mode = self._settings.load_channel_mode
            if channel_mode == "ch2":
                LoadClass = ProdigitCh2Load
            elif channel_mode == "both":
                LoadClass = ProdigitBothChannelsLoad
            else:  # "ch1" or any unrecognised value → default to CH1
                LoadClass = ProdigitCh1Load

        # Connect all PSUs
        psus: list[PowerSupply] = []
        for visa in psu_visas:
            psu = PSUClass(
                visa,
                baud_rate=baud,
                write_termination=write_term,
                read_termination=read_term,
                timeout_ms=timeout_ms,
                connect_preamble=psu_preamble,
            )
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
            load = LoadClass(
                visa,
                baud_rate=load_baud,
                write_termination=load_write_term,
                read_termination=load_read_term,
                timeout_ms=load_timeout_ms,
                connect_preamble=load_preamble,
                remote_enable_command=self._settings.load_remote_enable_command,
            )
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
        # Guard: all connected load panels must have settings applied before starting
        for i, panel in enumerate(self._load_panels):
            if panel.is_dirty:
                QMessageBox.warning(
                    self,
                    "Load Settings Not Applied",
                    f"Load {i + 1} settings have not been sent to the instrument.\n\n"
                    "Click \"Apply Load Settings\" on the load panel before starting the test.",
                )
                return
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

    def _on_load_settings_applied(self, idx: int, mode: str, value: float) -> None:
        """Send mode and value to the indexed load instrument.

        Called when the user clicks "Apply Load Settings" on a LoadPanel.
        On success the panel dirty flag is cleared.  On failure a message
        is logged and the panel stays dirty so the user knows the command
        did not reach the instrument.
        """
        if self._controller.state not in (TestState.CONNECTED, TestState.STOPPED):
            return
        if idx >= len(self._controller._loads):
            return

        load = self._controller._loads[idx]
        tag = f"Load-{idx}"

        # ── Mode ──────────────────────────────────────────────────────
        try:
            load.set_mode(mode)
        except CommunicationError as exc:
            self._alerts_log.append_entry(
                f"[{tag}] Mode set FAILED ({mode}): {exc}"
            )
            return  # Leave panel dirty — settings did not reach instrument

        # ── Value ─────────────────────────────────────────────────────
        try:
            load.set_value(mode, value)
        except CommunicationError as exc:
            self._alerts_log.append_entry(
                f"[{tag}] Value set FAILED ({mode} {value:.3g}): {exc}"
            )
            return

        # ── Optional verification (best-effort; silenced on failure) ──
        try:
            confirmed_mode = load.get_mode()
            self._alerts_log.append_entry(
                f"[{tag}] Settings applied: {mode} @ {value:.3g} "
                f"(instrument confirmed mode: {confirmed_mode})"
            )
        except Exception:
            self._alerts_log.append_entry(
                f"[{tag}] Settings applied: {mode} @ {value:.3g}"
            )

        # ── Mark panel as applied ─────────────────────────────────────
        if idx < len(self._load_panels):
            self._load_panels[idx].mark_applied(mode, value)

    def _on_load_input_requested(self, idx: int, on: bool) -> None:
        """Turn the indexed load input on (on=True) or off (on=False).

        Called when the user clicks Load ON or Load OFF on a LoadPanel.
        The panel's button highlight is updated to reflect the new state.
        On failure the alert log records the error and the highlight is not changed.
        """
        if self._controller.state not in (
            TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING
        ):
            return
        if idx >= len(self._controller._loads):
            return

        load = self._controller._loads[idx]
        tag  = f"Load-{idx}"
        try:
            if on:
                load.input_on()
                self._alerts_log.append_entry(f"[{tag}] Load input ON")
            else:
                load.input_off()
                self._alerts_log.append_entry(f"[{tag}] Load input OFF")
            if idx < len(self._load_panels):
                self._load_panels[idx].set_input_state(on)
        except CommunicationError as exc:
            self._alerts_log.append_entry(
                f"[{tag}] Load {'ON' if on else 'OFF'} failed: {exc}"
            )

    def _on_load_status_requested(self, idx: int) -> None:
        """Query mode and load state from the indexed load instrument.

        Results are displayed in the LoadPanel status field and logged to
        the alerts log.  Best-effort — individual query failures are silenced
        so a partial response is still shown.
        """
        if self._controller.state not in (
            TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING
        ):
            return
        if idx >= len(self._controller._loads):
            return

        load = self._controller._loads[idx]
        tag  = f"Load-{idx}"
        parts: list[str] = []

        # Load input state (Prodigit-specific; silenced for other profiles)
        if hasattr(load, "query_load_state"):
            state = load.query_load_state()
            parts.append(f"Input: {state or 'N/A'}")

        # Current mode
        try:
            mode = load.get_mode()
            parts.append(f"Mode: {mode}")
        except CommunicationError:
            parts.append("Mode: (query failed)")

        status_text = "  |  ".join(parts) if parts else "No status available"
        self._alerts_log.append_entry(f"[{tag}] Status — {status_text}")
        if idx < len(self._load_panels):
            self._load_panels[idx].set_status_text(status_text)

    def _on_psu_setpoint_changed(
        self, idx: int, voltage: float, current: float
    ) -> None:
        """Send voltage and current setpoints to the indexed PSU independently.

        Each command is attempted in its own try block so a voltage failure
        does not silently prevent the current command from being sent.
        Successes and failures are both logged to the alerts panel so the
        operator can confirm what reached the instrument.
        """
        if self._controller.state not in (
            TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING
        ):
            return
        if idx >= len(self._controller._psus):
            return

        psu = self._controller._psus[idx]
        tag = f"PSU-{idx}"

        # ── Voltage ──────────────────────────────────────────────────
        try:
            psu.set_voltage(voltage)
            # Read back to confirm the instrument stored the value
            try:
                confirmed_v = psu.get_voltage_setpoint()
                self._alerts_log.append_entry(
                    f"[{tag}] Voltage setpoint → {voltage:.3f} V "
                    f"(instrument confirmed: {confirmed_v:.3f} V)"
                )
            except Exception:
                self._alerts_log.append_entry(
                    f"[{tag}] Voltage setpoint sent: {voltage:.3f} V"
                )
        except CommunicationError as exc:
            self._alerts_log.append_entry(
                f"[{tag}] Voltage setpoint FAILED: {exc}"
            )

        # ── Current ──────────────────────────────────────────────────
        try:
            psu.set_current(current)
            # Read back to confirm the instrument stored the value.
            # NOTE: the measured current shown in the dashboard is what your
            # load actually draws — it will NOT equal the setpoint unless the
            # supply is in CC mode and the load exceeds this limit.
            try:
                confirmed_i = psu.get_current_setpoint()
                self._alerts_log.append_entry(
                    f"[{tag}] Current setpoint → {current:.3f} A "
                    f"(instrument confirmed: {confirmed_i:.3f} A). "
                    "Measured current = actual load draw, not this limit."
                )
            except Exception:
                self._alerts_log.append_entry(
                    f"[{tag}] Current setpoint sent: {current:.3f} A "
                    "(measured current = actual load draw, not this limit)"
                )
        except CommunicationError as exc:
            self._alerts_log.append_entry(
                f"[{tag}] Current setpoint FAILED: {exc}"
            )

    def _on_psu_output_requested(self, idx: int, on: bool) -> None:
        """Turn the indexed PSU output on or off."""
        if self._controller.state not in (
            TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING
        ):
            return
        if idx < len(self._controller._psus):
            try:
                psu = self._controller._psus[idx]
                if on:
                    psu.output_on()
                else:
                    psu.output_off()
                # Sync button state to confirmed instrument state
                if idx < len(self._psu_panels):
                    self._psu_panels[idx].set_output_state(on)
            except CommunicationError as exc:
                # Roll back button to previous state on failure
                if idx < len(self._psu_panels):
                    self._psu_panels[idx].set_output_state(not on)
                self._alerts_log.append_entry(
                    f"[PSU-{idx}] Output {'ON' if on else 'OFF'} failed: {exc}"
                )

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
        panel = self._load_panels[idx]
        panel.update_readings(cache["voltage"], cache["current"])

        # For Both-channel loads, forward the cached CH2 readings to the panel
        # so the GUI reflects the last measurement from ProdigitBothChannelsLoad.
        if idx < len(self._controller._loads):
            load = self._controller._loads[idx]
            if isinstance(load, ProdigitBothChannelsLoad):
                panel.update_ch2_readings(
                    load.measure_voltage_ch2(),
                    load.measure_current_ch2(),
                )

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec():
            self._controller.update_poll_rate(self._settings.poll_rate_hz)
            self._controller.update_notifier_url(self._settings.teams_webhook_url)

    def _show_operating_manual(self) -> None:
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QScrollArea, QTextBrowser

        dlg = QDialog(self)
        dlg.setWindowTitle("Operating Manual — Power Systems Dashboard")
        dlg.setMinimumSize(700, 560)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(_OPERATING_MANUAL_HTML)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.accept)

        layout = QVBoxLayout()
        layout.addWidget(browser, 1)
        layout.addWidget(buttons)
        dlg.setLayout(layout)
        dlg.exec()

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

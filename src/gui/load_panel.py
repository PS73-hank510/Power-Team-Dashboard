"""Electronic Load panel — channel selection, mode, setpoint, live readings,
and direct Load ON/OFF/Status control.

Mode and value controls are purely local — no command is sent to the
instrument until the user explicitly clicks "Apply Load Settings".  A
dirty flag tracks whether the local settings differ from the last
successfully applied state.  MainWindow checks this flag before allowing
a test to start.

Channel selection (CH1 / CH2 / Both) is persisted to settings and takes
effect on the *next* connection — the selected profile class is instantiated
using this preference when the user clicks Connect.  The Load ON / Load OFF
and Read Status buttons send commands immediately to the connected instrument.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState
from src.instruments.electronic_load import LOAD_MODES

# Units and ranges for each mode's setpoint spinbox
_MODE_UNITS = {"CC": "A", "CV": "V", "CR": "Ω", "CP": "W"}
_MODE_RANGES = {
    # min, max, decimals (unused — fixed at 3), singleStep
    "CC": (0.0, 100.0,   0.001, 0.01),
    "CV": (0.0, 1000.0,  0.001, 0.1),
    "CR": (0.0, 10000.0, 0.001, 1.0),
    "CP": (0.0, 10000.0, 0.001, 1.0),
}

# Channel selector options: (display label, settings value)
_CHANNEL_OPTIONS = [
    ("CH1",          "ch1"),
    ("CH2",          "ch2"),
    ("Both CH1+CH2", "both"),
]

_INSTRUCTIONS_HTML = (
    "<b>⚠ Prodigit 3302G / 3330F — recommended sequence:</b><br>"
    "1. Select channel (CH1 / CH2 / Both) — reconnect if changed<br>"
    "2. Set mode &amp; value, then click <b>Apply Load Settings</b><br>"
    "3. Click <b>Load ON</b> to begin drawing current<br>"
    "4. Click <b>Load OFF</b> before changing mode or disconnecting<br>"
    "<br>"
    "<b>⚠ Safety notes:</b><br>"
    "• The driver automatically sends LOAD OFF → CC 0 reset → MODE on<br>"
    "&nbsp;&nbsp;every mode change, but manual Load OFF first is safer.<br>"
    "• <b>CP mode:</b> if it does not engage, click Load OFF → Apply → Load ON.<br>"
    "• Standard SCPI profiles: channel selector has no effect — use<br>"
    "&nbsp;&nbsp;Apply Load Settings and the INPut ON/OFF commands only."
)


class LoadPanel(QGroupBox):
    """Panel for configuring and applying electronic load settings.

    The mode dropdown and value spinbox are purely local controls — no
    command is sent to the instrument until the user clicks
    "Apply Load Settings".  A dirty flag tracks unapplied state and is
    used by MainWindow to block test start until Apply is clicked.

    Signals:
        settings_applied(mode, value):
            User clicked Apply; MainWindow should call set_mode/set_value
            on the instrument and then call mark_applied().
        input_requested(on):
            User clicked Load ON (True) or Load OFF (False).
        status_requested():
            User clicked Read Status.
    """

    settings_applied = pyqtSignal(str, float)
    input_requested  = pyqtSignal(bool)
    status_requested = pyqtSignal()

    def __init__(
        self, settings: SettingsManager, index: int = 0, parent=None
    ) -> None:
        title = f"Electronic Load {index + 1}" if index > 0 else "Electronic Load"
        super().__init__(title, parent)
        self._settings = settings
        self._index = index
        self._dirty = True  # Not applied until user explicitly clicks Apply
        self._build_ui()
        self._load_from_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        """True when local settings have not yet been applied to the instrument."""
        return self._dirty

    def apply_state(self, state: TestState) -> None:
        """Enable / disable controls according to the current test state."""
        connected = state in (
            TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING
        )
        running = state == TestState.RUNNING

        # Mode / setpoint / Apply: locked while a test is running
        self._mode_combo.setEnabled(not running)
        self._value_spin.setEnabled(not running)
        self._apply_btn.setEnabled(not running)

        # Channel selector: only editable when not connected (takes effect on reconnect)
        self._channel_combo.setEnabled(not connected)

        # Load ON / OFF / Status: available any time the instrument is connected
        self._load_on_btn.setEnabled(connected)
        self._load_off_btn.setEnabled(connected)
        self._status_btn.setEnabled(connected)

    def mark_applied(self, mode: str, value: float) -> None:
        """Called by MainWindow after a successful instrument apply.

        Clears the dirty flag, updates the status label, and persists the
        last-applied mode to settings so it is remembered on next connect.
        """
        self._dirty = False
        unit = _MODE_UNITS.get(mode, "")
        self._status_label.setText(f"Applied: {mode} @ {value:.3f} {unit}")
        self._status_label.setStyleSheet("color: green; font-weight: bold;")
        self._apply_btn.setText("✓ Apply Load Settings")
        self._settings.last_load_mode = mode
        self._settings.save()

    def update_readings(self, voltage: float, current: float) -> None:
        """Update live CH1 measurement labels (called from the telemetry feed)."""
        self._v_label.setText(f"{voltage:.4f} V")
        self._i_label.setText(f"{current:.4f} A")

    def update_ch2_readings(self, voltage: float, current: float) -> None:
        """Update live CH2 measurement labels (called from the telemetry feed in Both mode)."""
        self._v2_label.setText(f"{voltage:.4f} V")
        self._i2_label.setText(f"{current:.4f} A")

    def set_input_state(self, on: bool) -> None:
        """Highlight the active Load ON / Load OFF button."""
        _active_on  = "background-color: #2d6a2d; color: white; font-weight: bold;"
        _active_off = "background-color: #6a2d2d; color: white; font-weight: bold;"
        self._load_on_btn.setStyleSheet(_active_on  if on  else "")
        self._load_off_btn.setStyleSheet(_active_off if not on else "")

    def set_status_text(self, text: str) -> None:
        """Display a status string returned by Read Status."""
        self._state_label.setText(text)

    # ------------------------------------------------------------------
    # Private — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Channel selector ──────────────────────────────────────────
        self._channel_combo = QComboBox()
        for label, _ in _CHANNEL_OPTIONS:
            self._channel_combo.addItem(label)
        self._channel_combo.setToolTip(
            "Select which Prodigit 3330F channel(s) to control.\n"
            "This setting takes effect on the next connection.\n"
            "Reconnect after changing the channel."
        )
        self._channel_combo.currentIndexChanged.connect(self._on_channel_changed)

        # ── Mode / setpoint controls ──────────────────────────────────
        self._mode_combo = QComboBox()
        for mode in LOAD_MODES:
            self._mode_combo.addItem(mode)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)

        self._value_spin = QDoubleSpinBox()
        self._value_spin.setDecimals(3)
        self._value_spin.setMinimumWidth(140)
        self._value_spin.setMinimumHeight(28)
        self._value_spin.valueChanged.connect(self._on_value_changed)

        self._apply_btn = QPushButton("Apply Load Settings")
        self._apply_btn.setToolTip(
            "Send the selected mode and value to the instrument.\n"
            "Settings must be applied before starting a test."
        )
        self._apply_btn.clicked.connect(self._on_apply_clicked)

        self._status_label = QLabel("Not applied — click Apply to send to instrument")
        self._status_label.setStyleSheet("color: orange;")
        self._status_label.setWordWrap(True)

        # ── Load ON / Load OFF / Read Status ──────────────────────────
        self._load_on_btn = QPushButton("Load ON")
        self._load_on_btn.setToolTip(
            "Enable the load input (instrument starts drawing current)."
        )
        self._load_on_btn.setEnabled(False)
        self._load_on_btn.clicked.connect(lambda: self.input_requested.emit(True))

        self._load_off_btn = QPushButton("Load OFF")
        self._load_off_btn.setToolTip(
            "Disable the load input (instrument stops drawing current).\n"
            "Always click Load OFF before changing mode."
        )
        self._load_off_btn.setEnabled(False)
        self._load_off_btn.clicked.connect(lambda: self.input_requested.emit(False))

        self._status_btn = QPushButton("Read Status")
        self._status_btn.setToolTip(
            "Query the instrument for current mode and load state."
        )
        self._status_btn.setEnabled(False)
        self._status_btn.clicked.connect(self.status_requested.emit)

        self._state_label = QLabel("—")
        self._state_label.setWordWrap(True)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        input_row.addWidget(self._load_on_btn)
        input_row.addWidget(self._load_off_btn)
        input_row.addWidget(self._status_btn)

        input_widget = QWidget()
        input_widget.setLayout(input_row)

        # ── CH1 live measurement labels ───────────────────────────────
        self._ch1_v_row_lbl = QLabel("Measured Voltage:")
        self._ch1_i_row_lbl = QLabel("Measured Current:")

        self._v_label = QLabel("--- V")
        self._i_label = QLabel("--- A")
        for lbl in (self._v_label, self._i_label):
            lbl.setStyleSheet(
                "font-family: monospace; font-size: 13px; font-weight: bold;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        # ── CH2 live measurement labels (Both mode only) ──────────────
        self._v2_label = QLabel("--- V")
        self._i2_label = QLabel("--- A")
        for lbl in (self._v2_label, self._i2_label):
            lbl.setStyleSheet(
                "font-family: monospace; font-size: 13px; font-weight: bold;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._ch2_group = QGroupBox("CH2 Readings")
        ch2_form = QFormLayout()
        ch2_form.addRow("CH2 Voltage:", self._v2_label)
        ch2_form.addRow("CH2 Current:", self._i2_label)
        self._ch2_group.setLayout(ch2_form)
        self._ch2_group.setVisible(False)

        # ── Operating instructions box ────────────────────────────────
        instr_lbl = QLabel(_INSTRUCTIONS_HTML)
        instr_lbl.setWordWrap(True)
        instr_lbl.setTextFormat(Qt.TextFormat.RichText)
        instr_lbl.setStyleSheet("font-size: 10px; color: #808080; padding: 4px;")

        instr_box = QGroupBox("Operating Instructions")
        instr_layout = QVBoxLayout()
        instr_layout.addWidget(instr_lbl)
        instr_box.setLayout(instr_layout)

        # ── Assemble main form ────────────────────────────────────────
        form = QFormLayout()
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(12)
        form.addRow("Channel:", self._channel_combo)
        form.addRow("─" * 24, QLabel(""))
        form.addRow("Mode:", self._mode_combo)
        form.addRow("Set Value:", self._value_spin)
        form.addRow("", self._apply_btn)
        form.addRow("Status:", self._status_label)
        form.addRow("─" * 24, QLabel(""))
        form.addRow("Load Control:", input_widget)
        form.addRow("State:", self._state_label)
        form.addRow("─" * 24, QLabel(""))
        form.addRow(self._ch1_v_row_lbl, self._v_label)
        form.addRow(self._ch1_i_row_lbl, self._i_label)

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(form)
        layout.addWidget(self._ch2_group)
        layout.addWidget(instr_box)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Private — settings persistence
    # ------------------------------------------------------------------

    def _load_from_settings(self) -> None:
        # Restore channel mode selection
        ch_mode = self._settings.load_channel_mode
        for i, (_, val) in enumerate(_CHANNEL_OPTIONS):
            if val == ch_mode:
                self._channel_combo.blockSignals(True)
                self._channel_combo.setCurrentIndex(i)
                self._channel_combo.blockSignals(False)
                break
        self._update_ch2_visibility()

        # Restore last-used load mode
        mode = self._settings.last_load_mode
        idx = self._mode_combo.findText(mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._update_spinbox_for_mode(mode)

    # ------------------------------------------------------------------
    # Private — event handlers
    # ------------------------------------------------------------------

    def _on_channel_changed(self, index: int) -> None:
        _, val = _CHANNEL_OPTIONS[index]
        self._settings.load_channel_mode = val
        self._settings.save()
        self._update_ch2_visibility()

    def _on_mode_changed(self, mode: str) -> None:
        self._update_spinbox_for_mode(mode)
        self._mark_dirty()

    def _on_value_changed(self, _value: float) -> None:
        self._mark_dirty()

    def _on_apply_clicked(self) -> None:
        mode  = self._mode_combo.currentText()
        value = self._value_spin.value()
        self.settings_applied.emit(mode, value)

    def _mark_dirty(self) -> None:
        """Record that local settings differ from the last successfully applied state."""
        self._dirty = True
        self._status_label.setText(
            "Not applied — click Apply to send to instrument"
        )
        self._status_label.setStyleSheet("color: orange;")
        self._apply_btn.setText("Apply Load Settings")

    # ------------------------------------------------------------------
    # Private — helpers
    # ------------------------------------------------------------------

    def _update_spinbox_for_mode(self, mode: str) -> None:
        unit = _MODE_UNITS.get(mode, "")
        rng  = _MODE_RANGES.get(mode, (0.0, 100.0, 0.001, 0.1))
        self._value_spin.blockSignals(True)
        self._value_spin.setRange(rng[0], rng[1])
        self._value_spin.setSingleStep(rng[3])
        self._value_spin.setSuffix(f" {unit}")
        self._value_spin.blockSignals(False)

    def _update_ch2_visibility(self) -> None:
        """Show the CH2 readings group only in Both-channel mode."""
        is_both = self._settings.load_channel_mode == "both"
        self._ch2_group.setVisible(is_both)
        # Relabel CH1 rows to make clear they show CH1 when both are visible
        prefix = "CH1 " if is_both else "Measured "
        self._ch1_v_row_lbl.setText(f"{prefix}Voltage:")
        self._ch1_i_row_lbl.setText(f"{prefix}Current:")

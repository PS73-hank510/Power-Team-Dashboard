"""Power Supply panel — setpoints and live measured values."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState


_STYLE_OUTPUT_ON = (
    "QPushButton { background-color: #27ae60; color: white; font-weight: bold;"
    " border-radius: 4px; padding: 4px 10px; }"
    "QPushButton:hover { background-color: #2ecc71; }"
    "QPushButton:disabled { background-color: #555; color: #999; }"
)
_STYLE_OUTPUT_OFF = (
    "QPushButton { background-color: #c0392b; color: white; font-weight: bold;"
    " border-radius: 4px; padding: 4px 10px; }"
    "QPushButton:hover { background-color: #e74c3c; }"
    "QPushButton:disabled { background-color: #555; color: #999; }"
)


class PsuPanel(QGroupBox):
    """Panel showing PSU voltage/current setpoints and live measurements.

    Signals:
        setpoint_changed(voltage, current): Emitted when the user clicks
            "Apply Setpoints", requesting the instrument to update its
            voltage and current limit.
        output_requested(on: bool): Emitted when the user clicks the Output
            button.  True → turn output ON, False → turn output OFF.
    """

    setpoint_changed = pyqtSignal(float, float)
    output_requested = pyqtSignal(bool)   # True = ON, False = OFF

    def __init__(self, settings: SettingsManager, index: int = 0, parent=None) -> None:
        title = f"Power Supply {index + 1}" if index > 0 else "Power Supply"
        super().__init__(title, parent)
        self._settings = settings
        self._index = index
        self._output_on: bool = False       # tracks last known output state
        self._build_ui()

    def apply_state(self, state: TestState) -> None:
        """Enable controls when the instrument is reachable; disable otherwise."""
        editable = state in (TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING)
        self._voltage_spin.setEnabled(editable)
        self._current_spin.setEnabled(editable)
        self._apply_btn.setEnabled(editable)
        self._output_btn.setEnabled(editable)

    def set_output_state(self, on: bool) -> None:
        """Sync the Output button appearance to the instrument's actual state."""
        self._output_on = on
        self._refresh_output_btn()

    def update_readings(self, voltage: float, current: float, power: float) -> None:
        """Update the live measurement labels."""
        self._v_label.setText(f"{voltage:.4f} V")
        self._i_label.setText(f"{current:.4f} A")
        self._p_label.setText(f"{power:.4f} W")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Setpoint inputs ──────────────────────────────────────────
        self._voltage_spin = QDoubleSpinBox()
        self._voltage_spin.setRange(0.0, 1000.0)
        self._voltage_spin.setSuffix(" V")
        self._voltage_spin.setDecimals(3)
        self._voltage_spin.setSingleStep(0.1)
        self._voltage_spin.setEnabled(False)

        self._current_spin = QDoubleSpinBox()
        self._current_spin.setRange(0.0, 100.0)
        self._current_spin.setSuffix(" A")
        self._current_spin.setDecimals(3)
        self._current_spin.setSingleStep(0.01)
        self._current_spin.setEnabled(False)

        # Apply button — sends V + I to the instrument in one shot
        self._apply_btn = QPushButton("Apply Setpoints")
        self._apply_btn.setToolTip(
            "Send the voltage and current limit to the power supply now."
        )
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply_clicked)

        # Output toggle button
        self._output_btn = QPushButton()
        self._output_btn.setToolTip("Toggle the PSU output on or off.")
        self._output_btn.setEnabled(False)
        self._output_btn.setMinimumWidth(130)
        self._output_btn.clicked.connect(self._on_output_clicked)
        self._refresh_output_btn()  # set initial label + style

        # ── Live measurement labels ──────────────────────────────────
        self._v_label = QLabel("--- V")
        self._i_label = QLabel("--- A")
        self._p_label = QLabel("--- W")
        for lbl in (self._v_label, self._i_label, self._p_label):
            lbl.setStyleSheet(
                "font-family: monospace; font-size: 13px; font-weight: bold;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        # ── Layout ───────────────────────────────────────────────────
        form = QFormLayout()
        form.addRow("Voltage Setpoint:", self._voltage_spin)
        form.addRow("Current Limit:", self._current_spin)

        form.addRow("─" * 20, QLabel(""))
        form.addRow("Measured Voltage:", self._v_label)
        form.addRow("Measured Current:", self._i_label)
        form.addRow("Measured Power:", self._p_label)

        # Buttons side by side at the bottom
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._output_btn)
        btn_row.addWidget(self._apply_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _refresh_output_btn(self) -> None:
        """Update the Output button label and colour to match self._output_on."""
        if self._output_on:
            self._output_btn.setText("⏻  Output ON")
            self._output_btn.setStyleSheet(_STYLE_OUTPUT_ON)
            self._output_btn.setToolTip("Output is ON — click to turn it OFF.")
        else:
            self._output_btn.setText("⏻  Output OFF")
            self._output_btn.setStyleSheet(_STYLE_OUTPUT_OFF)
            self._output_btn.setToolTip("Output is OFF — click to turn it ON.")

    def _on_apply_clicked(self) -> None:
        """Emit setpoint_changed with the current spinbox values."""
        self.setpoint_changed.emit(
            self._voltage_spin.value(), self._current_spin.value()
        )

    def _on_output_clicked(self) -> None:
        """Toggle output state and emit output_requested."""
        self._output_on = not self._output_on
        self._refresh_output_btn()
        self.output_requested.emit(self._output_on)

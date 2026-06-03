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


class PsuPanel(QGroupBox):
    """Panel showing PSU voltage/current setpoints and live measurements.

    Signals:
        setpoint_changed(voltage, current): Emitted when the user clicks
            "Apply Setpoints", requesting the instrument to update its
            voltage and current limit.
    """

    setpoint_changed = pyqtSignal(float, float)

    def __init__(self, settings: SettingsManager, index: int = 0, parent=None) -> None:
        title = f"Power Supply {index + 1}" if index > 0 else "Power Supply"
        super().__init__(title, parent)
        self._settings = settings
        self._index = index
        self._build_ui()

    def apply_state(self, state: TestState) -> None:
        """Enable setpoint controls when connected; disable otherwise."""
        editable = state in (TestState.CONNECTED, TestState.STOPPED, TestState.RUNNING)
        # Allow editing setpoints any time the instrument is reachable.
        # (Main window guards against sending during DISCONNECTED/RUNNING
        #  via its own state checks.)
        self._voltage_spin.setEnabled(editable)
        self._current_spin.setEnabled(editable)
        self._apply_btn.setEnabled(editable)

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
        self._voltage_spin.setEnabled(False)  # disabled until connected

        self._current_spin = QDoubleSpinBox()
        self._current_spin.setRange(0.0, 100.0)
        self._current_spin.setSuffix(" A")
        self._current_spin.setDecimals(3)
        self._current_spin.setSingleStep(0.01)
        self._current_spin.setEnabled(False)  # disabled until connected

        # Apply button — sends V + I to the instrument in one shot
        self._apply_btn = QPushButton("Apply Setpoints")
        self._apply_btn.setToolTip(
            "Send the voltage and current limit to the power supply now."
        )
        self._apply_btn.setEnabled(False)     # disabled until connected
        self._apply_btn.clicked.connect(self._on_apply_clicked)

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

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._apply_btn)

        form.addRow("─" * 20, QLabel(""))
        form.addRow("Measured Voltage:", self._v_label)
        form.addRow("Measured Current:", self._i_label)
        form.addRow("Measured Power:", self._p_label)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _on_apply_clicked(self) -> None:
        """Emit setpoint_changed with the current spinbox values."""
        self.setpoint_changed.emit(
            self._voltage_spin.value(), self._current_spin.value()
        )

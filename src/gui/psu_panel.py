"""Power Supply panel — setpoints and live measured values."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState


class PsuPanel(QGroupBox):
    """Panel showing PSU voltage/current setpoints and live measurements.

    Signals:
        setpoint_changed(voltage, current): User changed a setpoint value.
    """

    setpoint_changed = pyqtSignal(float, float)

    def __init__(self, settings: SettingsManager, index: int = 0, parent=None) -> None:
        title = f"Power Supply {index + 1}" if index > 0 else "Power Supply"
        super().__init__(title, parent)
        self._settings = settings
        self._index = index
        self._build_ui()

    def apply_state(self, state: TestState) -> None:
        """Lock setpoint inputs during RUNNING state."""
        locked = state == TestState.RUNNING
        self._voltage_spin.setEnabled(not locked)
        self._current_spin.setEnabled(not locked)

    def update_readings(self, voltage: float, current: float, power: float) -> None:
        """Update the live measurement labels."""
        self._v_label.setText(f"{voltage:.4f} V")
        self._i_label.setText(f"{current:.4f} A")
        self._p_label.setText(f"{power:.4f} W")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Setpoint inputs
        self._voltage_spin = QDoubleSpinBox()
        self._voltage_spin.setRange(0.0, 1000.0)
        self._voltage_spin.setSuffix(" V")
        self._voltage_spin.setDecimals(3)
        self._voltage_spin.setSingleStep(0.1)
        self._voltage_spin.valueChanged.connect(self._on_setpoint_changed)

        self._current_spin = QDoubleSpinBox()
        self._current_spin.setRange(0.0, 100.0)
        self._current_spin.setSuffix(" A")
        self._current_spin.setDecimals(3)
        self._current_spin.setSingleStep(0.01)
        self._current_spin.valueChanged.connect(self._on_setpoint_changed)

        # Live measurement labels
        self._v_label = QLabel("--- V")
        self._i_label = QLabel("--- A")
        self._p_label = QLabel("--- W")
        for lbl in (self._v_label, self._i_label, self._p_label):
            lbl.setStyleSheet("font-family: monospace; font-size: 13px; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        form = QFormLayout()
        form.addRow("Voltage Setpoint:", self._voltage_spin)
        form.addRow("Current Limit:", self._current_spin)
        form.addRow("─" * 20, QLabel(""))
        form.addRow("Measured Voltage:", self._v_label)
        form.addRow("Measured Current:", self._i_label)
        form.addRow("Measured Power:", self._p_label)

        layout = QVBoxLayout()
        layout.addLayout(form)
        self.setLayout(layout)

    def _on_setpoint_changed(self) -> None:
        self.setpoint_changed.emit(
            self._voltage_spin.value(), self._current_spin.value()
        )

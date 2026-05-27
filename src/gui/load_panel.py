"""Electronic Load panel — mode selector, setpoint, and live measurements."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState
from src.instruments.electronic_load import ElectronicLoad, LOAD_MODES

# Units for each mode's setpoint
_MODE_UNITS = {"CC": "A", "CV": "V", "CR": "Ω", "CP": "W"}
_MODE_RANGES = {
    "CC": (0.0, 100.0, 0.001, 0.01),    # min, max, decimals as step, step
    "CV": (0.0, 1000.0, 0.001, 0.1),
    "CR": (0.0, 10000.0, 0.001, 1.0),
    "CP": (0.0, 10000.0, 0.001, 1.0),
}


class LoadPanel(QGroupBox):
    """Panel for controlling the electronic load mode and setpoint.

    Signals:
        mode_changed(mode, value):  User changed the mode or setpoint.
    """

    mode_changed = pyqtSignal(str, float)

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__("Electronic Load", parent)
        self._settings = settings
        self._build_ui()
        self._load_from_settings()

    def apply_state(self, state: TestState) -> None:
        """Lock controls during RUNNING state."""
        locked = state == TestState.RUNNING
        self._mode_combo.setEnabled(not locked)
        self._value_spin.setEnabled(not locked)

    def update_readings(self, voltage: float, current: float) -> None:
        """Update live measurement labels."""
        self._v_label.setText(f"{voltage:.4f} V")
        self._i_label.setText(f"{current:.4f} A")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._mode_combo = QComboBox()
        for mode in LOAD_MODES:
            self._mode_combo.addItem(mode)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)

        self._value_spin = QDoubleSpinBox()
        self._value_spin.setDecimals(3)
        self._value_spin.valueChanged.connect(self._on_value_changed)

        self._v_label = QLabel("--- V")
        self._i_label = QLabel("--- A")
        for lbl in (self._v_label, self._i_label):
            lbl.setStyleSheet("font-family: monospace; font-size: 13px; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        form = QFormLayout()
        form.addRow("Mode:", self._mode_combo)
        form.addRow("Set Value:", self._value_spin)
        form.addRow("─" * 20, QLabel(""))
        form.addRow("Measured Voltage:", self._v_label)
        form.addRow("Measured Current:", self._i_label)

        layout = QVBoxLayout()
        layout.addLayout(form)
        self.setLayout(layout)

    def _load_from_settings(self) -> None:
        mode = self._settings.last_load_mode
        idx = self._mode_combo.findText(mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._update_spinbox_for_mode(mode)

    def _on_mode_changed(self, mode: str) -> None:
        self._update_spinbox_for_mode(mode)
        self._settings.last_load_mode = mode
        self._settings.save()
        self.mode_changed.emit(mode, self._value_spin.value())

    def _on_value_changed(self, value: float) -> None:
        mode = self._mode_combo.currentText()
        self._settings.save()
        self.mode_changed.emit(mode, value)

    def _update_spinbox_for_mode(self, mode: str) -> None:
        unit = _MODE_UNITS.get(mode, "")
        rng = _MODE_RANGES.get(mode, (0.0, 100.0, 0.001, 0.1))
        self._value_spin.blockSignals(True)
        self._value_spin.setRange(rng[0], rng[1])
        self._value_spin.setSingleStep(rng[3])
        self._value_spin.setSuffix(f" {unit}")
        self._value_spin.blockSignals(False)

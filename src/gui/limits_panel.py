"""Limits panel — per-parameter upper and lower limit configuration."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
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
from src.core.models import LimitPair, TestState

# Parameters exposed in the limits panel
# (display_label, settings_key)
_PARAMETERS = [
    ("PSU Voltage (V):", "PSU_voltage"),
    ("PSU Current (A):", "PSU_current"),
    ("PSU Power (W):", "PSU_power"),
    ("Load Voltage (V):", "LOAD_voltage"),
    ("Load Current (A):", "LOAD_current"),
]

_UNSET = -1e9  # sentinel: spin value at this = None (disabled)
_MAX_VAL = 1e6


class _LimitRow(QWidget):
    """One row: Min label + spin + Max label + spin for a single parameter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._min_spin = self._make_spin()
        self._max_spin = self._make_spin()

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Min:"))
        layout.addWidget(self._min_spin, 1)
        layout.addWidget(QLabel("Max:"))
        layout.addWidget(self._max_spin, 1)
        self.setLayout(layout)

    def set_values(self, pair: Optional[LimitPair]) -> None:
        if pair is None:
            self._min_spin.setValue(_UNSET)
            self._max_spin.setValue(_UNSET)
        else:
            self._min_spin.setValue(pair.min if pair.min is not None else _UNSET)
            self._max_spin.setValue(pair.max if pair.max is not None else _UNSET)

    def get_pair(self) -> LimitPair:
        min_v = None if self._min_spin.value() <= _UNSET + 1 else self._min_spin.value()
        max_v = None if self._max_spin.value() <= _UNSET + 1 else self._max_spin.value()
        return LimitPair(min=min_v, max=max_v)

    def set_enabled_all(self, enabled: bool) -> None:
        self._min_spin.setEnabled(enabled)
        self._max_spin.setEnabled(enabled)

    @staticmethod
    def _make_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(_UNSET, _MAX_VAL)
        spin.setDecimals(3)
        spin.setSingleStep(0.1)
        spin.setSpecialValueText("(off)")  # shown when value == minimum
        spin.setValue(_UNSET)
        spin.setMinimumWidth(80)
        return spin


class LimitsPanel(QGroupBox):
    """Panel for configuring upper and lower safety limits.

    Signals:
        limits_applied(dict):  Emitted when the user clicks Apply Limits.
                               Value is dict[str, LimitPair].
    """

    limits_applied = pyqtSignal(object)

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__("Safety Limits", parent)
        self._settings = settings
        self._rows: dict[str, _LimitRow] = {}
        self._build_ui()
        self._load_from_settings()

    def apply_state(self, state: TestState) -> None:
        """Lock all limit inputs and Apply button during RUNNING state."""
        locked = state == TestState.RUNNING
        for row in self._rows.values():
            row.set_enabled_all(not locked)
        self._apply_button.setEnabled(not locked)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        form = QFormLayout()
        form.setHorizontalSpacing(8)

        for label, key in _PARAMETERS:
            row = _LimitRow()
            self._rows[key] = row
            form.addRow(label, row)

        self._apply_button = QPushButton("Apply Limits")
        self._apply_button.setStyleSheet(
            "QPushButton { background-color: #6f42c1; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #5a32a3; }"
        )
        self._apply_button.clicked.connect(self._on_apply_clicked)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self._apply_button)
        self.setLayout(layout)

    def _load_from_settings(self) -> None:
        for key, row in self._rows.items():
            pair = self._settings.limits.get(key)
            row.set_values(pair)

    def _on_apply_clicked(self) -> None:
        limits: dict[str, LimitPair] = {}
        for key, row in self._rows.items():
            pair = row.get_pair()
            if pair.has_any():
                limits[key] = pair
        self.limits_applied.emit(limits)

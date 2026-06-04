"""Limits panel — per-parameter upper and lower limit configuration.

Displayed as a compact horizontal strip at the top of the right column so
all five parameters are visible simultaneously without taking vertical space.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import LimitPair, TestState

# Parameters exposed in the limits panel
# (display_label, settings_key)
_PARAMETERS = [
    ("PSU Voltage (V)", "PSU_voltage"),
    ("PSU Current (A)", "PSU_current"),
    ("PSU Power (W)",   "PSU_power"),
    ("Load Voltage (V)", "LOAD_voltage"),
    ("Load Current (A)", "LOAD_current"),
]

_UNSET = -1e9  # sentinel: spin value at this = None (disabled)
_MAX_VAL = 1e6


class _LimitRow(QWidget):
    """Logical container for one parameter's Min/Max spinboxes.

    The widget itself is not added to any layout — its two spinboxes are
    placed directly into the parent grid.  The class is kept as a container
    so that set_values / get_pair / set_enabled_all work unchanged.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.min_spin = self._make_spin()
        self.max_spin = self._make_spin()
        # Keep a hidden layout so Qt ownership is clear
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.min_spin)
        layout.addWidget(self.max_spin)
        self.setLayout(layout)

    def set_values(self, pair: Optional[LimitPair]) -> None:
        if pair is None:
            self.min_spin.setValue(_UNSET)
            self.max_spin.setValue(_UNSET)
        else:
            self.min_spin.setValue(pair.min if pair.min is not None else _UNSET)
            self.max_spin.setValue(pair.max if pair.max is not None else _UNSET)

    def get_pair(self) -> LimitPair:
        min_v = None if self.min_spin.value() <= _UNSET + 1 else self.min_spin.value()
        max_v = None if self.max_spin.value() <= _UNSET + 1 else self.max_spin.value()
        return LimitPair(min=min_v, max=max_v)

    def set_enabled_all(self, enabled: bool) -> None:
        self.min_spin.setEnabled(enabled)
        self.max_spin.setEnabled(enabled)

    @staticmethod
    def _make_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(_UNSET, _MAX_VAL)
        spin.setDecimals(3)
        spin.setSingleStep(0.1)
        spin.setSpecialValueText("(off)")  # shown when value == minimum
        spin.setValue(_UNSET)
        spin.setMinimumWidth(68)
        spin.setMaximumWidth(90)
        return spin


class LimitsPanel(QGroupBox):
    """Compact horizontal safety-limits bar.

    Five parameters (PSU V / A / W, Load V / A) each with a Min and Max
    spinbox, arranged side by side so the bar fits in a single compact strip
    at the top of the monitoring area.

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
        """Build a compact horizontal grid layout.

        Layout (one row of columns):
            [PSU Volt (V)]   [PSU Curr (A)]   [PSU Power (W)]   [Load Volt (V)]  [Load Curr (A)]   [Apply]
            Min:(off) Max:(off)  ...
        """
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        grid.setContentsMargins(6, 4, 6, 4)

        for col_idx, (label, key) in enumerate(_PARAMETERS):
            row_widget = _LimitRow()
            self._rows[key] = row_widget

            # Parameter name header
            hdr = QLabel(label)
            hdr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            hdr.setStyleSheet("font-size: 10px; font-weight: bold;")
            grid.addWidget(hdr, 0, col_idx * 3)
            grid.setColumnStretch(col_idx * 3, 1)

            # "Min" / "Max" sub-labels + spinboxes inline
            min_lbl = QLabel("Min")
            min_lbl.setStyleSheet("font-size: 9px; color: #aaa;")
            min_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            max_lbl = QLabel("Max")
            max_lbl.setStyleSheet("font-size: 9px; color: #aaa;")
            max_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Use a sub-widget so the two spins stay together
            sub = QWidget()
            sub_layout = QHBoxLayout()
            sub_layout.setContentsMargins(0, 0, 0, 0)
            sub_layout.setSpacing(3)
            sub_layout.addWidget(min_lbl)
            sub_layout.addWidget(row_widget.min_spin, 1)
            sub_layout.addWidget(max_lbl)
            sub_layout.addWidget(row_widget.max_spin, 1)
            sub.setLayout(sub_layout)

            grid.addWidget(sub, 1, col_idx * 3)

            # Thin vertical separator between parameters (except after last)
            if col_idx < len(_PARAMETERS) - 1:
                sep_col = col_idx * 3 + 1
                sep = QLabel("|")
                sep.setStyleSheet("color: #555;")
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(sep, 0, sep_col, 2, 1)  # spans both rows
                grid.setColumnStretch(sep_col, 0)

        # Apply button — spans both grid rows, rightmost column
        apply_col = len(_PARAMETERS) * 3 - 1
        self._apply_button = QPushButton("Apply\nLimits")
        self._apply_button.setMinimumWidth(76)
        self._apply_button.setMinimumHeight(44)
        self._apply_button.setStyleSheet(
            "QPushButton { background-color: #6f42c1; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #5a32a3; }"
        )
        self._apply_button.clicked.connect(self._on_apply_clicked)
        grid.addWidget(self._apply_button, 0, apply_col, 2, 1)

        self.setLayout(grid)

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

"""Connection panel — VISA resource string inputs and instrument scanning."""

from __future__ import annotations

import pyvisa
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState


class ConnectionPanel(QGroupBox):
    """Panel for configuring and opening VISA connections.

    Signals:
        connect_requested(psu_visa, load_visa):  User clicked Connect.
        disconnect_requested():                   User clicked Disconnect.
    """

    connect_requested = pyqtSignal(str, str)
    disconnect_requested = pyqtSignal()

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__("Connection", parent)
        self._settings = settings
        self._build_ui()
        self._load_from_settings()

    def apply_state(self, state: TestState) -> None:
        """Enable/disable widgets based on test state."""
        locked = state == TestState.RUNNING
        can_connect = state == TestState.DISCONNECTED
        can_disconnect = state in (TestState.CONNECTED, TestState.STOPPED)

        self._psu_field.setEnabled(not locked and can_connect)
        self._load_field.setEnabled(not locked and can_connect)
        self._scan_button.setEnabled(not locked and can_connect)
        self._connect_button.setEnabled(can_connect and not locked)
        self._disconnect_button.setEnabled(can_disconnect and not locked)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # PSU row
        self._psu_field = QLineEdit()
        self._psu_field.setPlaceholderText("e.g. USB0::0x0957::0x2C07::MY12345::INSTR")
        self._psu_field.editingFinished.connect(self._save_to_settings)

        # Load row
        self._load_field = QLineEdit()
        self._load_field.setPlaceholderText("e.g. USB0::0x2A45::0x0040::SN67890::INSTR")
        self._load_field.editingFinished.connect(self._save_to_settings)

        # Scan dropdown
        self._scan_combo = QComboBox()
        self._scan_combo.setMinimumWidth(260)
        self._scan_combo.currentTextChanged.connect(self._on_scan_selection)

        self._scan_button = QPushButton("Scan for Instruments")
        self._scan_button.clicked.connect(self._scan_instruments)

        scan_row = QHBoxLayout()
        scan_row.addWidget(self._scan_button)
        scan_row.addWidget(self._scan_combo, 1)

        # Connect / Disconnect buttons
        self._connect_button = QPushButton("Connect")
        self._connect_button.setStyleSheet(
            "QPushButton { background-color: #17a2b8; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #138496; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self._connect_button.clicked.connect(self._on_connect_clicked)

        self._disconnect_button = QPushButton("Disconnect")
        self._disconnect_button.setEnabled(False)
        self._disconnect_button.clicked.connect(self.disconnect_requested)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._connect_button)
        btn_row.addWidget(self._disconnect_button)
        btn_row.addStretch()

        form = QFormLayout()
        form.addRow("PSU VISA:", self._psu_field)
        form.addRow("Load VISA:", self._load_field)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(scan_row)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _load_from_settings(self) -> None:
        self._psu_field.setText(self._settings.psu_visa_string)
        self._load_field.setText(self._settings.load_visa_string)

    def _save_to_settings(self) -> None:
        self._settings.psu_visa_string = self._psu_field.text().strip()
        self._settings.load_visa_string = self._load_field.text().strip()
        self._settings.save()

    def _scan_instruments(self) -> None:
        """Populate dropdown with available VISA resources."""
        self._scan_combo.clear()
        try:
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()
            if resources:
                for r in resources:
                    self._scan_combo.addItem(r)
            else:
                self._scan_combo.addItem("(no instruments found)")
        except Exception as exc:
            self._scan_combo.addItem(f"(scan error: {exc})")

    def _on_scan_selection(self, text: str) -> None:
        """When user picks a scanned resource, offer to paste into active field."""
        if text.startswith("(") or not text:
            return
        # Paste into whichever field is focused, or PSU by default
        if self._load_field.hasFocus():
            self._load_field.setText(text)
        else:
            self._psu_field.setText(text)
        self._save_to_settings()

    def _on_connect_clicked(self) -> None:
        psu = self._psu_field.text().strip()
        load = self._load_field.text().strip()
        self.connect_requested.emit(psu, load)

"""Connection panel — dynamic VISA resource string inputs and scanning.

Supports variable numbers of power supplies and loads.
An optional "No load" checkbox enables PSU-only testing.
"""

from __future__ import annotations

import pyvisa
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState


class ConnectionPanel(QGroupBox):
    """Panel for configuring and opening VISA connections.

    Allows the user to add/remove VISA string rows for any number of
    power supplies and loads.  An empty load list is allowed for PSU-only
    testing.

    Signals:
        connect_requested(psu_visas, load_visas):
            User clicked Connect.  psu_visas is a list of non-empty VISA
            strings; load_visas is a (possibly empty) list.
        disconnect_requested():
            User clicked Disconnect.
    """

    connect_requested = pyqtSignal(list, list)  # (psu_visas, load_visas)
    disconnect_requested = pyqtSignal()

    # Each row entry: (container_widget, number_label, visa_field)
    _RowEntry = tuple  # (QWidget, QLabel, QLineEdit)

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__("Connection", parent)
        self._settings = settings
        self._psu_rows: list[ConnectionPanel._RowEntry] = []
        self._load_rows: list[ConnectionPanel._RowEntry] = []
        self._build_ui()
        self._load_from_settings()

    def apply_state(self, state: TestState) -> None:
        """Enable/disable widgets based on test state."""
        locked = state == TestState.RUNNING
        can_connect = state == TestState.DISCONNECTED
        can_disconnect = state in (TestState.CONNECTED, TestState.STOPPED)

        for _, _, field in self._psu_rows:
            field.setEnabled(not locked and can_connect)
        for _, _, field in self._load_rows:
            field.setEnabled(not locked and can_connect)

        self._no_load_check.setEnabled(not locked and can_connect)
        self._scan_button.setEnabled(not locked and can_connect)
        self._add_psu_btn.setEnabled(not locked and can_connect)
        no_load = self._no_load_check.isChecked()
        self._add_load_btn.setEnabled(not locked and can_connect and not no_load)
        self._connect_button.setEnabled(can_connect and not locked)
        self._disconnect_button.setEnabled(can_disconnect and not locked)

    # ------------------------------------------------------------------
    # Private — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Scan row ──────────────────────────────────────────────────
        self._scan_combo = QComboBox()
        self._scan_combo.setMinimumWidth(240)
        self._scan_combo.currentTextChanged.connect(self._on_scan_selection)
        self._scan_button = QPushButton("Scan for Instruments")
        self._scan_button.clicked.connect(self._scan_instruments)
        scan_row = QHBoxLayout()
        scan_row.addWidget(self._scan_button)
        scan_row.addWidget(self._scan_combo, 1)

        # ── PSU section ───────────────────────────────────────────────
        psu_header = QHBoxLayout()
        psu_header.addWidget(QLabel("<b>Power Supplies</b>"))
        psu_header.addStretch()
        self._add_psu_btn = QPushButton("+ Add PSU")
        self._add_psu_btn.setFixedWidth(90)
        self._add_psu_btn.clicked.connect(lambda: self._add_psu_row())
        psu_header.addWidget(self._add_psu_btn)

        self._psu_container = QWidget()
        self._psu_layout = QVBoxLayout()
        self._psu_layout.setContentsMargins(0, 0, 0, 0)
        self._psu_layout.setSpacing(2)
        self._psu_container.setLayout(self._psu_layout)

        # ── Load section ──────────────────────────────────────────────
        load_header = QHBoxLayout()
        load_header.addWidget(QLabel("<b>Electronic Loads</b>"))
        load_header.addStretch()
        self._add_load_btn = QPushButton("+ Add Load")
        self._add_load_btn.setFixedWidth(90)
        self._add_load_btn.clicked.connect(lambda: self._add_load_row())
        load_header.addWidget(self._add_load_btn)

        self._no_load_check = QCheckBox("No load (PSU-only test)")
        self._no_load_check.toggled.connect(self._on_no_load_toggled)

        self._load_container = QWidget()
        self._load_layout = QVBoxLayout()
        self._load_layout.setContentsMargins(0, 0, 0, 0)
        self._load_layout.setSpacing(2)
        self._load_container.setLayout(self._load_layout)

        # ── Connect / Disconnect buttons ──────────────────────────────
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

        # ── Assemble ──────────────────────────────────────────────────
        layout = QVBoxLayout()
        layout.addLayout(scan_row)
        layout.addLayout(psu_header)
        layout.addWidget(self._psu_container)
        layout.addLayout(load_header)
        layout.addWidget(self._no_load_check)
        layout.addWidget(self._load_container)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Private — row management
    # ------------------------------------------------------------------

    def _make_row(
        self,
        label_text: str,
        placeholder: str,
        visa_str: str,
    ) -> tuple:
        """Create a VISA input row widget. Returns (row_widget, label, field, remove_btn)."""
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(label_text)
        label.setFixedWidth(52)

        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setText(visa_str)
        field.editingFinished.connect(self._save_to_settings)

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(28)
        remove_btn.setToolTip("Remove this row")

        row_layout.addWidget(label)
        row_layout.addWidget(field, 1)
        row_layout.addWidget(remove_btn)
        row_widget.setLayout(row_layout)

        return row_widget, label, field, remove_btn

    def _add_psu_row(self, visa_str: str = "") -> None:
        """Append a PSU VISA string row."""
        self._add_row(
            self._psu_rows, self._psu_layout, "PSU",
            "e.g. USB0::0x0957::0x2C07::MY12345::INSTR",
            visa_str, self._remove_psu_row,
        )

    def _remove_psu_row(self, row_widget: QWidget, field: QLineEdit) -> None:
        """Remove a PSU row. At least one PSU row is always kept."""
        self._remove_row(self._psu_rows, self._psu_layout, "PSU", row_widget, min_rows=1)

    def _add_load_row(self, visa_str: str = "") -> None:
        """Append a Load VISA string row."""
        self._add_row(
            self._load_rows, self._load_layout, "Load",
            "e.g. USB0::0x2A45::0x0040::SN67890::INSTR",
            visa_str, self._remove_load_row,
        )

    def _remove_load_row(self, row_widget: QWidget, field: QLineEdit) -> None:
        """Remove a Load row. Removing the last row is allowed (PSU-only)."""
        self._remove_row(self._load_rows, self._load_layout, "Load", row_widget)

    def _add_row(
        self,
        rows: list,
        layout: "QVBoxLayout",
        kind: str,
        placeholder: str,
        visa_str: str,
        remover,
    ) -> None:
        """Shared helper: create a VISA input row, append it, and wire its remove button."""
        idx = len(rows)
        row_widget, label, field, remove_btn = self._make_row(
            f"{kind} {idx + 1}:", placeholder, visa_str
        )
        rows.append((row_widget, label, field))
        layout.addWidget(row_widget)
        remove_btn.clicked.connect(
            lambda _checked=False, rw=row_widget, f=field: remover(rw, f)
        )

    def _remove_row(
        self,
        rows: list,
        layout: "QVBoxLayout",
        kind: str,
        row_widget: QWidget,
        min_rows: int = 0,
    ) -> None:
        """Shared helper: remove a VISA input row and renumber the remaining ones."""
        if len(rows) <= min_rows:
            return
        idx = next((i for i, (rw, _, _) in enumerate(rows) if rw is row_widget), -1)
        if idx < 0:
            return
        rows.pop(idx)
        layout.removeWidget(row_widget)
        row_widget.hide()
        row_widget.deleteLater()
        self._relabel(rows, kind)
        self._save_to_settings()

    @staticmethod
    def _relabel(rows: list, kind: str) -> None:
        """Renumber the label column after adding or removing a row."""
        for i, (_, label, _) in enumerate(rows):
            label.setText(f"{kind} {i + 1}:")

    # ------------------------------------------------------------------
    # Private — settings persistence
    # ------------------------------------------------------------------

    def _load_from_settings(self) -> None:
        """Populate rows from saved settings."""
        psu_visas = self._settings.psu_visa_strings or [""]
        for visa in psu_visas:
            self._add_psu_row(visa)

        load_visas = self._settings.load_visa_strings or [""]
        for visa in load_visas:
            self._add_load_row(visa)

        # Restore no-load mode without triggering _on_no_load_toggled (which would
        # call _save_to_settings and potentially overwrite load VISA strings)
        if self._settings.no_load_mode:
            self._no_load_check.blockSignals(True)
            self._no_load_check.setChecked(True)
            self._no_load_check.blockSignals(False)
            self._load_container.setVisible(False)
            self._add_load_btn.setEnabled(False)

    def _save_to_settings(self) -> None:
        self._settings.psu_visa_strings = [
            f.text().strip() for _, _, f in self._psu_rows
        ]
        # Always persist load row values regardless of no-load mode, so that
        # VISA strings survive across no-load toggle on/off and app restarts.
        # The no_load_mode flag separately records whether PSU-only is active.
        self._settings.load_visa_strings = [
            f.text().strip() for _, _, f in self._load_rows
        ]
        self._settings.no_load_mode = self._no_load_check.isChecked()
        self._settings.save()

    def _on_no_load_toggled(self, checked: bool) -> None:
        self._load_container.setVisible(not checked)
        self._add_load_btn.setEnabled(not checked)
        # If user unchecks "No load" and there are no rows yet, add a blank one
        if not checked and not self._load_rows:
            self._add_load_row("")
        self._save_to_settings()

    # ------------------------------------------------------------------
    # Private — scan and connect
    # ------------------------------------------------------------------

    def _scan_instruments(self) -> None:
        """Populate the dropdown with available VISA resources."""
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
        """When the user picks a scanned resource, paste it into the focused field."""
        if text.startswith("(") or not text:
            return
        # Find whichever field has keyboard focus
        focused_field = None
        for _, _, f in list(self._psu_rows) + list(self._load_rows):
            if f.hasFocus():
                focused_field = f
                break
        if focused_field:
            focused_field.setText(text)
        elif self._psu_rows:
            self._psu_rows[0][2].setText(text)
        self._save_to_settings()

    def _on_connect_clicked(self) -> None:
        psu_visas = [
            f.text().strip()
            for _, _, f in self._psu_rows
            if f.text().strip()
        ]
        if self._no_load_check.isChecked():
            load_visas: list[str] = []
        else:
            load_visas = [
                f.text().strip()
                for _, _, f in self._load_rows
                if f.text().strip()
            ]

        # Warn if blank PSU rows were silently skipped
        blank_psus = len(self._psu_rows) - len(psu_visas)
        if psu_visas and blank_psus > 0:
            QMessageBox.warning(
                self, "Blank PSU Rows",
                f"{blank_psus} PSU row(s) had no address and will be skipped.\n"
                f"Connecting to {len(psu_visas)} PSU(s).",
            )

        self.connect_requested.emit(psu_visas, load_visas)

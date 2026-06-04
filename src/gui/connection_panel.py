"""Connection panel — dynamic VISA resource string inputs and scanning.

Supports variable numbers of power supplies and loads.
Each row uses an editable combo box that auto-populates with detected serial
COM ports (shown as "COM3 → ASRL3::INSTR") and previously used addresses.
An optional "No load" checkbox enables PSU-only testing.
"""

from __future__ import annotations

import logging
import re

import pyvisa
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.settings_manager import SettingsManager
from src.core.models import TestState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — COM ↔ ASRL conversion
# ---------------------------------------------------------------------------

def _com_to_asrl(device: str) -> str | None:
    """Convert "COM3" → "ASRL3::INSTR".  Returns None if not a COM port."""
    m = re.match(r"COM(\d+)$", device.strip(), re.IGNORECASE)
    return f"ASRL{m.group(1)}::INSTR" if m else None


def _asrl_to_com(visa: str) -> str | None:
    """Convert "ASRL3::INSTR" → "COM3".  Returns None if not an ASRL string."""
    m = re.match(r"ASRL(\d+)::INSTR$", visa.strip(), re.IGNORECASE)
    return f"COM{m.group(1)}" if m else None


def _visa_display(visa: str) -> str:
    """Return a human-friendly display string for a VISA resource.

    ASRL/COM addresses are shown as "COM3  →  ASRL3::INSTR".
    USB-TMC / GPIB / LAN addresses are shown as-is.
    """
    com = _asrl_to_com(visa)
    return f"{com}  →  {visa}" if com else visa


def _detect_com_ports() -> list[tuple[str, str, str]]:
    """Return [(device, visa_string, description), …] for all detected COM ports.

    Uses ``serial.tools.list_ports``.  Returns [] when pyserial is unavailable
    or no COM ports are present.
    """
    try:
        from serial.tools import list_ports  # type: ignore
        result: list[tuple[str, str, str]] = []
        for port in list_ports.comports():
            visa = _com_to_asrl(port.device)
            if visa is None:
                continue
            desc = port.description or ""
            # Strip the "(COMx)" suffix that pyserial sometimes appends to desc
            desc = re.sub(r"\s*\(COM\d+\)\s*$", "", desc, flags=re.IGNORECASE).strip()
            result.append((port.device, visa, desc))
        # Sort numerically by COM number
        result.sort(key=lambda t: int(re.search(r"\d+", t[0]).group() or "0"))
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# VisaComboBox — editable combo that maps friendly labels to VISA strings
# ---------------------------------------------------------------------------

class _VisaCombo(QComboBox):
    """Editable combo for VISA resource strings.

    Each item stores the plain VISA string as ``Qt.ItemDataRole.UserRole``
    data while displaying a friendlier label (e.g. "COM3  →  ASRL3::INSTR").
    When the user types text directly that isn't matched to an item, the raw
    text is normalised (COM→ASRL conversion applied) and used as-is.
    """

    def current_visa(self) -> str:
        """Return the VISA string for the current combo state."""
        # Prefer the item data when a list item is selected
        data = self.currentData(Qt.ItemDataRole.UserRole)
        if data and isinstance(data, str):
            return data
        # Free-text input — normalise COM→ASRL
        text = self.currentText().strip()
        asrl = _com_to_asrl(text)
        return asrl if asrl else text

    def set_visa(self, visa: str) -> None:
        """Select the item whose UserRole data matches visa, else set free text."""
        for i in range(self.count()):
            if self.itemData(i, Qt.ItemDataRole.UserRole) == visa:
                self.setCurrentIndex(i)
                return
        # Not in list — show the friendly form as free text
        com = _asrl_to_com(visa)
        self.setCurrentText(com if com else visa)

    def refresh(
        self,
        com_ports: list[tuple[str, str, str]],
        extra_visas: list[str],
    ) -> None:
        """Repopulate items from detected COM ports and extra (saved) VISA strings.

        The currently selected VISA string is preserved across the refresh.
        """
        current = self.current_visa()
        self.blockSignals(True)
        self.clear()

        seen: set[str] = set()

        # ── Detected COM ports first ───────────────────────────────────
        for device, visa, desc in com_ports:
            label = f"{device}  →  {visa}"
            if desc:
                label += f"   ({desc})"
            self.addItem(label, userData=visa)
            seen.add(visa)

        # ── Previously used addresses not already listed ───────────────
        for visa in extra_visas:
            if visa and visa not in seen:
                self.addItem(_visa_display(visa), userData=visa)
                seen.add(visa)

        self.blockSignals(False)
        self.set_visa(current)


# ---------------------------------------------------------------------------
# ConnectionPanel
# ---------------------------------------------------------------------------

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

    connect_requested   = pyqtSignal(list, list)
    disconnect_requested = pyqtSignal()

    # Row tuple: (container_widget, label, _VisaCombo)
    _RowEntry = tuple

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__("Connection", parent)
        self._settings = settings
        self._psu_rows:  list[ConnectionPanel._RowEntry] = []
        self._load_rows: list[ConnectionPanel._RowEntry] = []
        # Cache detected ports and saved addresses for combo refreshes
        self._com_ports: list[tuple[str, str, str]] = []
        self._build_ui()
        # Initial port scan so combos are populated before settings are restored
        self._com_ports = _detect_com_ports()
        self._load_from_settings()

    def apply_state(self, state: TestState) -> None:
        """Enable / disable widgets based on test state."""
        locked       = state == TestState.RUNNING
        can_connect  = state == TestState.DISCONNECTED
        can_disconnect = state in (TestState.CONNECTED, TestState.STOPPED)

        for _, _, combo in self._psu_rows:
            combo.setEnabled(not locked and can_connect)
        for _, _, combo in self._load_rows:
            combo.setEnabled(not locked and can_connect)

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
        # ── Scan button ──────────────────────────────────────────────
        self._scan_button = QPushButton("🔄  Scan Ports")
        self._scan_button.setToolTip(
            "Re-scan for connected COM ports and VISA instruments.\n"
            "Updates the address dropdowns in all rows."
        )
        self._scan_button.clicked.connect(self._scan_instruments)

        scan_row = QHBoxLayout()
        scan_row.addWidget(self._scan_button)
        scan_row.addStretch()

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
        self._psu_layout.setSpacing(4)
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
        self._load_layout.setSpacing(4)
        self._load_container.setLayout(self._load_layout)

        # ── Connect / Disconnect buttons ──────────────────────────────
        self._connect_button = QPushButton("Connect")
        self._connect_button.setStyleSheet(
            "QPushButton { background-color: #17a2b8; color: white;"
            " font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #138496; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self._connect_button.clicked.connect(self._on_connect_clicked)

        self._disconnect_button = QPushButton("Disconnect")
        self._disconnect_button.setEnabled(False)
        self._disconnect_button.setStyleSheet(
            "QPushButton { padding: 6px 16px; border-radius: 4px; }"
        )
        self._disconnect_button.clicked.connect(self.disconnect_requested)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._connect_button)
        btn_row.addWidget(self._disconnect_button)
        btn_row.addStretch()

        # ── Assemble ──────────────────────────────────────────────────
        layout = QVBoxLayout()
        layout.setSpacing(6)
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
        visa_str: str,
    ) -> tuple:
        """Create a VISA combo row.  Returns (row_widget, label, combo, remove_btn)."""
        row_widget  = QWidget()
        row_layout  = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        label = QLabel(label_text)
        label.setFixedWidth(54)

        combo = _VisaCombo()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setMinimumWidth(220)
        combo.lineEdit().setPlaceholderText("COM3  or  ASRL3::INSTR  or  USB0::…")
        combo.currentTextChanged.connect(self._save_to_settings)

        # Populate with current detected ports + this row's saved address
        extra = [visa_str] if visa_str else []
        combo.refresh(self._com_ports, extra)

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(28)
        remove_btn.setToolTip("Remove this row")

        row_layout.addWidget(label)
        row_layout.addWidget(combo, 1)
        row_layout.addWidget(remove_btn)
        row_widget.setLayout(row_layout)

        return row_widget, label, combo, remove_btn

    def _add_psu_row(self, visa_str: str = "") -> None:
        self._add_row(
            self._psu_rows, self._psu_layout, "PSU",
            visa_str, self._remove_psu_row,
        )

    def _remove_psu_row(self, row_widget: QWidget) -> None:
        self._remove_row(
            self._psu_rows, self._psu_layout, "PSU", row_widget, min_rows=1
        )

    def _add_load_row(self, visa_str: str = "") -> None:
        self._add_row(
            self._load_rows, self._load_layout, "Load",
            visa_str, self._remove_load_row,
        )

    def _remove_load_row(self, row_widget: QWidget) -> None:
        self._remove_row(
            self._load_rows, self._load_layout, "Load", row_widget
        )

    def _add_row(
        self,
        rows: list,
        layout: "QVBoxLayout",
        kind: str,
        visa_str: str,
        remover,
    ) -> None:
        idx = len(rows)
        row_widget, label, combo, remove_btn = self._make_row(
            f"{kind} {idx + 1}:", visa_str
        )
        rows.append((row_widget, label, combo))
        layout.addWidget(row_widget)
        remove_btn.clicked.connect(
            lambda _checked=False, rw=row_widget: remover(rw)
        )

    def _remove_row(
        self,
        rows: list,
        layout: "QVBoxLayout",
        kind: str,
        row_widget: QWidget,
        min_rows: int = 0,
    ) -> None:
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
        for i, (_, label, _) in enumerate(rows):
            label.setText(f"{kind} {i + 1}:")

    # ------------------------------------------------------------------
    # Private — settings persistence
    # ------------------------------------------------------------------

    def _load_from_settings(self) -> None:
        psu_visas = self._settings.psu_visa_strings or [""]
        for visa in psu_visas:
            self._add_psu_row(visa)

        load_visas = self._settings.load_visa_strings or [""]
        for visa in load_visas:
            self._add_load_row(visa)

        if self._settings.no_load_mode:
            self._no_load_check.blockSignals(True)
            self._no_load_check.setChecked(True)
            self._no_load_check.blockSignals(False)
            self._load_container.setVisible(False)
            self._add_load_btn.setEnabled(False)

    def _save_to_settings(self) -> None:
        self._settings.psu_visa_strings = [
            c.current_visa() for _, _, c in self._psu_rows
        ]
        self._settings.load_visa_strings = [
            c.current_visa() for _, _, c in self._load_rows
        ]
        self._settings.no_load_mode = self._no_load_check.isChecked()
        self._settings.save()

    def _on_no_load_toggled(self, checked: bool) -> None:
        self._load_container.setVisible(not checked)
        self._add_load_btn.setEnabled(not checked)
        if not checked and not self._load_rows:
            self._add_load_row("")
        self._save_to_settings()

    # ------------------------------------------------------------------
    # Private — scan
    # ------------------------------------------------------------------

    def _scan_instruments(self) -> None:
        """Re-scan COM ports + VISA resources; refresh all row combos."""
        self._scan_button.setText("Scanning…")
        self._scan_button.setEnabled(False)

        # 1. Detect serial COM ports
        self._com_ports = _detect_com_ports()

        # 2. Also scan via pyvisa for USB-TMC, GPIB, LAN instruments
        visa_resources: list[str] = []
        try:
            rm = pyvisa.ResourceManager()
            for r in rm.list_resources():
                if not r.upper().startswith("ASRL"):
                    visa_resources.append(r)
        except Exception as exc:
            logger.debug("VISA scan failed: %s", exc)

        # 3. Build the full extra-visas list (saved + found non-serial)
        saved_psu  = [c.current_visa() for _, _, c in self._psu_rows]
        saved_load = [c.current_visa() for _, _, c in self._load_rows]
        extra = list(dict.fromkeys(saved_psu + saved_load + visa_resources))

        # 4. Refresh every row combo with updated options
        for _, _, combo in list(self._psu_rows) + list(self._load_rows):
            cur = combo.current_visa()
            combo.refresh(self._com_ports, extra)
            combo.set_visa(cur)

        # 5. Report result
        n_com  = len(self._com_ports)
        n_visa = len(visa_resources)
        if n_com + n_visa == 0:
            msg = "No instruments found — check connections and try again."
        else:
            parts = []
            if n_com:
                ports_str = ", ".join(d for d, _, _ in self._com_ports)
                parts.append(f"{n_com} COM port(s): {ports_str}")
            if n_visa:
                parts.append(f"{n_visa} VISA instrument(s)")
            msg = "Found: " + " | ".join(parts)

        QMessageBox.information(self, "Scan Complete", msg)

        self._scan_button.setText("🔄  Scan Ports")
        self._scan_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Private — connect
    # ------------------------------------------------------------------

    def _on_connect_clicked(self) -> None:
        psu_visas = [
            c.current_visa()
            for _, _, c in self._psu_rows
            if c.current_visa()
        ]
        if self._no_load_check.isChecked():
            load_visas: list[str] = []
        else:
            load_visas = [
                c.current_visa()
                for _, _, c in self._load_rows
                if c.current_visa()
            ]

        blank_psus = len(self._psu_rows) - len(psu_visas)
        if psu_visas and blank_psus > 0:
            QMessageBox.warning(
                self, "Blank PSU Rows",
                f"{blank_psus} PSU row(s) had no address and will be skipped.\n"
                f"Connecting to {len(psu_visas)} PSU(s).",
            )

        self.connect_requested.emit(psu_visas, load_visas)

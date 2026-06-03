"""Settings dialog — poll rate, instrument control flags, log folder, Teams URL,
and serial-port / VISA session parameters."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QComboBox,
    QSpinBox,
    QVBoxLayout,
)

from src.config.settings_manager import (
    LOAD_PROFILE_LABELS,
    POLL_RATE_OPTIONS,
    PSU_PROFILE_LABELS,
    SettingsManager,
)

# Baud-rate options (most common RS-232 speeds)
_BAUD_RATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

# Line-termination options: (display label, Python string value)
_TERMINATIONS = [
    ("LF  (\\n)",    "\n"),
    ("CR+LF  (\\r\\n)", "\r\n"),
    ("CR  (\\r)",    "\r"),
    ("None  (\"\")",  ""),
]


class SettingsDialog(QDialog):
    """Modal settings dialog.

    Loads current settings on open; saves only when the user clicks OK.
    Cancel discards changes.
    """

    def __init__(self, settings: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        # ── Poll Rate ──────────────────────────────────────────────
        poll_group = QGroupBox("Polling")
        self._poll_combo = QComboBox()
        for hz in POLL_RATE_OPTIONS:
            self._poll_combo.addItem(f"{hz} Hz", hz)
        poll_form = QFormLayout()
        poll_form.addRow("Poll rate:", self._poll_combo)
        poll_group.setLayout(poll_form)

        # ── Instrument Control ─────────────────────────────────────
        instr_group = QGroupBox("Instrument Control")

        self._psu_profile_combo = QComboBox()
        for key, label in PSU_PROFILE_LABELS.items():
            self._psu_profile_combo.addItem(label, key)

        self._load_profile_combo = QComboBox()
        for key, label in LOAD_PROFILE_LABELS.items():
            self._load_profile_combo.addItem(label, key)

        self._psu_output_cb = QCheckBox("Control PSU output on Start/Stop")
        self._load_input_cb = QCheckBox("Control Load input on Start/Stop")

        instr_form = QFormLayout()
        instr_form.addRow("PSU command profile:", self._psu_profile_combo)
        instr_form.addRow("Load command profile:", self._load_profile_combo)

        instr_layout = QVBoxLayout()
        instr_layout.addLayout(instr_form)
        instr_layout.addWidget(self._psu_output_cb)
        instr_layout.addWidget(self._load_input_cb)
        instr_layout.addWidget(QLabel(
            "<small>Select the command set that matches each instrument. "
            "Takes effect on the next Connect.<br>"
            "When <i>Control PSU/Load output</i> is enabled, the dashboard sends "
            "ON/OFF commands automatically on test start and stop.</small>"))
        instr_group.setLayout(instr_layout)

        # ── Logging ────────────────────────────────────────────────
        log_group = QGroupBox("Logging")
        self._log_dir_field = QLineEdit()
        self._log_dir_field.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_log_dir)
        log_row = QHBoxLayout()
        log_row.addWidget(self._log_dir_field, 1)
        log_row.addWidget(browse_btn)
        log_form = QFormLayout()
        log_form.addRow("Log directory:", log_row)
        log_group.setLayout(log_form)

        # ── Teams Webhook ──────────────────────────────────────────
        teams_group = QGroupBox("Microsoft Teams Notifications")
        self._webhook_field = QLineEdit()
        self._webhook_field.setPlaceholderText("https://...workflows.microsoft.com/...")
        self._webhook_field.setEchoMode(QLineEdit.EchoMode.Normal)
        teams_form = QFormLayout()
        teams_form.addRow("Webhook URL:", self._webhook_field)
        teams_group.setLayout(teams_form)

        # ── PSU — Serial Port / VISA ───────────────────────────────
        serial_group = QGroupBox("PSU — Serial Port / VISA Session")

        self._baud_combo = QComboBox()
        for baud in _BAUD_RATES:
            self._baud_combo.addItem(str(baud), baud)

        self._write_term_combo = QComboBox()
        for label, val in _TERMINATIONS:
            self._write_term_combo.addItem(label, val)

        self._read_term_combo = QComboBox()
        for label, val in _TERMINATIONS:
            self._read_term_combo.addItem(label, val)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(100, 60_000)
        self._timeout_spin.setSingleStep(500)
        self._timeout_spin.setSuffix(" ms")

        self._psu_preamble_field = QLineEdit()
        self._psu_preamble_field.setPlaceholderText(
            "e.g. ADR 10  (TDK-Lambda GEN/GENESYS RS-232 address)"
        )

        self._load_preamble_field = QLineEdit()
        self._load_preamble_field.setPlaceholderText(
            "e.g. ADDR 1  (leave blank for most loads)"
        )

        serial_form = QFormLayout()
        serial_form.addRow("Baud rate:", self._baud_combo)
        serial_form.addRow("Write termination:", self._write_term_combo)
        serial_form.addRow("Read termination:", self._read_term_combo)
        serial_form.addRow("VISA timeout:", self._timeout_spin)
        serial_form.addRow("PSU connection preamble:", self._psu_preamble_field)
        serial_form.addRow("Load connection preamble:", self._load_preamble_field)
        serial_form.addRow(
            "",
            QLabel(
                "<small>Baud rate and termination apply to RS-232 / COM-port "
                "instruments (ASRL). USB-TMC, GPIB, and LAN instruments ignore "
                "the baud rate. Increase the timeout if your instrument is slow "
                "to respond.<br>"
                "<b>Connection preambles</b>: each is sent once immediately after "
                "the respective port opens, before any SCPI query — required by "
                "TDK-Lambda GEN/GENESYS and other instruments that need an address "
                "handshake (e.g. <i>ADR 10</i>). Leave blank for standard "
                "instruments. PSU and Load preambles are independent.</small>"
            ),
        )
        serial_group.setLayout(serial_form)

        # ── Load — Serial Port / VISA ──────────────────────────────
        load_serial_group = QGroupBox("Load — Serial Port / VISA Session")

        self._load_baud_combo = QComboBox()
        for baud in _BAUD_RATES:
            self._load_baud_combo.addItem(str(baud), baud)

        self._load_write_term_combo = QComboBox()
        for label, val in _TERMINATIONS:
            self._load_write_term_combo.addItem(label, val)

        self._load_read_term_combo = QComboBox()
        for label, val in _TERMINATIONS:
            self._load_read_term_combo.addItem(label, val)

        self._load_timeout_spin = QSpinBox()
        self._load_timeout_spin.setRange(100, 60_000)
        self._load_timeout_spin.setSingleStep(500)
        self._load_timeout_spin.setSuffix(" ms")

        load_serial_form = QFormLayout()
        load_serial_form.addRow("Baud rate:", self._load_baud_combo)
        load_serial_form.addRow("Write termination:", self._load_write_term_combo)
        load_serial_form.addRow("Read termination:", self._load_read_term_combo)
        load_serial_form.addRow("VISA timeout:", self._load_timeout_spin)
        load_serial_form.addRow(
            "",
            QLabel(
                "<small>These settings apply only to the Load instrument "
                "and are independent from the PSU settings above.</small>"
            ),
        )
        load_serial_group.setLayout(load_serial_form)

        # ── Buttons ────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(poll_group)
        layout.addWidget(instr_group)
        layout.addWidget(log_group)
        layout.addWidget(teams_group)
        layout.addWidget(serial_group)
        layout.addWidget(load_serial_group)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _load_values(self) -> None:
        # Poll rate
        idx = next(
            (i for i, hz in enumerate(POLL_RATE_OPTIONS)
             if abs(hz - self._settings.poll_rate_hz) < 0.01),
            0,
        )
        self._poll_combo.setCurrentIndex(idx)

        profile_idx = next(
            (i for i, k in enumerate(PSU_PROFILE_LABELS)
             if k == self._settings.psu_command_profile),
            0,
        )
        self._psu_profile_combo.setCurrentIndex(profile_idx)

        self._psu_output_cb.setChecked(self._settings.control_psu_output)
        self._load_input_cb.setChecked(self._settings.control_load_input)
        self._log_dir_field.setText(self._settings.log_directory)
        self._webhook_field.setText(self._settings.teams_webhook_url)

        # Serial / VISA
        baud_idx = next(
            (i for i, b in enumerate(_BAUD_RATES)
             if b == self._settings.serial_baud_rate),
            _BAUD_RATES.index(9600),
        )
        self._baud_combo.setCurrentIndex(baud_idx)

        write_idx = next(
            (i for i, (_, v) in enumerate(_TERMINATIONS)
             if v == self._settings.serial_write_termination),
            0,
        )
        self._write_term_combo.setCurrentIndex(write_idx)

        read_idx = next(
            (i for i, (_, v) in enumerate(_TERMINATIONS)
             if v == self._settings.serial_read_termination),
            0,
        )
        self._read_term_combo.setCurrentIndex(read_idx)

        self._timeout_spin.setValue(self._settings.visa_timeout_ms)
        self._psu_preamble_field.setText(self._settings.psu_connect_preamble)
        self._load_preamble_field.setText(self._settings.load_connect_preamble)

        # Load-specific serial / VISA settings
        load_baud_idx = next(
            (i for i, b in enumerate(_BAUD_RATES)
             if b == self._settings.load_serial_baud_rate),
            _BAUD_RATES.index(9600),
        )
        self._load_baud_combo.setCurrentIndex(load_baud_idx)

        load_write_idx = next(
            (i for i, (_, v) in enumerate(_TERMINATIONS)
             if v == self._settings.load_serial_write_termination),
            0,
        )
        self._load_write_term_combo.setCurrentIndex(load_write_idx)

        load_read_idx = next(
            (i for i, (_, v) in enumerate(_TERMINATIONS)
             if v == self._settings.load_serial_read_termination),
            0,
        )
        self._load_read_term_combo.setCurrentIndex(load_read_idx)

        self._load_timeout_spin.setValue(self._settings.load_visa_timeout_ms)

        load_profile_idx = next(
            (i for i, k in enumerate(LOAD_PROFILE_LABELS)
             if k == self._settings.load_command_profile),
            0,
        )
        self._load_profile_combo.setCurrentIndex(load_profile_idx)

    def _browse_log_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Log Directory",
            self._log_dir_field.text(),
        )
        if path:
            self._log_dir_field.setText(path)

    def _on_ok(self) -> None:
        url = self._webhook_field.text().strip()
        if url and not url.lower().startswith("https://"):
            QMessageBox.warning(
                self,
                "Invalid Webhook URL",
                "The Teams webhook URL must start with https://\n\n"
                "Microsoft Power Automate webhooks always use HTTPS. "
                "Please check the URL and try again.",
            )
            return

        self._settings.poll_rate_hz = self._poll_combo.currentData()
        self._settings.psu_command_profile = self._psu_profile_combo.currentData()
        self._settings.load_command_profile = self._load_profile_combo.currentData()
        self._settings.control_psu_output = self._psu_output_cb.isChecked()
        self._settings.control_load_input = self._load_input_cb.isChecked()
        self._settings.log_directory = self._log_dir_field.text()
        self._settings.teams_webhook_url = url

        # PSU serial / VISA
        self._settings.serial_baud_rate = self._baud_combo.currentData()
        self._settings.serial_write_termination = self._write_term_combo.currentData()
        self._settings.serial_read_termination = self._read_term_combo.currentData()
        self._settings.visa_timeout_ms = self._timeout_spin.value()
        self._settings.psu_connect_preamble = self._psu_preamble_field.text().strip()
        self._settings.load_connect_preamble = self._load_preamble_field.text().strip()

        # Load-specific serial / VISA
        self._settings.load_serial_baud_rate = self._load_baud_combo.currentData()
        self._settings.load_serial_write_termination = self._load_write_term_combo.currentData()
        self._settings.load_serial_read_termination = self._load_read_term_combo.currentData()
        self._settings.load_visa_timeout_ms = self._load_timeout_spin.value()

        self._settings.save()
        self.accept()

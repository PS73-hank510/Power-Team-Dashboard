"""Settings dialog — poll rate, instrument control flags, log folder, Teams URL."""

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
    QPushButton,
    QComboBox,
    QVBoxLayout,
)

from src.config.settings_manager import POLL_RATE_OPTIONS, SettingsManager


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
        self._psu_output_cb = QCheckBox("Control PSU output on Start/Stop")
        self._load_input_cb = QCheckBox("Control Load input on Start/Stop")
        instr_layout = QVBoxLayout()
        instr_layout.addWidget(self._psu_output_cb)
        instr_layout.addWidget(self._load_input_cb)
        instr_layout.addWidget(QLabel(
            "<small>When enabled, the dashboard sends OUTPut/INPut ON/OFF "
            "commands automatically on test start and stop.</small>"))
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

        self._psu_output_cb.setChecked(self._settings.control_psu_output)
        self._load_input_cb.setChecked(self._settings.control_load_input)
        self._log_dir_field.setText(self._settings.log_directory)
        self._webhook_field.setText(self._settings.teams_webhook_url)

    def _browse_log_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Log Directory",
            self._log_dir_field.text(),
        )
        if path:
            self._log_dir_field.setText(path)

    def _on_ok(self) -> None:
        self._settings.poll_rate_hz = self._poll_combo.currentData()
        self._settings.control_psu_output = self._psu_output_cb.isChecked()
        self._settings.control_load_input = self._load_input_cb.isChecked()
        self._settings.log_directory = self._log_dir_field.text()
        self._settings.teams_webhook_url = self._webhook_field.text().strip()
        self._settings.save()
        self.accept()

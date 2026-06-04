"""Control bar — Start/Stop button and test status indicator."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src.core.models import TestState

_START_STYLE = (
    "QPushButton { background-color: #28a745; color: white; font-weight: bold;"
    " font-size: 15px; padding: 10px 32px; border-radius: 6px; }"
    "QPushButton:hover { background-color: #218838; }"
    "QPushButton:disabled { background-color: #aaa; color: #eee; }"
)
_STOP_STYLE = (
    "QPushButton { background-color: #dc3545; color: white; font-weight: bold;"
    " font-size: 15px; padding: 10px 32px; border-radius: 6px; }"
    "QPushButton:hover { background-color: #c82333; }"
)


class ControlBar(QWidget):
    """Horizontal bar containing the Start/Stop button and a status label.

    Signals:
        start_requested:  Emitted when the Start button is clicked.
        stop_requested:   Emitted when the Stop button is clicked.
    """

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._button = QPushButton("▶  START TEST")
        self._button.setStyleSheet(_START_STYLE)
        self._button.setMinimumWidth(180)
        self._button.clicked.connect(self._on_button_clicked)

        self._status_label = QLabel("⬤  DISCONNECTED")
        self._status_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #6c757d;")

        self._is_running = False

        # Status on the left, Start/Stop button anchored to the right
        layout = QHBoxLayout()
        layout.addWidget(self._status_label)
        layout.addStretch()
        layout.addWidget(self._button)
        layout.setContentsMargins(8, 4, 8, 4)
        self.setLayout(layout)

    def apply_state(self, state: TestState) -> None:
        """Update button appearance and status label based on state."""
        if state == TestState.RUNNING:
            self._is_running = True
            self._button.setText("⏹  STOP TEST")
            self._button.setStyleSheet(_STOP_STYLE)
            self._button.setEnabled(True)
            self._status_label.setText("⬤  RUNNING")
            self._status_label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #28a745;"
            )
        elif state == TestState.CONNECTED:
            self._is_running = False
            self._button.setText("▶  START TEST")
            self._button.setStyleSheet(_START_STYLE)
            self._button.setEnabled(True)
            self._status_label.setText("⬤  CONNECTED")
            self._status_label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #17a2b8;"
            )
        elif state == TestState.STOPPED:
            self._is_running = False
            self._button.setText("▶  START TEST")
            self._button.setStyleSheet(_START_STYLE)
            self._button.setEnabled(True)
            self._status_label.setText("⬤  STOPPED")
            self._status_label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #e07800;"
            )
        elif state == TestState.DISCONNECTED:
            self._is_running = False
            self._button.setText("▶  START TEST")
            self._button.setStyleSheet(_START_STYLE)
            self._button.setEnabled(False)
            self._status_label.setText("⬤  DISCONNECTED")
            self._status_label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #6c757d;"
            )

    def _on_button_clicked(self) -> None:
        if self._is_running:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()

"""Alerts and event log widget — displays timestamped events newest-first."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox, QTextEdit, QVBoxLayout


class AlertsLogWidget(QGroupBox):
    """Read-only scrolling text log of timestamped events.

    Events are prepended so the newest entry is always at the top.
    """

    MAX_LINES = 500

    def __init__(self, parent=None) -> None:
        super().__init__("Event Log", parent)
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._text_edit.setMinimumHeight(120)

        layout = QVBoxLayout()
        layout.addWidget(self._text_edit)
        self.setLayout(layout)

    def append_entry(self, message: str) -> None:
        """Prepend a timestamped entry. Trims old entries if over MAX_LINES."""
        self._text_edit.moveCursor(self._text_edit.textCursor().MoveOperation.Start)
        self._text_edit.insertPlainText(message + "\n")

        # Trim if too many lines
        doc = self._text_edit.document()
        while doc.lineCount() > self.MAX_LINES:
            cursor = self._text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove trailing newline

    def clear_log(self) -> None:
        """Remove all entries."""
        self._text_edit.clear()

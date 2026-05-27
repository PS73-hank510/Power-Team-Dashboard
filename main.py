"""Entry point for the Power Systems Monitoring Dashboard."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from src.config.settings_manager import SettingsManager
from src.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Power Systems Monitoring Dashboard")
    app.setOrganizationName("Piersight")

    settings = SettingsManager()
    settings.load()

    window = MainWindow(settings)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

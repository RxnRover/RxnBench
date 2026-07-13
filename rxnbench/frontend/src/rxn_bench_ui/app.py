"""Entry point for the Automated Rxn Bench desktop UI."""

import sys

from PySide6.QtWidgets import QApplication

from .themes import build_qss, get as get_theme
from .core.main_window import MainWindow


def main():
    """Create the QApplication, apply the stylesheet, and start the event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("Rxn Bench")
    app.setStyleSheet(build_qss(get_theme("light")))

    window = MainWindow(theme_name="light")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

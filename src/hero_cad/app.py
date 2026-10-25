import sys
import os
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from hero_cad import __version__
from hero_cad.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HERO-CAD")
    app.setApplicationDisplayName("HERO-CAD")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("hero-cad")
    icon_path = os.environ.get("HERO_CAD_ICON")
    app.setWindowIcon(QIcon(icon_path) if icon_path else QIcon.fromTheme("hero-cad"))
    window = MainWindow()
    window.show()
    return app.exec()

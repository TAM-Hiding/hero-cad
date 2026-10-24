import sys
from PySide6.QtWidgets import QApplication
from hero_cad import __version__
from hero_cad.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HERO-CAD")
    app.setApplicationDisplayName("HERO-CAD")
    app.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    return app.exec()

import sys
from PySide6.QtWidgets import QApplication
from star_cad.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("STAR-CAD")
    window = MainWindow()
    window.show()
    return app.exec()

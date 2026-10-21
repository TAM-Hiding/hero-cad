from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget, QDoubleSpinBox, QFormLayout, QMainWindow, QMessageBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QWidget,
)
from star_cad.document import BoxParameters, Document
from star_cad.geometry import volume
from star_cad.ui.viewport import Viewport


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STAR-CAD 0.0.1 — Untitled (in memory)")
        self.resize(1200, 780)
        self.document = Document()
        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)
        self.browser = QTreeWidget()
        self.browser.setHeaderLabel("Model · mm")
        self.box_item = QTreeWidgetItem(self.browser, ["Box"])
        self.browser.setCurrentItem(self.box_item)
        self.add_panel("Model browser", self.browser, Qt.LeftDockWidgetArea)
        panel = QWidget()
        form = QFormLayout(panel)
        self.fields = {}
        for name, label in (("width", "Width · X"), ("depth", "Depth · Y"), ("height", "Height · Z")):
            field = QDoubleSpinBox()
            field.setDecimals(3)
            field.setRange(0.001, 100000)
            field.setSuffix(" mm")
            field.setValue(getattr(self.document.parameters, name))
            field.setKeyboardTracking(False)
            self.fields[name] = field
            form.addRow(label, field)
        self.apply_button = QPushButton("Apply dimensions")
        self.apply_button.clicked.connect(self.apply_dimensions)
        form.addRow(self.apply_button)
        self.add_panel("Box properties", panel, Qt.RightDockWidgetArea)
        toolbar = self.addToolBar("View")
        fit = QAction("Fit all", self)
        fit.setShortcut("F")
        fit.triggered.connect(self.viewport.fit)
        toolbar.addAction(fit)
        self.viewport.set_shape(self.document.shape, fit=True)
        self.update_status()

    def add_panel(self, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def apply_dimensions(self):
        try:
            self.document.set_box(BoxParameters(**{n: f.value() for n, f in self.fields.items()}))
        except Exception as error:
            QMessageBox.warning(self, "Cannot update box", str(error))
            return
        self.viewport.set_shape(self.document.shape)
        self.update_status()

    def update_status(self):
        self.statusBar().showMessage(
            f"Volume: {volume(self.document.shape):.3f} mm³  |  "
            "Left drag: orbit · middle/Shift-left drag: pan · wheel: zoom · F: fit"
        )

    def closeEvent(self, event):
        self.viewport.Finalize()
        super().closeEvent(event)

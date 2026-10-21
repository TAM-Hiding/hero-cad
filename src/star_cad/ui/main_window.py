from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QDockWidget, QDoubleSpinBox, QFormLayout, QMainWindow, QMessageBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QWidget,
)
from star_cad import __version__
from star_cad.document import BoxParameters, Document
from star_cad.geometry import volume
from star_cad.ui.viewport import Viewport


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
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
            field.valueChanged.connect(self.update_actions)
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
        file_menu = self.menuBar().addMenu("&File")
        self.new_action = self.action(file_menu, "&New", QKeySequence.New, self.new_document)
        self.open_action = self.action(file_menu, "&Open…", QKeySequence.Open, self.open_document)
        self.save_action = self.action(file_menu, "&Save", QKeySequence.Save, self.save_document)
        self.action(file_menu, "Save &As…", QKeySequence.SaveAs, lambda: self.save_document(save_as=True))
        edit_menu = self.menuBar().addMenu("&Edit")
        self.undo_action = self.action(edit_menu, "&Undo", QKeySequence.Undo, self.undo)
        self.redo_action = self.action(edit_menu, "&Redo", QKeySequence.Redo, self.redo)
        self.refresh(fit=True)

    def add_panel(self, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def action(self, menu, title, shortcut, callback):
        action = QAction(title, self)
        action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def field_parameters(self):
        for field in self.fields.values():
            field.interpretText()
        return BoxParameters(**{
            n: (f.value() if f.value() != self._shown_values[n]
                else getattr(self.document.parameters, n))
            for n, f in self.fields.items()
        })

    def has_pending_edits(self):
        return any(f.value() != self._shown_values[n] for n, f in self.fields.items())

    def update_actions(self):
        # Signals can arrive while the property panel is being constructed.
        if not hasattr(self, 'undo_action'):
            return
        pending = self.has_pending_edits()
        self.undo_action.setEnabled(pending or self.document.can_undo)
        self.redo_action.setEnabled(not pending and self.document.can_redo)
        name = self.document.path.name if self.document.path else "Untitled"
        marker = " *" if self.document.dirty or pending else ""
        self.setWindowTitle(f"STAR-CAD {__version__} — {name}{marker}")

    def refresh(self, fit=False):
        for name, field in self.fields.items():
            with QSignalBlocker(field):
                field.setValue(getattr(self.document.parameters, name))
                field.setToolTip(f"Stored dimension: {getattr(self.document.parameters, name):.15g} mm")
        # Preserve untouched loaded values even if the editor displays fewer decimals.
        self._shown_values = {n: f.value() for n, f in self.fields.items()}
        self.viewport.set_shape(self.document.shape, fit=fit)
        self.update_status()
        self.update_actions()

    def apply_dimensions(self):
        try:
            self.document.set_box(self.field_parameters())
        except Exception as error:
            QMessageBox.warning(self, "Cannot update box", str(error))
            return False
        self.refresh()
        return True

    def undo(self):
        try:
            # Undo first cancels uncommitted property edits.
            if not self.has_pending_edits():
                self.document.undo()
        except Exception as error:
            QMessageBox.warning(self, "Cannot undo", str(error))
            return
        self.refresh()

    def redo(self):
        if self.has_pending_edits():
            return
        try:
            self.document.redo()
        except Exception as error:
            QMessageBox.warning(self, "Cannot redo", str(error))
            return
        self.refresh()

    def save_document(self, checked=False, *, save_as=False):
        path = self.document.path
        if save_as or path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self, "Save STAR-CAD document", str(path or "Untitled.starcad"),
                "STAR-CAD documents (*.starcad)")
            if not selected:
                return False
            path = selected
            if not path.lower().endswith('.starcad'):
                path += '.starcad'
                if Path(path).exists() and QMessageBox.question(
                    self, "Replace file?", f"Replace {path}?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) != QMessageBox.Yes:
                    return False
        if not self.apply_dimensions():
            return False
        try:
            self.document.save(path)
        except Exception as error:
            QMessageBox.warning(self, "Cannot save document", str(error))
            return False
        self.update_actions()
        return True

    def confirm_replace(self):
        # Commit text to spinbox values before checking staged edits.
        self.field_parameters()
        if not (self.document.dirty or self.has_pending_edits()):
            return True
        answer = QMessageBox.question(
            self, "Unsaved changes", "Save changes before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save_document()
        return answer == QMessageBox.Discard

    def new_document(self):
        if not self.confirm_replace():
            return
        self.document = Document()
        self.refresh(fit=True)

    def open_document(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open STAR-CAD document", "", "STAR-CAD documents (*.starcad)")
        if not selected:
            return
        try:
            replacement = Document.load(selected)
        except Exception as error:
            QMessageBox.warning(self, "Cannot open document", str(error))
            return
        if not self.confirm_replace():
            return
        try:
            # Saving in the prompt may have changed the selected file itself.
            replacement = Document.load(selected)
        except Exception as error:
            QMessageBox.warning(self, "Cannot open document", str(error))
            return
        self.document = replacement
        self.refresh(fit=True)

    def update_status(self):
        self.statusBar().showMessage(
            f"Volume: {volume(self.document.shape):.3f} mm³  |  "
            "Left drag: orbit · middle/Shift-left drag: pan · wheel: zoom · F: fit"
        )

    def closeEvent(self, event):
        if not self.confirm_replace():
            event.ignore()
            return
        self.viewport.Finalize()
        super().closeEvent(event)

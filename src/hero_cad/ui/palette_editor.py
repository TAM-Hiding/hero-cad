"""Removable modeless experimental RGB editor; all state lives in Preferences."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor, QValidator
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTabWidget, QScrollArea, QWidget, QFormLayout, QPushButton, QLineEdit,
    QColorDialog, QFileDialog, QMessageBox)
from hero_cad.palette import COLORS, CATEGORIES, ENABLED
from hero_cad.ui.palette_controller import readable


class HexValidator(QValidator):
    def validate(self, text, pos):
        import re
        if re.fullmatch(r'#[0-9a-fA-F]{6}', text):
            return QValidator.Acceptable, text, pos
        if re.fullmatch(r'#?[0-9a-fA-F]{0,6}', text):
            return QValidator.Intermediate, text, pos
        return QValidator.Invalid, text, pos


class PaletteEditor(QDialog):
    def __init__(self, controller, parent):
        super().__init__(parent)
        self.controller = controller
        self.setObjectName('paletteEditor')
        self.setWindowTitle('Experimental UI Palette — HERO-CAD')
        self.setModal(False)
        self.resize(660, 650)
        self.setMinimumSize(480, 380)
        layout = QVBoxLayout(self)
        note = QLabel('Live appearance only · CAD geometry and history stay unchanged.\n'
                      'RGB colors only. Low-contrast control text/focus is adjusted for readability.')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(QLabel('Preset'))
        self.preset = QComboBox()
        self.preset.addItems(('HERO Default', 'Custom'))
        self.preset.currentIndexChanged.connect(lambda i:controller.preset(i == 1))
        row.addWidget(self.preset, 1)
        layout.addLayout(row)
        self.tabs = QTabWidget()
        self.fields, self.swatches = {}, {}
        for name in CATEGORIES:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            page = QWidget()
            form = QFormLayout(page)
            for key, spec in COLORS.items():
                if spec.category != name:
                    continue
                controls = QWidget()
                line = QHBoxLayout(controls)
                line.setContentsMargins(0, 0, 0, 0)
                swatch = QPushButton('Pick…')
                swatch.setAccessibleName(spec.label+' color picker')
                swatch.setFixedWidth(66)
                swatch.clicked.connect(lambda checked=False, key=key:self.pick_color(key))
                field = QLineEdit()
                field.setAccessibleName(spec.label+' hexadecimal RGB')
                field.setPlaceholderText('#RRGGBB')
                field.setMaxLength(7)
                field.setValidator(HexValidator(field))
                field.textEdited.connect(lambda text, key=key:self.edit_hex(key, text))
                field.editingFinished.connect(self.sync)
                reset = QPushButton('Reset')
                reset.setToolTip('Restore '+spec.label+' to its original default')
                reset.clicked.connect(lambda checked=False, key=key:controller.reset((key,)))
                line.addWidget(swatch); line.addWidget(field, 1); line.addWidget(reset)
                self.fields[key], self.swatches[key] = field, swatch
                form.addRow(spec.label, controls)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, name)
        layout.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        for label, callback in (('Reset category', self.reset_category),
                                ('Reset entire palette', lambda:controller.reset()),
                                ('Import Palette…', self.import_palette),
                                ('Export Palette…', self.export_palette)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.message = QLabel('HERO Default preserves the original styles. Custom remembers your experiments.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignRight)
        controller.changed.connect(self.sync)
        self.sync()

    def sync(self):
        colors = self.controller.colors()
        with QSignalBlocker(self.preset):
            self.preset.setCurrentIndex(1 if self.controller.store.get(ENABLED) else 0)
        for key, field in self.fields.items():
            # Preserve an unfinished hex edit while the user types.
            if field.hasFocus() and not field.hasAcceptableInput():
                continue
            field.setText(colors[key])
            color = colors[key]
            self.swatches[key].setStyleSheet('background-color:'+color+';color:'+readable('#FFFFFF',color)+';')

    def edit_hex(self, key, text):
        if self.fields[key].hasAcceptableInput():
            self.controller.set_color(key, text)

    def pick_color(self, key):
        dialog = QColorDialog(QColor(self.controller.colors()[key]), self)
        dialog.setWindowTitle(COLORS[key].label)
        original = self.controller.store.get('palette/v1/'+key)
        enabled = self.controller.store.get(ENABLED)
        dialog.currentColorChanged.connect(lambda color:self.controller.set_color(key, color.name()))
        try:
            if dialog.exec() != QDialog.Accepted:
                self.controller.store.set_many({'palette/v1/'+key:original, ENABLED:enabled})
        finally:
            dialog.deleteLater()

    def reset_category(self):
        category = CATEGORIES[self.tabs.currentIndex()]
        self.controller.reset(key for key,spec in COLORS.items() if spec.category == category)

    def import_palette(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import Palette', '', 'HERO palette (*.json)')
        if path:
            try:
                self.controller.import_file(path)
                self.message.setText('Imported complete RGB palette. Custom is active.')
            except (ValueError, OSError, UnicodeError) as error:
                QMessageBox.warning(self, 'Cannot import palette', str(error))

    def export_palette(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export Palette', 'hero-palette.json', 'HERO palette (*.json)')
        if path:
            try:
                self.controller.export_file(path)
                self.message.setText('Exported complete RGB palette to '+path)
            except (ValueError, OSError) as error:
                QMessageBox.warning(self, 'Cannot export palette', str(error))

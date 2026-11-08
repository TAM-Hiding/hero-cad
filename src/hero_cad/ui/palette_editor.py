"""Removable modeless experimental RGB editor; all state lives in Preferences."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor, QValidator
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTabWidget, QScrollArea, QWidget, QFormLayout, QPushButton, QLineEdit,
    QColorDialog, QFileDialog, QMessageBox)
from hero_cad.palette import COLORS, CATEGORIES, ENABLED, CONTRAST, MODE_COLORS
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
                      'RGB only · Inherit follows global sketch colors · Keyboard focus stays protected.')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(QLabel('Preset'))
        self.preset = QComboBox()
        self.preset.addItems(('HERO Default', 'Custom'))
        self.preset.currentIndexChanged.connect(lambda i:controller.preset(i == 1))
        row.addWidget(self.preset, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('Text Contrast'))
        self.text_contrast = QComboBox()
        self.text_contrast.addItems(('Automatic', 'Manual'))
        self.text_contrast.setAccessibleName('Text Contrast')
        self.text_contrast.currentTextChanged.connect(controller.set_contrast)
        row.addWidget(self.text_contrast, 1)
        layout.addLayout(row)
        self.contrast_info = QLabel()
        self.contrast_info.setWordWrap(True)
        layout.addWidget(self.contrast_info)
        self.tabs = QTabWidget()
        self.fields, self.swatches, self.inheritance = {}, {}, {}
        for name in CATEGORIES:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            page = QWidget()
            form = QFormLayout(page)
            keys = list(COLORS)
            if name == 'Sketch':
                first = ['sketch.normal', 'sketch.active', 'sketch.selected', *MODE_COLORS]
                keys = first + [key for key in keys if key not in first]
            for key in keys:
                spec = COLORS[key]
                if spec.category != name:
                    continue
                if name == 'Sketch' and key in ('sketch.normal', 'sketch.orange.normal', 'sketch.celadon.normal', 'sketch.profile'):
                    title = {'sketch.normal':'Global sketch colors', 'sketch.orange.normal':'Orange X-Ray',
                             'sketch.celadon.normal':'Celadon X-Ray', 'sketch.profile':'Profile fill, guides & Finish Sketch'}[key]
                    heading = QLabel(title)
                    heading.setProperty('paletteRole', 'heading')
                    form.addRow(heading)
                controls = QWidget()
                line = QHBoxLayout(controls)
                line.setContentsMargins(0, 0, 0, 0)
                if key in MODE_COLORS:
                    choice = QComboBox()
                    choice.addItems(('Inherit', 'Custom'))
                    choice.setAccessibleName(spec.label+' inheritance')
                    choice.currentIndexChanged.connect(lambda index, key=key:self.choose_inheritance(key, index))
                    self.inheritance[key] = choice
                    line.addWidget(choice)
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
                label = COLORS[MODE_COLORS[key]].label if key in MODE_COLORS else spec.label
                form.addRow(label, controls)
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
        with QSignalBlocker(self.text_contrast):
            self.text_contrast.setCurrentText(self.controller.store.get(CONTRAST))
        if self.controller.store.get(CONTRAST) == 'Manual':
            self.contrast_info.setText('Manual: explicit text RGB is used; low contrast is allowed. Focus rings remain protected.')
            self.contrast_info.setToolTip('Swatch labels and Finish Sketch text are derived for legibility; they have no separate text role.')
        else:
            changes = sorted(self.controller.adjustments)
            self.contrast_info.setText(f'Automatic: {len(changes)} foreground adjustment(s). Hover here for requested → displayed colors.')
            self.contrast_info.setToolTip('\n'.join(f'{a} → {b} on {bg}' for a,b,bg in changes) or 'No foreground substitutions.')
        overrides = self.controller.overrides()
        for key, field in self.fields.items():
            if key in self.inheritance:
                custom = key in overrides
                with QSignalBlocker(self.inheritance[key]):
                    self.inheritance[key].setCurrentIndex(1 if custom else 0)
                field.setEnabled(custom)
                self.swatches[key].setEnabled(custom)
                field.setToolTip('Custom RGB override' if custom else 'Inherited from '+COLORS[MODE_COLORS[key]].label)
            # Preserve an unfinished hex edit while the user types.
            if field.hasFocus() and not field.hasAcceptableInput():
                continue
            if field.text() != colors[key]:
                field.setText(colors[key])
            color = colors[key]
            style = 'background-color:'+color+';color:'+readable('#FFFFFF',color)+';'
            if self.swatches[key].styleSheet() != style:
                self.swatches[key].setStyleSheet(style)

    def choose_inheritance(self, key, index):
        if index == 0:
            self.controller.reset((key,))
        else:
            self.controller.set_color(key, self.controller.colors()[key])

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

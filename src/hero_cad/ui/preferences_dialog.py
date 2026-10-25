"""Immediate, categorized views of the same preferences used by quick controls."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QDialog, QListWidget, QStackedWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QWidget, QLabel,
    QDialogButtonBox, QPushButton, QScrollArea,
)
from hero_cad.preferences import CATEGORIES, PREFERENCES


class PreferencesDialog(QDialog):
    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.preferences = preferences
        self.setWindowTitle('HERO-CAD Settings')
        self.resize(720, 530)
        self.setMinimumSize(580, 420)
        palette = self.palette()
        for role, color in ((QPalette.Window, '#242e34'), (QPalette.WindowText, '#dae5e3'),
                            (QPalette.Base, '#192128'), (QPalette.AlternateBase, '#33434b'),
                            (QPalette.Text, '#dae5e3'), (QPalette.Button, '#33434b'),
                            (QPalette.ButtonText, '#dae5e3'), (QPalette.Highlight, '#865227'),
                            (QPalette.HighlightedText, '#ffe2b4')):
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.categories = QListWidget()
        self.categories.addItems(CATEGORIES)
        self.categories.setAccessibleName('Settings category')
        self.categories.setMaximumWidth(165)
        self.pages = QStackedWidget()
        self.controls = {}
        for category in CATEGORIES:
            page = QWidget()
            form = QFormLayout(page)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for key, spec in PREFERENCES.items():
                if spec.category != category or not spec.exposed:
                    continue
                if spec.kind is bool:
                    control = QCheckBox(spec.label)
                    control.toggled.connect(lambda value, name=key: preferences.set(name, value))
                    form.addRow(control)
                elif spec.kind is str:
                    control = QComboBox()
                    control.addItems(spec.choices)
                    control.currentTextChanged.connect(lambda value, name=key: preferences.set(name, value))
                    form.addRow(spec.label, control)
                else:
                    control = QDoubleSpinBox() if spec.kind is float else QSpinBox()
                    if spec.kind is float:
                        control.setDecimals(6)
                    control.setRange(spec.minimum, spec.maximum)
                    control.setKeyboardTracking(False)
                    control.valueChanged.connect(lambda value, name=key: preferences.set(name, value))
                    form.addRow(spec.label, control)
                control.setAccessibleName(spec.label)
                self.controls[key] = control
                self.update_control(key, preferences.get(key))
            if category == 'Sketching':
                note = QLabel('Individual sketch visibility belongs to the document.\nUse the browser Visible column; editing reveals hidden sketches temporarily.\n\nOpacity controls the dimension popup, not solid transparency.')
                note.setWordWrap(True)
                form.addRow(note)
            if category == 'Viewport':
                note = QLabel('Navigation bindings are unchanged: Shift-right drag pans;\nShift-right double-click aligns to a planar face.')
                note.setWordWrap(True)
                form.addRow(note)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.categories.setCurrentRow(0)
        row.addWidget(self.categories)
        row.addWidget(self.pages, 1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        self.restore_button = QPushButton('Restore Category Defaults')
        self.restore_button.clicked.connect(self.restore_category)
        buttons.addButton(self.restore_button, QDialogButtonBox.ResetRole)
        layout.addWidget(buttons)
        preferences.changed.connect(self.update_control)
        self.update_enabled()

    def update_control(self, key, value):
        control = self.controls.get(key)
        if control is None:
            return
        with QSignalBlocker(control):
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QComboBox):
                control.setCurrentText(value)
            else:
                control.setValue(value)
        self.update_enabled()

    def update_enabled(self):
        control = self.controls.get('grid/v1/manual_spacing')
        if control:
            control.setEnabled(not self.preferences.get('grid/v1/automatic'))

    def restore_category(self):
        self.preferences.restore_category(CATEGORIES[self.categories.currentRow()])

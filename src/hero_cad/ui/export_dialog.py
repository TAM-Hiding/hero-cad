"""Qt destination, scope and STL quality controls."""
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox

from hero_cad.manufacturing_export import EXTENSIONS, STL_QUALITY
from hero_cad.ui.document_dialog import DocumentDialog


class ExportDialog(DocumentDialog):
    def __init__(self, parent, directory, basename, format_name, selected_count, total_count):
        super().__init__(parent, directory, saving=True)
        self.format_name = format_name
        self.setObjectName('heroExportDialog')
        self.setWindowTitle(f'Export {format_name.upper()}')
        extensions = EXTENSIONS[format_name]
        patterns = [f'*.{"".join(f"[{c}{c.upper()}]" for c in extension[1:])}' for extension in extensions]
        self.setNameFilter(f'{format_name.upper()} files ({" ".join(patterns)})')
        self.setDefaultSuffix(extensions[0][1:])
        self.selectFile(basename + extensions[0])

        layout = self.layout()
        row = layout.rowCount()
        self.scope = QComboBox(self)
        self.scope.addItem(f'All current bodies ({total_count})', False)
        if selected_count:
            self.scope.addItem(f'Selected bodies ({selected_count})', True)
            self.scope.setCurrentIndex(1)
        else:
            self.scope.setToolTip('Select a current body or an unambiguous face or edge to export a selection.')
        scope_label = QLabel('Export scope', self)
        scope_label.setBuddy(self.scope)
        layout.addWidget(scope_label, row, 0)
        layout.addWidget(self.scope, row, 1)
        self.quality = None
        if format_name == 'stl':
            self.quality = QComboBox(self)
            self.quality.addItems(list(STL_QUALITY))
            self.quality.setCurrentText('Standard')
            quality_label = QLabel('Mesh quality', self)
            quality_label.setBuddy(self.quality)
            layout.addWidget(quality_label, row + 1, 0)
            layout.addWidget(self.quality, row + 1, 1)
            layout.addWidget(QLabel('Binary STL · coordinates in millimeters', self), row + 2, 1)

    def accept(self):
        if not self.findChild(QLineEdit, 'fileNameEdit').text().strip():
            return
        files = self.selectedFiles()
        if len(files) != 1:
            return
        path = Path(files[0])
        if not path.is_dir() and path.suffix.lower() not in EXTENSIONS[self.format_name]:
            extensions = ' or '.join(EXTENSIONS[self.format_name])
            QMessageBox.warning(self, 'Cannot export', f'Use a {extensions} file extension.')
            return
        # Qt confirms overwriting the final name, with the default suffix applied.
        super().accept()

    def export_options(self):
        try:
            if self.exec():
                return self.selectedFiles()[0], self.scope.currentData(), (
                    self.quality.currentText() if self.quality else 'Standard')
            return None
        finally:
            self.deleteLater()

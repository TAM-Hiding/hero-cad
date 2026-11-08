"""The stock Qt Save As dialog, with predictable filename editing."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox

from hero_cad.persistence import DOCUMENT_EXTENSION, require_document_extension


# The bracket glob also matches case variants in case-sensitive platform dialogs.
DOCUMENT_FILTER = f'HERO-CAD documents (*{DOCUMENT_EXTENSION} *.[hH][cC][aA][dD])'


class SaveDocumentDialog(QFileDialog):
    def __init__(self, parent, directory, filename):
        super().__init__(parent)
        # Native GTK/portal dialogs do not expose their filename editor to Qt.
        self.setOption(QFileDialog.Option.DontUseNativeDialog)
        self.setWindowTitle('Save HERO-CAD document')
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        self.setFileMode(QFileDialog.FileMode.AnyFile)
        self.setNameFilter(DOCUMENT_FILTER)
        self.setDefaultSuffix(DOCUMENT_EXTENSION[1:])
        self.setDirectory(str(directory))
        self.selectFile(filename)
        self._filename_edit = self.findChild(QLineEdit, 'fileNameEdit')

    def showEvent(self, event):
        super().showEvent(event)
        self._filename_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        # QLineEdit indexes UTF-16 code units, including for non-BMP filenames.
        basename = self._filename_edit.text()[:-len(DOCUMENT_EXTENSION)]
        self._filename_edit.setSelection(0, len(basename.encode('utf-16-le')) // 2)

    def accept(self):
        if not self._filename_edit.text().strip():
            return
        files = self.selectedFiles()
        if len(files) != 1:
            return
        path = Path(files[0])
        try:
            if not path.is_dir():
                require_document_extension(path)
                if path.is_symlink() and not path.exists():
                    raise ValueError(f'The destination is a broken symbolic link: {path}')
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Cannot save document', str(error))
            return
        # Qt checks overwrite on the actual path, including its default suffix.
        super().accept()

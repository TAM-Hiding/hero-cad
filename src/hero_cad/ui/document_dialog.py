"""Stock Qt document dialogs with shared appearance and file filtering."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox

from hero_cad.persistence import DOCUMENT_EXTENSION, require_document_extension


# The bracket glob also matches case variants in case-sensitive platform dialogs.
DOCUMENT_FILTER = f'HERO-CAD documents (*{DOCUMENT_EXTENSION} *.[hH][cC][aA][dD])'


class DocumentDialog(QFileDialog):
    def __init__(self, parent, directory, *, saving=False):
        super().__init__(parent)
        self.setOption(QFileDialog.Option.DontUseNativeDialog)
        self.setObjectName('heroDocumentDialog')
        action = 'Save' if saving else 'Open'
        self.setWindowTitle(f'{action} HERO-CAD document')
        self.setAcceptMode(QFileDialog.AcceptSave if saving else QFileDialog.AcceptOpen)
        self.setFileMode(QFileDialog.AnyFile if saving else QFileDialog.ExistingFile)
        self.setNameFilter(DOCUMENT_FILTER)
        self.setDirectory(str(directory))

    def select_path(self):
        try:
            if self.exec():
                return self.selectedFiles()[0]
            return None
        finally:
            self.deleteLater()


class SaveDocumentDialog(DocumentDialog):
    def __init__(self, parent, directory, filename):
        super().__init__(parent, directory, saving=True)
        self.setDefaultSuffix(DOCUMENT_EXTENSION[1:])
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

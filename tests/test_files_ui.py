import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox
from star_cad.document import BoxParameters, Document
from star_cad.ui.main_window import MainWindow


def window(qtbot):
    result = MainWindow()
    qtbot.addWidget(result)
    result.show()
    return result


def test_save_pending_open_undo_and_precision(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    path = tmp_path / 'part.starcad'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(path), ''))
    w.fields['width'].setValue(65.125)
    assert '*' in w.windowTitle()
    assert w.save_document()
    assert Document.load(path).parameters.width == 65.125
    assert '*' not in w.windowTitle()
    w.undo_action.trigger()
    assert w.fields['width'].value() == 40 and '*' in w.windowTitle()
    w.redo_action.trigger()
    assert w.fields['width'].value() == 65.125 and '*' not in w.windowTitle()
    precise = Document(BoxParameters(width=12.3456789))
    precise.save(path)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(path), ''))
    w.open_action.trigger()
    assert not w.has_pending_edits()
    assert w.save_document()
    assert Document.load(path).parameters.width == 12.3456789


def test_pending_undo_cancels_fields_without_changing_history(qtbot):
    w = window(qtbot)
    w.fields['width'].setValue(50)
    w.apply_dimensions()
    w.fields['depth'].setValue(60)
    w.undo()
    assert w.fields['depth'].value() == 30 and w.document.parameters.width == 50
    w.undo()
    assert w.document.parameters.width == 40


def test_cancel_and_failed_open_preserve_document(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    w.fields['width'].setValue(50)
    w.apply_dimensions()
    original = w.document
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Cancel)
    w.new_document()
    assert w.document is original
    assert not w.close()
    path = tmp_path / 'bad.starcad'
    path.write_text('{')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(path), ''))
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: errors.append(a))
    w.open_document()
    assert errors and w.document is original and w.document.dirty
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)


def test_save_cancel_blocks_new_and_close(qtbot, monkeypatch):
    w = window(qtbot)
    w.fields['height'].setValue(45)
    original = w.document
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: ('', ''))
    w.new_document()
    assert w.document is original and w.fields['height'].value() == 45
    assert not w.close()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)
    w.new_document()
    assert w.document is not original and w.fields['height'].value() == 20


def test_failed_save_blocks_close(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    w.fields['width'].setValue(50)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(tmp_path / 'missing' / 'part.starcad'), ''))
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: errors.append(a))
    assert not w.close()
    assert errors and w.document.dirty and w.document.path is None
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)


def test_open_current_file_after_save_prompt_uses_saved_changes(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    path = tmp_path / 'part.starcad'
    w.document.save(path)
    w.fields['width'].setValue(75)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(path), ''))
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save)
    w.open_document()
    assert w.document.parameters.width == 75
    assert not w.document.dirty and not w.document.can_undo


def test_appended_suffix_cannot_silently_overwrite(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    path = tmp_path / 'part.starcad'
    path.write_text('existing file')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(tmp_path / 'part'), ''))
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.No)
    assert not w.save_document()
    assert path.read_text() == 'existing file'
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)


def test_apply_reads_uncommitted_spinbox_text(qtbot):
    from PySide6.QtCore import Qt
    w = window(qtbot)
    field = w.fields['width']
    field.setFocus()
    field.lineEdit().selectAll()
    qtbot.keyClicks(field.lineEdit(), '88.125')
    qtbot.mouseClick(w.apply_button, Qt.LeftButton)
    assert w.document.parameters.width == 88.125


def test_save_as_preserves_original_and_changes_path(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    original = tmp_path / 'original.starcad'
    copy = tmp_path / 'copy.starcad'
    w.document.save(original)
    w.fields['height'].setValue(45)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(tmp_path / 'copy'), ''))
    assert w.save_document(save_as=True)
    assert w.document.path == copy and not w.document.dirty
    assert Document.load(original).parameters.height == 20
    assert Document.load(copy).parameters.height == 45

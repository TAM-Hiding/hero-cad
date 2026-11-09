import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox
from hero_cad.document import BoxParameters, Document
from hero_cad.ui.main_window import MainWindow


def window(qtbot):
    result = MainWindow()
    qtbot.addWidget(result)
    result.show()
    qtbot.waitExposed(result)
    return result


def test_save_pending_open_undo_and_precision(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    path = tmp_path / 'part.hcad'
    monkeypatch.setattr(w, 'select_document_save_path', lambda *a: str(path))
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
    monkeypatch.setattr(w, 'select_document_open_path', lambda *a: str(path))
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
    path = tmp_path / 'bad.hcad'
    path.write_text('{')
    monkeypatch.setattr(w, 'select_document_open_path', lambda *a: str(path))
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
    monkeypatch.setattr(w, 'select_document_save_path', lambda *a: None)
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
    monkeypatch.setattr(w, 'select_document_save_path', lambda *a: str(tmp_path / 'missing' / 'part.hcad'))
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: errors.append(a))
    assert not w.close()
    assert errors and w.document.dirty and w.document.path is None
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)


def test_open_current_file_after_save_prompt_uses_saved_changes(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    path = tmp_path / 'part.hcad'
    w.document.save(path)
    w.fields['width'].setValue(75)
    monkeypatch.setattr(w, 'select_document_open_path', lambda *a: str(path))
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Save)
    w.open_document()
    assert w.document.parameters.width == 75
    assert not w.document.dirty and not w.document.can_undo


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
    original = tmp_path / 'original.hcad'
    copy = tmp_path / 'copy.hcad'
    w.document.save(original)
    w.fields['height'].setValue(45)
    monkeypatch.setattr(w, 'select_document_save_path', lambda *a: str(copy))
    assert w.save_document(save_as=True)
    assert w.document.path == copy and not w.document.dirty
    assert Document.load(original).parameters.height == 20
    assert Document.load(copy).parameters.height == 45


@pytest.fixture
def models_directory(monkeypatch, tmp_path):
    from PySide6.QtCore import QStandardPaths

    documents = tmp_path / 'XDG.Documents'
    monkeypatch.setattr(QStandardPaths, 'writableLocation', lambda location: str(documents))
    return documents / 'HERO-CAD' / 'Models'


def with_save_dialog(qtbot, interact):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLineEdit
    from hero_cad.ui.document_dialog import SaveDocumentDialog

    def drive_dialog():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, SaveDocumentDialog)
            editor = dialog.findChild(QLineEdit, 'fileNameEdit')
            qtbot.waitUntil(lambda: QApplication.focusWidget() is editor)
            interact(dialog, editor)
        finally:
            if dialog and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, drive_dialog)


def test_first_save_and_save_as_shortcuts_focus_basename(qtbot, models_directory, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    w = window(qtbot)
    w.activateWindow()
    qtbot.waitUntil(w.isActiveWindow)
    w.fields['width'].setValue(64)
    assert not models_directory.exists()

    def rename(suggestion, name):
        def interact(dialog, editor):
            assert dialog.windowTitle() == 'Save HERO-CAD document'
            assert '*.hcad' in dialog.nameFilters()[0]
            assert dialog.directory().absolutePath() == str(models_directory)
            assert models_directory.is_dir()
            assert editor.text() == suggestion + '.hcad'
            assert editor.selectedText() == suggestion
            qtbot.keyClicks(QApplication.focusWidget(), name)
            assert editor.text() == name + '.hcad'
            qtbot.keyClick(editor, Qt.Key_Return)
        return interact

    with_save_dialog(qtbot, rename('Untitled', 'Gearbox'))
    qtbot.keyClick(w, Qt.Key_S, Qt.ControlModifier)
    original = models_directory / 'Gearbox.hcad'
    assert w.document.path == original
    assert w.windowTitle().endswith('Gearbox.hcad') and not w.document.dirty
    w.activateWindow()
    qtbot.waitUntil(w.isActiveWindow)

    def unexpected(*args):
        pytest.fail('Ctrl+S opened Save As for a named document')

    w.fields['height'].setValue(45)
    with monkeypatch.context() as patch:
        patch.setattr(w, 'select_document_save_path', unexpected)
        qtbot.keyClick(w, Qt.Key_S, Qt.ControlModifier)
    assert Document.load(original).parameters.height == 45

    w.fields['height'].setValue(53)
    with_save_dialog(qtbot, rename('Gearbox', 'RotaryAdapter'))
    qtbot.keyClick(w, Qt.Key_S, Qt.ControlModifier | Qt.ShiftModifier)
    copy = models_directory / 'RotaryAdapter.hcad'
    assert w.document.path == copy and not w.document.dirty
    assert Document.load(copy).parameters.height == 53
    assert Document.load(original).parameters.height == 45


@pytest.mark.parametrize(('entered', 'filename'), [
    ('Bracket', 'Bracket.hcad'),
    ('Bracket.hcad', 'Bracket.hcad'),
    ('Bracket.HCAD', 'Bracket.HCAD'),
    ('Bracket.starcad', None),
    ('.hcad', None),
    ('', None),
])
def test_save_dialog_extension_handling(qtbot, models_directory, monkeypatch, entered, filename):
    from PySide6.QtCore import Qt

    w = window(qtbot)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))

    def enter_name(dialog, editor):
        editor.setText(entered)
        qtbot.keyClick(editor, Qt.Key_Return)
        assert dialog.isVisible() == (filename is None)

    with_save_dialog(qtbot, enter_name)
    assert w.save_document() == (filename is not None)
    if filename:
        assert w.document.path == models_directory / filename
        assert Document.load(w.document.path).features == w.document.features
        assert list(models_directory.iterdir()) == [w.document.path]
    else:
        assert w.document.path is None
        assert not list(models_directory.iterdir())
        if entered:
            assert warnings and '.hcad' in warnings[0]


def test_suffixless_save_confirms_actual_destination_once(qtbot, tmp_path):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    w = window(qtbot)
    w.document.save(tmp_path / 'original.hcad')
    destination = tmp_path / 'part.hcad'
    destination.write_text('existing file')
    prompts = []

    def enter_name(dialog, editor):
        def decline():
            prompt = QApplication.activeModalWidget()
            if isinstance(prompt, QMessageBox):
                prompts.append(prompt.text())
                prompt.button(QMessageBox.No).click()

        editor.setText('part')
        QTimer.singleShot(0, decline)
        qtbot.keyClick(editor, Qt.Key_Return)
        assert dialog.isVisible()

    with_save_dialog(qtbot, enter_name)
    assert not w.save_document(save_as=True)
    assert len(prompts) == 1 and 'part.hcad' in prompts[0]
    assert destination.read_text() == 'existing file'
    assert w.document.path == tmp_path / 'original.hcad'


def test_cancel_dialogs_leave_pending_work_and_directory_untouched(qtbot, models_directory):
    from PySide6.QtCore import Qt
    from hero_cad.ui.main_window import LAST_DOCUMENT_DIRECTORY

    w = window(qtbot)
    doc = w.document
    w.fields['width'].setValue(71)
    with_save_dialog(qtbot, lambda dialog, editor: qtbot.keyClick(editor, Qt.Key_Escape))
    assert not w.save_document()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    def cancel_open():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QFileDialog)
            assert dialog.acceptMode() == QFileDialog.AcceptOpen
            assert '*.hcad' in dialog.nameFilters()[0]
        finally:
            if dialog:
                qtbot.keyClick(dialog, Qt.Key_Escape)

    w.activateWindow()
    qtbot.waitUntil(w.isActiveWindow)
    QTimer.singleShot(0, cancel_open)
    qtbot.keyClick(w, Qt.Key_O, Qt.ControlModifier)
    assert w.document is doc and doc.path is None and not doc.can_undo
    assert w.fields['width'].value() == 71 and w.windowTitle().endswith(' *')
    assert not w.preferences.contains(LAST_DOCUMENT_DIRECTORY)


@pytest.mark.parametrize(('suffix', 'payload', 'error'), [
    ('.starcad', '{"format":"star-cad"}', '.hcad'),
    ('.hcad', '{"format":"star-cad"}', 'Unsupported document format'),
    ('.hcad', '{"format":"hero-cad","units":"mm","version":99}', 'Unsupported document version'),
    ('.hcad', '{"format":"hero-cad","units":"mm","version":3,"features":[{}]}', 'Invalid document fields'),
])
def test_unsupported_open_leaves_active_document(qtbot, tmp_path, monkeypatch, suffix, payload, error):
    from hero_cad.ui.main_window import LAST_DOCUMENT_DIRECTORY

    w = window(qtbot)
    current = tmp_path / 'Current'
    current.mkdir()
    w.document.save(current / 'Current.hcad')
    w.refresh()
    w.fields['depth'].setValue(34)
    w.apply_dimensions()
    doc, title = w.document, w.windowTitle()
    bad = tmp_path / ('Bad' + suffix)
    bad.write_text(payload)
    warnings = []
    monkeypatch.setattr(w, 'select_document_open_path', lambda *args: str(bad))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: pytest.fail('Prompted before validating the file'))
    w.open_document()
    assert len(warnings) == 1 and error in warnings[0]
    assert w.document is doc and w.windowTitle() == title
    assert doc.dirty and doc.parameters.depth == 34
    assert not w.preferences.contains(LAST_DOCUMENT_DIRECTORY)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)


def test_models_directory_failure_shows_fallback(qtbot, models_directory, tmp_path, monkeypatch):
    from pathlib import Path

    home = tmp_path / 'Home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: home)
    models_directory.parent.mkdir(parents=True)
    models_directory.write_text('file blocking directory creation')
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    w = window(qtbot)

    def check_directory(dialog, editor):
        assert dialog.directory().absolutePath() == str(home)
        assert editor.text() == 'Untitled.hcad'

    with_save_dialog(qtbot, check_directory)
    assert not w.save_document()
    assert str(models_directory) in warnings[0] and str(home) in warnings[0]
    assert w.document.path is None and not list(home.iterdir())


def test_failed_atomic_replace_preserves_savepoint_and_directory(qtbot, tmp_path, monkeypatch):
    from hero_cad.ui.main_window import LAST_DOCUMENT_DIRECTORY

    w = window(qtbot)
    path = tmp_path / 'Original.hcad'
    w.document.save(path)
    previous = path.read_bytes()
    other_directory = tmp_path / 'Other'
    other_directory.mkdir()
    destination = other_directory / path.name
    destination.write_bytes(previous)
    w.preferences.setValue(LAST_DOCUMENT_DIRECTORY, str(tmp_path))
    w.fields['width'].setValue(73)
    warnings = []

    def fail_replace(*args):
        raise OSError('simulated replace failure')

    monkeypatch.setattr('hero_cad.document.os.replace', fail_replace)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(w, 'select_document_save_path', lambda *args: str(destination))
    assert not w.save_document(save_as=True)
    assert warnings == ['simulated replace failure']
    assert path.read_bytes() == previous and destination.read_bytes() == previous
    assert list(other_directory.iterdir()) == [destination]
    assert w.document.path == path and w.document.dirty
    assert w.document.parameters.width == 73 and w.windowTitle().endswith(' *')
    assert w.preferences.value(LAST_DOCUMENT_DIRECTORY) == str(tmp_path)


def test_multi_profile_save_reopens_after_restart(qtbot, tmp_path, monkeypatch):
    import json
    import subprocess
    import sys
    from math import pi

    from hero_cad.features import ProfileReference
    from hero_cad.sketch import Circle, Rectangle
    from hero_cad.ui.main_window import LAST_DOCUMENT_DIRECTORY

    w = window(qtbot)
    d = w.document
    box = d.features[0].id
    sketch = d.add_sketch('XY')
    entities = (Circle(6, 7, 2), Rectangle(14, 5, 4, 5))
    for entity in entities:
        d.add_entity(sketch, entity)
    extrusion = d.add_multi_extrusion(
        sketch, tuple(ProfileReference(e.id) for e in entities), 3,
        operation='cut', target_id=box)
    w.refresh()
    project = tmp_path / 'Project'
    project.mkdir()
    path = project / 'Pockets.HCAD'
    monkeypatch.setattr(w, 'select_document_save_path', lambda *args: str(path))
    assert w.save_document()
    assert w.preferences.value(LAST_DOCUMENT_DIRECTORY) == str(project)
    saved = json.loads(path.read_text())
    assert saved['format'] == 'hero-cad' and saved['version'] == 15

    script = """
import json
import sys
from pathlib import Path
from OCP.BRepCheck import BRepCheck_Analyzer
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from hero_cad.booleans import bounds
from hero_cad.geometry import volume
from hero_cad.persistence import serialize
from hero_cad.ui.main_window import MainWindow

app = QApplication([])
window = MainWindow(settings=QSettings(sys.argv[1], QSettings.IniFormat))
project_file, extrusion = Path(sys.argv[2]), sys.argv[3]

def choose_file(directory):
    assert directory == project_file.parent
    return str(project_file)

window.select_document_open_path = choose_file
window.open_document()
assert window.document.path == project_file
assert not window.document.dirty and not window.document.can_undo
assert window.windowTitle().endswith(project_file.name)
assert window.document.active_body_ids == {extrusion}
assert all(status.valid for status in window.document.statuses.values())
shape = window.document.solid_shapes[extrusion]
assert BRepCheck_Analyzer(shape).IsValid()
print(json.dumps({'document': serialize(window.document.features),
                  'volume': volume(shape), 'bounds': bounds(shape)}))
window.close()
"""
    result = subprocess.run(
        [sys.executable, '-c', script, w.preferences.fileName(), str(path), extrusion],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    reopened = json.loads(result.stdout)
    assert reopened['document'] == saved
    assert reopened['volume'] == pytest.approx(24000 - 3 * (4 * pi + 20))
    assert reopened['bounds'] == pytest.approx([0, 40, 0, 30, 0, 20])


def test_open_updates_directory_and_current_document_has_priority(qtbot, tmp_path, monkeypatch):
    from hero_cad.ui.main_window import LAST_DOCUMENT_DIRECTORY

    w = window(qtbot)
    saved_dir = tmp_path / 'Last'
    saved_dir.mkdir()
    w.preferences.setValue(LAST_DOCUMENT_DIRECTORY, str(saved_dir))
    current = tmp_path / 'Current'
    current.mkdir()
    w.document.save(current / 'Original.hcad')
    opened = tmp_path / 'Opened'
    opened.mkdir()
    destination = opened / 'Another.hcad'
    Document(BoxParameters(width=67)).save(destination)

    (opened / 'Legacy.starcad').write_text('old document')

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QLineEdit, QListView

    def choose_file():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QFileDialog)
            assert dialog.windowTitle() == 'Open HERO-CAD document'
            assert dialog.testOption(QFileDialog.DontUseNativeDialog)
            assert dialog.fileMode() == QFileDialog.ExistingFile
            assert '*.hcad' in dialog.nameFilters()[0]
            assert dialog.directory().absolutePath() == str(current)
            editor = dialog.findChild(QLineEdit, 'fileNameEdit')
            editor.setFocus()
            editor.setText(str(opened))
            qtbot.keyClick(editor, Qt.Key_Return)
            assert dialog.directory().absolutePath() == str(opened)

            dialog.setViewMode(QFileDialog.List)
            view = dialog.findChild(QListView, 'listView')
            model = view.model()
            root = view.rootIndex()
            qtbot.waitUntil(lambda: model.rowCount(root) > 0)
            files = {model.index(row, 0, root).data(): model.index(row, 0, root)
                     for row in range(model.rowCount(root))}
            assert 'Legacy.starcad' not in files
            index = files[destination.name]
            view.scrollTo(index)
            position = view.visualRect(index).center()
            qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=position)
            qtbot.mouseDClick(view.viewport(), Qt.LeftButton, pos=position)
            assert not dialog.isVisible()
        finally:
            if dialog and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, choose_file)
    w.open_document()
    assert w.document.path == destination and w.document.parameters.width == 67
    assert w.preferences.value(LAST_DOCUMENT_DIRECTORY) == str(opened)
    w.new_document()

    def cancel_save(directory, filename):
        assert directory == opened and filename == 'Untitled.hcad'
        return None

    monkeypatch.setattr(w, 'select_document_save_path', cancel_save)
    assert not w.save_document()


def test_document_dialogs_share_palette_and_contrast_without_changing_file(qtbot, tmp_path):
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QLabel, QLineEdit, QListView, QDialogButtonBox
    from hero_cad.palette import CONTRAST, ENABLED, PREFIX
    from hero_cad.ui.document_dialog import DocumentDialog, SaveDocumentDialog

    w = window(qtbot)
    path = tmp_path / 'Adapter.hcad'
    w.document.save(path)
    original = path.read_bytes()
    dialogs = (DocumentDialog(w, tmp_path), SaveDocumentDialog(w, tmp_path, path.name))
    def cancel_button(dialog):
        return dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel)

    def button_fill(dialog):
        image = cancel_button(dialog).grab().toImage()
        return image.pixelColor(5, image.height() // 2)

    defaults = []
    for dialog in dialogs:
        qtbot.addWidget(dialog)
        assert dialog.testOption(QFileDialog.DontUseNativeDialog)
        dialog.show()
        qtbot.waitExposed(dialog)
        defaults.append(button_fill(dialog))
    assert defaults[0] == defaults[1]

    colors = {
        'dialogs.background': '#182839',
        'ui.text': '#202D3A',
        'controls.input': '#1D334B',
        'controls.input_text': '#25364C',
        'controls.normal': '#34254C',
        'controls.text': '#392747',
        'controls.selection': '#59353C',
        'controls.selection_text': '#623741',
        'controls.focus': '#E6B680',
    }

    for mode in ('Manual', 'Automatic'):
        w.preference_store.set_many({**{PREFIX+key: value for key, value in colors.items()},
                                     ENABLED: True, CONTRAST: mode})
        for dialog in dialogs:
            dialog.activateWindow()
            qtbot.waitUntil(dialog.isActiveWindow)
            label = dialog.findChild(QLabel, 'fileNameLabel')
            editor = dialog.findChild(QLineEdit, 'fileNameEdit')
            view = dialog.findChild(QListView, 'listView')
            button = cancel_button(dialog)
            editor.setFocus()
            qtbot.waitUntil(editor.hasFocus)
            editor.setText('Adapter.hcad')
            editor.selectAll()

            def foreground(key):
                return QColor(colors[key] if mode == 'Manual' else '#FFFFFF')

            assert dialog.palette().color(QPalette.Window) == QColor(colors['dialogs.background'])
            assert label.palette().color(QPalette.WindowText) == foreground('ui.text')
            assert editor.palette().color(QPalette.Base) == QColor(colors['controls.input'])
            assert editor.palette().color(QPalette.Text) == foreground('controls.input_text')
            assert button.palette().color(QPalette.Button) == QColor(colors['controls.normal'])
            assert button.palette().color(QPalette.ButtonText) == foreground('controls.text')
            for widget in (editor, view):
                assert widget.palette().color(QPalette.Highlight) == QColor(colors['controls.selection'])
                assert widget.palette().color(QPalette.HighlightedText) == foreground('controls.selection_text')

            # Sample the painted input border, selected text area and button fill.
            image = editor.grab().toImage()
            assert image.pixelColor(image.width() // 2, 0) == QColor(colors['controls.focus'])
            assert QColor(colors['controls.selection']).rgb() in {
                image.pixel(x, image.height() // 2) for x in range(image.width())}
        # Qt's button style shades the fill. Check the actual color changes
        # from the default and that the two dialogs paint it the same way.
        fills = [button_fill(dialog) for dialog in dialogs]
        assert fills != defaults and fills[0] == fills[1]

    for dialog in dialogs:
        dialog.reject()
    assert not w.document.dirty and w.document.path == path
    w.document.save(path)
    assert path.read_bytes() == original

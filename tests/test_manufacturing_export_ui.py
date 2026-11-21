from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QMessageBox
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
import pytest

from hero_cad.face_history import subshapes
from hero_cad.ui.display_geometry import Selection
from hero_cad.ui.export_dialog import ExportDialog
from hero_cad.ui.main_window import LAST_DOCUMENT_DIRECTORY, LAST_EXPORT_DIRECTORY
from test_manufacturing_export import model, read_step, read_stl
from test_sketch_ui import window


def export_action(w, format_name):
    file_menu = next(menu for menu in w.menuBar().findChildren(QMenu) if menu.title() == '&File')
    export_menu = next(menu for menu in file_menu.findChildren(QMenu) if menu.title() == '&Export')
    return next(action for action in export_menu.actions() if action.text() == f'{format_name.upper()}…')


@pytest.mark.parametrize('format_name,filename', [('stl', 'fixture'), ('step', 'fixture.STP')])
def test_export_menu_dialog_keeps_selection_visibility_and_save_state(qtbot, tmp_path, format_name, filename):
    w = window(qtbot)
    w.document, (box, cylinder) = model('disconnected')
    native_dir = tmp_path/'native'
    native_dir.mkdir()
    w.document.save(native_dir/'part.hcad')
    w.remember_document_directory()
    native_bytes = w.document.path.read_bytes()
    w.refresh()
    w.show_base_box.setChecked(False)
    w.browser.setCurrentItem(w.browser_items['extrude', cylinder])
    before = w.document.features, tuple(w.document._undo), tuple(w.document._redo), w.document.path
    selected = w.selected_keys()
    views = []

    def accept_export():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ExportDialog)
        views.append((dialog.scope.currentText(), dialog.quality.currentText() if dialog.quality else None))
        dialog.setDirectory(str(tmp_path))
        dialog.findChild(QLineEdit, 'fileNameEdit').setText(filename)
        dialog.accept()

    QTimer.singleShot(0, accept_export)
    export_action(w, format_name).trigger()
    assert views == [('Selected bodies (1)', 'Standard' if format_name == 'stl' else None)]
    if format_name == 'stl':
        assert read_stl(tmp_path/'fixture.stl')[0] == pytest.approx((-61, -49, -23, -11, 0, 8), abs=0.08)
    else:
        assert len(read_step(tmp_path/filename)) == 1
    assert w.selected_keys() == selected
    assert not w.show_base_box.isChecked()
    assert not w.document.dirty
    assert (w.document.features, tuple(w.document._undo), tuple(w.document._redo), w.document.path) == before
    assert w.document.path.read_bytes() == native_bytes
    assert w.preferences.value(LAST_DOCUMENT_DIRECTORY) == str(native_dir)
    assert w.preferences.value(LAST_EXPORT_DIRECTORY) == str(tmp_path)


def test_export_resolves_faces_and_edges_and_all_includes_hidden_current_bodies(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    w.document, (box, cylinder) = model('disconnected')
    w.refresh()
    w.show_base_box.setChecked(False)
    body = w.document.solid_shapes[cylinder]
    w.viewport.selections = [
        Selection('face', 0, subshapes(body, TopAbs_FACE)[0]),
        Selection('edge', 0, subshapes(body, TopAbs_EDGE)[0]),
    ]
    before = list(w.viewport.selections)

    def export_all(dialog):
        assert dialog.scope.count() == 2
        return tmp_path/'all.step', False, 'Standard'

    monkeypatch.setattr(ExportDialog, 'export_options', export_all)
    assert w.export_manufacturing('step')
    assert len(read_step(tmp_path/'all.step')) == 2
    assert w.viewport.selections == before
    assert not w.show_base_box.isChecked()


def test_failed_and_cancelled_export_do_not_update_directory(qtbot, monkeypatch, tmp_path):
    w = window(qtbot)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(ExportDialog, 'export_options', lambda dialog: None)
    assert not w.export_manufacturing('stl')
    monkeypatch.setattr(ExportDialog, 'export_options',
                        lambda dialog: (tmp_path/'missing'/'part', False, 'Standard'))
    assert not w.export_manufacturing('stl')
    assert len(warnings) == 1 and 'missing' in warnings[0]
    assert w.preferences.value(LAST_EXPORT_DIRECTORY) is None


def test_pending_property_edits_are_not_committed(qtbot, monkeypatch):
    w = window(qtbot)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    w.fields['width'].setValue(w.document.parameters.width + 1)
    before = w.document.features
    assert not w.export_manufacturing('stl')
    assert 'pending property edits' in warnings[0]
    assert w.document.features == before and not w.document.dirty
    assert w.has_pending_edits()


def test_export_dialog_requires_one_filename(qtbot, tmp_path):
    dialog = ExportDialog(None, tmp_path, 'part', 'stl', 0, 1)
    qtbot.addWidget(dialog)
    entry = dialog.findChild(QLineEdit, 'fileNameEdit')
    entry.setText('"first.stl" "second.stl"')
    assert len(dialog.selectedFiles()) == 2
    dialog.accept()
    assert dialog.result() == 0

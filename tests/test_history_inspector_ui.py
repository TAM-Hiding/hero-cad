from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from hero_cad.document import Document
from hero_cad.history_inspection import feature_history_text
from hero_cad.sketch import Circle
from test_history_inspection import chain
from test_sketch_ui import window


def select(w, identifier):
    feature = w.document.feature(identifier)
    w.browser.setCurrentItem(w.browser_items[(feature.type, identifier)])


def test_actual_browser_inspection_preserves_document_and_editing(qtbot, monkeypatch):
    w = window(qtbot)
    w.document, box, sketch, circle, cut = chain()
    w.refresh()
    doc = w.document
    state = dict(doc.__dict__)
    stacks = list(doc._undo), list(doc._redo)
    def forbidden(*args, **kwargs):
        raise AssertionError('Selection/inspection must not regenerate')
    with monkeypatch.context() as m:
        m.setattr(Document, '_regenerate', forbidden)
        w.property_tabs.setCurrentIndex(1)
        for identifier in (box, sketch, cut):
            select(w, identifier)
            assert w.history_inspector.toPlainText() == feature_history_text(doc, identifier)
        assert w.history_inspector.isReadOnly()
        qtbot.keyClicks(w.history_inspector, 'cannot edit')
        assert w.history_inspector.toPlainText() == feature_history_text(doc, cut)
        assert doc.__dict__ == state and (doc._undo, doc._redo) == stacks
    # Entity selections inspect their owning feature, retaining existing editors.
    w.browser.setCurrentItem(w.browser_items[('entity', sketch, circle.id)])
    assert w.history_inspector.toPlainText() == feature_history_text(doc, sketch)
    w.activateWindow()
    qtbot.waitUntil(w.isActiveWindow)
    w.focus_parameters()  # Existing Edit Parameters action reveals its editor.
    assert w.property_tabs.currentIndex() == 0
    qtbot.waitUntil(next(iter(w.entity_fields.values())).hasFocus)
    w.entity_fields['radius'].setValue(3)
    qtbot.mouseClick(w.entity_apply, Qt.LeftButton)
    assert doc.feature(sketch).parameters.entities[0].radius == 3
    select(w, cut)
    assert w.entity_context == ('extrude', cut)
    assert not w.entity_fields['distance'].isEnabled()  # Through All unchanged.
    w.browser.setCurrentItem(w.browser_items[('plane', 'XY')])
    assert not w.history_inspector.toPlainText()


def test_updates_through_creation_deletion_undo_redo_and_file_actions(qtbot, tmp_path, monkeypatch):
    w = window(qtbot)
    w.document, box, sketch, circle, cut = chain()
    w.refresh()
    w.property_tabs.setCurrentIndex(1)
    select(w, cut)
    original = w.history_inspector.toPlainText()
    f = w.document.feature(cut)
    w.document.replace_feature(replace(f, parameters=replace(f.parameters, direction=1)))
    w.refresh()
    assert 'Status: Unresolved' in w.history_inspector.toPlainText()
    assert w.document.statuses[cut].error in w.history_inspector.toPlainText()
    w.undo()
    assert w.history_inspector.toPlainText() == original
    w.redo()
    failed = w.history_inspector.toPlainText()
    assert 'Status: Unresolved' in failed
    path = tmp_path / 'inspected.starcad'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (str(path), ''))
    assert w.save_document()
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(path), ''))
    w.open_document()
    assert w.history_inspector.toPlainText() == failed
    assert not w.document.dirty
    w.document.delete(features=(cut,))
    w.refresh()
    assert w.browser_key == ('box', box)
    assert 'History position: 1 of 2' in w.history_inspector.toPlainText()
    assert '#3 · Extrusion' not in w.history_inspector.toPlainText()
    w.undo()
    select(w, cut)
    assert w.history_inspector.toPlainText() == failed
    w.new_document()
    assert 'History position: 1 of 1' in w.history_inspector.toPlainText()
    assert cut not in w.history_inspector.toPlainText()
    sid = w.document.add_sketch('YZ')
    w.refresh()
    select(w, sid)
    assert 'History position: 2 of 2' in w.history_inspector.toPlainText()


def test_visibility_fast_path_and_scrollable_history(qtbot):
    w = window(qtbot)
    sid = w.document.add_sketch('XY')
    w.document.add_entity(sid, Circle(0, 0, 2))
    w.refresh()
    select(w, sid)
    w.property_tabs.setCurrentIndex(1)
    item = w.browser_items[('sketch', sid)]
    rect = w.browser.visualItemRect(item)
    from PySide6.QtCore import QPoint
    point = QPoint(w.browser.columnViewportPosition(1) + 15, rect.center().y())
    qtbot.mouseClick(w.browser.viewport(), Qt.LeftButton, pos=point)
    assert 'Hidden (display only' in w.history_inspector.toPlainText()
    assert 'Status: Valid' in w.history_inspector.toPlainText()
    w.history_inspector.resize(200, 100)
    assert w.history_inspector.verticalScrollBar().maximum() > 0
    w.history_inspector.verticalScrollBar().setValue(10)
    previous = w.history_inspector.verticalScrollBar().value()
    w.update_history_inspector()
    assert w.history_inspector.verticalScrollBar().value() == previous


def test_joined_history_failure_and_recovery_stays_synchronized(qtbot):
    from test_history_inspection import joined_transition_chain, convert_to_join
    w = window(qtbot)
    w.document, box, source, extrusion, attached, cut = joined_transition_chain()
    w.refresh()
    w.property_tabs.setCurrentIndex(1)
    select(w, attached)
    original = w.history_inspector.toPlainText()
    convert_to_join(w.document, box, source, extrusion)
    w.refresh()
    assert 'Status: Unresolved' in w.history_inspector.toPlainText()
    assert w.document.statuses[attached].error in w.history_inspector.toPlainText()
    w.undo()
    assert w.history_inspector.toPlainText() == original
    w.redo()
    select(w, cut)
    assert 'Status: Blocked by unresolved dependencies' in w.history_inspector.toPlainText()
    select(w, extrusion)
    assert '#4 · Sketch 2 — Supporting face · End Face' in w.history_inspector.toPlainText()
    assert '#5 · Extrusion 2 — Boolean target body · Cut' in w.history_inspector.toPlainText()

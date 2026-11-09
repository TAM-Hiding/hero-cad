"""Real pointer selection, complete previews and transactional publication."""
from dataclasses import replace
from math import pi
import numpy as np
import pytest
from PySide6.QtCore import Qt
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.sketch import Circle
from test_sketch_ui import window, enter, click
from test_sketch_visibility import capture


def selected_window(qtbot, count=6):
    w = window(qtbot)
    w.tool_island.set_collapsed(True)
    sid = enter(w)
    circles = tuple(Circle(x, y, 2) for y in (8, 20) for x in (6, 18, 30))
    for circle in circles:
        w.document.add_entity(sid, circle)
    w.refresh(fit=True)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.profile_action.setChecked(True)
    for circle in circles[:count]:
        click(qtbot, v, frame, (circle.x, circle.y), Qt.ShiftModifier)
    assert len(v.profiles.selections) == count
    return w, sid, circles, frame


def open_cut(w, distance=3):
    w.extrude_action.trigger()
    p = w.operation_panel
    p.preview_timer.stop()
    p.operation.setCurrentIndex(p.operation.findData('cut'))
    p.target.setCurrentIndex(p.target.findData(w.document.features[0].id))
    p.quick_distance.setText(str(distance))
    p.preview_timer.stop()
    return p


def test_shift_add_toggle_replace_clear_escape_and_all_region_highlights(qtbot):
    w, sid, circles, frame = selected_window(qtbot)
    v, d = w.viewport, w.document
    before, undo = d.features, tuple(d._undo)
    assert v.profiles.actor.GetVisibility()
    mesh = v.profiles.mapper.GetInput()
    assert mesh.GetNumberOfCells() > 0
    # Orange fill exists at each selected center, including after camera zoom.
    from test_sketch_ui import pixel
    for scale in (1, .8):
        camera = v.renderer.GetActiveCamera()
        camera.SetParallelScale(camera.GetParallelScale()*scale)
        image = capture(v)
        for c in circles:
            point = pixel(v, frame.to_world((c.x, c.y)))
            patch = image[image.shape[0]-1-point.y()-2:image.shape[0]-1-point.y()+3,
                          point.x()-2:point.x()+3]
            assert np.any((patch[...,0] > patch[...,2]+40) & (patch[...,1] > patch[...,2]+20))
    click(qtbot, v, frame, (6, 8), Qt.ShiftModifier)
    assert len(v.profiles.selections) == 5
    click(qtbot, v, frame, (6, 8), Qt.ShiftModifier)
    assert len(v.profiles.selections) == 6
    click(qtbot, v, frame, (18, 8))
    assert len(v.profiles.selections) == 1 and v.profiles.selection[1].outer_id == circles[1].id
    click(qtbot, v, frame, (38, 28), Qt.ShiftModifier)
    assert len(v.profiles.selections) == 1
    click(qtbot, v, frame, (38, 28))
    assert not v.profiles.selections and not v.profiles.actor.GetVisibility()
    click(qtbot, v, frame, (6, 8))
    qtbot.keyClick(v, Qt.Key_Escape)
    assert not v.profiles.selections and not v.profiles.actor.GetVisibility()
    assert d.features == before and tuple(d._undo) == undo


def test_six_profile_preview_cancel_apply_reuse_edit_and_history(qtbot, tmp_path, monkeypatch):
    w, sid, circles, frame = selected_window(qtbot)
    v, d = w.viewport, w.document
    before, history, original_mesh = d.features, tuple(d._undo), v.mapper.GetInput()
    selected = v.profiles.selections
    p = open_cut(w)
    assert v.profiles.selections == selected and len(p.definition().parameters.profiles) == 6
    assert p.preview()
    assert volume(p.candidate.shape) == pytest.approx(24000-72*pi)
    assert p.mapper.GetInput().GetNumberOfCells() > 0
    p.cancel()
    assert d.features == before and tuple(d._undo) == history and v.mapper.GetInput() is original_mesh
    assert not v.profiles.selections and not v.profiles.actor.GetVisibility()
    assert not p.actor.GetVisibility() and p.candidate is None
    w.profile_action.setChecked(True)
    for c in circles:
        click(qtbot, v, frame, (c.x, c.y), Qt.ShiftModifier)
    p = open_cut(w)
    assert p.preview()
    def fail(*args, **kw): raise AssertionError('Apply must reuse the evaluated preview')
    with monkeypatch.context() as patch:
        patch.setattr(Document, '_regenerate', fail)
        assert p.commit()
    eid = d.features[-1].id
    assert len(d.features) == len(before)+1 and len(d._undo) == len(history)+1
    assert not v.profiles.selections and not v.profiles.actor.GetVisibility()
    assert volume(d.shape) == pytest.approx(24000-72*pi)
    pixels = capture(v)
    assert np.count_nonzero((pixels[...,0] > 65) & (pixels[...,2] > pixels[...,0]+10)
                            & (pixels[...,1] > pixels[...,0]+5)) > 100
    w.undo(); assert d.features == before
    w.redo(); assert d.features[-1].id == eid
    d.save(tmp_path/'multi.hcad')
    assert Document.load(d.path).features == d.features
    w.browser.setCurrentItem(w.browser_items[('extrude', eid)])
    w.edit_operation()
    assert len(p.definition().parameters.profiles) == 6
    p.distance.setValue(4)
    assert p.preview() and p.commit()
    assert volume(d.shape) == pytest.approx(24000-96*pi)
    # Auto-hidden sketches are still explicitly inspectable/reusable.
    w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
    w.edit_sketch()
    assert d.feature(sid).parameters.entities == circles
    w.profile_action.setChecked(True)
    click(qtbot, v, frame, (6, 8))
    assert v.profiles.selection[1].outer_id == circles[0].id


@pytest.mark.parametrize('stage', ['invalid_new', 'invalid_cut', 'display'])
def test_failed_multi_preview_or_apply_preserves_native_display_history_and_selection(qtbot, monkeypatch, stage):
    w, sid, circles, frame = selected_window(qtbot)
    v, d = w.viewport, w.document
    before, native, mesh, history = d.features, d.shape, v.mapper.GetInput(), tuple(d._undo)
    selected = v.profiles.selections
    p = open_cut(w)
    if stage == 'invalid_new':
        p.operation.setCurrentIndex(p.operation.findData('new'))
        assert not p.preview()
        assert 'Cut or Join' in p.feedback.text()
    elif stage == 'invalid_cut':
        p.quick_distance.setText('-3')
        assert not p.preview()
    else:
        assert p.preview()
        def fail(*args, **kw): raise ValueError('Injected multi-profile display preparation failure')
        monkeypatch.setattr(w, 'prepare_document_display', fail)
        assert not p.commit()
    assert d.features == before and d.shape.IsSame(native) and tuple(d._undo) == history
    assert v.mapper.GetInput() is mesh and v.profiles.selections == selected
    assert not p.actor.GetVisibility() and p.candidate is None
    p.cancel()


def test_source_edit_undo_exit_and_document_replacement_clear_selection(qtbot):
    w, sid, circles, frame = selected_window(qtbot)
    v = w.viewport
    w.edit_document(lambda d:d.update_entity(sid, replace(circles[-1], radius=3)))
    w.refresh()
    assert not v.profiles.selections and not v.profiles.actor.GetVisibility()
    click(qtbot, v, frame, (6, 8))
    assert v.profiles.selection
    w.undo()
    assert not v.profiles.selections
    w.profile_action.setChecked(True)
    click(qtbot, v, frame, (6, 8))
    assert v.profiles.selection
    w.profile_action.setChecked(False)
    assert not v.profiles.selections
    w.profile_action.setChecked(True)
    click(qtbot, v, frame, (6, 8))
    w.document = Document()
    w.refresh(fit=True)
    assert not v.profiles.selections and not v.profiles.cache


def test_cross_sketch_policy_and_ambiguous_overlap(qtbot):
    w, sid, circles, frame = selected_window(qtbot, 0)
    w.finish_sketch()
    other = w.document.add_sketch('XY')
    w.document.add_entity(other, Circle(50, 10, 3))
    overlapping = w.document.add_sketch('XY')
    w.document.add_entity(overlapping, Circle(18, 8, 2))
    w.refresh(fit=True)
    v = w.viewport
    w.show_base_box.setChecked(False)
    v.orient('Top')
    w.profile_action.setChecked(True)
    v.profiles.scope_id = None
    click(qtbot, v, frame, (6, 8))
    assert v.profiles.selection[0] == sid
    chosen = v.profiles.selections
    click(qtbot, v, frame, (50, 10), Qt.ShiftModifier)
    assert v.profiles.selections == chosen and 'one sketch' in w.statusBar().currentMessage()
    click(qtbot, v, frame, (50, 10))
    assert v.profiles.selection[0] == other and len(v.profiles.selections) == 1
    click(qtbot, v, frame, (18, 8))
    assert not v.profiles.selections and not v.profiles.actor.GetVisibility()
    assert 'unambiguous' in w.statusBar().currentMessage()


def test_invalid_properties_distance_preserves_complete_multi_result(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    w, sid, circles, frame = selected_window(qtbot)
    p = open_cut(w)
    assert p.preview() and p.commit()
    d, v = w.document, w.viewport
    eid = d.features[-1].id
    w.browser.setCurrentItem(w.browser_items[('extrude', eid)])
    before, shape, mesh, history = d.features, d.shape, v.mapper.GetInput(), tuple(d._undo)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args))
    w.entity_fields['distance'].setValue(-3)
    assert not w.apply_dimensions() and warnings
    assert d.features == before and d.shape.IsSame(shape) and tuple(d._undo) == history
    assert v.mapper.GetInput() is mesh and d.statuses[eid].valid

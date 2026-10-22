import numpy as np
import pytest
from PySide6.QtCore import Qt
from star_cad.document import Document
from star_cad.sketch import Circle, Rectangle, FaceReference
from test_sketch_ui import window, enter, pixel, hover


def attached_plate(qtbot):
    w = window(qtbot)
    d = w.document
    source = d.add_sketch('XY')
    rect = Rectangle(0,0,50,25)
    d.add_entity(source,rect)
    eid = d.add_extrusion(source,rect.id,distance=10)
    w.refresh(fit=True)
    w.create_face_sketch(FaceReference(eid,'end'))
    return w, source, eid, w.viewport.sketch.active_id, rect


def test_settings_can_hide_only_box_without_changing_document_or_pending_fields(qtbot,tmp_path):
    w = window(qtbot)
    assert 'Settings' in [a.text().replace('&','') for a in w.menuBar().actions()]
    assert w.show_base_box.isEnabled()
    before = w.document.features
    n = len(w.document._undo)
    w.fields['width'].setValue(51)
    scale = w.viewport.renderer.GetActiveCamera().GetParallelScale()
    w.show_base_box.setChecked(False)
    assert w.viewport.mapper.GetInput().GetNumberOfCells() == 0
    assert not w.viewport.faces and not w.viewport.edges
    assert w.visible_volume == 0
    assert w.fields['width'].value() == 51  # Visibility must not discard pending edits.
    assert w.viewport.renderer.GetActiveCamera().GetParallelScale() == scale
    assert w.document.features == before and len(w.document._undo) == n and not w.document.dirty
    w.refresh()
    assert not w.show_base_box.isChecked() and w.viewport.mapper.GetInput().GetNumberOfCells() == 0
    w.document.save(tmp_path/'hidden.starcad')
    assert Document.load(w.document.path).features == before
    w.show_base_box.setChecked(True)
    assert w.viewport.mapper.GetInput().GetNumberOfCells() > 0 and w.visible_volume > 0


def test_explicit_base_visibility_survives_refresh_history_and_new_document(qtbot,monkeypatch):
    w = window(qtbot)
    w.show_base_box.setChecked(False)
    source = w.document.add_sketch('XY')
    circle = Circle(60,0,3)
    w.document.add_entity(source,circle)
    eid = w.document.add_extrusion(source,circle.id,distance=5)
    w.refresh()
    assert not w.show_base_box.isChecked()
    assert w.visible_volume == pytest.approx(45*np.pi)
    w.document.delete(features=(eid,))
    w.refresh()
    assert not w.show_base_box.isChecked() and w.visible_volume == 0
    w.undo()
    assert not w.show_base_box.isChecked() and w.visible_volume > 0
    monkeypatch.setattr(w,'confirm_replace',lambda:True)
    w.new_document()
    assert not w.show_base_box.isChecked() and w.visible_volume == 0


def test_face_sketch_keeps_solids_and_other_sketches_as_read_only_context(qtbot):
    w,source,eid,sid,rect = attached_plate(qtbot)
    v,d = w.viewport,w.document
    assert v.actor.GetVisibility() and v.edge_actor.GetVisibility()
    assert v.actor.GetProperty().GetOpacity() == .35
    assert (source,rect.id) in v.sketch.mapping
    point = pixel(v,d.feature(source).parameters.frame.to_world((25,0)))
    x,y = point.x()*v.GetRenderWindow().GetSize()[0]/v.width(), v.GetRenderWindow().GetSize()[1]-1-point.y()*v.GetRenderWindow().GetSize()[1]/v.height()
    assert v.sketch.hit(x,y) is None  # Visible source geometry cannot be edited here.
    before = d.features
    w.tool_choice.setCurrentText('Circle')
    frame = d.feature(sid).parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((10,10))))
    hover(v,pixel(v,frame.to_world((13,10))))
    w.show_base_box.setChecked(True)
    assert v.sketch.controller.tool and v.sketch.preview_actor.GetVisibility()
    assert d.features == before  # Toggle does not commit/cancel construction.
    qtbot.mouseRelease(v,Qt.LeftButton,pos=pixel(v,frame.to_world((13,10))))
    circle = d.feature(sid).parameters.entities[0]
    assert circle.radius == pytest.approx(3,abs=.2)
    assert v.actor.GetVisibility() and (source,rect.id) in v.sketch.mapping
    w.finish_sketch()
    assert v.actor.GetProperty().GetOpacity() == 1
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.edit_sketch()
    assert v.actor.GetVisibility() and v.actor.GetProperty().GetOpacity() == .35


def test_origin_sketch_retains_isolated_editing(qtbot):
    w = window(qtbot)
    sid = enter(w)
    assert not w.viewport.actor.GetVisibility() and not w.viewport.edge_actor.GetVisibility()
    w.finish_sketch()
    assert w.viewport.actor.GetVisibility() and w.viewport.actor.GetProperty().GetOpacity() == 1


def test_reference_visibility_and_grid_with_plate_render(qtbot):
    from test_sketch_visibility import capture,cyan
    w,source,eid,sid,rect = attached_plate(qtbot)
    v = w.viewport
    w.axes_action.setChecked(False)
    # Put the plate footprint in the center of the orthographic sketch view.
    frame = w.document.feature(sid).parameters.frame
    camera = v.renderer.GetActiveCamera()
    focus = frame.to_world((25,12.5))
    camera.SetFocalPoint(*focus)
    camera.SetPosition(*(focus[i]+100*frame.normal[i] for i in range(3)))
    camera.SetParallelScale(22)
    v.clamp_zoom()
    shown = capture(v)
    assert np.count_nonzero(cyan(shown)) > 40  # Existing source rectangle.
    w.grid_action.setChecked(False)
    no_grid = capture(v)
    assert np.count_nonzero(np.max(abs(shown-no_grid),axis=2)>3) > 100
    w.grid_action.setChecked(True)
    v.actor.VisibilityOff()
    v.edge_actor.VisibilityOff()
    no_plate = capture(v)
    assert np.count_nonzero(np.max(abs(shown-no_plate),axis=2)>8) > 1000
    v.actor.VisibilityOn()
    v.edge_actor.VisibilityOn()
    w.document.add_entity(sid,Circle(15,12,3))
    w.refresh()
    assert np.count_nonzero(cyan(capture(v))) > 60
    w.finish_sketch()
    assert v.actor.GetProperty().GetOpacity() == 1


def test_hide_only_box_is_empty_render_and_restore_is_visible(qtbot):
    from test_sketch_visibility import capture
    w = window(qtbot)
    v = w.viewport
    w.axes_action.setChecked(False)
    shown = capture(v)
    w.show_base_box.setChecked(False)
    hidden = capture(v)
    assert np.count_nonzero(np.max(abs(shown-hidden),axis=2)>8) > 1000
    assert np.max(hidden,axis=(0,1))-np.min(hidden,axis=(0,1)) == pytest.approx((0,0,0),abs=2)
    w.show_base_box.setChecked(True)
    assert np.count_nonzero(np.max(abs(capture(v)-hidden),axis=2)>8) > 1000

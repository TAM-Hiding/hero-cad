import numpy as np
import pytest
from PySide6.QtCore import Qt
from hero_cad.attachments import reference_key, planar_frame
from hero_cad.document import Document
from hero_cad.sketch import Circle, FaceReference
from test_evaluated_faces import screwdriver, slot_regions, center
from test_face_attachment_ui import look, coincident
from test_sketch_ui import window, enter, pixel
from test_sketch_visibility import capture


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_origin_plane_shows_cut_body_and_editable_geometry_through_it(qtbot, plane):
    w = window(qtbot)
    w.document, source, circle, body, cutter_sketch, rectangle, result = screwdriver()
    w.refresh(fit=True)
    v, d = w.viewport, w.document
    sid = enter(w, plane)
    assert v.actor.GetVisibility() and v.edge_actor.GetVisibility()
    assert v.actor.GetProperty().GetOpacity() == .35
    assert v.edge_actor.GetProperty().GetOpacity() == 1.  # Auto keeps CAD boundaries readable.
    # The displayed mesh maps actual current output faces, never the old prism.
    assert all(any(face.IsSame(current) for current in d.face_maps[result].values())
               or not planar_is_face(face) for face in v.faces)
    w.axes_action.setChecked(False)
    w.grid_action.setChecked(False)
    frame = d.feature(sid).parameters.frame
    look(v, frame, (0, 5))
    with_body = capture(v)
    v.actor.VisibilityOff(); v.edge_actor.VisibilityOff()
    without_body = capture(v)
    assert np.count_nonzero(np.max(abs(with_body-without_body), axis=2) > 4) > 500
    v.set_solid_visibility(True)
    # Active sketch curves contribute visible pixels through the reference body.
    c = Circle(0, 5, 2)
    d.add_entity(sid, c)
    w.refresh()
    shown = capture(v)
    v.sketch.actor.VisibilityOff()
    hidden = capture(v)
    assert np.count_nonzero(np.max(abs(shown-hidden), axis=2) > 4) > 50
    v.sketch.actor.VisibilityOn()
    p = pixel(v, frame.to_world((2, 5)))
    x, y = p.x()*v.GetRenderWindow().GetSize()[0]/v.width(), v.GetRenderWindow().GetSize()[1]-1-p.y()*v.GetRenderWindow().GetSize()[1]/v.height()
    assert v.sketch.hit(x, y) == (sid, c.id)
    # Visibility preferences continue filtering the displayed geometry in edit.
    box_face_count = len(v.faces)
    w.show_base_box.setChecked(True)
    assert len(v.faces) == box_face_count+6
    w.show_base_box.setChecked(False)
    assert len(v.faces) == box_face_count
    assert v.actor.GetProperty().GetOpacity() == .35
    w.finish_sketch()
    assert v.actor.GetProperty().GetOpacity() == 1


def planar_is_face(face):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    return BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane


@pytest.mark.parametrize('separate_tool', [False, True])
def test_current_split_faces_right_click_repeat_reenter_save_and_history(qtbot, separate_tool, tmp_path):
    w = window(qtbot)
    w.document, source, circle, body, cutter_sketch, rectangle, result = screwdriver(separate_tool=separate_tool)
    w.refresh(fit=True)
    v, d = w.viewport, w.document
    refs, sketches = [], []
    # Actual viewport picks on both disjoint top regions and the slot floor.
    # Repeat the first region as well: faces never acquire an occupied flag.
    for index in (0, 1, 2, 0):
        face = slot_regions(d, result, source)[index]
        frame = planar_frame(face)
        point = look(v, frame, frame.to_local(center(face)))
        v.set_selection_mode('edge')
        qtbot.mouseClick(v, Qt.RightButton, pos=pixel(v, point))
        assert [a.text() for a in w._context_menu.actions()] == ['New Sketch']
        w._context_menu.actions()[0].trigger()
        w._context_menu.close()
        sid = v.sketch.active_id
        p = d.feature(sid).parameters
        assert p.attachment.parent_id == result
        coincident(p.frame, face)
        assert v.actor.GetVisibility() and v.actor.GetProperty().GetOpacity() == .35
        assert v.renderer.GetActiveCamera().GetDirectionOfProjection() == pytest.approx(tuple(-n for n in p.frame.normal))
        assert 'Evaluated Planar Face' in w.property_info.text()
        refs.append(p.attachment)
        sketches.append(sid)
        # Offset from the next face-pick point so curves don't cover the target.
        d.add_entity(sid, Circle(30, 30, .5))
        w.refresh()
        w.finish_sketch()
    # Each click has its own source-local witness; current face identity still
    # agrees even if pixel rounding changes the point between camera fits.
    identities = [(ref.parent_id, reference_key(ref)) for ref in refs]
    assert identities[0] == identities[-1] and len(set(identities)) == 3
    assert all(ref.support is not None for ref in refs) and len(set(sketches)) == 4
    before = d.features
    w.undo(); w.redo()
    assert d.features == before
    for sid in sketches:
        w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
        w.edit_sketch()
        assert v.sketch.active_id == sid
        w.finish_sketch()

    d.save(tmp_path / 'faces.starcad')
    loaded = Document.load(d.path)
    assert loaded.features == d.features
    w.document = loaded
    w.refresh(fit=True)
    assert v.sketch.active_id is None
    for sid in sketches:
        w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
        w.edit_sketch()
        assert v.sketch.active_id == sid
        w.finish_sketch()


def test_finished_curve_context_still_offers_new_sketch_on_underlying_face(qtbot):
    w = window(qtbot)
    d, v = w.document, w.viewport
    ref = FaceReference(d.features[0].id, '+Z')
    first = d.add_face_sketch(ref)
    circle = Circle(10, 10, 3)
    d.add_entity(first, circle)
    w.refresh()
    frame = d.feature(first).parameters.frame
    point = look(v, frame, (13, 10))
    qtbot.mouseClick(v, Qt.RightButton, pos=pixel(v, point))
    assert [a.text() for a in w._context_menu.actions()] == ['Edit Parameters', 'Edit Sketch', 'Delete', 'New Sketch']
    w._context_menu.actions()[-1].trigger()
    w._context_menu.close()
    second = v.sketch.active_id
    assert second != first and d.feature(second).parameters.attachment == ref
    assert d.feature(first).parameters.entities == (circle,)

from dataclasses import replace
import numpy as np
import pytest
from PySide6.QtCore import Qt
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.sketch import Circle, Rectangle, FaceReference
from hero_cad.attachments import planar_frame
from test_sketch_ui import window, pixel, hover
from test_sketch_editing_ui import type_dimension
from test_face_attachments import compound_fixture, coincident


def look(v, frame, uv=(10,10)):
    camera = v.renderer.GetActiveCamera()
    point = frame.to_world(uv)
    camera.SetFocalPoint(*point)
    camera.SetPosition(*(point[i]+frame.normal[i]*150 for i in range(3)))
    camera.SetViewUp(*frame.v)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(35)
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    return point


@pytest.mark.parametrize('name', ['+X','-X','+Y','-Y','+Z','-Z'])
def test_box_right_click_actual_face_create_exact_circle_reenter(qtbot,name,tmp_path):
    w = window(qtbot)
    v = w.viewport
    box_id = w.document.features[0].id
    face = w.document.face_maps[box_id][name]
    frame = planar_frame(face)
    # Pick the geometric center (frame origins can lie outside the bounded face).
    center = [20,15,10]
    axis = 'XYZ'.index(name[1])
    center[axis] = (40,30,20)[axis] if name[0] == '+' else 0
    point = look(v,frame,frame.to_local(center))
    v.set_selection_mode('edge')
    qtbot.mouseClick(v,Qt.RightButton,pos=pixel(v,point))
    assert [a.text() for a in w._context_menu.actions()] == ['New Sketch']
    assert v.selection.kind == 'face'
    before = w.document.features
    w._context_menu.actions()[0].trigger()
    w._context_menu.close()
    sid = v.sketch.active_id
    p = w.document.feature(sid).parameters
    assert p.attachment == FaceReference(box_id,name)
    assert w.document.features[:-1] == before
    coincident(p.frame,face)
    camera = v.renderer.GetActiveCamera()
    assert camera.GetDirectionOfProjection() == pytest.approx(tuple(-n for n in p.frame.normal))
    assert camera.GetParallelProjection()
    assert 'Box / '+name in w.property_info.text()
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,p.frame.to_world((0,0))))
    hover(v,pixel(v,p.frame.to_world((5,0))))
    type_dimension(qtbot,v,'2.1234567890123')
    qtbot.mouseRelease(v,Qt.LeftButton,pos=pixel(v,p.frame.to_world((5,0))))
    circle = w.document.feature(sid).parameters.entities[0]
    assert circle.radius == 2.1234567890123
    w.finish_sketch()
    w.document.set_box(BoxParameters(50,40,30))
    w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.edit_sketch()
    assert v.sketch.active_id == sid
    current = w.document.feature(sid).parameters
    assert current.entities == (circle,)
    coincident(current.frame,w.document.face_maps[box_id][name])
    assert v.sketch.origin_actor.GetPosition() == current.frame.origin
    w.document.save(tmp_path/'box.starcad')
    assert Document.load(w.document.path).features == w.document.features


@pytest.mark.parametrize('side', [False,True])
def test_extrusion_face_menu_slot_follow_and_undo(qtbot,side):
    w = window(qtbot)
    d,v = w.document,w.viewport
    source = d.add_sketch('XZ')
    rect = Rectangle(0,0,50,25,13)
    d.add_entity(source,rect)
    eid = d.add_extrusion(source,rect.id,distance=10)
    w.refresh(fit=True)
    key = ('side',rect.id,'edge0') if side else ('end',None,None)
    face = d.face_maps[eid][key]
    ref = d.face_reference(face)
    # Invoke the same validated context path after analytic face selection.
    w.face_context_menu((face,planar_frame(face).origin),v.mapToGlobal(pixel(v,(0,0,0))))
    w._context_menu.actions()[0].trigger()
    w._context_menu.close()
    sid = v.sketch.active_id
    frame = d.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v,Qt.LeftButton,Qt.ShiftModifier,pos=pixel(v,frame.to_world((0,0))))
    hover(v,pixel(v,frame.to_world((5,0))))
    type_dimension(qtbot,v,'2')
    qtbot.mouseRelease(v,Qt.LeftButton,pos=pixel(v,frame.to_world((5,0))))
    hover(v,pixel(v,frame.to_world((12,0))))
    type_dimension(qtbot,v,'12')
    slot = d.feature(sid).parameters.entities[0]
    assert slot.radius == 2 and slot.distance == 12
    w.finish_sketch()
    before = d.feature(sid).parameters
    d.replace_feature(replace(d.feature(eid),parameters=replace(d.feature(eid).parameters,distance=20)))
    w.refresh()
    current = d.feature(sid).parameters
    assert current.entities == before.entities
    coincident(current.frame,d.face_maps[eid][key])
    assert d.face_reference(d.face_maps[eid][key]) == ref
    w.undo()
    assert d.feature(sid).parameters == before
    w.redo()
    assert d.feature(sid).parameters == current


def test_compound_angle_face_pick_camera_and_sketch_frame(qtbot,monkeypatch):
    w = window(qtbot)
    w.document = compound_fixture(monkeypatch)
    w.refresh(fit=True)
    v,d = w.viewport,w.document
    face = d.face_maps[d.features[0].id]['+Z']
    frame = planar_frame(face)
    # Project the actual bounded-face center using mass properties.
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face,props)
    center = props.CentreOfMass()
    point = look(v,frame,frame.to_local((center.X(),center.Y(),center.Z())))
    qtbot.mouseClick(v,Qt.RightButton,pos=pixel(v,point))
    w._context_menu.actions()[0].trigger()
    w._context_menu.close()
    p = d.feature(v.sketch.active_id).parameters
    coincident(p.frame,face)
    assert all(abs(x) > .1 for x in p.frame.normal)
    assert v.renderer.GetActiveCamera().GetDirectionOfProjection() == pytest.approx(tuple(-n for n in p.frame.normal))
    assert v.renderer.GetActiveCamera().GetViewUp() == pytest.approx(frame.v)


def test_unresolved_browser_feedback_prevents_sketch_edit(qtbot):
    w = window(qtbot)
    d = w.document
    source = d.add_sketch('XY')
    rect = Rectangle(0,0,20,10)
    d.add_entity(source,rect)
    eid = d.add_extrusion(source,rect.id)
    sid = d.add_face_sketch(FaceReference(eid,'side',rect.id,'edge0'))
    d.add_entity(sid,Circle(1,2,.5))
    w.refresh()
    d.update_entity(source,Circle(0,0,5,id=rect.id))
    w.refresh()
    item = w.browser_items[('sketch',sid)]
    assert 'UNRESOLVED' in item.text(0)
    w.browser.setCurrentItem(item)
    assert 'Unresolved face' in w.property_info.text()
    w.edit_sketch()
    assert v_active(w) is None and 'Unresolved face' in w.statusBar().currentMessage()
    assert sid not in {f.id for f in w.viewport.sketch.features}


def v_active(w):
    return w.viewport.sketch.active_id


def test_moved_attachment_updates_cached_curve_and_visible_render(qtbot):
    from test_sketch_visibility import capture,cyan
    w = window(qtbot)
    d,v = w.document,w.viewport
    sid = d.add_face_sketch(FaceReference(d.features[0].id,'+Z'))
    circle = Circle(10,10,4)
    d.add_entity(sid,circle)
    w.refresh()
    # Hide solids so line displacement can be measured without occlusion.
    v.actor.VisibilityOff()
    v.edge_actor.VisibilityOff()
    look(v,planar_frame(d.face_maps[d.features[0].id]['+X']),(-10,10))
    initial_path = v.sketch.world_path(d.feature(sid),circle,64)
    initial = capture(v)
    assert np.count_nonzero(cyan(initial)) > 20
    d.set_box(BoxParameters(40,30,30))
    w.refresh()
    v.actor.VisibilityOff()
    v.edge_actor.VisibilityOff()
    moved = capture(v)
    new_path = v.sketch.world_path(d.feature(sid),circle,64)
    assert all(b[2]-a[2] == 10 for a,b in zip(initial_path,new_path))
    assert np.count_nonzero(cyan(moved)) > 20
    assert np.count_nonzero(np.max(abs(moved-initial),axis=2) > 5) > 30


def test_finished_attached_curve_visible_on_face_but_hidden_behind_solid_render(qtbot):
    from test_sketch_visibility import capture, cyan
    w = window(qtbot)
    d,v = w.document,w.viewport
    box = d.features[0].id
    top = d.add_face_sketch(FaceReference(box,'+Z'))
    d.add_entity(top,Circle(10,10,4))
    w.refresh()
    frame = d.feature(top).parameters.frame
    look(v,frame,(10,10))
    shown = capture(v)
    assert np.count_nonzero(cyan(shown)) > 50
    d.delete(features=(top,))
    bottom = d.add_face_sketch(FaceReference(box,'-Z'))
    # Bottom U=-X, V=+Y: place the circle within the box footprint.
    d.add_entity(bottom,Circle(-10,10,4))
    w.refresh()
    hidden = capture(v)
    assert np.count_nonzero(cyan(hidden)) < 5

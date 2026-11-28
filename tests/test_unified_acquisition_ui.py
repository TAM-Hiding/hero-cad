from dataclasses import replace
from math import hypot
import pytest
from PySide6.QtCore import Qt
from hero_cad.document import Document
from hero_cad.sketch import Line, Rectangle, Circle, Slot
from hero_cad.profiles import regions
from hero_cad.geometry import volume
from hero_cad.manufacturing_export import export_document
from test_sketch_ui import window, pixel, hover
from test_model_references_ui import attached, move_to


def test_completed_rectangle_and_model_share_indicators_and_input(qtbot,tmp_path):
    w = window(qtbot)
    sid = attached(w)
    v,s = w.viewport,w.viewport.sketch
    source = Rectangle(4,5,12,10)
    w.document.add_entity(sid,source)
    w.refresh()
    v.fit()
    w.tool_choice.setCurrentText('Rectangle')
    start = move_to(w,(4,5))
    assert s.snap_result.target == 'ENDPOINT' and s.snap_result.entity_id == source.id
    assert s.reference_actor.GetVisibility()
    qtbot.mousePress(v,Qt.LeftButton,pos=start)
    end = move_to(w,(20,30))
    assert s.snap_result.target == 'MODEL MIDPOINT'
    qtbot.mouseRelease(v,Qt.LeftButton,pos=end)
    rect = w.document.feature(sid).parameters.entities[-1]
    assert (rect.x,rect.y,rect.width,rect.height) == (4,5,16,25)
    assert source == w.document.feature(sid).parameters.entities[0]
    path = tmp_path/'mixed.hcad'
    w.document.save(path)
    d = Document.load(path)
    assert d.features == w.document.features
    # Two overlapping rectangles still evaluate ordinary bounded cells.
    assert regions(d.feature(sid).parameters)
    w.tool_choice.setCurrentText('Line')
    move_to(w,(10,5))
    assert s.snap_result.target == 'SKETCH MIDPOINT'
    assert s.snap_mapper.GetInput().GetNumberOfLines() == 1
    assert s.snap_result.entity_id == source.id
    assert not v.selections and s.active_id == sid


@pytest.mark.parametrize('construction',[False,True])
def test_sketch_curves_and_construction_cache_follow_edits(qtbot,monkeypatch,construction):
    import hero_cad.ui.sketch_view as module
    w = window(qtbot)
    sid = attached(w)
    v,s = w.viewport,w.viewport.sketch
    circle = Circle(12,13,4,construction=construction)
    line = Line(5,4,25,4,construction=construction)
    w.document.add_entity(sid,circle)
    w.document.add_entity(sid,line)
    w.refresh()
    v.fit()
    calls = []
    original = module.sketch_references
    def evaluated(entities):
        calls.append(1)
        return original(entities)
    monkeypatch.setattr(module,'sketch_references',evaluated)
    w.tool_choice.setCurrentText('Circle')
    for _ in range(4):
        move_to(w,(12,13))
        assert s.snap_result.target == 'CENTER' and s.snap_result.entity_id == circle.id
        move_to(w,(16,13))
        assert s.snap_result.target == 'SKETCH CURVE'
        assert hypot(s.snap_result.point[0]-circle.x,s.snap_result.point[1]-circle.y) == pytest.approx(circle.radius,abs=1e-10)
        move_to(w,(15,4))
        assert s.snap_result.target == 'SKETCH MIDPOINT'
    assert len(calls) == 1
    edited = replace(circle,x=17)
    w.document.update_entity(sid,edited)
    w.refresh()
    move_to(w,(17,13))
    assert s.snap_result.point == (17,13) and len(calls) == 2
    w.undo()
    move_to(w,(12,13))
    assert s.snap_result.point == (12,13)
    if construction:
        assert not regions(w.document.feature(sid).parameters)


@pytest.mark.parametrize('plane',['+X','+Y','+Z'])
def test_planar_loyalty_during_oblique_camera_drawing(qtbot,plane):
    w = window(qtbot)
    sid = attached(w,plane)
    v,s = w.viewport,w.viewport.sketch
    frame = s.feature.parameters.frame
    source = Line(6.123456789123,7.123456789123,14.123456789123,11.123456789123,construction=True)
    w.document.add_entity(sid,source)
    w.refresh()
    camera = v.renderer.GetActiveCamera()
    camera.Azimuth(27)
    camera.Elevation(19)
    camera.OrthogonalizeViewUp()
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    w.tool_choice.setCurrentText('Line')
    start = move_to(w,source.points[0])
    qtbot.mouseClick(v,Qt.LeftButton,pos=start)
    end = move_to(w,source.points[1])
    qtbot.mouseClick(v,Qt.LeftButton,pos=end)
    entity = w.document.feature(sid).parameters.entities[-1]
    assert entity.points == source.points
    assert w.document.feature(sid).parameters.frame == frame
    for p in entity.points:
        world = frame.to_world(p)
        assert sum((world[i]-frame.origin[i])*frame.normal[i] for i in range(3)) == pytest.approx(0,abs=1e-10)


def test_preview_never_becomes_an_acquisition_source(qtbot):
    w = window(qtbot)
    sid = attached(w)
    v,s = w.viewport,w.viewport.sketch
    v.fit()
    w.tool_choice.setCurrentText('Circle')
    frame = s.feature.parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((12,14))))
    hover(v,pixel(v,frame.to_world((17,14))))
    assert s.controller.tool.preview_entity is not None
    assert w.document.feature(sid).parameters.entities == ()
    assert s._sketch_references.points == () and s._sketch_references.arcs == ()


def test_acquired_sketch_profile_survives_reopen_and_modeling(qtbot,tmp_path):
    w = window(qtbot)
    sid = attached(w)
    v = w.viewport
    source = Line(7.123456789123,5.123456789123,21.123456789123,5.123456789123,construction=True)
    w.document.add_entity(sid,source)
    w.refresh()
    v.fit()
    w.tool_choice.setCurrentText('Rectangle')
    start = move_to(w,source.points[0])
    qtbot.mousePress(v,Qt.LeftButton,pos=start)
    end = move_to(w,(source.x2,14.123456789123))
    expected = v.sketch.snap_result.point
    qtbot.mouseRelease(v,Qt.LeftButton,pos=end)
    rect = w.document.feature(sid).parameters.entities[-1]
    assert (rect.x,rect.y) == source.points[0]
    assert rect.width == pytest.approx(expected[0]-source.x1,abs=1e-12)
    w.finish_sketch()
    path = tmp_path/'sketch-acquired.hcad'
    w.document.save(path)
    for operation,distance in (('new',2),('join',2),('cut',-2)):
        d = Document.load(path)
        kwargs = {} if operation == 'new' else dict(operation=operation,target_id=d.features[0].id)
        eid = d.add_extrusion(sid,rect.id,distance=distance,**kwargs)
        area = rect.width*rect.height
        expected_volume = {'new':area*2,'join':24000+area*2,'cut':24000-area*2}[operation]
        assert volume(d.solid_shapes[eid]) == pytest.approx(expected_volume)
        for fmt in ('stl','step'):
            export_document(d,tmp_path/f'{operation}.{fmt}',fmt,body_ids=(eid,))

import pytest
from PySide6.QtCore import QPoint, Qt
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.geometry import volume
from hero_cad.manufacturing_export import export_document
from hero_cad.sketch import Circle, Rectangle, Slot
from test_sketch_ui import window, pixel, hover
from test_face_attachments import compound_fixture


def attached(w, name='+Z'):
    d = w.document
    face = d.face_maps[d.features[0].id][name]
    sid = d.add_face_sketch(d.face_reference(face))
    w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.edit_sketch_action.trigger()
    w.viewport.sketch.guides.snap_grid = False
    w.viewport.sketch.guides.snap_origin = False
    return sid


def move_to(w, local, offset=QPoint(2,2)):
    v = w.viewport
    pos = pixel(v,v.sketch.feature.parameters.frame.to_world(local))+offset
    hover(v,pos)
    return pos


def test_corner_rectangle_save_reopen_operations_and_export(qtbot,tmp_path):
    w = window(qtbot)
    sid = attached(w)
    v = w.viewport
    w.tool_choice.setCurrentText('Rectangle')
    a,b = (0,0),(40,30)
    start = move_to(w,a)
    assert v.sketch.snap_result.point == a
    assert v.sketch.reference_actor.GetVisibility()
    qtbot.mousePress(v,Qt.LeftButton,pos=start)
    end = move_to(w,b)
    qtbot.mouseRelease(v,Qt.LeftButton,pos=end)
    rect, = w.document.feature(sid).parameters.entities
    assert (rect.x,rect.y,rect.width,rect.height) == (0,0,40,30)
    assert v.sketch.active_id == sid and not v.selections
    w.finish_sketch_action.trigger()
    assert not v.sketch.reference_actor.GetVisibility()
    path = tmp_path/'acquired.hcad'
    w.document.save(path)
    d = Document.load(path)
    assert d.features == w.document.features
    box = d.features[0].id
    for operation,distance,expected in [('new',2,2400),('join',2,26400),('cut',-2,21600)]:
        candidate = Document.load(path)
        kwargs = {} if operation == 'new' else dict(operation=operation,target_id=box)
        eid = candidate.add_extrusion(sid,rect.id,distance=distance,**kwargs)
        assert volume(candidate.solid_shapes[eid]) == pytest.approx(expected)
        candidate.undo()
        assert candidate.features == d.features
        candidate.redo()
        assert volume(candidate.solid_shapes[eid]) == pytest.approx(expected)
        for fmt in ('stl','step'):
            export_document(candidate,tmp_path/f'{operation}.{fmt}',fmt,body_ids=(eid,))


@pytest.mark.parametrize('name',['+X','-X','+Y','-Y','+Z','-Z'])
def test_midpoint_and_line_placement_on_each_face(qtbot,name):
    w = window(qtbot)
    sid = attached(w,name)
    v,s = w.viewport,w.viewport.sketch
    w.tool_choice.setCurrentText('Line')
    # Build targets through the actual event adapter, then inspect analytic data.
    move_to(w,(0,0))
    refs = s._model_references
    line = max(refs.lines,key=lambda line: sum((a-b)**2 for a,b in zip(line.a,line.b)))
    midpoint = tuple((a+b)/2 for a,b in zip(line.a,line.b))
    start = move_to(w,midpoint)
    assert s.snap_result.target == 'MODEL MIDPOINT'
    assert s.snap_result.point == midpoint
    qtbot.mouseClick(v,Qt.LeftButton,pos=start)
    along = tuple(a+.23*(b-a) for a,b in zip(line.a,line.b))
    end = move_to(w,along)
    result = s.snap_result
    assert result.target == 'MODEL EDGE'
    qtbot.mouseClick(v,Qt.LeftButton,pos=end)
    entity, = w.document.feature(sid).parameters.entities
    assert entity.points == (midpoint,result.point)
    a,b = line.a,line.b
    assert (entity.x2-a[0])*(b[1]-a[1])-(entity.y2-a[1])*(b[0]-a[0]) == pytest.approx(0,abs=1e-12)
    assert not v.selections and s.active_id == sid
    w.tool_choice.setCurrentText('Select')
    assert not s.snap_actor.GetVisibility() and not s.reference_actor.GetVisibility()


@pytest.mark.parametrize('tool',['Circle','Slot'])
def test_circular_hole_center_and_construction_tools(qtbot,tool):
    w = window(qtbot)
    d = w.document
    source = d.add_sketch('XY')
    rect,hole = Rectangle(0,0,40,30),Circle(11,12,3)
    d.add_entity(source,rect)
    d.add_entity(source,hole)
    body = d.add_extrusion(source,rect.id,(hole.id,),distance=7)
    sid = d.add_face_sketch(d.face_reference(d.face_maps[body][('end',None,None)]))
    w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.edit_sketch_action.trigger()
    v,s = w.viewport,w.viewport.sketch
    s.guides.snap_grid = False
    w.tool_choice.setCurrentText(tool)
    w.construction_action.setChecked(True)
    start = move_to(w,(11,12))
    assert s.snap_result.target == 'MODEL CENTER'
    assert s.snap_result.point == (11,12)
    qtbot.mousePress(v,Qt.LeftButton,pos=start)
    end = move_to(w,(13,12),QPoint(0,0))
    qtbot.mouseRelease(v,Qt.LeftButton,pos=end)
    if tool == 'Slot':
        end = move_to(w,(20,12),QPoint(0,0))
        qtbot.mouseClick(v,Qt.LeftButton,pos=end)
    entity, = d.feature(sid).parameters.entities
    assert isinstance(entity,Circle if tool == 'Circle' else Slot)
    assert (entity.x,entity.y) == (11,12)
    if tool == 'Circle':
        assert entity.construction
    assert s.active_id == sid and not v.selections


def test_cache_refresh_zoom_palette_and_free_grid_sketch_targets(qtbot,monkeypatch):
    import hero_cad.ui.sketch_view as module
    w = window(qtbot)
    sid = attached(w)
    v,s = w.viewport,w.viewport.sketch
    w.document.add_entity(sid,Circle(13,17,2))
    w.refresh()
    w.tool_choice.setCurrentText('Line')
    calls = []
    original = module.model_references
    def evaluated(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(module,'model_references',evaluated)
    for zoom in (20,40,80):
        v.renderer.GetActiveCamera().SetParallelScale(zoom)
        v.GetRenderWindow().Render()
        move_to(w,(40,30))
        assert s.snap_result.point == (40,30)
        assert s.snap_result.target == 'MODEL ENDPOINT'
    assert len(calls) == 1
    move_to(w,(13,17))
    assert s.snap_result.target == 'CENTER'
    s.guides.snap_grid = True
    s.guides.automatic = False
    s.guides.manual_spacing = 1
    move_to(w,(20,12),QPoint(0,0))
    assert s.snap_result.target == 'GRID'
    s.guides.snap_grid = False
    move_to(w,(20,12),QPoint(0,0))
    assert s.snap_result.target == 'FREE'
    w.document.set_box(BoxParameters(50,30,20))
    w.refresh()
    move_to(w,(50,30))
    assert s.snap_result.point == (50,30) and len(calls) == 2
    v.palette_colors['snap.center'] = (.2,.8,.4)
    s.apply_snap_color()
    assert s.snap_actor.GetProperty().GetColor() == (.2,.8,.4)
    assert s.reference_actor.GetProperty().GetColor() == (.2,.8,.4)
    move_to(w,(20,12))
    assert not s.reference_actor.GetVisibility()


def test_compound_orientation_two_sketches_and_wireframe(qtbot,monkeypatch):
    w = window(qtbot)
    w.document = compound_fixture(monkeypatch)
    sid = attached(w)
    v,s = w.viewport,w.viewport.sketch
    assert all(abs(c) > .1 for c in s.feature.parameters.frame.normal)
    w.tool_choice.setCurrentText('Line')
    move_to(w,(0,0))
    line = s._model_references.lines[0]
    a = move_to(w,line.a)
    qtbot.mouseClick(v,Qt.LeftButton,pos=a)
    b = move_to(w,line.b)
    qtbot.mouseClick(v,Qt.LeftButton,pos=b)
    entity, = w.document.feature(sid).parameters.entities
    assert entity.points[0] == pytest.approx(line.a,abs=1e-12)
    assert entity.points[1] == pytest.approx(line.b,abs=1e-12)
    w.finish_sketch()
    second = attached(w)
    assert second != sid
    v.set_display_mode('CAD Wireframe')
    w.tool_choice.setCurrentText('Circle')
    move_to(w,line.a)
    assert s.snap_result.point == pytest.approx(line.a,abs=1e-12)
    assert s.reference_actor.GetVisibility()
    assert w.document.feature(sid).parameters.entities == (entity,)

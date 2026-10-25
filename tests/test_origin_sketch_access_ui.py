"""Foreground editing and explicit finished-sketch profile access, no offsets."""
import numpy as np
import pytest
from PySide6.QtCore import Qt
from hero_cad.sketch import Circle,Line,Rectangle,Slot,PLANES
from hero_cad.document import Document
from test_sketch_ui import window,enter,click,pixel
from test_sketch_visibility import capture,cyan


def view_plane(v,frame):
    c=v.renderer.GetActiveCamera();focal=frame.to_world((12,10))
    c.SetFocalPoint(*focal);c.SetPosition(*(focal[i]+100*frame.normal[i] for i in range(3)))
    c.SetViewUp(*frame.v);c.ParallelProjectionOn();c.SetParallelScale(23)
    v.clamp_zoom()


@pytest.mark.parametrize('plane',['XY','XZ','YZ'])
@pytest.mark.parametrize('body',[False,True])
def test_active_entities_remain_visible_selectable_and_at_exact_plane(qtbot,plane,body):
    w=window(qtbot);w.tool_island.set_collapsed(True)
    sid=enter(w,plane);v=w.viewport
    if not body:w.show_base_box.setChecked(False)
    entities=(Line(4,4,16,4),Circle(10,10,3),Rectangle(18,6,6,4),Slot(5,16,1,8))
    for e in entities:w.document.add_entity(sid,e)
    w.refresh();frame=w.document.feature(sid).parameters.frame
    assert frame==PLANES[plane] and frame.origin==(0,0,0)
    w.grid_action.setChecked(False);w.axes_action.setChecked(False)
    w.xray_choice.setCurrentText('Orange');view_plane(v,frame)
    shown=capture(v)
    assert np.count_nonzero(cyan(shown))>100
    assert v.sketch_renderer.GetActiveCamera() is v.renderer.GetActiveCamera()
    assert v.sketch.foreground_actor.GetProperty().GetLineWidth()==1
    assert bool(v.mapper.GetInput().GetNumberOfCells())==body
    if body:
        assert v.actor.GetProperty().GetOpacity()==.85
        v.sketch.foreground_actor.VisibilityOff()
        legacy=capture(v)
        v.sketch.foreground_actor.VisibilityOn()
        if plane == 'XZ':  # This front-facing plane was already readable.
            assert np.count_nonzero(cyan(shown))>=np.count_nonzero(cyan(legacy))
        else:
            assert np.count_nonzero(cyan(shown))>np.count_nonzero(cyan(legacy))+40
    for e,point in zip(entities,((8,4),(13,10),(18,8),(9,17))):
        click(qtbot,v,frame,point)
        assert v.sketch.entity_id==e.id and v.selection is None
    w.tool_choice.setCurrentText('Line')
    click(qtbot,v,frame,(2,2));click(qtbot,v,frame,(4,2))
    assert len(w.document.feature(sid).parameters.entities)==5
    w.tool_choice.setCurrentText('Select')
    w.profile_action.setChecked(True);click(qtbot,v,frame,(10,10))
    assert v.profiles.selection[0]==sid and v.profiles.selection[1].outer_id==entities[1].id
    assert w.document.feature(sid).parameters.frame==frame
    w.profile_action.setChecked(False);w.xray_choice.setCurrentText('Off');w.finish_sketch()
    assert not v.sketch.foreground_actor.GetVisibility()
    assert v.actor.GetProperty().GetOpacity()==1
    assert w.document.feature(sid).parameters.entities[:4]==entities


@pytest.mark.parametrize('plane,operation,depth',[
    ('XY','new',3),('XY','cut',3),('XY','join',-3),
    ('XZ','new',3),('XZ','cut',-3),('YZ','join',-3)])
def test_finish_explicit_profile_access_extrude_reopen_and_normal_faces(qtbot,plane,operation,depth,tmp_path):
    w=window(qtbot);w.tool_island.set_collapsed(True);v=w.viewport
    sid=enter(w,plane);c=Circle(10,10,3);w.document.add_entity(sid,c);w.refresh()
    frame=w.document.feature(sid).parameters.frame
    w.finish_sketch();view_plane(v,frame)
    # In normal model mode, a click inside the hidden profile picks the real body.
    qtbot.mouseClick(v,Qt.LeftButton,pos=pixel(v,frame.to_world((10,10))))
    assert v.selection and v.selection.kind=='face'
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.profile_action.setChecked(True)
    assert v.profiles.scope_id==sid and v.profiles.selection is None
    click(qtbot,v,frame,(10,10))
    assert v.profiles.selection[0]==sid and w.extrude_action.isEnabled()
    w.extrude_action.trigger();p=w.operation_panel
    qtbot.waitUntil(lambda:p.quick_distance.hasFocus())
    p.operation.setCurrentIndex(p.operation.findData(operation));p.quick_distance.setText(str(depth))
    qtbot.keyClick(p.quick_distance,Qt.Key_Return)
    result=w.document.features[-1]
    assert result.type=='extrude' and result.parameters.operation==operation
    assert w.document.statuses[result.id].valid
    assert w.document.feature(sid).parameters.frame==frame
    saved=w.document.features;w.undo();w.redo();assert w.document.features==saved
    w.document.save(tmp_path/'origin.starcad')
    w.document=Document.load(w.document.path);w.refresh()
    assert w.document.features==saved
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)]);w.edit_sketch()
    assert v.sketch.active_id==sid and v.sketch.foreground_actor.GetVisibility()
    w.finish_sketch();assert v.sketch.active_id is None


def test_explicit_scope_disambiguates_coincident_sketches_without_auto_selection(qtbot):
    w=window(qtbot);v=w.viewport
    ids=[]
    for _ in range(2):
        sid=w.document.add_sketch('XY');w.document.add_entity(sid,Circle(10,10,3));ids.append(sid)
    w.refresh();frame=w.document.feature(ids[0]).parameters.frame
    w.show_base_box.setChecked(False);view_plane(v,frame)
    w.browser.setCurrentItem(w.browser_items[('box',w.document.features[0].id)])
    w.profile_action.setChecked(True);click(qtbot,v,frame,(10,10))
    assert v.profiles.scope_id is None and v.profiles.selection is None
    for sid in ids:
        w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
        assert v.profiles.scope_id==sid and v.profiles.selection is None
        click(qtbot,v,frame,(10,10))
        assert v.profiles.selection[0]==sid
    w.profile_action.setChecked(False)
    assert v.profiles.scope_id is None and not v.sketch.foreground_actor.GetVisibility()

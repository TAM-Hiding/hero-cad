"""Current cap picks, synchronized commands and repeated sketch/cut workflow."""
from dataclasses import replace
from PySide6.QtCore import Qt
import pytest
from hero_cad.sketch import Slot,Circle
from test_current_face_references import cylinder,cap,untagged
from test_sketch_ui import window,pixel


def select_and_enter(w,qtbot,face_point):
    v=w.viewport
    qtbot.mouseClick(v,Qt.LeftButton,pos=pixel(v,face_point))
    assert v.selection and w.new_sketch_action.isEnabled()
    button=w.tool_island.buttons['sketch.new']
    assert button.isEnabled() and button.defaultAction() is w.new_sketch_action
    assert w.commands.execute('sketch.new')
    assert v.sketch.active_id
    return v.sketch.active_id


def test_repeated_modified_cylinder_caps_enable_toolbar_and_island(qtbot,tmp_path):
    w=window(qtbot);v=w.viewport
    d,source,outer,inner,body=cylinder(True)
    w.document=d;w.refresh(fit=True);w.tool_island.set_collapsed(True)
    for n in range(2):
        v.orient('Top')
        sid=select_and_enter(w,qtbot,(0,-11,10))
        slot=Slot(-8,-5 if n==0 else 5,1.5,16)
        d.add_entity(sid,slot);w.refresh();w.finish_sketch()
        # Use the same real modeless preview/Apply path as normal extrusion.
        w.operation_panel.open(source=(sid,slot.id,()))
        panel=w.operation_panel
        panel.operation.setCurrentIndex(panel.operation.findData('cut'))
        panel.target.setCurrentIndex(panel.target.findData(body))
        panel.distance.setValue(-10)
        assert panel.preview() and panel.commit()
        body=d.features[-1].id
        assert d.statuses[body].valid
        v.orient('Top')
        extra=select_and_enter(w,qtbot,(0,-11,10))
        d.add_entity(extra,Circle(1,2,.3));w.refresh();w.finish_sketch()
    # Opposite cap remains available, with no restart or rollback to history.
    camera=v.renderer.GetActiveCamera()
    camera.SetPosition(0,0,-100);camera.SetFocalPoint(0,0,0);camera.SetViewUp(0,1,0);v.clamp_zoom()
    sid=select_and_enter(w,qtbot,(0,-11,0))
    w.finish_sketch();before=d.features
    w.undo();w.redo();assert d.features==before
    d.save(tmp_path/'cylinder-ui.starcad')
    w.document=type(d).load(d.path);w.refresh(fit=True);v.orient('Top')
    select_and_enter(w,qtbot,(0,-11,10))


def test_unlabelled_current_face_allows_new_sketch_but_changed_snapshot_is_unresolved(qtbot,monkeypatch):
    w=window(qtbot)
    d,source,cutter,c,body=untagged(monkeypatch)
    w.document=d;w.refresh(fit=True);w.tool_island.set_collapsed(True)
    w.viewport.orient('Top')
    sid=select_and_enter(w,qtbot,(0,-11,10))
    assert d.feature(sid).parameters.attachment.snapshot is not None
    w.finish_sketch()
    d.update_entity(cutter,replace(c,radius=3));w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    assert d.statuses[sid].reference_state=='missing' and not w.edit_sketch_action.isEnabled()
    assert 'checked current geometry' in w.browser_items[('sketch',sid)].toolTip(0)
    # A fresh user choice on the new geometry is independent of the old failure.
    w.viewport.orient('Top')
    select_and_enter(w,qtbot,(0,-11,10))

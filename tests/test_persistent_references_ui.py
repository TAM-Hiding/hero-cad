"""Real face clicks, topology recovery, history and failure diagnostics."""
from PySide6.QtCore import Qt
import pytest
from hero_cad.sketch import Circle
from test_persistent_references import pocket, split, attached, resolution
from test_sketch_ui import window, pixel


def test_clicked_witness_survives_split_and_history_without_stale_picking(qtbot,tmp_path):
    w=window(qtbot)
    d,box,cutter,r,cut,face=pocket()
    w.document=d;w.refresh(fit=True)
    v=w.viewport;v.orient('Top')
    qtbot.mouseClick(v,Qt.RightButton,pos=pixel(v,(5,5,10)))
    w._context_menu.actions()[0].trigger();w._context_menu.close()
    sid=v.sketch.active_id
    p=d.feature(sid).parameters
    assert p.attachment.support.anchor==pytest.approx((5,5),abs=.15)
    assert v.selection is None  # Sketch refresh rebuilt and cleared transient mappings.
    d.add_entity(sid,Circle(3,3,.5));w.refresh();w.finish_sketch()
    ref=d.feature(sid).parameters.attachment
    split(d,cutter,r);w.refresh()
    assert d.statuses[sid].valid and resolution(d,ref).face is not None
    for _ in range(2):
        w.undo();w.redo()
        assert d.statuses[sid].reference_state=='resolved'
        assert d.feature(sid).parameters.attachment==ref
        v.orient('Top')
        qtbot.mouseClick(v,Qt.LeftButton,pos=pixel(v,(5,25,10)))
        assert v.selection and v.selection.kind=='face'
        assert w.new_sketch_action.isEnabled()
        assert d.face_reference(v.selection.shape,point=v.selection.point).parent_id==cut
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.edit_sketch();assert v.sketch.active_id==sid
    assert v.renderer.GetActiveCamera().GetDirectionOfProjection()==pytest.approx(tuple(-n for n in p.frame.normal))
    w.finish_sketch()
    d.save(tmp_path/'clicked.starcad')
    loaded=type(d).load(d.path)
    assert loaded.features==d.features and loaded.feature(sid).parameters.attachment==ref


def test_ambiguous_reference_is_visible_in_existing_diagnostics(qtbot):
    w=window(qtbot)
    d,box,cutter,r,cut,face=pocket()
    ref,sid,c,eid=attached(d,cut,face,(5,12,10))
    split(d,cutter,r)
    w.document=d;w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    assert d.statuses[sid].reference_state=='ambiguous'
    assert 'UNRESOLVED' in w.browser_items[('sketch',sid)].text(0)
    assert 'Ambiguous face' in w.browser_items[('sketch',sid)].toolTip(0)
    assert not w.edit_sketch_action.isEnabled()
    w.undo()
    assert d.statuses[sid].valid
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    assert w.edit_sketch_action.isEnabled()
    w.edit_sketch();assert w.viewport.sketch.active_id==sid


def test_context_on_selected_face_preserves_batch_and_uses_clicked_witness(qtbot):
    w=window(qtbot)
    d,box,cutter,r,cut,face=pocket();split(d,cutter,r)
    w.document=d;w.refresh(fit=True)
    v=w.viewport;v.orient('Top')
    qtbot.mouseClick(v,Qt.LeftButton,pos=pixel(v,(5,5,10)))
    qtbot.mouseClick(v,Qt.LeftButton,Qt.ShiftModifier,pos=pixel(v,(5,25,10)))
    assert len(v.selections)==2
    before={(s.kind,s.index) for s in v.selections}
    qtbot.mouseClick(v,Qt.RightButton,pos=pixel(v,(5,5,10)))
    assert {(s.kind,s.index) for s in v.selections}==before
    w._context_menu.actions()[0].trigger();w._context_menu.close()
    p=d.feature(v.sketch.active_id).parameters
    assert p.attachment.support.anchor==pytest.approx((5,5),abs=.15)

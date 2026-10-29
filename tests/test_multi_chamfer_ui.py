import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QMessageBox
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cone, GeomAbs_Cylinder
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.sketch import Circle
from hero_cad.ui.operation_appearance import OPERATION_STYLE
from test_sketch_ui import window,pixel
from test_viewport import project
from test_multi_chamfers import slot_model,box_top
from test_chamfers import state


def slot_window(qtbot):
    w=window(qtbot)
    w.document=slot_model()[0]
    w.refresh()
    w.viewport.orient('Top')
    w.viewport.set_selection_mode('edge')
    return w


def click(qtbot,v,point,shift=False,button=Qt.LeftButton):
    qtbot.mouseClick(v,button,Qt.ShiftModifier if shift else Qt.NoModifier,pos=pixel(v,point))


def assert_highlights(v, count):
    from hero_cad.ui.display_geometry import selected_mesh
    assert len({item.index for item in v.selections}) == count
    expected=sum(selected_mesh(v.edge_mapper.GetInput(),'edge_id',item.index).GetNumberOfCells()
                 for item in v.selections)
    assert expected > 0 and v.highlight_mapper.GetInput().GetNumberOfCells()==expected
    assert v.highlight_actor.GetVisibility()


def test_real_context_tangent_selection_highlights_closed_slot_without_history(qtbot):
    w=slot_window(qtbot);v=w.viewport;doc=w.document
    before=state(doc);stacks=doc._undo[:],doc._redo[:]
    geometry=v.mapper.GetInput();camera=v.renderer.GetActiveCamera()
    click(qtbot,v,(25,10,20),button=Qt.RightButton)
    assert v.selection.kind=='edge'
    menu=w._context_menu
    assert w.tangent_chain_action in menu.actions() and w.tangent_chain_action.isEnabled()
    qtbot.mouseClick(menu,Qt.LeftButton,pos=menu.actionGeometry(w.tangent_chain_action).center())
    assert_highlights(v,4)
    assert w.chamfer_action.isEnabled() and not w.tangent_chain_action.isEnabled()
    assert all(a is b for a,b in zip(state(doc),before)) and (doc._undo,doc._redo)==stacks
    assert v.mapper.GetInput() is geometry
    v.orient('Isometric');assert v.renderer.GetActiveCamera() is camera and len(v.selections)==4
    v.orient('Top')
    click(qtbot,v,(16,7,20),shift=True)
    assert_highlights(v,3)
    click(qtbot,v,(16,7,20),shift=True)
    assert_highlights(v,4)
    # A context click on a member preserves the manual batch.
    click(qtbot,v,(25,10,20),button=Qt.RightButton)
    assert len(v.selections)==4 and w.chamfer_action.isEnabled()
    w._context_menu.hide()
    v.clear_selection();assert not v.highlight_actor.GetVisibility() and not w.chamfer_action.isEnabled()


def test_manual_slot_preview_failure_cancel_commit_properties_and_persistence(qtbot,tmp_path,monkeypatch):
    w=slot_window(qtbot);v=w.viewport;doc=w.document
    original=doc.features;stacks=doc._undo[:],doc._redo[:]
    click(qtbot,v,(16,7,20))
    w.chamfer_action.trigger();p=w.operation_panel
    assert 'Selected edges: 1' in p.tools_label.text()
    p.quick_distance.setText('.5')
    assert not p.preview() and 'explicit selection' in p.feedback.text()
    assert doc.features==original and (doc._undo,doc._redo)==stacks
    p.cancel()
    # Manual mixed line/arc selection uses the existing Shift toggle path.
    points=((16,7,20),(25,10,20),(16,13,20),(7,10,20))
    for i,point in enumerate(points):click(qtbot,v,point,shift=i>0)
    assert len(v.selections)==4 and w.chamfer_action.isEnabled()
    w.tool_island.set_collapsed(True);w.tool_island.place(QPoint(40,12))
    w.chamfer_action.trigger()
    qtbot.waitUntil(lambda:not p.open_timer.isActive())
    assert p.styleSheet()==OPERATION_STYLE and 'Selected edges: 4' in p.tools_label.text()
    anchor=w.tool_island.mapToGlobal(QPoint())
    assert p.frameGeometry().left()==anchor.x()
    assert p.frameGeometry().top()==anchor.y()+w.tool_island.height()+3
    assert p.quick_distance.hasFocus()
    p.quick_distance.setText('.5');assert p.preview()
    assert p.actor.GetVisibility() and doc.features==original
    assert len(p.candidate.features)==len(original)+1
    candidate_volume=volume(p.candidate.solid_shapes[p.feature_id])
    p.cancel();assert doc.features==original and not p.actor.GetVisibility()
    for i,point in enumerate(points):click(qtbot,v,point,shift=i>0)
    w.chamfer_action.trigger();p.quick_distance.setText('.5');assert p.apply_input()
    cid=doc.features[-1].id
    assert len(doc.feature(cid).parameters.edges)==4 and doc.feature(cid).type=='chamfer'
    assert volume(doc.solid_shapes[cid])==pytest.approx(candidate_volume)
    assert 'Selected edges: 4' in w.history_inspector.toPlainText()
    assert 'Edge 4:' in w.history_inspector.toPlainText()
    w.entity_fields['distance'].setValue(1);assert w.apply_dimensions()
    assert doc.feature(cid).id==cid and doc.feature(cid).parameters.distance==1
    accepted=state(doc);messages=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:messages.append(args[-1]))
    w.entity_fields['distance'].setValue(100)
    assert not w.apply_dimensions() and messages
    assert all(a is b for a,b in zip(state(doc),accepted))
    w.undo()  # Cancel invalid property text first.
    w.undo();assert doc.feature(cid).parameters.distance==.5
    w.undo();assert doc.features==original
    w.redo();w.redo();assert doc.feature(cid).parameters.distance==1
    doc.save(tmp_path/'ui-multi.starcad');loaded=Document.load(doc.path)
    assert loaded.features==doc.features and loaded.statuses[cid].valid
    v.orient('Top');v.set_selection_mode('face')
    for point,kind in [((16,6.5,19.5),GeomAbs_Plane),((25.5,10,19.5),GeomAbs_Cone),((4,4,20),GeomAbs_Plane)]:
        v.pick_at(*project(v,point));assert v.selection.kind=='face'
        assert BRepAdaptor_Surface(v.selection.shape).GetType()==kind
    # Picking uses rebuilt mappings after complete Undo/Redo.
    v.set_selection_mode('edge');v.pick_at(*project(v,(0,15,20)))
    assert v.selection.kind=='edge' and doc.edge_reference(v.selection.shape)[0]==cid


def test_manual_two_straight_edges_and_cross_body_rejection(qtbot):
    w=window(qtbot);v=w.viewport
    w.show_base_box.setChecked(True);v.orient('Top');v.set_selection_mode('edge')
    click(qtbot,v,(0,15,20));click(qtbot,v,(40,15,20),shift=True)
    assert len(v.selections)==2 and w.chamfer_action.isEnabled()
    w.chamfer_action.trigger();p=w.operation_panel;p.quick_distance.setText('1');assert p.apply_input()
    assert len(w.document.features[-1].parameters.edges)==2
    assert volume(w.document.shape)==pytest.approx(23970)
    w.undo()
    sid=w.document.add_sketch('XY');circle=Circle(60,15,5);w.document.add_entity(sid,circle)
    w.document.add_extrusion(sid,circle.id,distance=20)
    w.refresh();w.show_base_box.setChecked(True);v.orient('Top');v.set_selection_mode('edge')
    click(qtbot,v,(0,15,20));click(qtbot,v,(65,15,20),shift=True)
    assert len(v.selections)==2 and not w.chamfer_action.isEnabled()
    assert 'same current solid body' in w.chamfer_action.toolTip()

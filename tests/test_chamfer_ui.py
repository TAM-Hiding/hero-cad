import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.sketch import Circle
from test_sketch_ui import window
from test_viewport import project


def select_edge(w, point=(20,0,0)):
    w.show_base_box.setChecked(True)
    w.viewport.orient('Front')
    w.viewport.set_selection_mode('edge')
    w.viewport.pick_at(*project(w.viewport,point))
    assert w.viewport.selection.kind == 'edge'
    assert w.chamfer_action.isEnabled()


def test_chamfer_preview_cancel_commit_properties_history_and_picking(qtbot, tmp_path):
    w = window(qtbot)
    v, doc = w.viewport, w.document
    assert not w.chamfer_action.isEnabled()
    select_edge(w)
    before = doc.features
    assert w.commands.execute('model.chamfer')
    panel = w.operation_panel
    assert panel.active and panel.windowTitle() == 'Chamfer'
    assert panel.quick_distance.isVisible() and panel.preview_button.isVisible()
    assert not panel.operation.isVisible() and not panel.target.isVisible()
    panel.quick_distance.setText('2')
    assert panel.preview()
    assert panel.actor.GetVisibility()
    assert panel.mapper.GetInput().GetNumberOfCells() > 0
    assert volume(panel.candidate.shape) == pytest.approx(23920)
    assert doc.features == before and not doc.can_undo and not doc.dirty
    panel.cancel()
    assert doc.features == before and not panel.actor.GetVisibility()
    assert v.mapper.GetInput().GetNumberOfCells() > 0
    select_edge(w)
    w.chamfer_action.trigger()
    panel.quick_distance.setText('2')
    assert panel.apply_input()
    cid = doc.features[-1].id
    assert w.browser_key == ('chamfer',cid)
    assert w.entity_context == ('chamfer',cid)
    assert 'Chamfer 1' in w.browser_items[('chamfer',cid)].text(0)
    assert w.entity_apply.text() == 'Apply chamfer distance'
    assert w.entity_fields['distance'].value() == 2
    assert 'Edge identity:' in w.history_inspector.toPlainText()
    w.entity_fields['distance'].setValue(3)
    assert w.apply_dimensions()
    assert doc.feature(cid).parameters.distance == 3
    assert volume(doc.shape) == pytest.approx(23820)
    w.undo()
    assert volume(doc.shape) == pytest.approx(23920)
    w.undo()
    assert doc.features == before and volume(doc.shape) == pytest.approx(24000)
    w.redo()
    w.redo()
    assert doc.feature(cid).parameters.distance == 3
    v.orient('Front')
    v.set_selection_mode('face')
    v.pick_at(*project(v,(20,0,10)))
    assert v.selection.kind == 'face'
    assert doc.face_reference(v.selection.shape).parent_id == cid
    v.set_selection_mode('edge')
    v.pick_at(*project(v,(20,0,20)))
    assert v.selection.kind == 'edge'
    assert doc.edge_reference(v.selection.shape)[0] == cid
    doc.save(tmp_path/'ui-chamfer.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features
    assert volume(loaded.shape) == pytest.approx(23820)
    # A real framebuffer check: ensure the accepted solid renders visibly.
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    import numpy as np
    v.clear_selection()
    v.orient('Isometric')
    capture = vtkWindowToImageFilter()
    capture.SetInput(v.GetRenderWindow())
    capture.ReadFrontBufferOff()
    capture.Update()
    pixels = vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars())
    assert np.count_nonzero((pixels[:,2] > pixels[:,0]) & (pixels[:,0] > 65)) > 500


@pytest.mark.parametrize('value',['0','-1','nan','1e309','invalid'])
def test_invalid_chamfer_input_has_no_history(qtbot,value):
    w = window(qtbot)
    select_edge(w)
    original = w.document.features
    w.chamfer_action.trigger()
    panel = w.operation_panel
    panel.quick_distance.setText(value)
    assert not panel.apply_button.isEnabled()
    assert not panel.apply_input()
    assert w.document.features == original and not w.document.can_undo
    assert not panel.actor.GetVisibility()
    panel.cancel()


def test_failed_preview_and_property_edit_preserve_valid_model(qtbot,monkeypatch):
    w = window(qtbot)
    select_edge(w)
    w.chamfer_action.trigger()
    panel = w.operation_panel
    before = w.document.features
    panel.quick_distance.setText('100')
    assert not panel.apply_input()
    assert panel.active and panel.candidate is None
    assert w.document.features == before and not w.document.can_undo
    assert not panel.actor.GetVisibility()
    assert w.viewport.mapper.GetInput().GetNumberOfCells() > 0
    panel.quick_distance.setText('1.23456789012345')
    assert panel.apply_input()
    cid = w.document.features[-1].id
    assert w.document.feature(cid).parameters.distance == 1.23456789012345
    accepted, shape = w.document.features, w.document.shape
    messages = []
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:messages.append(args[-1]))
    w.entity_fields['distance'].setValue(100)
    assert not w.apply_dimensions()
    assert w.document.features == accepted and w.document.shape is shape
    assert messages
    # Cancel pending invalid Properties input via Undo, then edit dialog keeps ID.
    w.undo()
    w.browser.setCurrentItem(w.browser_items[('chamfer',cid)])
    w.edit_operation()
    assert panel.active and panel.windowTitle() == 'Chamfer'
    panel.quick_distance.setText('2')
    assert panel.apply_input()
    assert w.document.features[-1].id == cid
    assert w.document.feature(cid).parameters.distance == 2
    # The shared panel still opens a normal extrusion afterward.
    sid = w.document.add_sketch('XY')
    c = Circle(60,0,2)
    w.document.add_entity(sid,c)
    w.refresh()
    panel.open(source=(sid,c.id,()),quick=True)
    assert panel.operation.isVisible() and panel.chamfer_parameters is None
    panel.cancel()


def test_chamfer_disabled_for_faces_and_sketch_edit_and_enabled_for_multiple_edges(qtbot):
    w = window(qtbot)
    select_edge(w)
    w.viewport.set_selection_mode('face')
    w.viewport.pick_at(*project(w.viewport,(20,0,10)))
    assert not w.chamfer_action.isEnabled()
    sid = w.document.add_sketch('XY')
    w.refresh()
    select_edge(w)
    w.viewport.sketch.enter(sid)
    assert not w.chamfer_action.isEnabled()
    w.viewport.sketch.finish()
    select_edge(w)
    # Shift-selection creates the same authoritative multi-selection list.
    w.viewport.pick_at(*project(w.viewport,(20,0,20)), additive=True)
    assert len(w.viewport.selections) == 2
    assert w.chamfer_action.isEnabled()
    c = Circle(10,10,5)
    w.document.add_entity(sid,c)
    w.document.add_extrusion(sid,c.id)
    w.show_base_box.setChecked(False)
    w.refresh()
    w.viewport.orient('Top')
    w.viewport.set_selection_mode('edge')
    w.viewport.pick_at(*project(w.viewport,(15,10,10)))
    assert w.viewport.selection.kind == 'edge'
    assert w.chamfer_action.isEnabled()
    assert w.document.edge_reference(w.viewport.selection.shape)[1].curve_type == 'circle'


@pytest.mark.parametrize('kind,z,point', [
    ('hole',20,(20,15,20)), ('boss',30,(20,15,30)), ('arc',30,(10,15,30)),
])
def test_curved_chamfer_pick_preview_cancel_apply_properties_and_bevel_selection(qtbot,tmp_path,kind,z,point):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPalette
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone
    from test_circular_chamfers import model
    from hero_cad.ui.operation_appearance import OPERATION_STYLE, INPUT
    w=window(qtbot)
    w.document=model(kind)[0]
    doc=w.document
    w.refresh()
    w.tool_island.set_collapsed(True)
    w.tool_island.place(QPoint(40,12))
    v=w.viewport
    v.orient('Top')
    v.set_selection_mode('edge')
    v.pick_at(*project(v,point))
    assert v.selection.kind=='edge' and w.chamfer_action.isEnabled()
    target,reference=doc.edge_reference(v.selection.shape)
    assert reference.curve_type==('arc' if kind=='arc' else 'circle')
    before=doc.features
    original_volume=volume(doc.solid_shapes[target])
    w.chamfer_action.trigger()
    p=w.operation_panel
    qtbot.waitUntil(lambda:not p.open_timer.isActive())
    assert p.styleSheet()==OPERATION_STYLE
    assert p.quick_distance.palette().color(QPalette.Base).name().upper()==INPUT.upper()
    anchor=w.tool_island.mapToGlobal(QPoint())
    assert p.frameGeometry().left()==anchor.x()
    assert p.frameGeometry().top()==anchor.y()+w.tool_island.height()+3
    p.quick_distance.setText('.5')
    assert p.preview() and p.actor.GetVisibility()
    assert volume(p.candidate.solid_shapes[p.feature_id]) < original_volume
    assert doc.features==before
    p.cancel()
    assert doc.features==before and not p.actor.GetVisibility()
    v.set_selection_mode('edge')
    v.pick_at(*project(v,point))
    assert w.chamfer_action.isEnabled()
    w.chamfer_action.trigger()
    p.quick_distance.setText('.5')
    assert p.apply_input()
    cid=doc.features[-1].id
    assert doc.feature(cid).type=='chamfer'
    assert w.entity_context==('chamfer',cid)
    assert ('Circular arc:' if kind=='arc' else 'Circle:') in w.history_inspector.toPlainText()
    w.entity_fields['distance'].setValue(1)
    assert w.apply_dimensions()
    assert doc.feature(cid).id==cid and doc.feature(cid).parameters.distance==1
    w.undo()
    assert doc.feature(cid).parameters.distance==.5
    w.redo()
    assert doc.feature(cid).parameters.distance==1
    doc.save(tmp_path/f'ui-{kind}.starcad')
    loaded=Document.load(doc.path)
    assert loaded.features==doc.features and loaded.statuses[cid].valid
    # Pick the conical bevel through the normal tessellation-to-OCCT face map.
    v.orient('Top')
    v.set_selection_mode('face')
    bevel_point=(20.5,15,19.5) if kind=='hole' else (19.5,15,29.5) if kind=='boss' else (10.5,15,29.5)
    v.pick_at(*project(v,bevel_point))
    assert v.selection.kind=='face'
    assert BRepAdaptor_Surface(v.selection.shape).GetType()==GeomAbs_Cone
    with pytest.raises(ValueError,match='planar'):
        doc.face_reference(v.selection.shape)

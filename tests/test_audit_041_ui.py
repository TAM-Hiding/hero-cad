"""Real failed previews, display-stage atomicity and viewport-only invariants."""
from types import SimpleNamespace
import pytest
from hero_cad.features import ChamferParameters
from hero_cad.ui.display_geometry import DisplayMeshError, tessellate
from hero_cad.geometry import make_box
from test_sketch_ui import window
from test_viewport import project
from test_audit_041 import slot_fin


def test_slot_fin_preview_boundary_failure_after_valid_preview_can_cancel(qtbot):
    w = window(qtbot)
    doc, target, _, _, refs = slot_fin()
    w.document = doc
    w.refresh(fit=True)
    before, shape = doc.features, doc.shape
    stacks = doc._undo[:], doc._redo[:]
    panel = w.operation_panel
    panel.open_chamfer(ChamferParameters(target, refs, .999))
    assert panel.preview() and panel.actor.GetVisibility()
    assert panel.mapper.GetInput().GetNumberOfCells() > 0
    panel.quick_distance.setText('1.2')
    assert not panel.preview()
    assert 'result validation failed' in panel.feedback.text()
    assert 'topology_valid=False' in panel.feedback.text()
    assert panel.candidate is None and not panel.actor.GetVisibility()
    assert not panel.apply_button.isEnabled()
    assert doc.features is before and doc.shape is shape
    assert (doc._undo, doc._redo) == stacks
    assert w.viewport.mapper.GetInput().GetNumberOfCells() > 0
    assert not w.viewport.selections and not w.viewport.highlight_actor.GetVisibility()
    panel.cancel()
    assert not panel.active and doc.features is before


def test_tessellation_failure_reports_stage_and_face_without_claiming_geometry_cause(monkeypatch):
    import hero_cad.ui.display_geometry as module
    monkeypatch.setattr(module, 'BRep_Tool', SimpleNamespace(Triangulation_s=lambda *a: None))
    with pytest.raises(DisplayMeshError) as failure:
        tessellate(make_box(4, 3, 2))
    assert failure.value.stage == 'tessellation' and failure.value.face_index == 0
    assert 'face 1' in str(failure.value) and 'status_flags=' in str(failure.value)
    assert 'does not establish the geometric cause' in str(failure.value)


@pytest.mark.parametrize('stage', ['tessellate', 'edge_mesh'])
def test_display_preparation_failure_keeps_meshes_maps_and_selection(qtbot, monkeypatch, stage):
    import hero_cad.ui.viewport as module
    w = window(qtbot)
    w.show_base_box.setChecked(True)
    v = w.viewport
    v.orient('Front')
    v.pick_at(*project(v, (20, 0, 10)))
    assert v.selection is not None
    before = (v.mapper.GetInput(), v.edge_mapper.GetInput(), v.faces, v.edges,
              v.selection, v.selections, v.highlight_mapper.GetInput())
    def fail(*args):
        raise ValueError('injected display preparation failure')
    monkeypatch.setattr(module, stage, fail)
    with pytest.raises(ValueError, match='injected'):
        v.set_shape(make_box(10, 10, 10))
    after = (v.mapper.GetInput(), v.edge_mapper.GetInput(), v.faces, v.edges,
             v.selection, v.selections, v.highlight_mapper.GetInput())
    assert all(a is b for a, b in zip(before, after))


def test_mesh_failure_in_preview_preserves_document_and_restores_display(qtbot, monkeypatch):
    import hero_cad.ui.operation_panel as module
    w = window(qtbot)
    doc, target, _, _, refs = slot_fin()
    w.document = doc
    w.refresh(fit=True)
    before, shape = doc.features, doc.shape
    panel = w.operation_panel
    panel.open_chamfer(ChamferParameters(target, refs, .5))
    def fail(*args):
        raise DisplayMeshError(2, SimpleNamespace(IsDone=lambda: True, GetStatusFlags=lambda: 1))
    monkeypatch.setattr(module, 'tessellate', fail)
    assert not panel.preview()
    assert 'Tessellation failed' in panel.feedback.text()
    assert panel.candidate is None and not panel.actor.GetVisibility()
    assert doc.features is before and doc.shape is shape
    assert w.viewport.mapper.GetInput().GetNumberOfCells() > 0
    panel.cancel()


def test_camera_style_selection_and_history_inspection_never_remesh_or_regenerate(qtbot, monkeypatch):
    import hero_cad.ui.viewport as module
    from hero_cad.document import Document
    from hero_cad.history_inspection import feature_history_text
    w = window(qtbot)
    w.show_base_box.setChecked(True)
    v = w.viewport
    surface, wire, shape = v.mapper.GetInput(), v.edge_mapper.GetInput(), w.document.shape
    def unexpected(*args, **kwargs):
        raise AssertionError('Viewport-only action attempted geometry/display rebuilding')
    monkeypatch.setattr(module, 'tessellate', unexpected)
    monkeypatch.setattr(module, 'edge_mesh', unexpected)
    monkeypatch.setattr(Document, '_regenerate', unexpected)
    camera = v.renderer.GetActiveCamera()
    v.orient('Front')
    v.pick_at(*project(v, (20, 0, 10)))
    assert v.selection.kind == 'face'
    v.set_selection_mode('edge')
    v.pick_at(*project(v, (20, 0, 0)))
    assert v.selection.kind == 'edge'
    v.set_xray_mode('Orange')
    v.set_display_mode('CAD Wireframe')
    v.set_display_mode('Shaded with CAD Edges')
    camera.Azimuth(10)
    camera.Dolly(1.05)
    camera.SetParallelScale(camera.GetParallelScale()*.9)
    focal, position = camera.GetFocalPoint(), camera.GetPosition()
    camera.SetFocalPoint(focal[0]+1, *focal[1:])
    camera.SetPosition(position[0]+1, *position[1:])
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    assert 'History position' in feature_history_text(w.document, w.document.features[0].id)
    assert v.mapper.GetInput() is surface and v.edge_mapper.GetInput() is wire
    assert w.document.shape is shape
    # Verify actual rendered output rather than accepting a silent GL failure.
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    import numpy as np
    capture = vtkWindowToImageFilter()
    capture.SetInput(v.GetRenderWindow())
    capture.ReadFrontBufferOff()
    capture.Update()
    pixels = vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars())
    assert np.count_nonzero((pixels[:, 0] > 80) & (pixels[:, 1] > 80)) > 500

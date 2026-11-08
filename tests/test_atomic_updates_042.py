"""Document/history and display publication agree, including injected failures."""
from dataclasses import replace
from math import pi
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QMessageBox, QFileDialog
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_EDGE
from hero_cad.document import Document
from hero_cad.features import BoxParameters, FeatureError
from hero_cad.geometry import volume
from hero_cad.booleans import bounds
from hero_cad.sketch import Circle
from hero_cad.ui.display_geometry import DisplayMeshError
from test_sketch_ui import window
from test_audit_041 import slot_fin


def fixture(qtbot):
    w = window(qtbot)
    d = w.document
    sid = d.add_sketch('XY')
    circle = Circle(60, 0, 5)
    d.add_entity(sid, circle)
    eid = d.add_extrusion(sid, circle.id, distance=10)
    w.refresh(fit=True)
    w.entity_context, w.browser_key = ('extrude', eid), ('extrude', eid)
    w.show_properties()
    w.viewport.select_face(w.viewport.faces[0])
    return w, sid, circle, eid


def snapshot(w):
    d, v = w.document, w.viewport
    names = tuple(n for n in Document._evaluation_fields if n != 'last_failure')
    return (d, tuple(getattr(d, n) for n in names), d.path, d._saved_features,
            v.mapper, v.edge_mapper, v.faces, v.edges, v.planar_normals,
            v.selection, v.selections, v.highlight_mapper.GetInput(), v.highlight_actor.GetVisibility(),
            v.sketch.mapper, v.sketch.foreground_mapper, v.sketch.highlight_mapper,
            v.sketch.mapping, v.sketch._path_cache, w.show_base_box.isChecked(),
            w.browser_key, w.entity_context, v.support_mapper, v.support_mapper.GetInput(),
            v.support_actor.GetVisibility(), getattr(v, '_support_key', None))


def unchanged(w, before):
    after = snapshot(w)
    assert after[0] is before[0]
    assert all(a is b for a,b in zip(after[1], before[1]))
    assert all(a is b for a,b in zip(after[4:12], before[4:12]))
    assert after[2:4] == before[2:4] and after[12:] == before[12:]
    assert w.viewport.selection is None or any(w.viewport.selection.shape.IsSame(f) for f in w.viewport.faces)


def fail(message='injected display failure'):
    def rejected(*args, **kwargs):
        raise ValueError(message)
    return rejected


def test_candidate_preserves_policy_and_history_and_adopts_without_regeneration(monkeypatch):
    doc = Document()
    before = doc.__dict__.copy()
    candidate = doc.candidate()
    assert candidate.shape is doc.shape and candidate.face_maps is doc.face_maps
    assert candidate._undo is not doc._undo and candidate._redo is not doc._redo
    candidate.set_box(BoxParameters(width=45))
    assert doc.features is before['features'] and doc._undo == []
    monkeypatch.setattr(Document, '_regenerate', fail('adoption must not regenerate'))
    doc.adopt_candidate(candidate)
    assert doc.parameters.width == 45 and len(doc._undo) == 1
    assert doc.shape is candidate.shape and doc.face_maps is candidate.face_maps
    assert doc.path is None and doc._saved_features is before['_saved_features']


def test_candidate_stale_or_wrong_owner_is_rejected():
    doc = Document()
    candidate = doc.candidate()
    candidate.set_box(BoxParameters(width=45))
    with pytest.raises(ValueError, match='Document changed'):
        Document().adopt_candidate(candidate)
    doc.set_box(BoxParameters(depth=35))
    before = doc.__dict__.copy()
    with pytest.raises(ValueError, match='Document changed'):
        doc.adopt_candidate(candidate)
    assert doc.__dict__ == before


def test_properties_success_is_one_evaluation_one_mesh_and_normal_history(qtbot, monkeypatch, tmp_path):
    import hero_cad.ui.viewport as module
    w, _, _, eid = fixture(qtbot)
    doc, previous = w.document, w.document.features
    counts = {'regenerate': 0, 'tessellate': 0}
    native, mesh = Document._regenerate, module.tessellate
    def regen(self, *a, **kw):
        counts['regenerate'] += 1
        return native(self, *a, **kw)
    def tess(*a, **kw):
        counts['tessellate'] += 1
        return mesh(*a, **kw)
    monkeypatch.setattr(Document, '_regenerate', regen)
    monkeypatch.setattr(module, 'tessellate', tess)
    stacks = len(doc._undo)
    w.entity_fields['distance'].setValue(11)
    assert w.apply_dimensions()
    assert counts == {'regenerate': 1, 'tessellate': 1}
    assert w.document is doc and doc.feature(eid).parameters.distance == 11
    assert len(doc._undo) == stacks+1 and doc._undo[-1] == previous
    assert BRepCheck_Analyzer(doc.solid_shapes[eid]).IsValid()
    assert volume(doc.solid_shapes[eid]) == pytest.approx(pi*25*11)
    assert bounds(doc.solid_shapes[eid]) == pytest.approx((55,65,-5,5,0,11), abs=1e-7)
    assert w.viewport.mapper.GetInput().GetBounds()[5] == pytest.approx(11)
    assert w.viewport.selection is None and not w.viewport.selections
    doc.save(tmp_path/'edited.hcad')
    reopened = Document.load(doc.path)
    assert reopened.features == doc.features and reopened.statuses == doc.statuses
    w.undo()
    assert doc.feature(eid).parameters.distance == 10
    w.redo()
    assert doc.feature(eid).parameters.distance == 11


@pytest.mark.parametrize('stage', ['tessellation', 'edges', 'picking_maps', 'mapper', 'publication'])
def test_properties_display_failure_preserves_model_selection_stacks_and_file(qtbot, monkeypatch, tmp_path, stage):
    import hero_cad.ui.viewport as module
    w, _, _, _ = fixture(qtbot)
    w.document.save(tmp_path/'original.hcad')
    contents = w.document.path.read_bytes()
    before = snapshot(w)
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: errors.append(a[-1]))
    if stage == 'tessellation':
        def failed_mesh(*a):
            raise DisplayMeshError(0, SimpleNamespace(IsDone=lambda: True, GetStatusFlags=lambda: 1))
        monkeypatch.setattr(module, 'tessellate', failed_mesh)
    elif stage == 'edges':
        monkeypatch.setattr(module, 'edge_mesh', fail())
    elif stage == 'picking_maps':
        native = module.subshapes
        def maps(shape, kind):
            if kind == TopAbs_EDGE:
                raise ValueError('injected picking-map failure after faces')
            return native(shape, kind)
        monkeypatch.setattr(module, 'subshapes', maps)
    elif stage == 'mapper':
        monkeypatch.setattr(module, 'vtkPolyDataMapper', fail('injected detached mapper failure'))
    else:
        native = w.viewport.install_shape
        calls = []
        def publish(prepared):
            native(prepared)
            calls.append(True)
            if len(calls) == 1:
                raise ValueError('injected publication failure after mapper swap')
        monkeypatch.setattr(w.viewport, 'install_shape', publish)
    w.entity_fields['distance'].setValue(11)
    assert not w.apply_dimensions() and errors
    unchanged(w, before)
    expected = 'tessellation' if stage == 'tessellation' else 'viewport_presentation' if stage == 'publication' else 'display_preparation'
    assert w.document.last_failure.status.diagnostic_stage == expected
    w.document.save(w.document.path)
    assert w.document.path.read_bytes() == contents
    reopened = Document.load(w.document.path)
    assert reopened.features == w.document.features
    assert volume(reopened.shape) == pytest.approx(volume(w.document.shape))


@pytest.mark.parametrize('layer', [1, 3])
def test_sketch_vtk_or_highlight_preparation_failure_is_atomic(qtbot, monkeypatch, layer):
    import hero_cad.ui.sketch_view as module
    w, sid, circle, _ = fixture(qtbot)
    w.entity_context, w.browser_key = (sid, circle.id), ('entity', sid, circle.id)
    w.show_properties()
    before = snapshot(w)
    native, calls = module.paths_mesh, []
    def paths(*a):
        calls.append(True)
        if len(calls) == layer:
            raise ValueError('injected sketch layer preparation failure')
        return native(*a)
    monkeypatch.setattr(module, 'paths_mesh', paths)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: None)
    w.entity_fields['radius'].setValue(6)
    assert not w.apply_dimensions()
    unchanged(w, before)
    assert w.document.feature(sid).parameters.entities[0].radius == 5


def test_geometry_failure_preserves_last_valid_model(qtbot, monkeypatch):
    w = window(qtbot)
    doc, target, _, _, refs = slot_fin()
    cid = doc.add_chamfer(target, refs, .5)
    w.document = doc
    w.refresh(fit=True)
    w.entity_context, w.browser_key = ('chamfer', cid), ('chamfer', cid)
    w.show_properties()
    w.viewport.select_face(w.viewport.faces[0])
    before = snapshot(w)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: None)
    w.entity_fields['distance'].setValue(1.2)
    assert not w.apply_dimensions()
    unchanged(w, before)
    assert doc.last_failure.status.diagnostic_stage == 'result_validation'


@pytest.mark.parametrize('action', ['undo', 'redo', 'open', 'new', 'delete', 'refresh'])
def test_other_update_paths_keep_committed_state_when_display_fails(qtbot, monkeypatch, tmp_path, action):
    import hero_cad.ui.viewport as module
    w, _, _, eid = fixture(qtbot)
    if action == 'redo':
        w.undo()
        w.viewport.select_face(w.viewport.faces[0])
    if action == 'delete':
        w.viewport.setFocus()
        w.browser.setCurrentItem(w.browser_items[('extrude', eid)])
    if action == 'open':
        path = tmp_path/'replacement.hcad'
        Document(BoxParameters(width=65)).save(path)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(path), ''))
    before = snapshot(w)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Discard)
    monkeypatch.setattr(module, 'edge_mesh', fail())
    if action == 'refresh':
        with pytest.raises(ValueError, match='injected'):
            w.refresh()
    else:
        getattr(w, {'open': 'open_document', 'new': 'new_document', 'delete': 'delete_selected'}.get(action, action))()
    unchanged(w, before)


def test_upstream_edit_can_commit_expected_unresolved_dependents(qtbot, tmp_path):
    w = window(qtbot)
    doc, target, _, _, refs = slot_fin()
    cid = doc.add_chamfer(target, refs, .5)
    sid = doc.add_sketch('XY')
    hole = Circle(30, 20, 1)
    doc.add_entity(sid, hole)
    downstream = doc.add_extrusion(sid, hole.id, distance=5, operation='cut', target_id=cid)
    w.document = doc
    w.refresh(fit=True)
    w.entity_context, w.browser_key = ('extrude', target), ('extrude', target)
    w.show_properties()
    w.entity_fields['distance'].setValue(11)
    assert w.apply_dimensions()
    assert doc.feature(target).parameters.distance == 11
    assert not doc.statuses[cid].valid and doc.statuses[cid].diagnostic_stage == 'edge_resolution'
    assert doc.statuses[downstream].blocked_by == cid
    assert cid not in doc.solid_shapes and downstream not in doc.solid_shapes
    assert w.viewport.mapper.GetInput().GetNumberOfCells() > 0
    doc.save(tmp_path/'unresolved.hcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and loaded.statuses == doc.statuses
    w.undo()
    assert doc.statuses[cid].valid and doc.statuses[downstream].valid
    w.redo()
    assert not doc.statuses[cid].valid


def test_operation_apply_preflights_edges_and_reuses_preview_evaluation(qtbot, monkeypatch):
    import hero_cad.ui.viewport as module
    w, sid, circle, _ = fixture(qtbot)
    panel = w.operation_panel
    panel.open(source=(sid, circle.id, ()), quick=True)
    panel.quick_distance.setText('12')
    assert panel.preview()
    doc, before = w.document, w.document.features
    original_state, original_undo = doc.shape, doc._undo[:]
    with monkeypatch.context() as patch:
        patch.setattr(Document, '_regenerate', fail('Apply must adopt, not regenerate'))
        patch.setattr(module, 'tessellate', fail('Apply must reuse preview surface'))
        patch.setattr(module, 'edge_mesh', fail('injected final edge preparation failure'))
        assert not panel.commit()
    assert doc.features is before and doc.shape is original_state and doc._undo == original_undo
    assert not panel.actor.GetVisibility() and panel.candidate is None
    assert panel.mapper.GetInput() is None
    assert w.viewport.mapper.GetInput().GetNumberOfCells() > 0
    assert panel.preview()
    with monkeypatch.context() as patch:
        patch.setattr(Document, '_regenerate', fail('Apply must adopt, not regenerate'))
        patch.setattr(module, 'tessellate', fail('Apply must reuse preview surface'))
        assert panel.commit()
    assert len(doc.features) == len(before)+1 and len(doc._undo) == len(original_undo)+1
    assert doc.features[-1].parameters.distance == 12


def test_leaf_sketch_failure_keeps_native_state_and_fast_path(qtbot, monkeypatch):
    import hero_cad.ui.sketch_view as module
    w = window(qtbot)
    sid = w.document.add_sketch('XY')
    circle = Circle(60, 0, 5)
    w.document.add_entity(sid, circle)
    w.refresh()
    w.entity_context, w.browser_key = (sid, circle.id), ('entity', sid, circle.id)
    w.show_properties()
    before = snapshot(w)
    monkeypatch.setattr(Document, '_regenerate', fail('leaf edit must not regenerate solids'))
    monkeypatch.setattr(module, 'paths_mesh', fail('injected leaf display failure'))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: None)
    w.entity_fields['radius'].setValue(6)
    assert not w.apply_dimensions()
    unchanged(w, before)


def test_failed_visibility_change_preserves_scene_and_document(qtbot, monkeypatch):
    import hero_cad.ui.viewport as module
    w, _, _, _ = fixture(qtbot)
    before = snapshot(w)
    monkeypatch.setattr(module, 'tessellate', fail('injected visibility meshing failure'))
    w.show_base_box.setChecked(not w.show_base_box.isChecked())
    unchanged(w, before)


def test_preview_cancel_restores_cached_meshes_even_if_meshing_is_unavailable(qtbot, monkeypatch):
    import hero_cad.ui.viewport as module
    w, sid, circle, _ = fixture(qtbot)
    panel = w.operation_panel
    before = snapshot(w)
    panel.open(source=(sid, circle.id, ()), quick=True)
    panel.quick_distance.setText('12')
    assert panel.preview()
    monkeypatch.setattr(module, 'tessellate', fail('Cancel must restore, not remesh'))
    monkeypatch.setattr(module, 'edge_mesh', fail('Cancel must restore, not rebuild edges'))
    panel.cancel()
    unchanged(w, before)
    assert not panel.actor.GetVisibility() and panel.candidate is None and panel.preview_surface is None


def test_ui_save_after_canceling_failed_properties_keeps_file_and_stacks(qtbot, monkeypatch, tmp_path):
    import hero_cad.ui.viewport as module
    w, _, _, _ = fixture(qtbot)
    doc = w.document
    doc.save(tmp_path/'valid.hcad')
    original = doc.path.read_bytes()
    stacks = doc._undo[:], doc._redo[:]
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: None)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'edge_mesh', fail())
        w.entity_fields['distance'].setValue(11)
        assert not w.apply_dimensions()
    w.undo()  # Existing UX: discard pending text first, without moving history.
    assert w.save_document()
    assert (doc._undo, doc._redo) == stacks and doc.path.read_bytes() == original
    reopened = Document.load(doc.path)
    assert reopened.features == doc.features
    assert volume(reopened.shape) == pytest.approx(volume(doc.shape))


def test_support_face_highlight_is_prepared_before_committing_attached_frame(qtbot, monkeypatch):
    import hero_cad.ui.support_face as module
    from hero_cad.sketch import FaceReference
    w = window(qtbot)
    w.show_base_box.setChecked(True)
    sid = w.document.add_face_sketch(FaceReference(w.document.features[0].id, '+Z'))
    w.refresh()
    w.viewport.sketch.enter(sid)
    w.entity_context, w.browser_key = None, ('box', w.document.features[0].id)
    w.show_properties()
    before = snapshot(w)
    assert w.viewport.support_actor.GetVisibility()
    monkeypatch.setattr(module, 'selected_mesh', fail('injected support highlight preparation failure'))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a: None)
    w.fields['height'].setValue(21)
    assert not w.apply_dimensions()
    unchanged(w, before)
    assert w.document.feature(sid).parameters.frame.origin[2] == 20


def test_unchanged_properties_during_preview_restore_baseline_without_empty_display(qtbot, monkeypatch):
    import hero_cad.ui.viewport as module
    w, sid, circle, eid = fixture(qtbot)
    panel = w.operation_panel
    before, stacks = w.document.features, (w.document._undo[:], w.document._redo[:])
    original_mesh = w.viewport.mapper.GetInput()
    panel.open(source=(sid, circle.id, ()), quick=True)
    panel.quick_distance.setText('12')
    assert panel.preview() and w.viewport.mapper.GetInput().GetNumberOfCells() == 0
    with monkeypatch.context() as patch:
        patch.setattr(module, 'tessellate', fail('Unchanged Properties should reuse retained baseline'))
        assert w.apply_dimensions()
    assert not panel.active and not panel.actor.GetVisibility()
    assert w.viewport.mapper.GetInput() is original_mesh
    assert w.document.features == before and (w.document._undo, w.document._redo) == stacks
    assert w.document.feature(eid).parameters.distance == 10

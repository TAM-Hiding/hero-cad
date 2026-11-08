"""Measured 2 mm fin boundary; preserve state instead of demanding a ridge."""
from dataclasses import replace
from math import pi
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_FACE
from hero_cad.document import Document
from hero_cad.features import Feature, FeatureError
from hero_cad.geometry import volume
from hero_cad.booleans import bounds
from hero_cad.sketch import Circle, SketchParameters
from hero_cad.history_inspection import feature_history_text
from hero_cad.ui.display_geometry import tessellate
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
# Also works with the README's console-script pytest invocation, which does not
# add the repository root to sys.path. Reuse the actual benchmark fixture.
_spec = spec_from_file_location('audit_benchmark', Path(__file__).resolve().parents[1]/'tools/benchmark_audit_041.py')
_benchmark = module_from_spec(_spec)
_spec.loader.exec_module(_benchmark)
slot_fin, stable_id = _benchmark.slot_fin, _benchmark.stable_id
from test_chamfers import state


@pytest.mark.parametrize('distance', [.5, .9, .99, .999, 1., 1.001, 1.2])
def test_slot_fin_boundary_valid_geometry_or_atomic_classified_failure(distance, tmp_path):
    doc, target, _, _, refs = slot_fin()
    before = state(doc)
    stacks = doc._undo[:], doc._redo[:]
    original = volume(doc.shape)
    if distance < 1:
        cid = doc.add_chamfer(target, refs, distance)
        result = doc.solid_shapes[cid]
        # Integrated obround parallel offsets over the bevel height.
        removed = (24+2*pi)*distance**2/2-pi*distance**3/3
        assert volume(result) == pytest.approx(original-removed)
        assert BRepCheck_Analyzer(result).IsValid()
        assert bounds(result) == pytest.approx((0, 40, 0, 30, 0, 15), abs=1e-7)
        assert tessellate(result).GetNumberOfCells() > 0
    else:
        # This kernel rejects these cases; a future valid native result is also
        # acceptable, provided validity and material removal are demonstrated.
        try:
            cid = doc.add_chamfer(target, refs, distance)
        except FeatureError as error:
            assert error.status.diagnostic_stage in ('chamfer_construction', 'result_validation')
            assert 'OCCT' in str(error)
            assert all(a is b for a, b in zip(state(doc), before))
            assert (doc._undo, doc._redo) == stacks
            assert doc.last_failure is error
        else:
            assert doc.feature(cid).parameters.distance == distance
            assert BRepCheck_Analyzer(doc.shape).IsValid()
            assert 0 < volume(doc.shape) < original
            assert tessellate(doc.shape).GetNumberOfCells() > 0
    doc.save(tmp_path/'boundary.hcad')
    reopened = Document.load(doc.path)
    assert reopened.features == doc.features and reopened.statuses == doc.statuses
    assert volume(reopened.shape) == pytest.approx(volume(doc.shape))


def test_failed_distance_edit_keeps_last_valid_history_and_serialization(tmp_path):
    doc, target, _, _, refs = slot_fin()
    cid = doc.add_chamfer(target, refs, .999)
    doc.save(tmp_path/'accepted.hcad')
    contents = doc.path.read_bytes()
    before = state(doc)
    stacks = doc._undo[:], doc._redo[:]
    with pytest.raises(FeatureError) as failure:
        doc.replace_feature(replace(doc.feature(cid), parameters=replace(doc.feature(cid).parameters, distance=1.2)))
    assert failure.value.status.diagnostic_stage == 'result_validation'
    assert 'topology_valid=False' in str(failure.value)
    assert all(a is b for a, b in zip(state(doc), before))
    assert (doc._undo, doc._redo) == stacks and not doc.dirty
    doc.save(doc.path)
    assert doc.path.read_bytes() == contents
    doc.undo()
    assert doc.active_body_ids == {target}
    doc.redo()
    assert doc.statuses[cid].valid


@pytest.mark.parametrize('change', ['base_width', 'slot_width', 'fin_height', 'intermediary', 'new_hole'])
def test_upstream_edits_preserve_or_explicitly_invalidate_fin_witnesses(change, tmp_path):
    doc, target, sid, slot, refs = slot_fin()
    cid = doc.add_chamfer(target, refs, .5)
    hole_source = doc.add_sketch('XY')
    hole = Circle(30, 20, 1)
    doc.add_entity(hole_source, hole)
    cut = doc.add_extrusion(hole_source, hole.id, distance=5, operation='cut', target_id=cid)
    before = doc.features
    if change == 'base_width':
        doc.set_box(replace(doc.parameters, width=45))
    elif change == 'slot_width':
        doc.update_entity(sid, replace(slot, radius=1.5))
    elif change == 'fin_height':
        fin = doc.feature(target)
        doc.replace_feature(replace(fin, parameters=replace(fin.parameters, distance=11)))
    elif change == 'intermediary':
        extra = Feature('sketch', SketchParameters('XZ'), ('plane:XZ',), stable_id('intermediary'))
        index = next(i for i, f in enumerate(doc.features) if f.id == cid)
        doc.set_features((*doc.features[:index], extra, *doc.features[index:]))
    else:
        # A new cut changes edge counts before the chamfer without touching its rim.
        source = Feature('sketch', SketchParameters('XY', entities=(Circle(32, 8, 1),)), ('plane:XY',))
        from hero_cad.features import ExtrudeParameters
        added = Feature('extrude', ExtrudeParameters(source.id, source.parameters.entities[0].id,
                        distance=5, operation='cut', target_id=target), (source.id, target))
        index = next(i for i, f in enumerate(doc.features) if f.id == cid)
        chamfer = doc.feature(cid)
        changed = replace(chamfer, parameters=replace(chamfer.parameters, target_id=added.id), references=(added.id,))
        doc.set_features((*doc.features[:index], source, added, changed, *doc.features[index+1:]))
    valid = change not in ('slot_width', 'fin_height')
    assert doc.statuses[cid].valid == valid
    assert doc.statuses[cut].valid == valid
    assert doc.statuses[hole_source].valid
    if not valid:
        assert doc.statuses[cid].diagnostic_stage == 'edge_resolution'
        assert doc.statuses[cut].blocked_by == cid
        assert cid not in doc.solid_shapes and cut not in doc.solid_shapes
        assert 'Failure stage: Edge Resolution' in feature_history_text(doc, cid)
    doc.save(tmp_path/'references.hcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and loaded.statuses == doc.statuses
    doc.undo()
    assert doc.features == before and doc.statuses[cid].valid and doc.statuses[cut].valid
    doc.redo()
    assert doc.features == loaded.features and doc.statuses == loaded.statuses


def test_removed_support_face_blocks_attached_sketch_without_substitution(tmp_path):
    doc, target, sid, slot, refs = slot_fin()
    cid = doc.add_chamfer(target, refs, .5)
    # Select the actual surviving current descendant, not a historical face.
    from hero_cad.face_history import subshapes
    current = next(face for face in subshapes(doc.solid_shapes[cid], TopAbs_FACE)
                   if abs(bounds(face)[4]-15) < 1e-7 and abs(bounds(face)[5]-15) < 1e-7)
    from OCP.TopoDS import TopoDS
    child = doc.add_face_sketch(doc.face_reference(TopoDS.Face_s(current)))
    before = doc.features
    doc.update_entity(sid, replace(slot, radius=.4))
    assert not doc.statuses[cid].valid and doc.statuses[child].blocked_by == cid
    doc.save(tmp_path/'missing-face.hcad')
    loaded = Document.load(doc.path)
    assert loaded.statuses == doc.statuses
    doc.undo()
    assert doc.features == before and doc.statuses[child].valid


def test_failure_stage_distinguishes_native_builder_and_result(monkeypatch):
    import hero_cad.chamfers as module
    doc, target, _, _, refs = slot_fin()
    def fail(*args):
        raise RuntimeError('injected builder failure')
    monkeypatch.setattr(module, 'BRepFilletAPI_MakeChamfer', fail)
    with pytest.raises(FeatureError) as failure:
        doc.add_chamfer(target, refs, .5)
    assert failure.value.status.diagnostic_stage == 'chamfer_construction'


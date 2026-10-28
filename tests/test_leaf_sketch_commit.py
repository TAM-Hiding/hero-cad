"""Identity, atomicity and conservative fallback for entity-only leaf edits."""
from dataclasses import replace
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from hero_cad.document import Document
from hero_cad.features import FeatureError, BoxParameters
from hero_cad.geometry import volume
from hero_cad.sketch import Circle, Line, FaceReference


def solid_state(doc):
    return tuple(getattr(doc, name) for name in (
        'shape', 'solid_shapes', 'face_maps', 'face_lineages', 'source_faces', 'active_body_ids', 'statuses'))


def test_leaf_commits_retain_coherent_solid_state_and_history(monkeypatch, tmp_path):
    doc = Document()
    sid = doc.add_face_sketch(FaceReference(doc.features[0].id, '+Z'))
    unused = doc.add_sketch('XZ')  # Edited sketch need not be last in history.
    original = doc.features
    state = solid_state(doc)
    frame = doc.feature(sid).parameters.frame
    with monkeypatch.context() as patch:
        patch.setattr(doc, '_regenerate', lambda *a, **k: pytest.fail('Leaf edit regenerated solids'))
        for entity in (Line(0, 0, 1, 1), Circle(4, 4, 2), Line(2, 0, 3, 1)):
            doc.add_entity(sid, entity)
            assert all(a is b for a, b in zip(solid_state(doc), state))
        doc.update_entity(sid, replace(entity, x2=4))
        assert doc.feature(sid).parameters.frame == frame
        assert doc.feature(unused) == original[-1]
    accepted = doc.features
    doc.undo()
    assert doc.feature(sid).parameters.entities[-1] == entity
    doc.redo()
    assert doc.features == accepted
    for _ in range(4):
        doc.undo()
    assert doc.features == original
    for _ in range(4):
        doc.redo()
    assert doc.features == accepted
    doc.save(tmp_path/'leaf.starcad')
    loaded = Document.load(tmp_path/'leaf.starcad')
    assert loaded.features == doc.features
    assert volume(loaded.shape) == pytest.approx(volume(doc.shape))
    assert BRepCheck_Analyzer(loaded.shape).IsValid()
    ref = FaceReference(doc.features[0].id, '+Z')
    assert doc.face_reference(doc.face_maps[ref.parent_id]['+Z']) == ref
    assert loaded.face_reference(loaded.face_maps[ref.parent_id]['+Z']) == ref


def test_leaf_failures_are_atomic(monkeypatch):
    import hero_cad.document as module
    doc = Document()
    sid = doc.add_sketch('XY')
    other = doc.add_sketch('XY')
    circle = Circle(0, 0, 1)
    doc.add_entity(other, circle)
    doc.undo()
    features, state = doc.features, solid_state(doc)
    stacks = doc._undo[:], doc._redo[:]
    def fail(*args):
        raise ValueError('sketch kernel failure')
    with monkeypatch.context() as patch:
        patch.setattr(module, 'make_sketch', fail)
        with pytest.raises(FeatureError, match='sketch kernel failure'):
            doc.add_entity(sid, circle)
    assert doc.features == features
    assert all(a is b for a, b in zip(solid_state(doc), state))
    assert (doc._undo, doc._redo) == stacks
    doc.redo()
    state, features = solid_state(doc), doc.features
    with pytest.raises(FeatureError, match='Duplicate entity'):
        doc.add_entity(sid, circle)
    with pytest.raises(FeatureError, match='Duplicate entity'):
        doc.add_entity(sid, replace(circle, id=doc.features[0].id))
    assert doc.features == features
    assert all(a is b for a, b in zip(solid_state(doc), state))


def test_consumed_sketch_and_upstream_changes_regenerate(monkeypatch):
    doc = Document()
    sid = doc.add_sketch('XY')
    circle = Circle(5, 5, 2)
    doc.add_entity(sid, circle)
    eid = doc.add_extrusion(sid, circle.id)
    calls = []
    regenerate = doc._regenerate
    def tracked(*args, **kwargs):
        calls.append(True)
        return regenerate(*args, **kwargs)
    monkeypatch.setattr(doc, '_regenerate', tracked)
    before = volume(doc.solid_shapes[eid])
    doc.update_entity(sid, replace(circle, radius=3))
    assert len(calls) == 1
    assert volume(doc.solid_shapes[eid]) > before
    doc.set_box(BoxParameters(width=50))
    assert len(calls) == 2
    doc.undo()
    doc.redo()
    assert len(calls) == 4


def test_unresolved_history_uses_full_regeneration(monkeypatch):
    from test_history_inspection import joined_transition_chain, convert_to_join
    doc, box, source, extrusion, attached, cut = joined_transition_chain()
    leaf = doc.add_sketch('XY')
    convert_to_join(doc, box, source, extrusion)
    assert not doc.statuses[attached].valid
    definitions = doc.features
    shape = doc.shape
    doc.add_entity(leaf, Line(0, 0, 1, 1))
    assert doc.shape is not shape
    assert not doc.statuses[attached].valid and doc.features[:-1] == definitions[:-1]
    doc.undo()  # entity edit
    doc.undo()  # upstream invalidation
    assert doc.statuses[attached].valid and doc.statuses[cut].valid
    assert BRepCheck_Analyzer(doc.shape).IsValid()


def test_leaf_after_boolean_preserves_topology_and_reopens(tmp_path):
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from hero_cad.ui.display_geometry import subshapes
    doc = Document()
    target = doc.features[0].id
    source = doc.add_sketch('XY')
    c = Circle(10, 10, 3)
    doc.add_entity(source, c)
    cut = doc.add_extrusion(source, c.id, distance=20, operation='cut', target_id=target)
    top_key = next(key for key, face in doc.face_maps[cut].items()
                   if BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane
                   and BRepAdaptor_Surface(face).Plane().Location().Z() == 20)
    reference = doc.face_reference(doc.face_maps[cut][top_key])
    sid = doc.add_face_sketch(reference)
    state = solid_state(doc)
    counts = tuple(len(subshapes(doc.shape, kind)) for kind in (TopAbs_FACE, TopAbs_EDGE))
    doc.add_entity(sid, Circle(25, 10, 2))
    assert all(a is b for a, b in zip(solid_state(doc), state))
    path = tmp_path/'cut-leaf.starcad'
    doc.save(path)
    loaded = Document.load(path)
    assert loaded.features == doc.features and loaded.statuses == doc.statuses
    assert volume(loaded.shape) == pytest.approx(volume(doc.shape))
    assert tuple(len(subshapes(loaded.shape, kind)) for kind in (TopAbs_FACE, TopAbs_EDGE)) == counts
    assert loaded.face_reference(loaded.face_maps[cut][top_key]) == reference

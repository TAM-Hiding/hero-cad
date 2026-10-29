from dataclasses import replace
from math import pi
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.GeomAbs import GeomAbs_Plane
from hero_cad.document import Document
from hero_cad.features import BoxParameters, ChamferParameters, FeatureError
from hero_cad.chamfers import EdgeReference, edge_reference, resolve_edge
from hero_cad.face_history import subshapes
from hero_cad.geometry import volume
from hero_cad.booleans import bounds
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, FaceReference
from hero_cad.history_inspection import feature_history_text


def bottom_edge(doc, target=None):
    target = target or next(iter(doc.active_body_ids))
    for edge in subshapes(doc.solid_shapes[target], TopAbs_EDGE):
        try:
            t, ref = doc.edge_reference(edge)
        except ValueError:
            continue
        if ref.endpoints == ((0., 0., 0.), (0., 30., 0.)):
            return t, ref
    raise AssertionError('Expected Y edge at X=Z=0')


def first_edge(doc, target):
    for edge in subshapes(doc.solid_shapes[target], TopAbs_EDGE):
        try:
            owner, ref = doc.edge_reference(edge)
            return owner, ref
        except ValueError:
            pass
    raise AssertionError('Expected one eligible straight edge')


def state(doc):
    return tuple(getattr(doc, name) for name in ('features', 'shape', 'solid_shapes', 'face_maps',
                 'face_lineages', 'source_faces', 'active_body_ids', 'sketch_shapes', 'statuses'))


def test_box_chamfer_geometry_edit_history_and_persistence(tmp_path):
    doc = Document()
    target, ref = bottom_edge(doc)
    cid = doc.add_chamfer(target, ref, 2)
    assert doc.features[-1].type == 'chamfer'
    assert doc.features[-1].references == (target,)
    assert doc.active_body_ids == {cid}
    assert BRepCheck_Analyzer(doc.shape).IsValid()
    assert bounds(doc.shape) == pytest.approx((0,40,0,30,0,20),abs=1e-7)
    assert volume(doc.shape) == pytest.approx(24000 - 30*2**2/2)
    bevel = doc.source_faces[cid][('bevel', None, None)]
    surf = BRepAdaptor_Surface(bevel)
    assert surf.GetType() == GeomAbs_Plane
    normal = surf.Plane().Axis().Direction()
    assert abs(normal.X()) == pytest.approx(abs(normal.Z()))
    assert abs(normal.Y()) < 1e-9
    changed = replace(doc.feature(cid), parameters=replace(doc.feature(cid).parameters, distance=3))
    doc.replace_feature(changed)
    assert doc.feature(cid).id == cid
    assert volume(doc.shape) == pytest.approx(24000 - 30*3**2/2)
    text = feature_history_text(doc, cid)
    assert 'Chamfer 1' in text and 'Equal distance: 3 mm' in text
    assert 'Chamfer target body / selected edge' in text
    doc.undo()
    assert doc.feature(cid).parameters.distance == 2
    doc.redo()
    assert doc.feature(cid).parameters.distance == 3
    doc.undo()
    doc.undo()
    assert doc.active_body_ids == {target} and volume(doc.shape) == pytest.approx(24000)
    doc.redo()
    assert volume(doc.shape) == pytest.approx(23940)
    doc.save(tmp_path/'chamfer.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and loaded.statuses == doc.statuses
    assert volume(loaded.shape) == pytest.approx(volume(doc.shape))
    assert len(subshapes(loaded.shape, TopAbs_FACE)) == 7
    assert serialize(doc.features)['version'] == 12
    assert deserialize(serialize(doc.features)) == doc.features


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf'), True, 100001, '2'])
def test_invalid_distances_rejected(value):
    doc = Document()
    target, ref = bottom_edge(doc)
    original = state(doc)
    with pytest.raises(ValueError, match='positive'):
        doc.add_chamfer(target, ref, value)
    assert state(doc) == original and not doc.can_undo


def test_failed_creation_and_distance_edit_are_atomic():
    doc = Document()
    target, ref = bottom_edge(doc)
    original = state(doc)
    with pytest.raises(FeatureError):
        doc.add_chamfer(target, ref, 100)
    assert all(a is b for a,b in zip(state(doc), original)) and not doc.can_undo
    cid = doc.add_chamfer(target, ref, 2)
    doc.undo()
    doc.redo()
    previous, stacks = state(doc), (doc._undo[:], doc._redo[:])
    with pytest.raises(FeatureError):
        doc.replace_feature(replace(doc.feature(cid), parameters=replace(doc.feature(cid).parameters, distance=100)))
    assert all(a is b for a,b in zip(state(doc), previous))
    assert (doc._undo, doc._redo) == stacks
    assert doc.feature(cid).parameters.distance == 2
    with pytest.raises(ValueError, match='current'):
        doc.add_chamfer(target, ref, 1)  # Historical target cannot be reused.


def test_edge_matching_survives_regeneration_and_conservative_upstream_edits(tmp_path):
    doc = Document()
    target, ref = bottom_edge(doc)
    cid = doc.add_chamfer(target, ref, 2)
    doc.set_box(BoxParameters(width=50))  # Selected bottom edge stays identical.
    assert doc.statuses[cid].valid
    assert volume(doc.shape) == pytest.approx(30000-60)
    doc.set_box(BoxParameters(width=50, depth=40))  # Segment length changes.
    assert not doc.statuses[cid].valid
    assert 'automatic edge substitution refused' in doc.statuses[cid].error
    assert cid not in doc.solid_shapes and target in doc.active_body_ids
    doc.save(tmp_path/'unresolved.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and not loaded.statuses[cid].valid
    doc.undo()
    assert doc.statuses[cid].valid and doc.active_body_ids == {cid}
    doc.redo()
    assert not doc.statuses[cid].valid
    doc.undo()
    assert doc.feature(cid).parameters.edge == ref
    # Candidate enumeration order cannot change resolution.
    edge = resolve_edge(ref, doc.solid_shapes[target], tuple(reversed(doc.face_lineages[target])))
    assert edge_reference(edge, doc.face_lineages[target]) == ref


def test_seams_stale_edges_and_ambiguous_ownership_rejected():
    doc = Document()
    sid = doc.add_sketch('XY')
    circle = Circle(10,10,5)
    doc.add_entity(sid, circle)
    eid = doc.add_extrusion(sid, circle.id)
    edges = subshapes(doc.solid_shapes[eid], TopAbs_EDGE)
    errors = []
    for edge in edges:
        try:
            doc.edge_reference(edge)
        except ValueError as error:
            errors.append(str(error))
    assert any('manifold' in message for message in errors)
    old = subshapes(doc.solid_shapes[doc.features[0].id], TopAbs_EDGE)[0]
    doc.set_box(BoxParameters(width=50))
    with pytest.raises(ValueError, match='exactly one current'):
        doc.edge_reference(old)
    target, ref = bottom_edge(doc, doc.features[0].id)
    with pytest.raises(ValueError, match='ambiguous'):
        import hero_cad.chamfers as module
        from unittest.mock import patch
        real = module.subshapes
        def duplicated(shape, kind):
            result = real(shape,kind)
            return result+result if shape is doc.solid_shapes[target] else result
        with patch.object(module, 'subshapes', duplicated):
            resolve_edge(ref, doc.solid_shapes[target], doc.face_lineages[target])


@pytest.mark.parametrize('operation', ['new', 'join', 'cut', 'boolean_join', 'boolean_cut'])
def test_chamfer_after_extrusion_and_boolean(operation):
    doc = Document()
    box = doc.features[0].id
    sid = doc.add_sketch('XY')
    rect = Rectangle(30,5,20,10) if 'join' in operation else Rectangle(5,5,10,10)
    doc.add_entity(sid,rect)
    boolean = operation.startswith('boolean_')
    eid = doc.add_extrusion(sid,rect.id,distance=10,
                            operation='new' if boolean else operation,
                            target_id=None if boolean or operation == 'new' else box)
    target = doc.add_boolean(operation[8:],box,(eid,)) if boolean else eid
    t, ref = first_edge(doc,target)
    cid = doc.add_chamfer(t,ref,.5)
    assert doc.statuses[cid].valid and cid in doc.active_body_ids
    assert BRepCheck_Analyzer(doc.solid_shapes[cid]).IsValid()
    assert doc.features[-1].references == (target,)
    assert doc.features[-2].id == target


def test_complex_bored_solid_and_downstream_face_sketch(tmp_path):
    doc = Document()
    target = doc.features[0].id
    for x in (7,16,25,34):
        for y in (7,23):
            sid = doc.add_sketch('XY')
            c = Circle(x,y,2)
            doc.add_entity(sid,c)
            target = doc.add_extrusion(sid,c.id,distance=20,operation='cut',target_id=target)
    t, ref = bottom_edge(doc,target)
    cid = doc.add_chamfer(t,ref,1)
    assert volume(doc.shape) == pytest.approx(24000-8*pi*4*20-15)
    bevel = doc.source_faces[cid][('bevel', None, None)]
    face = doc.face_reference(bevel)
    attached = doc.add_face_sketch(face)
    assert doc.statuses[attached].valid
    c = Circle(0,0,1)
    doc.add_entity(attached,c)
    # Unused face-sketch commits retain PR34's coherent state.
    old = doc.shape
    doc.add_entity(attached, Circle(5,0,1))
    assert doc.shape is old
    doc.save(tmp_path/'complex.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and all(s.valid for s in loaded.statuses.values())
    doc.replace_feature(replace(doc.feature(cid), parameters=replace(doc.feature(cid).parameters, distance=1.5)))
    assert doc.statuses[attached].valid
    from hero_cad.attachments import planar_frame, same_plane
    assert same_plane(doc.feature(attached).parameters.frame,
                      planar_frame(doc.source_faces[cid][('bevel',None,None)]))
    # Another edge on the chamfer result may be chamfered as its own feature.
    target, ref = first_edge(doc,cid)
    second = doc.add_chamfer(target,ref,.2)
    assert doc.statuses[second].valid


def test_native_tangent_chain_is_rejected_without_partial_history():
    doc = Document()
    box = doc.features[0].id
    sid = doc.add_sketch('XY')
    rectangle = Rectangle(40,0,10,30)
    doc.add_entity(sid,rectangle)
    target = doc.add_extrusion(sid,rectangle.id,distance=20,operation='join',target_id=box)
    ref = next(doc.edge_reference(edge)[1] for edge in subshapes(doc.solid_shapes[target],TopAbs_EDGE)
               if doc.edge_reference(edge)[1].endpoints == ((0.,0.,0.),(40.,0.,0.)))
    previous, stacks = state(doc), (doc._undo[:],doc._redo[:])
    with pytest.raises(FeatureError,match='edge-chain propagation'):
        doc.add_chamfer(target,ref,1)
    assert all(a is b for a,b in zip(state(doc),previous))
    assert (doc._undo,doc._redo) == stacks


def test_chamfer_can_feed_downstream_cut_and_recover():
    doc = Document()
    target, ref = bottom_edge(doc)
    cid = doc.add_chamfer(target,ref,1)
    sid = doc.add_sketch('XY')
    c = Circle(15,15,3)
    doc.add_entity(sid,c)
    cut = doc.add_extrusion(sid,c.id,distance=20,operation='cut',target_id=cid)
    assert doc.statuses[cut].valid
    doc.set_box(BoxParameters(depth=40))
    assert not doc.statuses[cid].valid and not doc.statuses[cut].valid
    doc.undo()
    assert doc.statuses[cid].valid and doc.statuses[cut].valid
    assert BRepCheck_Analyzer(doc.shape).IsValid()
    with pytest.raises(ValueError, match='references'):
        doc.delete(features=(cid,))


def test_kernel_failure_preserves_document(monkeypatch):
    import hero_cad.chamfers as module
    doc = Document()
    target, ref = bottom_edge(doc)
    original = state(doc)
    def fail(*args):
        raise RuntimeError('kernel failure')
    monkeypatch.setattr(module,'BRepFilletAPI_MakeChamfer',fail)
    with pytest.raises(FeatureError,match='kernel failure'):
        doc.add_chamfer(target,ref,1)
    assert all(a is b for a,b in zip(state(doc),original))


def test_schema_rejects_malformed_or_legacy_chamfer():
    doc = Document()
    target, ref = bottom_edge(doc)
    doc.add_chamfer(target,ref,1)
    payload = serialize(doc.features)
    payload['version'] = 11
    with pytest.raises(ValueError,match='Unsupported feature'):
        deserialize(payload)
    payload['version'] = 12
    payload['features'][-1]['parameters']['edge']['endpoints'] = [[0,0,0]]
    with pytest.raises(ValueError):
        deserialize(payload)
    assert serialize(Document().features)['version'] == 3  # Existing format unchanged.

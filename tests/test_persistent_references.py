"""Source-local persistent witnesses over real OCCT Boolean descendants."""
from dataclasses import replace
import json
import pytest
from OCP.TopAbs import TopAbs_FACE
from hero_cad.attachments import ResolutionState, resolve_supported_face, reference_key
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.geometry import volume
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, FaceReference, decode_face_origin
from test_evaluated_faces import center
from test_face_attachments import coincident


def pocket():
    d = Document(BoxParameters(40,30,10))
    box = d.features[0].id
    sid = d.add_face_sketch(FaceReference(box,'+Z'))
    r = Rectangle(18,13,4,4)
    d.add_entity(sid,r)
    cut = d.add_extrusion(sid,r.id,distance=-3,operation='cut',target_id=box)
    top = next(face for face in d.face_maps[cut].values() if abs(center(face)[2]-10)<1e-7)
    return d,box,sid,r,cut,top


def attached(d, cut, face, point):
    ref = d.face_reference(face,point=point)
    assert ref.support is not None
    sid = d.add_face_sketch(ref)
    c = Circle(5,5,.5); d.add_entity(sid,c)
    eid = d.add_extrusion(sid,c.id,distance=1)
    return ref,sid,c,eid


def split(d,sid,r):
    d.update_entity(sid,replace(r,x=-2,y=12,width=44,height=6))


def resolution(d,ref):
    return resolve_supported_face(ref,d.face_maps,{f.id:f for f in d.features},d.face_lineages,d.source_faces)


def test_split_recovery_uses_stored_source_point_and_preserves_frame(tmp_path):
    d,box,cutter,r,cut,face = pocket()
    ref,sid,c,eid = attached(d,cut,face,(5,5,10))
    old = d.feature(sid).parameters
    assert ref.support.count == 1 and ref.support.anchor == pytest.approx((5,5))
    assert decode_face_origin(ref.support.root)[0] == box
    split(d,cutter,r)
    assert reference_key(ref) not in d.face_maps[cut]  # Exact signature really changed.
    roots = frozenset(ref.support.origins)
    descendants = [f for f,t in d.face_lineages[cut] if t == roots]
    assert len(descendants) == 2  # Both current regions retain the historical root.
    assert len(d.face_descendants(FaceReference(box,'+Z'),cut)) == 2
    found = resolution(d,ref)
    assert found.state == ResolutionState.RESOLVED
    assert center(found.face)[1] < 12
    assert d.statuses[sid].reference_state == 'resolved' and d.statuses[eid].valid
    assert d.feature(sid).parameters == old
    coincident(old.frame, found.face)
    d.set_box(BoxParameters(45,35,15))
    assert d.statuses[sid].valid and d.statuses[eid].valid
    p = d.feature(sid).parameters
    assert p.frame.origin[2] == pytest.approx(15)
    assert p.frame.u == old.frame.u and p.frame.v == old.frame.v
    assert p.entities == (c,) and p.attachment == ref
    before = d.features
    d.undo();d.redo();assert d.features == before
    d.save(tmp_path/'witness.starcad')
    data = json.loads(d.path.read_text())
    assert data['version'] == 9 and data['format'] == 'star-cad'
    loaded = Document.load(d.path)
    assert loaded.features == d.features and loaded.feature(sid).parameters.attachment == ref
    assert resolution(loaded,ref).state == ResolutionState.RESOLVED
    assert volume(loaded.shape) == pytest.approx(volume(d.shape))


@pytest.mark.parametrize('point,state', [((5,12,10),'ambiguous'), ((5,15,10),'missing')])
def test_split_boundary_or_removed_point_never_chooses_another_region(point,state,tmp_path):
    d,box,cutter,r,cut,face = pocket()
    ref,sid,c,eid = attached(d,cut,face,point)
    old = d.feature(sid).parameters
    split(d,cutter,r)
    assert resolution(d,ref).state.value == state
    assert d.statuses[sid].reference_state == state and not d.statuses[sid].valid
    assert not d.statuses[eid].valid and eid not in d.solid_shapes
    assert sid not in d.sketch_shapes and d.feature(sid).parameters == old
    d.save(tmp_path/(state+'.starcad'))
    loaded = Document.load(d.path)
    assert loaded.statuses[sid].reference_state == state
    assert loaded.feature(sid).parameters == old
    d.undo();assert d.statuses[sid].valid and d.statuses[eid].valid
    d.redo();assert d.statuses[sid].reference_state == state
    # A broken dependent does not prevent unrelated editing.
    other = d.add_sketch('XZ');d.add_entity(other,Circle(2,3,1))
    assert d.statuses[other].valid


def test_removed_supporting_face_is_missing_not_last_frame_fallback(tmp_path):
    d,box,cutter,r,cut,face = pocket()
    ref,sid,c,eid = attached(d,cut,face,(5,5,10))
    old = d.feature(sid).parameters
    d.update_entity(cutter,replace(r,x=-2,y=-2,width=44,height=34))
    assert d.statuses[cut].valid  # Still a valid lower block, but the old top is gone.
    assert d.statuses[sid].reference_state == 'missing'
    assert d.feature(sid).parameters == old and eid not in d.solid_shapes
    assert not resolution(d,ref).face
    d.save(tmp_path/'deleted.starcad')
    loaded = Document.load(d.path)
    assert loaded.statuses[sid].reference_state == 'missing'
    d.undo();assert d.statuses[sid].valid


def test_reversed_occt_enumeration_preserves_reference_and_descendants(monkeypatch):
    d,box,cutter,r,cut,face = pocket()
    ref,sid,c,eid = attached(d,cut,face,(5,5,10))
    split(d,cutter,r)
    import hero_cad.face_history as history
    original = history.subshapes
    monkeypatch.setattr(history,'subshapes',lambda shape,kind: list(reversed(original(shape,kind))))
    other = Document(features=d.features)
    assert other.features == d.features and other.statuses[sid].valid
    assert resolution(other,ref).state == ResolutionState.RESOLVED
    assert center(resolution(other,ref).face) == pytest.approx(center(resolution(d,ref).face))


def test_legacy_evaluated_reference_keeps_exact_only_semantics(tmp_path):
    d,box,cutter,r,cut,face = pocket()
    enriched = d.face_reference(face,point=(5,5,10))
    legacy = replace(enriched,support=None)
    sid = d.add_face_sketch(legacy)
    payload = serialize(d.features)
    assert payload['version'] == 7 and 'support' not in payload['features'][-1]['parameters']['attachment']
    loaded = Document(features=deserialize(payload))
    assert loaded.features == d.features and loaded.statuses[sid].valid
    split(loaded,cutter,r)
    assert loaded.statuses[sid].reference_state == 'missing'
    assert loaded.feature(sid).parameters.attachment.support is None


def test_attachments_resolve_at_their_parent_history_stage():
    d,box,cutter,r,cut,face = pocket()
    ref = d.face_reference(face,point=(5,15,10))
    sid = d.add_face_sketch(ref)
    later = d.add_face_sketch(FaceReference(box,'+Z'))
    slot = Rectangle(-2,12,44,6);d.add_entity(later,slot)
    result = d.add_extrusion(later,slot.id,distance=-3,operation='cut',target_id=cut)
    assert result in d.active_body_ids and cut not in d.active_body_ids
    assert d.statuses[sid].valid and d.feature(sid).parameters.attachment.parent_id == cut
    assert resolution(d,ref).state == ResolutionState.RESOLVED


@pytest.mark.parametrize('mutate', [
    lambda s:s.update(anchor=[True,0]),
    lambda s:s.update(anchor=[float('nan'),0]),
    lambda s:s.update(count=0),
    lambda s:s.update(sense=0),
    lambda s:s.update(origins=s['origins']*2),
    lambda s:s.update(root='unrelated'),
    lambda s:s.update(origins=['Face7']),
    lambda s:s.update(extra='not allowed'),
])
def test_strict_persisted_support_validation(mutate):
    d,box,cutter,r,cut,face = pocket()
    ref=d.face_reference(face,point=(5,5,10));sid=d.add_face_sketch(ref)
    payload=serialize(d.features)
    mutate(payload['features'][-1]['parameters']['attachment']['support'])
    with pytest.raises(ValueError):
        deserialize(payload)


def test_missing_root_and_multiple_plausible_descendants_are_diagnostic():
    d,box,cutter,r,cut,face = pocket()
    ref=d.face_reference(face,point=(5,5,10))
    definitions={f.id:f for f in d.features}
    missing=resolve_supported_face(ref,d.face_maps,definitions,d.face_lineages,{})
    assert missing.state == ResolutionState.MISSING and missing.face is None
    # A provider publishing overlapping descendants must never gain ordinal IDs.
    maps={**d.face_maps,cut:{}}
    rows=d.face_lineages[cut]
    tokens=frozenset(ref.support.origins)
    duplicate=next(row for row in rows if row[1]==tokens)
    ambiguous=resolve_supported_face(ref,maps,definitions,{**d.face_lineages,cut:(*rows,duplicate)},d.source_faces)
    assert ambiguous.state == ResolutionState.AMBIGUOUS and ambiguous.face is None


def test_new_body_semantic_faces_seed_the_same_ancestry_system():
    d=Document();sid=d.add_sketch('XY')
    r=Rectangle(0,0,20,15);d.add_entity(sid,r)
    body=d.add_extrusion(sid,r.id,distance=7)
    ref=FaceReference(body,'end')
    faces=d.face_descendants(ref,body)
    assert len(faces)==1 and faces[0].IsSame(d.face_maps[body][reference_key(ref)])
    assert all(decode_face_origin(t)[0]==body for _,tokens in d.face_lineages[body] for t in tokens)


def test_failed_candidate_does_not_replace_reference_caches():
    from hero_cad.features import FeatureError
    d,box,cutter,r,cut,face=pocket()
    ref,sid,c,eid=attached(d,cut,face,(5,5,10))
    before=d.features,d.face_maps,d.face_lineages,d.source_faces,d.active_body_ids
    # A forward dependency is rejected before any derived caches are published.
    bad=replace(d.feature(cutter),references=(eid,))
    with pytest.raises(FeatureError):
        d.replace_feature(bad)
    assert (d.features,d.face_maps,d.face_lineages,d.source_faces,d.active_body_ids)==before
    assert resolution(d,ref).state==ResolutionState.RESOLVED

"""New explicit current faces vs conservative historical attachment recovery."""
from dataclasses import replace
import json
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from hero_cad.document import Document
from hero_cad.attachments import AttachmentError, planar_frame, resolve_attachment, reference_key
from hero_cad.sketch import Circle,Slot,FaceReference
from hero_cad.persistence import serialize,deserialize
from hero_cad.face_geometry import face_digest
from hero_cad.face_history import subshapes
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from test_evaluated_faces import screwdriver,slot_regions


def world(frame,uv,z):
    point=frame.to_world(uv)
    return tuple(point[i]+z*frame.normal[i] for i in range(3))


def cap(d,body,frame,z):
    result=[]
    for raw in subshapes(d.solid_shapes[body],TopAbs_FACE):
        face=TopoDS.Face_s(raw)
        if BRepAdaptor_Surface(face).GetType()!=GeomAbs_Plane:
            continue
        plane=planar_frame(face)
        if abs(abs(sum(a*b for a,b in zip(plane.normal,frame.normal)))-1)<1e-9 and abs(sum((plane.origin[i]-frame.origin[i])*frame.normal[i] for i in range(3))-z)<1e-7:
            result.append(face)
    assert len(result)==1
    return result[0]


def cylinder(annular=False,plane='XY'):
    d=Document();sid=d.add_sketch(plane)
    outer=Circle(0,0,15);d.add_entity(sid,outer)
    inner=Circle(0,0,2)
    if annular:d.add_entity(sid,inner)
    body=d.add_extrusion(sid,outer.id,(inner.id,) if annular else (),distance=10)
    return d,sid,outer,inner,body


@pytest.mark.parametrize('annular',[False,True])
@pytest.mark.parametrize('plane',['XY','XZ','YZ'])
def test_cylinder_hole_slots_repeat_both_caps_edits_reload_history(annular,plane,tmp_path):
    d,source,outer,inner,body=cylinder(annular,plane)
    frame=d.feature(source).parameters.frame
    sketches=[];cuts=[];hole=None
    for stage in range(2 if annular else 3):
        # New references to both caps at every evaluated stage, with no restart.
        for z in (0,10):
            for _ in range(2):
                face=cap(d,body,frame,z)
                ref=d.face_reference(face,point=world(frame,(0,-11),z))
                sid=d.add_face_sketch(ref);d.add_entity(sid,Circle(2,3,.2))
                sketches.append((sid,ref))
        top=cap(d,body,frame,10)
        sid=d.add_face_sketch(d.face_reference(top,point=world(frame,(0,-11),10)))
        if stage==0 and not annular:
            entity=Circle(0,0,2);hole=(sid,entity)
        else:
            entity=Slot(-8,-5 if stage==(0 if annular else 1) else 5,1.5,16)
        d.add_entity(sid,entity)
        body=d.add_extrusion(sid,entity.id,distance=-10,operation='cut',target_id=body,
                             extent='through_all',direction=-1)
        cuts.append((sid,entity))
    # A final repeated attachment after all cuts, including the earliest bug stage.
    for z in (0,10):
        sid=d.add_face_sketch(d.face_reference(cap(d,body,frame,z),point=world(frame,(0,-11),z)))
        sketches.append((sid,d.feature(sid).parameters.attachment))
    # New Body distance, hole diameter, and slot dimensions retain safe support.
    seed=next(f for f in d.features if f.type=='extrude' and f.parameters.operation=='new')
    d.replace_feature(replace(seed,parameters=replace(seed.parameters,distance=14)))
    if annular:d.update_entity(source,replace(inner,radius=2.5))
    else:d.update_entity(hole[0],replace(hole[1],radius=2.5))
    slot_sid,slot=cuts[-1];d.update_entity(slot_sid,replace(slot,radius=1.8,distance=17))
    assert all(s.valid for s in d.statuses.values())
    assert all(d.feature(sid).parameters.attachment==ref for sid,ref in sketches)
    before=d.features;d.undo();d.redo();assert d.features==before
    d.save(tmp_path/(plane+str(annular)+'.starcad'))
    loaded=Document.load(d.path)
    assert loaded.features==d.features and all(s.valid for s in loaded.statuses.values())
    for z in (0,14):
        assert loaded.add_face_sketch(loaded.face_reference(cap(loaded,body,frame,z),point=world(frame,(0,-11),z)))


def test_concentric_prism_walls_get_distinct_radius_based_roots():
    d,source,outer,inner,body=cylinder(True)
    mapping=d.source_faces[body]
    assert ('curve',outer.id,'circle') in mapping and ('curve',inner.id,'circle') in mapping
    assert not mapping[('curve',outer.id,'circle')].IsSame(mapping[('curve',inner.id,'circle')])
    assert len(d.face_lineages[body])==4


def untagged(monkeypatch,with_slot=False):
    import hero_cad.document as module
    real=module.primitive_lineage
    monkeypatch.setattr(module,'primitive_lineage',lambda identifier,mapping:tuple((f,frozenset()) for f in mapping.values()))
    d,source,outer,inner,seed=cylinder()
    cutter=d.add_sketch('XY');c=Circle(0,0,2);d.add_entity(cutter,c)
    body=d.add_extrusion(cutter,c.id,distance=10,operation='cut',target_id=seed)
    if with_slot:
        slot_sketch=d.add_sketch('XY');slot=Slot(-8,-5,1.5,16)
        d.add_entity(slot_sketch,slot)
        body=d.add_extrusion(slot_sketch,slot.id,distance=10,operation='cut',target_id=body)
    monkeypatch.setattr(module,'primitive_lineage',real)
    return d,source,cutter,c,body


def test_explicit_face_without_any_history_uses_checked_snapshot(monkeypatch,tmp_path):
    d,source,cutter,c,body=untagged(monkeypatch)
    frame=d.feature(source).parameters.frame
    assert d.face_maps[body]=={} and all(not tokens for _,tokens in d.face_lineages[body])
    ref=d.face_reference(cap(d,body,frame,10),point=(0,-11,10))
    assert ref.snapshot and ref.support is None
    sid=d.add_face_sketch(ref);d.add_entity(sid,Circle(3,4,.2))
    assert d.statuses[sid].valid
    payload=serialize(d.features)
    assert payload['version']==10
    payload['version']=9
    with pytest.raises(ValueError,match='version 10'):
        deserialize(payload)
    d.save(tmp_path/'snapshot.starcad')
    loaded=Document.load(d.path)
    # The geometry is the same when known ancestry becomes available again.
    assert loaded.features==d.features and loaded.statuses[sid].valid
    import hero_cad.face_geometry as geometry
    original=geometry.subshapes
    monkeypatch.setattr(geometry,'subshapes',lambda shape,kind:list(reversed(original(shape,kind))))
    assert Document(features=d.features).features==d.features
    old=d.feature(sid).parameters
    d.update_entity(cutter,replace(c,radius=3))
    assert not d.statuses[sid].valid and d.statuses[sid].reference_state=='missing'
    assert d.feature(sid).parameters==old and sid not in d.sketch_shapes
    d.undo();assert d.statuses[sid].valid
    d.redo();assert not d.statuses[sid].valid
    d.save(tmp_path/'snapshot-missing.starcad')
    assert not Document.load(d.path).statuses[sid].valid


def test_unpublished_but_known_descendants_can_get_new_supported_references():
    d,source,circle,body,cutter,r,result=screwdriver()
    faces=slot_regions(d,result,source)[:2]
    d.face_maps[result]={}  # Model a conservative publisher excluding this neighborhood.
    refs=[]
    for index,point in enumerate(((0,-6,10),(0,6,10))):
        face=slot_regions(d,result,source)[index]
        ref=d.face_reference(face,point=point)
        assert ref.support is not None and ref.snapshot is None
        refs.append(ref)
        sid=d.add_face_sketch(ref)
        assert d.statuses[sid].valid
        d.face_maps[result]={}
    assert refs[0].segment!=refs[1].segment
    assert refs[0].support.origins==refs[1].support.origins
    # Existing legacy identity still has no right to invoke new-reference creation.
    with pytest.raises(AttachmentError,match='Unresolved'):
        resolve_attachment(FaceReference(result,'evaluated',segment='0'*64),d.face_maps,{f.id:f for f in d.features})


@pytest.mark.parametrize('field,value',[('anchor',[True,0,0]),('anchor',[0,0]),('anchor',[float('nan'),0,0]),('origins',['Face7'])])
def test_snapshot_schema_is_strict(monkeypatch,field,value):
    d,source,cutter,c,body=untagged(monkeypatch)
    ref=d.face_reference(cap(d,body,d.feature(source).parameters.frame,10),point=(0,-11,10))
    d.add_face_sketch(ref);payload=serialize(d.features)
    payload['features'][-1]['parameters']['attachment']['snapshot'][field]=value
    with pytest.raises(ValueError):deserialize(payload)


def test_missing_current_ownership_and_boundary_selection_have_specific_errors():
    d,source,outer,inner,body=cylinder()
    face=cap(d,body,d.feature(source).parameters.frame,10)
    with pytest.raises(AttachmentError,match='current evaluated'):
        Document().face_reference(face)
    d.face_maps[body]={}
    with pytest.raises(AttachmentError,match='strictly inside'):
        d.face_reference(face,point=(0,15,10))
    base=d.features[0].id
    d.solid_shapes[base]=d.solid_shapes[body]
    with pytest.raises(AttachmentError,match='Ambiguous owning body'):
        d.face_reference(face,point=(0,-11,10))


def test_current_snapshot_handles_slot_arcs_and_reversed_boundary_traversal(monkeypatch):
    d,source,cutter,c,body=untagged(monkeypatch,with_slot=True)
    face=cap(d,body,d.feature(source).parameters.frame,10)
    ref=d.face_reference(face,point=(0,-11,10))
    assert ref.snapshot is not None
    sid=d.add_face_sketch(ref)
    import hero_cad.face_geometry as geometry
    original=geometry.subshapes
    monkeypatch.setattr(geometry,'subshapes',lambda shape,kind:list(reversed(original(shape,kind))))
    loaded=Document(features=deserialize(serialize(d.features)))
    assert loaded.statuses[sid].valid and loaded.features==d.features

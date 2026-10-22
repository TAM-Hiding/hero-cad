from dataclasses import replace
from math import radians
import json
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from star_cad.attachments import AttachmentError, planar_frame, reference_key
from star_cad.document import Document
from star_cad.features import BoxParameters, FeatureError
from star_cad.geometry import volume
from star_cad.sketch import Circle, Rectangle, Slot, FaceReference
from star_cad.persistence import serialize, deserialize


def prism(plane='XY', entity=None, distance=10):
    d = Document()
    sid = d.add_sketch(plane)
    entity = entity or Rectangle(0, 0, 50, 25, 17)
    d.add_entity(sid, entity)
    eid = d.add_extrusion(sid, entity.id, distance=distance)
    return d, sid, eid, entity


def coincident(frame, face):
    plane = BRepAdaptor_Surface(face).Plane()
    origin = plane.Location()
    n = plane.Axis().Direction()
    for uv in ((0,0), (3,7), (-5,11)):
        p = frame.to_world(uv)
        assert sum((p[i]-origin.Coord(i+1))*n.Coord(i+1) for i in range(3)) == pytest.approx(0, abs=1e-9)
        assert frame.to_local(p) == pytest.approx(uv, abs=1e-9)
    assert frame.normal == pytest.approx(planar_frame(face).normal, abs=1e-12)


@pytest.mark.parametrize('name', ['+X','-X','+Y','-Y','+Z','-Z'])
def test_box_faces_attach_move_and_keep_local_geometry(name):
    d = Document()
    box = d.features[0]
    ref = d.face_reference(d.face_maps[box.id][name])
    assert ref == FaceReference(box.id, name)
    sid = d.add_face_sketch(ref)
    circle = Circle(3, 4, .02)
    d.add_entity(sid, circle)
    old = d.feature(sid).parameters.frame
    d.set_box(BoxParameters(60, 50, 40))
    p = d.feature(sid).parameters
    assert p.entities == (circle,) and p.frame.u == old.u and p.frame.v == old.v
    coincident(p.frame, d.face_maps[box.id][name])
    axis = 'XYZ'.index(name[1])
    assert p.frame.origin[axis] == (getattr(d.parameters, ('width','depth','height')[axis]) if name[0] == '+' else 0)
    assert BRepCheck_Analyzer(d.sketch_shapes[sid]).IsValid()
    d.undo()
    assert d.feature(sid).parameters.frame == old
    d.redo()
    assert d.feature(sid).parameters == p


@pytest.mark.parametrize('plane', ['XY','XZ','YZ'])
@pytest.mark.parametrize('distance', [10,-10])
@pytest.mark.parametrize('cap', ['start','end'])
def test_caps_follow_signed_distance_and_source_dimensions(plane, distance, cap):
    d, source, eid, rect = prism(plane, distance=distance)
    ref = FaceReference(eid, cap)
    assert d.face_reference(d.face_maps[eid][reference_key(ref)]) == ref
    sid = d.add_face_sketch(ref)
    slot = Slot(2,3,1,7,29)
    d.add_entity(sid, slot)
    d.replace_feature(replace(d.feature(eid), parameters=replace(d.feature(eid).parameters, distance=distance*2)))
    d.update_entity(source, replace(rect, width=80, height=30))
    p = d.feature(sid).parameters
    coincident(p.frame, d.face_maps[eid][reference_key(ref)])
    expected = tuple(x*(distance*2 if cap == 'end' else 0) for x in d.feature(source).parameters.frame.normal)
    assert p.frame.origin == pytest.approx(expected)
    assert p.entities == (slot,)
    assert BRepCheck_Analyzer(d.sketch_shapes[sid]).IsValid()


@pytest.mark.parametrize('entity,names', [
    (Rectangle(2,3,20,10,31), ['edge0','edge1','edge2','edge3']),
    (Slot(2,3,2,15,31), ['tangent0','tangent1']),
])
@pytest.mark.parametrize('plane', ['XY','XZ','YZ'])
def test_planar_sides_identified_by_boundary_not_order(entity, names, plane):
    d, source, eid, _ = prism(plane, entity)
    attachments = []
    for name in names:
        ref = FaceReference(eid, 'side', entity.id, name)
        face = d.face_maps[eid][reference_key(ref)]
        assert d.face_reference(face) == ref
        sid = d.add_face_sketch(ref)
        d.add_entity(sid, Circle(1,2,.3))
        attachments.append((sid, ref))
    updated = replace(entity, angle=entity.angle+27, x=9, y=-7)
    d.update_entity(source, updated)
    for sid, ref in attachments:
        coincident(d.feature(sid).parameters.frame, d.face_maps[eid][reference_key(ref)])
        assert d.feature(sid).parameters.entities[0].radius == .3


def test_hole_side_identity_survives_dimension_edit_and_reordering():
    d, source, eid, outer = prism(entity=Rectangle(0,0,50,25))
    # Recreate extrusion after adding a hole (existing topology rules apply).
    d.delete(features=(eid,))
    hole = Rectangle(5,5,10,8,12)
    d.add_entity(source,hole)
    eid = d.add_extrusion(source,outer.id,(hole.id,),10)
    ref = FaceReference(eid,'side',hole.id,'edge2')
    sid = d.add_face_sketch(ref)
    p = d.feature(source).parameters
    d.replace_feature(replace(d.feature(source), parameters=replace(p, entities=(replace(hole,width=11),outer))))
    coincident(d.feature(sid).parameters.frame,d.face_maps[eid][reference_key(ref)])


def test_invalidated_side_preserves_parameters_blocks_downstream_and_recovers(tmp_path):
    d, source, eid, rect = prism(entity=Rectangle(0,0,50,25))
    sid = d.add_face_sketch(FaceReference(eid,'side',rect.id,'edge0'))
    circle = Circle(1,2,.2)
    d.add_entity(sid,circle)
    downstream = d.add_extrusion(sid,circle.id,distance=1)
    old = d.feature(sid).parameters
    # Same stable boundary UUID, but primitive replacement removes its edge0.
    d.update_entity(source,Circle(0,0,5,id=rect.id))
    assert not d.statuses[sid].valid and 'edge0' in d.statuses[sid].error
    assert not d.statuses[downstream].valid
    assert d.feature(sid).parameters == old
    assert sid not in d.sketch_shapes and downstream not in d.solid_shapes
    d.save(tmp_path/'unresolved.starcad')
    reopened = Document.load(d.path)
    assert not reopened.statuses[sid].valid and reopened.feature(sid).parameters == old
    assert not reopened.dirty
    d.undo()
    assert d.statuses[sid].valid and d.statuses[downstream].valid
    d.redo()
    assert not d.statuses[sid].valid
    d.update_entity(source,rect)
    assert d.statuses[sid].valid and d.statuses[downstream].valid


def test_v5_roundtrip_chain_and_reference_validation(tmp_path):
    d, source, eid, rect = prism()
    sid = d.add_face_sketch(FaceReference(eid,'end'))
    circle = Circle(1,2,.5)
    d.add_entity(sid,circle)
    downstream = d.add_extrusion(sid,circle.id,distance=2)
    d.save(tmp_path/'attached.starcad')
    assert json.loads(d.path.read_text())['version'] == 5
    other = Document.load(d.path)
    assert other.features == d.features and not other.dirty
    assert volume(other.solid_shapes[downstream]) == pytest.approx(volume(d.solid_shapes[downstream]))
    with pytest.raises(ValueError,match='references'):
        d.delete(features=(eid,))
    payload = serialize(d.features)
    attached = next(f for f in payload['features'] if f['id'] == sid)
    attached['parameters']['frame']['u'] = [2,0,0]
    with pytest.raises(ValueError,match='orthonormal'):
        deserialize(payload)
    p = d.feature(sid).parameters
    bad = replace(d.feature(sid),references=(downstream,),parameters=replace(p,attachment=FaceReference(downstream,'end')))
    with pytest.raises(FeatureError,match='cyclic or forward'):
        d.replace_feature(bad)


def test_nonplanar_and_unknown_faces_rejected_without_history():
    d, source, eid, circle = prism(entity=Circle(0,0,5))
    n = len(d._undo)
    from star_cad.ui.display_geometry import subshapes
    faces = subshapes(d.solid_shapes[eid],TopAbs_FACE)
    curved = next(f for f in faces if BRepAdaptor_Surface(f).GetType().name != 'GeomAbs_Plane')
    with pytest.raises(AttachmentError,match='planar'):
        d.face_reference(curved)
    other = Document()
    with pytest.raises(AttachmentError,match='reliable'):
        d.face_reference(other.face_maps[other.features[0].id]['+Z'])
    with pytest.raises(AttachmentError,match='Unresolved'):
        d.add_face_sketch(FaceReference(eid,'side',circle.id,'edge0'))
    assert len(d._undo) == n


def compound_fixture(monkeypatch):
    """Test-only located box; product gains no transform/import operation."""
    import star_cad.document as module
    original = module.make_box
    x,y = gp_Trsf(),gp_Trsf()
    x.SetRotation(gp_Ax1(gp_Pnt(),gp_Dir(1,0,0)),radians(31))
    y.SetRotation(gp_Ax1(gp_Pnt(),gp_Dir(0,1,0)),radians(-23))
    transform = y.Multiplied(x)
    transform.SetTranslationPart(gp_Vec(7,-11,13))
    location = TopLoc_Location(transform)
    def make(*args,**kwargs):
        shape,mapping = original(*args,**kwargs)
        return shape.Moved(location), {k:TopoDS.Face_s(f.Moved(location)) for k,f in mapping.items()}
    monkeypatch.setattr(module,'make_box',make)
    return Document()


def test_compound_angle_attachment_exact_plane_and_downstream(monkeypatch,tmp_path):
    d = compound_fixture(monkeypatch)
    sid = d.add_face_sketch(FaceReference(d.features[0].id,'+Z'))
    d.add_entity(sid,Circle(2,3,1))
    eid = d.add_extrusion(sid,d.feature(sid).parameters.entities[0].id,distance=2)
    cap = d.add_face_sketch(FaceReference(eid,'end'))
    assert all(abs(x) > .1 for x in d.feature(cap).parameters.frame.normal)
    for identifier in (sid,cap):
        p = d.feature(identifier).parameters
        key = p.attachment.face if identifier == sid else reference_key(p.attachment)
        coincident(p.frame,d.face_maps[p.attachment.parent_id][key])
    d.set_box(BoxParameters(50,25,30))
    coincident(d.feature(sid).parameters.frame,d.face_maps[d.features[0].id]['+Z'])
    d.save(tmp_path/'angle.starcad')
    assert Document.load(d.path).features == d.features


def test_cap_depth_reversal_preserves_local_frame_without_mirroring(tmp_path):
    d, source, eid, rect = prism()
    sid = d.add_face_sketch(FaceReference(eid,'end'))
    circle = Circle(2,3,1)
    d.add_entity(sid,circle)
    before = d.feature(sid).parameters.frame
    d.replace_feature(replace(d.feature(eid),parameters=replace(d.feature(eid).parameters,distance=-10)))
    after = d.feature(sid).parameters.frame
    assert after.u == before.u and after.v == before.v and after.normal == before.normal
    assert after.origin == (0,0,-10) and d.feature(sid).parameters.entities == (circle,)
    d.save(tmp_path/'reversed.starcad')
    assert Document.load(d.path).feature(sid).parameters.frame == after

from dataclasses import replace
from math import pi
import json
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt
from star_cad.booleans import combine,bounds,OperationError
from star_cad.document import Document
from star_cad.features import BoxParameters,Feature,BooleanParameters,FeatureError
from star_cad.geometry import volume
from star_cad.sketch import Circle,Rectangle,FaceReference
from star_cad.persistence import serialize,deserialize


def cylinder(d, x=5, depth=15):
    sid = d.add_sketch('XY')
    c = Circle(x,5,2)
    d.add_entity(sid,c)
    eid = d.add_extrusion(sid,c.id,distance=depth)
    return sid,c,eid


@pytest.mark.parametrize('op,expected',[('join',1500),('cut',500),('intersect',500)])
def test_two_boxes_exact_kernel_result(op,expected):
    a = BRepPrimAPI_MakeBox(10,10,10).Shape()
    b = BRepPrimAPI_MakeBox(gp_Pnt(5,0,0),10,10,10).Shape()
    s = combine(op,a,[b])
    assert BRepCheck_Analyzer(s).IsValid() and volume(s) == pytest.approx(expected)
    assert bounds(s)[1] == pytest.approx(15 if op=='join' else 5 if op=='cut' else 10)


@pytest.mark.parametrize('op,expected',[('join',1000+20*pi),('cut',1000-40*pi),('intersect',40*pi)])
def test_box_cylinder_parametric_history_persistence(op,expected,tmp_path):
    d = Document(BoxParameters(10,10,10))
    box = d.features[0].id
    sid,c,eid = cylinder(d)
    bid = d.add_boolean(op,box,(eid,))
    assert volume(d.solid_shapes[bid]) == pytest.approx(expected)
    assert d.active_body_ids == {bid}
    assert set(d.solid_shapes) == {box,eid,bid}
    before=d.features
    d.update_entity(sid,replace(c,radius=1))
    assert d.features[-1].id==bid and d.features[-1].parameters.target_id==box
    d.undo(); assert d.features==before
    d.redo(); d.save(tmp_path/'boolean.starcad')
    loaded=Document.load(d.path)
    assert loaded.features==d.features and loaded.active_body_ids==d.active_body_ids
    assert json.loads(d.path.read_text())['version']==6


@pytest.mark.parametrize('op',['join','cut','intersect'])
def test_disjoint_or_touching_rejected_and_document_atomic(op):
    d=Document(BoxParameters(10,10,10))
    _,_,eid=cylinder(d,x=30)
    before,n=d.features,len(d._undo)
    with pytest.raises(FeatureError,match='overlap'):
        d.add_boolean(op,d.features[0].id,(eid,))
    assert d.features==before and len(d._undo)==n
    a=BRepPrimAPI_MakeBox(10,10,10).Shape()
    touching=BRepPrimAPI_MakeBox(gp_Pnt(10,0,0),10,10,10).Shape()
    with pytest.raises(OperationError):
        combine(op,a,[touching])


@pytest.mark.parametrize('through',[False,True])
def test_face_cut_blind_or_through_recomputes_target_thickness(through,tmp_path):
    d=Document(BoxParameters(20,20,10))
    box=d.features[0].id
    sid=d.add_face_sketch(FaceReference(box,'+Z'))
    c=Circle(10,10,2); d.add_entity(sid,c)
    eid=d.add_extrusion(sid,c.id,distance=-5,operation='cut',target_id=box,
                       extent='through_all' if through else 'distance',direction=-1)
    assert volume(d.solid_shapes[eid])==pytest.approx(4000-4*pi*(10 if through else 5))
    d.set_box(BoxParameters(20,20,25))
    assert volume(d.solid_shapes[eid])==pytest.approx(10000-4*pi*(25 if through else 5))
    if not through:
        p=d.feature(eid).parameters
        d.replace_feature(replace(d.feature(eid),parameters=replace(p,distance=-8)))
        assert volume(d.solid_shapes[eid])==pytest.approx(10000-32*pi)
    d.save(tmp_path/'cut.starcad')
    assert Document.load(d.path).features==d.features


@pytest.mark.parametrize('plane',['XY','XZ','YZ'])
@pytest.mark.parametrize('direction',[-1,1])
def test_through_all_on_signed_extrusion_caps(plane,direction):
    d=Document()
    sid=d.add_sketch(plane)
    r=Rectangle(0,0,20,20);d.add_entity(sid,r)
    target=d.add_extrusion(sid,r.id,distance=direction*10)
    cap=d.add_face_sketch(FaceReference(target,'end'))
    # Use cap-local coordinates; outward frame may reverse V.
    frame=d.feature(cap).parameters.frame
    local=frame.to_local(d.feature(sid).parameters.frame.to_world((10,10)))
    c=Circle(*local,2);d.add_entity(cap,c)
    cut=d.add_extrusion(cap,c.id,operation='cut',target_id=target,extent='through_all',direction=-1)
    assert volume(d.solid_shapes[cut])==pytest.approx(4000-40*pi)
    d.replace_feature(replace(d.feature(target),parameters=replace(d.feature(target).parameters,distance=direction*30)))
    assert volume(d.solid_shapes[cut])==pytest.approx(12000-120*pi)


def test_negative_new_body_is_not_subtraction_and_unrelated_body_survives():
    d=Document(BoxParameters(10,10,10))
    sid,c,eid=cylinder(d,depth=-5)
    assert d.feature(eid).parameters.operation=='new'
    assert len(d.active_body_ids)==2
    _,_,other=cylinder(d,x=40)
    # Positive second cylinder intersects the box.
    _,_,tool=cylinder(d)
    result=d.add_boolean('cut',d.features[0].id,(tool,))
    assert d.active_body_ids=={eid,other,result}


def test_existing_operation_failure_keeps_parameters_and_recovers(tmp_path):
    d=Document(BoxParameters(10,10,10))
    sid,c,eid=cylinder(d)
    result=d.add_boolean('join',d.features[0].id,(eid,))
    p=d.feature(result).parameters
    d.update_entity(sid,replace(c,x=40))
    assert not d.statuses[result].valid and result not in d.solid_shapes
    assert d.feature(result).parameters==p
    d.save(tmp_path/'failed.starcad')
    assert not Document.load(d.path).statuses[result].valid
    d.undo();assert d.statuses[result].valid


def test_changed_prism_to_boolean_unresolves_old_cap_reference():
    d=Document(BoxParameters(10,10,10))
    sid,c,eid=cylinder(d)
    attached=d.add_face_sketch(FaceReference(eid,'end'))
    d.add_entity(attached,Circle(0,0,.2))
    p=d.feature(eid).parameters
    d.replace_feature(replace(d.feature(eid),parameters=replace(p,operation='join',target_id=d.features[0].id),
                              references=(sid,d.features[0].id)))
    assert not d.statuses[attached].valid and 'Unresolved face' in d.statuses[attached].error
    assert d.feature(attached).parameters.entities


def test_dependency_validation_and_legacy_defaults():
    d=Document()
    sid,c,eid=cylinder(d)
    legacy=serialize(d.features)
    assert legacy['version']==4
    assert deserialize(legacy)[-1].parameters.operation=='new'
    p=replace(d.feature(eid).parameters,direction=-1)
    assert p.direction==1  # Signed-distance mode has no second direction state.
    assert deserialize(serialize((d.features[0],d.feature(sid),replace(d.feature(eid),parameters=p))))[-1].parameters==p
    p=BooleanParameters('join',d.features[0].id,(eid,))
    f=Feature('boolean',p,(d.features[0].id,eid))
    with pytest.raises(FeatureError,match='forward'):
        d.set_features((d.features[0],f,*d.features[1:]))
    with pytest.raises(ValueError):
        BooleanParameters('join',eid,(eid,))


def test_join_connected_chain_does_not_depend_on_tool_order():
    box=lambda x:BRepPrimAPI_MakeBox(gp_Pnt(x,0,0),10,10,10).Shape()
    assert volume(combine('join',box(0),[box(15),box(7)]))==pytest.approx(2500)

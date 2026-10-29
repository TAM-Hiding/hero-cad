"""Native curved chamfers and conservative geometric reference regression cases."""
from copy import deepcopy
from dataclasses import replace
from math import pi, cos, sin
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from hero_cad.chamfers import edge_reference, resolve_edge
from hero_cad.document import Document
from hero_cad.face_history import subshapes, primitive_lineage
from hero_cad.features import BoxParameters, FeatureError
from hero_cad.geometry import volume
from hero_cad.booleans import bounds, OperationError
from hero_cad.history_inspection import feature_history_text
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, Slot
from test_chamfers import state


def model(kind='hole'):
    doc = Document()
    sid = doc.add_sketch('XY')
    entity = Slot(10,10,3,12,0) if kind == 'slot' else Circle(15,15,5)
    doc.add_entity(sid, entity)
    target = doc.add_extrusion(sid, entity.id, distance=20 if kind in ('hole','slot') else 30,
                               operation='cut' if kind in ('hole','slot') else 'join',
                               target_id=doc.features[0].id)
    if kind == 'arc':
        cut_sketch = doc.add_sketch('XY')
        cutter = Rectangle(15,0,25,30)
        doc.add_entity(cut_sketch, cutter)
        target = doc.add_extrusion(cut_sketch, cutter.id, distance=40, operation='cut', target_id=target)
    return doc, target, sid, entity


def curved_edge(doc, target, z, x=15):
    for edge in subshapes(doc.solid_shapes[target], TopAbs_EDGE):
        try:
            reference = edge_reference(edge, doc.face_lineages[target])
        except ValueError:
            continue
        if reference.curve_type != 'line' and reference.center == (x,15.,z):
            return edge, reference
    raise AssertionError('Expected eligible circular edge')


def circular_geometry(shape):
    return [BRepAdaptor_Curve(TopoDS.Edge_s(e)) for e in subshapes(shape,TopAbs_EDGE)
            if BRepAdaptor_Curve(TopoDS.Edge_s(e)).GetType() == GeomAbs_Circle]


@pytest.mark.parametrize('kind,z', [('hole',20), ('hole',0), ('boss',30), ('arc',30)])
def test_native_curved_chamfer_geometry_history_edit_undo_persistence(kind,z,tmp_path):
    doc, target, sid, entity = model(kind)
    edge, ref = curved_edge(doc,target,z)
    old_volume = volume(doc.solid_shapes[target])
    old_bounds = bounds(doc.solid_shapes[target])
    cid = doc.add_chamfer(target,ref,.5)
    assert doc.feature(cid).type == 'chamfer'
    assert doc.feature(cid).references == (target,)
    assert doc.features[-2].id == target
    assert BRepCheck_Analyzer(doc.solid_shapes[cid]).IsValid()
    # Revolved triangular bevel: integral 2*pi*(r +/- t)*(d-t) dt.
    def removed(d):
        return (pi*5*d*d + (1 if kind == 'hole' else -1)*pi*d**3/3) * (.5 if kind == 'arc' else 1)
    assert volume(doc.solid_shapes[cid]) == pytest.approx(old_volume-removed(.5))
    assert bounds(doc.solid_shapes[cid]) == pytest.approx(old_bounds,abs=1e-7)
    bevel = doc.source_faces[cid][('bevel',None,None)]
    assert BRepAdaptor_Surface(bevel).GetType() == GeomAbs_Cone
    assert any(bevel.IsSame(f) and tokens for f,tokens in doc.face_lineages[cid])
    # The other hole rim keeps its exact radius and elevation.
    if kind == 'hole':
        assert any(c.Circle().Radius() == pytest.approx(5) and
                   c.Circle().Location().Z() == pytest.approx(20-z)
                   for c in circular_geometry(doc.solid_shapes[cid]))
    changed = replace(doc.feature(cid), parameters=replace(doc.feature(cid).parameters,distance=1))
    doc.replace_feature(changed)
    assert doc.feature(cid).id == cid
    assert volume(doc.solid_shapes[cid]) == pytest.approx(old_volume-removed(1))
    text = feature_history_text(doc,cid)
    assert ('Circular arc:' if kind=='arc' else 'Circle:') in text
    assert 'Edge identity:' in text and 'Target:' in text
    doc.undo()
    assert doc.feature(cid).parameters.distance == .5
    doc.undo()
    assert target in doc.active_body_ids and cid not in doc.solid_shapes
    doc.redo(); doc.redo()
    assert doc.feature(cid) == changed
    doc.save(tmp_path/f'{kind}-{z}.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and loaded.statuses == doc.statuses
    assert volume(loaded.solid_shapes[cid]) == pytest.approx(old_volume-removed(1))
    assert serialize(doc.features)['version'] == 13
    assert deserialize(serialize(doc.features)) == doc.features
    assert doc.feature(cid).parameters.edge == ref
    assert edge_reference(resolve_edge(ref,doc.solid_shapes[target],doc.face_lineages[target]),
                          doc.face_lineages[target]) == ref


def test_circular_reference_upstream_changes_unresolved_and_undo_recovery(tmp_path):
    doc,target,sid,circle = model()
    _,ref = curved_edge(doc,target,20)
    cid = doc.add_chamfer(target,ref,1)
    doc.set_box(BoxParameters(width=45))
    assert doc.statuses[cid].valid  # Same circle, different outer plate width.
    for changed in (replace(circle,radius=6), replace(circle,x=16)):
        doc.update_entity(sid,changed)
        assert not doc.statuses[cid].valid and cid not in doc.solid_shapes
        assert 'missing or changed' in doc.statuses[cid].error
        doc.save(tmp_path/'unresolved.starcad')
        loaded=Document.load(doc.path)
        assert not loaded.statuses[cid].valid and loaded.feature(cid).parameters.edge == ref
        doc.undo()
        assert doc.statuses[cid].valid
        doc.redo()
        assert not doc.statuses[cid].valid
        doc.undo()
        assert doc.statuses[cid].valid


def test_similar_circles_scoped_to_geometry_ancestry_and_explicit_body():
    doc,target,sid,circle = model()
    second_sid=doc.add_sketch('XY'); second=Circle(28,15,5);doc.add_entity(second_sid,second)
    target=doc.add_extrusion(second_sid,second.id,distance=20,operation='cut',target_id=target)
    _,ref=curved_edge(doc,target,20)
    resolved=resolve_edge(ref,doc.solid_shapes[target],doc.face_lineages[target])
    assert BRepAdaptor_Curve(resolved).Circle().Location().X() == 15
    _,other=curved_edge(doc,target,20,28)
    with pytest.raises(OperationError,match='missing or changed'):
        resolve_edge(replace(ref,center=other.center),doc.solid_shapes[target],doc.face_lineages[target])
    # A geometrically identical rim in a different body has different construction ancestry.
    independent=doc.add_extrusion(sid,circle.id,distance=20)
    with pytest.raises(OperationError,match='missing or changed'):
        resolve_edge(ref,doc.solid_shapes[independent],doc.face_lineages[independent])
    # Duplicate native enumeration is ambiguous, never first-match wins.
    from unittest.mock import patch
    import hero_cad.chamfers as module
    real=module.subshapes
    def duplicates(shape,kind):
        result=real(shape,kind)
        return result+result if shape is doc.solid_shapes[target] else result
    with patch.object(module,'subshapes',duplicates), pytest.raises(OperationError,match='ambiguous'):
        resolve_edge(ref,doc.solid_shapes[target],doc.face_lineages[target])
    assert doc.edge_reference(resolve_edge(ref,doc.solid_shapes[target],doc.face_lineages[target]))[0] == target


def cylinder_rim(axis, angle=None):
    shape=(BRepPrimAPI_MakeCylinder(axis,5,10) if angle is None else
           BRepPrimAPI_MakeCylinder(axis,5,10,angle)).Shape()
    mapping={}
    for f in subshapes(shape,TopAbs_FACE):
        surface=BRepAdaptor_Surface(TopoDS.Face_s(f))
        if surface.GetType()==GeomAbs_Cylinder:
            key=('curve','00000000-0000-0000-0000-000000000001','circle')
        elif abs(surface.Plane().Axis().Direction().Z())>.9:
            key='+Z' if surface.Plane().Location().Z()>5 else '-Z'
        else:
            # Only the cap/cylinder ancestry participates in the selected rim.
            continue
        mapping[key]=TopoDS.Face_s(f)
    lineage=primitive_lineage('00000000-0000-0000-0000-000000000002',mapping)
    for e in subshapes(shape,TopAbs_EDGE):
        curve=BRepAdaptor_Curve(TopoDS.Edge_s(e))
        if curve.GetType()==GeomAbs_Circle and curve.Circle().Location().Z()>5:
            return TopoDS.Edge_s(e),lineage
    raise AssertionError('Expected top rim')


@pytest.mark.parametrize('tilted',[False,True])
@pytest.mark.parametrize('angle',[None,pi/2,pi,3*pi/2])
def test_native_circle_and_arc_parameterization_axis_and_edge_reversal(angle,tilted):
    arc=angle is not None
    edge,lineage=cylinder_rim(gp_Ax2(gp_Pnt(),gp_Dir(0,0,1),gp_Dir(1,0,0)),angle)
    ref=edge_reference(edge,lineage)
    assert edge_reference(TopoDS.Edge_s(edge.Reversed()),tuple(reversed(lineage)))==ref
    if arc:
        # Same upper semicircle traversed in reverse with a reversed circle axis.
        other,other_lineage=cylinder_rim(gp_Ax2(gp_Pnt(0,0,10),gp_Dir(0,0,-1),gp_Dir(cos(angle),sin(angle),0)),angle)
        # This helper selects z>5, i.e. the cylinder start cap in this fixture.
        # Give that geometrically identical cap the same construction ancestry.
        other_lineage=tuple((f, frozenset(t.replace('"-Z"','"+Z"') for t in ts)) for f,ts in other_lineage)
    else:
        other,other_lineage=cylinder_rim(gp_Ax2(gp_Pnt(),gp_Dir(0,0,1),gp_Dir(0,1,0)))
    assert edge_reference(other,other_lineage)==ref
    if tilted:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Ax1, gp_Trsf
        transform=gp_Trsf()
        transform.SetRotation(gp_Ax1(gp_Pnt(1,2,3),gp_Dir(1,2,3)),.7)
        def moved_reference(e,faces):
            from hero_cad.geometry import compound
            builder=BRepBuilderAPI_Transform(compound([f for f,_ in faces]),transform,True)
            moved=TopoDS.Edge_s(builder.ModifiedShape(e))
            moved_faces=tuple((TopoDS.Face_s(builder.ModifiedShape(f)),ts) for f,ts in faces)
            return edge_reference(moved,moved_faces)
        # Transform each shared topology together, retaining adjacency.
        assert moved_reference(edge,lineage)==moved_reference(other,other_lineage)
    if not arc:
        assert ref.endpoints==() and ref.midpoint is None  # No seam persisted.
    else:
        if angle != pi:
            return
        opposite,opposite_lineage=cylinder_rim(gp_Ax2(gp_Pnt(),gp_Dir(0,0,1),gp_Dir(-1,0,0)),pi)
        opposite_ref=edge_reference(opposite,opposite_lineage)
        assert opposite_ref.endpoints==ref.endpoints
        assert opposite_ref.midpoint!=ref.midpoint
        assert opposite_ref!=ref


def test_slot_arc_reference_persistence_and_tangent_chain_refusal():
    doc,target,_,_=model('slot')
    refs=[]
    for e in subshapes(doc.solid_shapes[target],TopAbs_EDGE):
        try: ref=edge_reference(e,doc.face_lineages[target])
        except ValueError: continue
        if ref.curve_type=='arc': refs.append(ref)
    assert len(refs)==4
    for ref in refs:
        assert ref.radius==3 and abs(ref.endpoints[0][1]-ref.endpoints[1][1])==6
        previous=state(doc); stacks=doc._undo[:],doc._redo[:]
        with pytest.raises(FeatureError,match='edge-chain propagation'):
            doc.add_chamfer(target,ref,.5)
        assert all(a is b for a,b in zip(state(doc),previous))
        assert (doc._undo,doc._redo)==stacks
    # Arc records round-trip even when a stored feature is unresolved upstream.
    from hero_cad.features import Feature,ChamferParameters
    features=doc.features+(Feature('chamfer',ChamferParameters(target,refs[0]),(target,)),)
    assert deserialize(serialize(features))==features


@pytest.mark.parametrize('value',[0,-1,100])
def test_invalid_circular_distances_and_failed_edits_are_atomic(value):
    doc,target,_,_=model()
    _,ref=curved_edge(doc,target,20)
    previous=state(doc);stacks=doc._undo[:],doc._redo[:]
    with pytest.raises(ValueError):doc.add_chamfer(target,ref,value)
    assert all(a is b for a,b in zip(state(doc),previous))
    assert (doc._undo,doc._redo)==stacks
    cid=doc.add_chamfer(target,ref,1)
    previous=state(doc);stacks=doc._undo[:],doc._redo[:]
    with pytest.raises(ValueError):
        doc.replace_feature(replace(doc.feature(cid),parameters=replace(doc.feature(cid).parameters,distance=value)))
    assert all(a is b for a,b in zip(state(doc),previous))
    assert (doc._undo,doc._redo)==stacks


@pytest.mark.parametrize('field,value',[
    ('curve_type','ellipse'),('center',[0,0]),('center',[True,0,0]),('center',[float('nan'),0,0]),
    ('radius',0),('radius',True),('radius',float('inf')),('axis',[0,0,-1]),('axis',[0,0,2]),
    ('endpoints',[[0,0,0],[1,0,0]]),('midpoint',[1,0,0]),('extra',1)])
def test_strict_circular_persistence_rejects_malformed_geometry(field,value):
    doc,target,_,_=model();_,ref=curved_edge(doc,target,20);doc.add_chamfer(target,ref,1)
    payload=serialize(doc.features)
    payload['features'][-1]['parameters']['edge'][field]=value
    with pytest.raises(ValueError):deserialize(payload)


def test_arc_schema_checks_and_old_reader_boundary():
    doc,target,_,_=model('arc');_,ref=curved_edge(doc,target,30);doc.add_chamfer(target,ref,1)
    payload=serialize(doc.features)
    for field,value in [('midpoint',None),('midpoint',[15,15,30]),('midpoint',[15,10,30]),
                        ('axis',[1,0,0]),('endpoints',[[15,10,30],[15,10,30]])]:
        bad=deepcopy(payload);bad['features'][-1]['parameters']['edge'][field]=value
        with pytest.raises(ValueError):deserialize(bad)
    payload['version']=12
    with pytest.raises(ValueError):deserialize(payload)


def test_unsupported_ellipse_and_spline_never_approximated():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Elips
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    from OCP.TColgp import TColgp_Array1OfPnt
    ellipse=BRepBuilderAPI_MakeEdge(gp_Elips(gp_Ax2(gp_Pnt(),gp_Dir(0,0,1)),5,3)).Edge()
    points=TColgp_Array1OfPnt(1,4)
    for i,p in enumerate(((0,0,0),(1,2,0),(3,1,1),(5,0,0)),1):points.SetValue(i,gp_Pnt(*p))
    spline=BRepBuilderAPI_MakeEdge(GeomAPI_PointsToBSpline(points).Curve()).Edge()
    for edge in (ellipse,spline):
        with pytest.raises(OperationError,match='ellipses and freeform'):
            edge_reference(edge,())


def test_circular_chamfer_face_lineage_and_downstream_planar_sketch_cut():
    doc,target,_,_=model();_,ref=curved_edge(doc,target,20);cid=doc.add_chamfer(target,ref,1)
    bevel=doc.source_faces[cid][('bevel',None,None)]
    with pytest.raises(ValueError,match='planar'):
        doc.face_reference(bevel)
    cylinder=next(f for f in subshapes(doc.solid_shapes[cid],TopAbs_FACE)
                  if BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType()==GeomAbs_Cylinder)
    assert any(cylinder.IsSame(f) and tokens for f,tokens in doc.face_lineages[cid])
    with pytest.raises(ValueError,match='planar'):doc.face_reference(TopoDS.Face_s(cylinder))
    top=next(f for f in subshapes(doc.solid_shapes[cid],TopAbs_FACE)
             if BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType()==GeomAbs_Plane and
             abs(BRepAdaptor_Surface(TopoDS.Face_s(f)).Plane().Location().Z()-20)<1e-7)
    attached=doc.add_face_sketch(doc.face_reference(TopoDS.Face_s(top)))
    # Use a point expressed in the actual support frame, away from the bore.
    frame=doc.feature(attached).parameters.frame
    point=frame.to_local((5,5,20));circle=Circle(*point,1);doc.add_entity(attached,circle)
    cut=doc.add_extrusion(attached,circle.id,distance=-5,operation='cut',target_id=cid)
    assert all(s.valid for s in doc.statuses.values()) and BRepCheck_Analyzer(doc.solid_shapes[cut]).IsValid()
    doc.set_box(BoxParameters(width=45))
    assert doc.statuses[attached].valid and doc.statuses[cut].valid


@pytest.mark.parametrize('failure',['exception','not_done','invalid_solid','no_change'])
def test_circular_native_failures_do_not_publish_candidate_state(monkeypatch,failure):
    import hero_cad.chamfers as module
    doc,target,_,_=model();_,ref=curved_edge(doc,target,20)
    original=state(doc);stacks=doc._undo[:],doc._redo[:]
    native=module.BRepFilletAPI_MakeChamfer
    class FailingBuilder:
        def __init__(self,body):
            if failure=='exception':raise RuntimeError('injected kernel construction failure')
            self.delegate=native(body)
            self.body=body
        def __getattr__(self,name):return getattr(self.delegate,name)
        def IsDone(self):return failure!='not_done' and self.delegate.IsDone()
        def Shape(self):
            if failure=='invalid_solid':return subshapes(self.body,TopAbs_FACE)[0]
            if failure=='no_change':return self.body
            return self.delegate.Shape()
    monkeypatch.setattr(module,'BRepFilletAPI_MakeChamfer',FailingBuilder)
    with pytest.raises(FeatureError):doc.add_chamfer(target,ref,1)
    assert all(a is b for a,b in zip(state(doc),original))
    assert (doc._undo,doc._redo)==stacks


def test_full_circle_axis_reversal_and_arc_endpoint_change():
    edge,lineage=cylinder_rim(gp_Ax2(gp_Pnt(),gp_Dir(0,0,1),gp_Dir(1,0,0)))
    other,other_lineage=cylinder_rim(gp_Ax2(gp_Pnt(0,0,10),gp_Dir(0,0,-1),gp_Dir(0,1,0)))
    assert edge_reference(edge,lineage)==edge_reference(other,other_lineage)
    doc,target,_,_=model('arc');_,ref=curved_edge(doc,target,30)
    cid=doc.add_chamfer(target,ref,.5)
    cutter_sketch=doc.feature(target).parameters.sketch_id
    cutter=doc.feature(cutter_sketch).parameters.entities[0]
    doc.update_entity(cutter_sketch,replace(cutter,x=14,width=26))
    assert not doc.statuses[cid].valid
    assert 'missing or changed' in doc.statuses[cid].error
    doc.undo()
    assert doc.statuses[cid].valid

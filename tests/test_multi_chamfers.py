"""Explicit collections, single native builders, and transient analytic chains."""
from copy import deepcopy
from dataclasses import replace
from math import pi, tan
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Circle
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir, gp_Circ
from hero_cad.booleans import OperationError, bounds
from hero_cad.chamfers import edge_reference, resolve_edge, tangent_chain, TANGENT_ANGLE
from hero_cad.document import Document
from hero_cad.face_history import subshapes, primitive_lineage
from hero_cad.features import ChamferParameters, BoxParameters, FeatureError
from hero_cad.geometry import volume, compound
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, Slot
from hero_cad.history_inspection import feature_history_text
from test_chamfers import state, bottom_edge
from test_circular_chamfers import model, curved_edge


def box_top(doc):
    target=doc.features[0].id
    refs=[doc.edge_reference(e)[1] for e in subshapes(doc.solid_shapes[target],TopAbs_EDGE)
          if all(p[2]==20 for p in doc.edge_reference(e)[1].endpoints)]
    assert len(refs)==4
    return target,tuple(refs)


def slot_model(depth=20):
    doc=Document();sid=doc.add_sketch('XY');slot=Slot(10,10,3,12,0);doc.add_entity(sid,slot)
    target=doc.add_extrusion(sid,slot.id,distance=depth,operation='cut',target_id=doc.features[0].id)
    seed=next(e for e in subshapes(doc.solid_shapes[target],TopAbs_EDGE)
              if (lambda r:r.curve_type=='arc' and r.center[2]==0)(doc.edge_reference(e)[1]))
    chain=doc.tangent_edges(seed)
    return doc,target,sid,slot,chain


@pytest.mark.parametrize('count',[2,4])
def test_box_multi_chamfer_is_one_feature_with_canonical_references(count,tmp_path):
    doc=Document();target,refs=box_top(doc)
    if count==2:
        refs=tuple(r for r in refs if r.endpoints[0][0]==r.endpoints[1][0])
    assert len(refs)==count
    params=ChamferParameters(target,refs,.5)
    assert params==ChamferParameters(target,tuple(reversed(refs)),.5)
    cid=doc.add_chamfer(target,refs,.5)
    assert doc.features[-1].references==(target,) and doc.active_body_ids=={cid}
    assert len(doc.feature(cid).parameters.edges)==count
    removed=(30*.5**2 if count==2 else 70*.5**2-4*.5**3/3)
    assert volume(doc.solid_shapes[cid])==pytest.approx(24000-removed)
    assert bounds(doc.solid_shapes[cid])==pytest.approx((0,40,0,30,0,20),abs=1e-7)
    assert BRepCheck_Analyzer(doc.solid_shapes[cid]).IsValid()
    changed=replace(doc.feature(cid),parameters=replace(doc.feature(cid).parameters,distance=1))
    doc.replace_feature(changed)
    assert doc.feature(cid).id==cid
    assert volume(doc.solid_shapes[cid])==pytest.approx(24000-(30 if count==2 else 70-4/3))
    doc.undo(); assert doc.feature(cid).parameters.distance==.5
    doc.undo(); assert doc.active_body_ids=={target}
    doc.redo();doc.redo();assert doc.feature(cid)==changed
    doc.save(tmp_path/'multi.starcad');loaded=Document.load(doc.path)
    assert loaded.features==doc.features and loaded.statuses==doc.statuses
    assert volume(loaded.solid_shapes[cid])==pytest.approx(volume(doc.solid_shapes[cid]))
    assert serialize(doc.features)['version']==14
    text=feature_history_text(doc,cid)
    assert f'Selected edges: {count}' in text and 'Edge 1:' in text and 'Chamfer target body' in text


@pytest.mark.parametrize('depth',[10,20])
def test_complete_slot_or_pocket_rim_one_builder_and_editable(depth,tmp_path,monkeypatch):
    doc,target,sid,slot,chain=slot_model(depth)
    _,refs=doc.edge_references(chain)
    assert len(refs)==4 and sorted(r.curve_type for r in refs)==['arc','arc','line','line']
    original=volume(doc.solid_shapes[target])
    import hero_cad.chamfers as module
    native=module.BRepFilletAPI_MakeChamfer
    builders=[]
    def counted(body):
        builder=native(body);builders.append(builder);return builder
    monkeypatch.setattr(module,'BRepFilletAPI_MakeChamfer',counted)
    cid=doc.add_chamfer(target,tuple(reversed(refs)),.5)
    assert len(builders)==1
    def removed(d):return (24+6*pi)*d*d/2+pi*d**3/3
    assert volume(doc.solid_shapes[cid])==pytest.approx(original-removed(.5))
    assert BRepCheck_Analyzer(doc.solid_shapes[cid]).IsValid()
    assert len(doc.source_faces[cid])==4
    assert all(key[0]=='bevel' and len(key[2])==64 for key in doc.source_faces[cid])
    doc.replace_feature(replace(doc.feature(cid),parameters=replace(doc.feature(cid).parameters,distance=1)))
    assert volume(doc.solid_shapes[cid])==pytest.approx(original-removed(1))
    doc.save(tmp_path/'slot.starcad');loaded=Document.load(doc.path)
    assert loaded.features==doc.features and loaded.statuses[cid].valid
    assert volume(loaded.solid_shapes[cid])==pytest.approx(original-removed(1))
    doc.update_entity(sid,replace(slot,radius=4))
    assert not doc.statuses[cid].valid and cid not in doc.solid_shapes
    assert len(doc.feature(cid).parameters.edges)==4
    doc.undo();assert doc.statuses[cid].valid


def test_mixed_line_circle_and_opposite_rims():
    doc,target,_,_=model('hole');_,circle=curved_edge(doc,target,20)
    _,line=bottom_edge(doc,target)
    original=volume(doc.solid_shapes[target]);cid=doc.add_chamfer(target,(circle,line),.5)
    assert volume(doc.solid_shapes[cid])==pytest.approx(original-30*.5**2/2-5*pi*.5**2-pi*.5**3/3)
    doc.undo();_,other=curved_edge(doc,target,0)
    cid=doc.add_chamfer(target,(circle,other),.5)
    assert volume(doc.solid_shapes[cid])==pytest.approx(original-2*(5*pi*.5**2+pi*.5**3/3))


@pytest.mark.parametrize('subset',[1,2,3])
def test_partial_slot_contour_refuses_unselected_edges_transactionally(subset):
    doc,target,_,_,chain=slot_model();_,refs=doc.edge_references(chain)
    original=state(doc);stacks=doc._undo[:],doc._redo[:]
    with pytest.raises(FeatureError,match='explicit selection'):
        doc.add_chamfer(target,refs[:subset],.5)
    assert all(a is b for a,b in zip(state(doc),original)) and (doc._undo,doc._redo)==stacks


@pytest.mark.parametrize('bad',['empty','duplicate','mutable','wrong','too_many'])
def test_bad_parameter_collections(bad):
    doc=Document();target,refs=box_top(doc)
    edges={'empty':(),'duplicate':(refs[0],refs[0]),'mutable':list(refs),'wrong':(refs[0],1),
           'too_many':refs*65}[bad]
    with pytest.raises(ValueError):ChamferParameters(target,edges)


def test_cross_body_duplicate_stale_and_unsupported_manual_selection_rejected():
    doc=Document();target,refs=box_top(doc);edge=resolve_edge(refs[0],doc.solid_shapes[target],doc.face_lineages[target])
    sid=doc.add_sketch('XY');circle=Circle(60,0,5);doc.add_entity(sid,circle)
    other=doc.add_extrusion(sid,circle.id)
    rim=next(e for e in subshapes(doc.solid_shapes[other],TopAbs_EDGE)
             if BRepAdaptor_Curve(TopoDS.Edge_s(e)).GetType()==GeomAbs_Circle)
    edge=resolve_edge(refs[0],doc.solid_shapes[target],doc.face_lineages[target])
    with pytest.raises(OperationError,match='same current solid'):doc.edge_references((edge,rim))
    with pytest.raises(ValueError,match='Duplicate'):doc.edge_references((edge,edge))
    with pytest.raises(OperationError,match='at least one'):doc.edge_references(())
    doc.set_box(BoxParameters(width=45))
    with pytest.raises(OperationError,match='current solid'):doc.edge_references((edge,))


def test_one_missing_reference_suppresses_entire_feature_and_downstream():
    doc=Document();target,refs=box_top(doc);cid=doc.add_chamfer(target,refs,.5)
    sid=doc.add_sketch('XY');circle=Circle(15,15,2);doc.add_entity(sid,circle)
    cut=doc.add_extrusion(sid,circle.id,distance=20,operation='cut',target_id=cid)
    doc.set_box(BoxParameters(width=45))
    assert not doc.statuses[cid].valid and not doc.statuses[cut].valid
    assert cid not in doc.solid_shapes and cut not in doc.solid_shapes
    assert len(doc.feature(cid).parameters.edges)==4
    doc.undo();assert doc.statuses[cid].valid and doc.statuses[cut].valid


@pytest.mark.parametrize('failure',['excessive','native_exception','invalid_solid','duplicate_resolved'])
def test_multi_failure_is_atomic(failure,monkeypatch):
    import hero_cad.chamfers as module
    doc=Document();target,refs=box_top(doc)
    previous=state(doc);stacks=doc._undo[:],doc._redo[:]
    if failure=='native_exception':
        def fail(*args):raise RuntimeError('injected construction failure')
        monkeypatch.setattr(module,'BRepFilletAPI_MakeChamfer',fail)
    elif failure=='invalid_solid':
        native=module.one_solid;calls=[]
        def invalid(shape):
            calls.append(shape)
            if len(calls)>1:raise OperationError('invalid resulting solid')
            return native(shape)
        monkeypatch.setattr(module,'one_solid',invalid)
    elif failure=='duplicate_resolved':
        edge=resolve_edge(refs[0],doc.solid_shapes[target],doc.face_lineages[target])
        monkeypatch.setattr(module,'resolve_edges',lambda refs,*args:tuple(edge for _ in refs))
    with pytest.raises(FeatureError):doc.add_chamfer(target,refs,100 if failure=='excessive' else .5)
    assert all(a is b for a,b in zip(state(doc),previous)) and (doc._undo,doc._redo)==stacks


@pytest.mark.parametrize('change',['empty','one','duplicate','malformed','legacy_version','both_keys','not_list'])
def test_multi_schema_rejects_malformed_collections(change):
    doc=Document();target,refs=box_top(doc);doc.add_chamfer(target,refs,.5)
    payload=serialize(doc.features);p=payload['features'][-1]['parameters']
    if change=='empty':p['edges']=[]
    if change=='one':p['edges']=p['edges'][:1]
    if change=='duplicate':p['edges'][1]=deepcopy(p['edges'][0])
    if change=='malformed':p['edges'][0]['endpoints']=[[0,0]]
    if change=='legacy_version':payload['version']=13
    if change=='both_keys':p['edge']=deepcopy(p['edges'][0])
    if change=='not_list':p['edges']={}
    with pytest.raises(ValueError):deserialize(payload)


def test_multi_bevel_lineage_planar_attachment_and_downstream_cut(tmp_path):
    doc,target,_,_,chain=slot_model();_,refs=doc.edge_references(chain);cid=doc.add_chamfer(target,refs,.5)
    planar=next(f for f in doc.source_faces[cid].values() if BRepAdaptor_Surface(f).GetType()==GeomAbs_Plane)
    ref=doc.face_reference(planar)
    sid=doc.add_face_sketch(ref)
    assert doc.statuses[sid].valid
    assert serialize(doc.features)['version']==14
    doc.save(tmp_path/'bevel.starcad');loaded=Document.load(doc.path)
    assert loaded.features==doc.features and loaded.statuses[sid].valid
    # Cylinder walls keep ancestry; the unaffected outer plane supports a cut.
    for face in subshapes(doc.solid_shapes[cid],TopAbs_FACE):
        if BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType()==GeomAbs_Cylinder:
            assert any(face.IsSame(f) and tokens for f,tokens in doc.face_lineages[cid])
    other=doc.add_sketch('XY');circle=Circle(4,4,1);doc.add_entity(other,circle)
    cut=doc.add_extrusion(other,circle.id,distance=20,operation='cut',target_id=cid)
    assert doc.statuses[cut].valid and BRepCheck_Analyzer(doc.solid_shapes[cut]).IsValid()
    doc.replace_feature(replace(doc.feature(cid),parameters=replace(doc.feature(cid).parameters,distance=.75)))
    assert doc.statuses[sid].valid and doc.statuses[cut].valid


def graph_fixture(edges):
    """Native open graph for traversal only; each edge has two real adjacent faces.

    Deliberately not a publishable solid: a branching graph isolates the selector's
    ambiguity handling without asking a modeling builder to accept nonmanifold CAD.
    """
    lineage=[]
    for edge in edges:
        curve=BRepAdaptor_Curve(edge);a=curve.Value(curve.FirstParameter());b=curve.Value(curve.LastParameter())
        for z,key in ((3,'+X'),(-3,'-X')):
            c=(curve.Circle().Location() if curve.GetType()==GeomAbs_Circle
               else gp_Pnt((a.X()+b.X())/2,(a.Y()+b.Y())/2,z))
            wire=BRepBuilderAPI_MakeWire(edge,BRepBuilderAPI_MakeEdge(b,c).Edge(),BRepBuilderAPI_MakeEdge(c,a).Edge()).Wire()
            face=BRepBuilderAPI_MakeFace(wire).Face()
            lineage.extend(primitive_lineage('00000000-0000-0000-0000-000000000001',{key:face}))
    return compound(edges),tuple(lineage)


def line(a,b):return BRepBuilderAPI_MakeEdge(gp_Pnt(*a),gp_Pnt(*b)).Edge()


def test_tangent_open_chain_corners_disconnected_and_reversal():
    edges=[line((0,0,0),(5,0,0)),line((5,0,0),(10,0,0)),line((10,0,0),(10,5,0)),line((50,0,0),(55,0,0))]
    body,lineage=graph_fixture(edges)
    for seed in (edges[0],TopoDS.Edge_s(edges[1].Reversed())):
        chain=tangent_chain(seed,body,lineage)
        assert len(chain)==2 and all(any(e.IsSame(x) for x in edges[:2]) for e in chain)
    assert len(tangent_chain(edges[2],body,lineage))==1


@pytest.mark.parametrize('factor,expected',[(.5,2),(2,1)])
def test_conservative_tangent_angular_tolerance(factor,expected):
    edges=[line((0,0,0),(5,0,0)),line((5,0,0),(10,5*tan(TANGENT_ANGLE*factor),0))]
    body,lineage=graph_fixture(edges)
    assert len(tangent_chain(edges[0],body,lineage))==expected


def test_ambiguous_tangent_branch_rejected_even_after_visiting_a_neighbor():
    arc=BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(5,5,0),gp_Dir(0,0,1)),5),-pi/2,0).Edge()
    edges=[line((0,0,0),(5,0,0)),line((5,0,0),(10,0,0)),arc]
    body,lineage=graph_fixture(edges)
    with pytest.raises(OperationError,match='Ambiguous tangent-chain'):tangent_chain(edges[0],body,lineage)


def test_closed_slot_chain_is_selection_only_and_is_body_scoped():
    doc,target,_,_,chain=slot_model();before=state(doc);stacks=doc._undo[:],doc._redo[:]
    for edge in chain:
        selected=doc.tangent_edges(TopoDS.Edge_s(edge.Reversed()))
        assert len(selected)==4
        assert all(any(e.IsSame(old) for old in chain) for e in selected)
    assert all(a is b for a,b in zip(state(doc),before)) and (doc._undo,doc._redo)==stacks
    box=Document();target=box.features[0].id
    assert len(box.tangent_edges(subshapes(box.solid_shapes[target],TopAbs_EDGE)[0]))==1


def test_unsupported_curve_is_a_chain_boundary_and_not_dropped_from_manual_selection():
    from OCP.gp import gp_Elips, gp_Vec
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.GeomAbs import GeomAbs_Ellipse
    ellipse=gp_Elips(gp_Ax2(gp_Pnt(5,3,0),gp_Dir(0,0,1)),5,3)
    unsupported=BRepBuilderAPI_MakeEdge(ellipse,-pi/2,0).Edge()
    seed=line((0,0,0),(5,0,0))
    _,lineage=graph_fixture((seed,))
    assert len(tangent_chain(seed,compound((seed,unsupported)),lineage))==1
    # A valid native elliptical prism isolates eligibility without adding an
    # unsupported imported-feature type to the application's feature catalogue.
    face=BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(ellipse).Edge()).Wire()).Face()
    solid=BRepPrimAPI_MakePrism(face,gp_Vec(0,0,10)).Shape()
    assert BRepCheck_Analyzer(solid).IsValid()
    doc=Document();target=doc.features[0].id;doc.solid_shapes[target]=solid
    edge=next(e for e in subshapes(solid,TopAbs_EDGE)
              if BRepAdaptor_Curve(TopoDS.Edge_s(e)).GetType()==GeomAbs_Ellipse)
    with pytest.raises(OperationError,match='ellipses and freeform'):doc.edge_references((edge,))


@pytest.mark.parametrize('gap,expected',[(.5e-7,2),(2e-7,1)])
def test_chain_endpoint_tolerance(gap,expected):
    edges=[line((0,0,0),(5,0,0)),line((5+gap,0,0),(10,0,0))]
    body,lineage=graph_fixture(edges)
    assert len(tangent_chain(edges[0],body,lineage))==expected


def test_native_builder_omitting_one_requested_edge_cannot_publish_partial_result(monkeypatch):
    import hero_cad.chamfers as module
    doc=Document();target,refs=box_top(doc);previous=state(doc)
    native=module.BRepFilletAPI_MakeChamfer
    class OmittingBuilder:
        def __init__(self,body):self.delegate=native(body);self.calls=0
        def __getattr__(self,name):return getattr(self.delegate,name)
        def Add(self,distance,edge):
            self.calls+=1
            if self.calls!=2:self.delegate.Add(distance,edge)
    monkeypatch.setattr(module,'BRepFilletAPI_MakeChamfer',OmittingBuilder)
    with pytest.raises(FeatureError,match='every selected'):doc.add_chamfer(target,refs,.5)
    assert all(a is b for a,b in zip(state(doc),previous)) and not doc.can_undo

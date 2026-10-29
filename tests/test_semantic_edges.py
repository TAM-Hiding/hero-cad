"""Semantic box-edge transport, deliberately limited to unmixed box faces."""
from dataclasses import replace
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.chamfers import resolve_edge, resolve_edges, edge_reference, base_edge_identity
from hero_cad.face_history import subshapes
from hero_cad.geometry import volume, compound
from hero_cad.booleans import OperationError, bounds
from hero_cad.sketch import Slot, Circle


def acceptance_model():
    doc = Document()
    box = doc.features[0].id
    sid = doc.add_face_sketch(doc.face_reference(doc.source_faces[box]['+Z']))
    slot = Slot(10, 10, 3, 12, 0)
    doc.add_entity(sid, slot)
    target = doc.add_extrusion(sid, slot.id, distance=-10, operation='cut', target_id=box)
    for z in (20, 10):
        seed = next(e for e in subshapes(doc.solid_shapes[target], TopAbs_EDGE)
                    if (lambda r: r.curve_type == 'arc' and r.center[2] == z)(doc.edge_reference(e)[1]))
        _, refs = doc.edge_references(doc.tangent_edges(seed))
        assert len(refs) == 4
        target = doc.add_chamfer(target, refs, .5)
    refs = tuple(doc.edge_reference(e)[1] for e in subshapes(doc.solid_shapes[target], TopAbs_EDGE)
                 if base_edge_identity(doc.edge_reference(e)[1]) is not None)
    assert len(refs) == 12
    cid = doc.add_chamfer(target, refs, .5)
    return doc, box, cid


@pytest.mark.parametrize('dimension,value', [('width',41),('width',39),('depth',31),('depth',29)])
def test_primary_slot_rims_and_twelve_exterior_edges(dimension, value, tmp_path):
    doc, box, cid = acceptance_model()
    definitions = doc.features
    refs = doc.feature(cid).parameters.edges
    initial = volume(doc.shape)
    doc.set_box(replace(doc.feature(box).parameters, **{dimension:value}))
    changed = volume(doc.shape)
    assert all(s.valid for s in doc.statuses.values())
    assert len(refs) == 12 and doc.feature(cid).parameters.edges == refs
    assert doc.features[1:] == definitions[1:]
    assert BRepCheck_Analyzer(doc.solid_shapes[cid]).IsValid()
    dimensions = dict(width=40, depth=30, height=20, **{})
    dimensions[dimension] = value
    assert bounds(doc.shape) == pytest.approx((0,dimensions['width'],0,dimensions['depth'],0,dimensions['height']),abs=1e-7)
    assert (changed-initial) == pytest.approx((value-{'width':40,'depth':30,'height':20}[dimension]) *
        {'width':30*20-4*.5**2/2, 'depth':40*20-4*.5**2/2, 'height':40*30-4*.5**2/2}[dimension], abs=1e-6)
    doc.undo()
    assert volume(doc.shape) == pytest.approx(initial)
    assert doc.features == definitions
    doc.redo()
    assert volume(doc.shape) == pytest.approx(changed)
    assert all(s.valid for s in doc.statuses.values())
    doc.save(tmp_path/'semantic.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features and loaded.statuses == doc.statuses
    assert volume(loaded.shape) == pytest.approx(changed)


@pytest.mark.parametrize('count', [1,4,12])
def test_moved_and_unchanged_box_edges_and_orientation(count):
    doc = Document(); box = doc.features[0].id
    refs = tuple(doc.edge_reference(e)[1] for e in subshapes(doc.shape, TopAbs_EDGE))
    cid = doc.add_chamfer(box, refs[:count], .5)
    doc.set_box(BoxParameters(width=41))
    assert doc.statuses[cid].valid and len(doc.feature(cid).parameters.edges) == count
    for ref in refs:
        edge = resolve_edge(ref, doc.solid_shapes[box], doc.face_lineages[box])
        current = edge_reference(TopoDS.Edge_s(edge.Reversed()), tuple(reversed(doc.face_lineages[box])))
        assert current.neighbors == ref.neighbors
    with pytest.raises(OperationError, match='Duplicate resolved'):
        resolve_edges((refs[0],refs[0]), doc.solid_shapes[box], doc.face_lineages[box])


def test_split_pair_is_ambiguous_and_does_not_pick_one_fragment():
    doc = Document(); box = doc.features[0].id
    ref = next(doc.edge_reference(e)[1] for e in subshapes(doc.shape, TopAbs_EDGE)
               if doc.edge_reference(e)[1].endpoints == ((40.,0.,20.),(40.,30.,20.)))
    sid = doc.add_sketch('XY'); circle = Circle(40,15,3); doc.add_entity(sid,circle)
    cut = doc.add_extrusion(sid,circle.id,distance=20,operation='cut',target_id=box)
    doc.set_box(BoxParameters(width=41))
    matches = [e for e in subshapes(doc.solid_shapes[cut],TopAbs_EDGE)
               if edge_reference(e,doc.face_lineages[cut]).neighbors == ref.neighbors]
    assert len(matches) == 2
    with pytest.raises(OperationError,match='ambiguous semantic'):
        resolve_edge(ref,doc.solid_shapes[cut],doc.face_lineages[cut])


def test_missing_disappearing_foreign_and_ineligible_ancestry():
    doc = Document(); box = doc.features[0].id
    refs = tuple(doc.edge_reference(e)[1] for e in subshapes(doc.shape,TopAbs_EDGE))
    doc.set_box(BoxParameters(width=41,depth=31,height=21))
    other = Document(); foreign = other.features[0].id
    for ref in refs:
        with pytest.raises(OperationError,match='missing or changed'):
            resolve_edge(ref, other.solid_shapes[foreign], other.face_lineages[foreign])
        with pytest.raises(OperationError):
            resolve_edge(ref, compound(()), ())
        # A union of face histories is deliberately ineligible.
        mixed = replace(ref,neighbors=tuple(sorted((tuple(sorted(set(ref.neighbors[0]+ref.neighbors[1]))), ref.neighbors[1]))))
        assert base_edge_identity(mixed) is None
        with pytest.raises(OperationError):
            resolve_edge(mixed,doc.solid_shapes[box],doc.face_lineages[box])
        with pytest.raises(OperationError):
            resolve_edge(ref,doc.solid_shapes[box],())


@pytest.mark.parametrize('height', [19,21])
def test_all_exterior_edges_follow_height_change(height):
    doc = Document(); box = doc.features[0].id
    refs = tuple(doc.edge_reference(e)[1] for e in subshapes(doc.shape,TopAbs_EDGE))
    cid = doc.add_chamfer(box,refs,.5)
    doc.set_box(BoxParameters(height=height))
    assert doc.statuses[cid].valid and BRepCheck_Analyzer(doc.shape).IsValid()
    assert bounds(doc.shape) == pytest.approx((0,40,0,30,0,height),abs=1e-7)


def test_slot_rim_motion_remains_outside_semantic_box_scope():
    doc, box, cid = acceptance_model()
    doc.set_box(BoxParameters(height=21))
    rim = next(f for f in doc.features if f.type == 'chamfer')
    assert not doc.statuses[rim.id].valid and doc.statuses[rim.id].blocked_by is None
    assert doc.statuses[cid].blocked_by is not None
    assert 'Unresolved chamfer edge' in doc.statuses[rim.id].error


@pytest.mark.parametrize('change', ['one_face','different_context','wrong_direction','curve_type'])
def test_contradictory_or_insufficient_identity_cannot_transport(change):
    doc = Document(); box = doc.features[0].id
    ref = next(doc.edge_reference(e)[1] for e in subshapes(doc.shape,TopAbs_EDGE)
               if doc.edge_reference(e)[1].endpoints == ((40.,0.,0.),(40.,0.,20.)))
    if change == 'one_face':
        bad = replace(ref,neighbors=(ref.neighbors[0],ref.neighbors[0]))
    elif change == 'different_context':
        import json
        token = json.loads(ref.neighbors[1][0]); token[0] = Document().features[0].id
        bad = replace(ref,neighbors=tuple(sorted((ref.neighbors[0],(json.dumps(token,separators=(',',':')),)))))
    elif change == 'wrong_direction':
        bad = replace(ref,endpoints=((40.,0.,0.),(41.,0.,20.)))
    else:
        bad = replace(ref,curve_type='circle',endpoints=(),center=(40.,0.,10.),radius=10.,axis=(0.,1.,0.))
    assert base_edge_identity(bad) is None
    doc.set_box(BoxParameters(width=41))
    with pytest.raises(OperationError,match='missing or changed'):
        resolve_edge(bad,doc.solid_shapes[box],doc.face_lineages[box])


def test_changed_candidate_curve_class_is_not_an_eligible_semantic_match(monkeypatch):
    import hero_cad.chamfers as module
    doc = Document(); box = doc.features[0].id
    ref = next(doc.edge_reference(e)[1] for e in subshapes(doc.shape,TopAbs_EDGE)
               if doc.edge_reference(e)[1].endpoints == ((40.,0.,0.),(40.,0.,20.)))
    doc.set_box(BoxParameters(width=41))
    native = module.edge_reference
    def changed(edge,lineage):
        result = native(edge,lineage)
        if result.neighbors == ref.neighbors:
            return replace(result,curve_type='circle',endpoints=(),center=(41.,0.,10.),radius=10.,axis=(0.,1.,0.))
        return result
    monkeypatch.setattr(module,'edge_reference',changed)
    with pytest.raises(OperationError,match='missing or changed'):
        resolve_edge(ref,doc.solid_shapes[box],doc.face_lineages[box])


def test_ambiguous_cut_keeps_multi_feature_definitions_and_blocks_dependents():
    doc = Document(); box = doc.features[0].id
    sid = doc.add_sketch('XY'); circle = Circle(20,15,3); doc.add_entity(sid,circle)
    cut = doc.add_extrusion(sid,circle.id,distance=20,operation='cut',target_id=box)
    refs = []
    for e in subshapes(doc.solid_shapes[cut],TopAbs_EDGE):
        try:
            ref = edge_reference(e,doc.face_lineages[cut])
        except OperationError:
            continue
        if base_edge_identity(ref) is not None:
            refs.append(ref)
    refs = tuple(refs)
    assert len(refs) == 12
    cid = doc.add_chamfer(cut,refs,.5)
    refs = doc.feature(cid).parameters.edges
    other = doc.add_sketch('XY'); hole = Circle(10,10,1); doc.add_entity(other,hole)
    dependent = doc.add_extrusion(other,hole.id,distance=20,operation='cut',target_id=cid)
    doc.update_entity(sid,replace(circle,x=40))
    assert doc.statuses[cut].valid and not doc.statuses[cid].valid
    assert doc.statuses[cid].blocked_by is None
    assert doc.statuses[dependent].blocked_by == cid
    assert cid not in doc.solid_shapes and dependent not in doc.solid_shapes
    assert doc.feature(cid).parameters.edges == refs
    assert len(doc.features) == 6
    doc.undo(); assert doc.statuses[cid].valid and doc.statuses[dependent].valid

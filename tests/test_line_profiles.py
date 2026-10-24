from dataclasses import replace
import copy
import json
from math import pi
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from hero_cad.attachments import reference_key
from hero_cad.document import Document
from hero_cad.features import BoxParameters, FeatureError
from hero_cad.geometry import volume
from hero_cad.line_profiles import CONNECT_TOLERANCE, loop_id
from hero_cad.persistence import deserialize
from hero_cad.profiles import regions, contains
from hero_cad.sketch import Circle, Line, Rectangle, FaceReference
from test_face_attachments import coincident


def polygon(points):
    return tuple(Line(*a, *b) for a, b in zip(points, points[1:]+points[:1]))


TRIANGLE = [(0, 0), (12, 0), (3, 8)]
TRAPEZOID = [(0, 0), (12, 0), (10, 6), (2, 6)]
CONCAVE = [(0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10)]
DOVETAIL = [(2, 4), (12, 4), (10, 10), (4, 10)]


def document(entities, plane='XY'):
    d = Document()
    sid = d.add_sketch(plane)
    feature = d.feature(sid)
    d.replace_feature(replace(feature, parameters=replace(feature.parameters, entities=tuple(entities))))
    return d, sid


@pytest.mark.parametrize('points,area', [(TRIANGLE, 48), (TRAPEZOID, 60), (CONCAVE, 51), (DOVETAIL, 48)])
@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
@pytest.mark.parametrize('distance', [3, -3])
def test_polygon_prisms_exact_volume_planes_and_signed_distance(points, area, plane, distance):
    lines = polygon(points)
    d, sid = document(lines, plane)
    region, = regions(d.feature(sid).parameters)
    assert region.outer_id == loop_id(e.id for e in lines)
    assert region.line_ids == tuple(sorted(e.id for e in lines))
    eid = d.add_extrusion(sid, region.outer_id, distance=distance)
    assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()
    assert volume(d.solid_shapes[eid]) == pytest.approx(area*abs(distance), rel=1e-11)
    assert d.feature(eid).parameters.line_ids == region.line_ids


def test_dovetail_through_block_and_all_boolean_modes():
    lines = polygon(DOVETAIL)
    d, sid = document(lines, 'XZ')
    region, = regions(d.feature(sid).parameters)
    eid = d.add_extrusion(sid, region.outer_id, operation='cut', target_id=d.features[0].id,
                          extent='through_all', direction=-1)
    assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()
    assert volume(d.solid_shapes[eid]) == pytest.approx(40*30*20-48*30)
    d.set_box(BoxParameters(40, 50, 20))
    assert volume(d.solid_shapes[eid]) == pytest.approx(40*50*20-48*50)


@pytest.mark.parametrize('op,expected', [('join', 1630), ('cut', 650), ('intersect', 350)])
def test_line_profile_uses_existing_material_operations(op, expected):
    d, sid = document(polygon([(5, -2), (15, -2), (15, 12), (5, 12)]))
    d.set_box(BoxParameters(10, 10, 10))
    region, = regions(d.feature(sid).parameters)
    eid = d.add_extrusion(sid, region.outer_id, distance=7, operation=op, target_id=d.features[0].id)
    assert volume(d.solid_shapes[eid]) == pytest.approx(expected)
    assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()


def test_disjoint_regions_primitives_and_remote_open_chains():
    a, b = polygon(TRIANGLE), polygon([(30, 0), (40, 0), (40, 10), (30, 10)])
    circle = Circle(60, 0, 3)
    d, sid = document((*a, Line(-10, -10, -5, -5), *reversed(b), circle))
    rs = regions(d.feature(sid).parameters)
    assert {r.outer_id for r in rs} == {loop_id(e.id for e in a), loop_id(e.id for e in b), circle.id}
    assert sum(contains(r.face, (3, 2, 0)) for r in rs) == 1
    assert sum(contains(r.face, (35, 5, 0)) for r in rs) == 1
    assert not any(contains(r.face, (-7, -7, 0)) for r in rs)
    assert not regions(document(a[:-1])[0].sketches[0].parameters)


@pytest.mark.parametrize('gap,closed', [(0., True), (CONNECT_TOLERANCE*.5, True), (CONNECT_TOLERANCE*2, False), (.01, False)])
def test_endpoint_tolerance_does_not_rewrite_source_geometry(gap, closed):
    lines = (*polygon([(0, 0), (10, 0), (10, 10), (0, 10)])[:-1], Line(0, 10, -gap, 0))
    d, sid = document(lines)
    before = d.features
    rs = regions(d.feature(sid).parameters)
    assert bool(rs) == closed and d.features == before
    if closed:
        eid = d.add_extrusion(sid, rs[0].outer_id, distance=2)
        assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()
        assert d.feature(sid).parameters.entities == lines
        assert lines[-1].x2 == -gap


@pytest.mark.parametrize('entities', [
    polygon([(0, 0), (10, 10), (0, 10), (10, 0)]),
    (Line(0, 0, 10, 0), Line(5, 0, 15, 0)),
    (Line(0, 0, 10, 0), Line(10, 0, 0, 0)),
    (*polygon(TRIANGLE), Line(0, 0, -5, -5)),
    (Line(0, 0, 10, 0), Line(10, 0, 5, 0)),
])
def test_crossing_overlap_duplicate_and_branch_arrangements_rejected(entities):
    d, sid = document(entities)
    with pytest.raises(ValueError, match='line|Line'):
        regions(d.feature(sid).parameters)


def test_nested_line_and_primitive_holes_never_silently_fill():
    outer = polygon([(0, 0), (40, 0), (40, 30), (0, 30)])
    hole = polygon([(20, 5), (30, 5), (30, 15), (20, 15)])
    circle = Circle(10, 10, 3)
    d, sid = document((*outer, *hole, circle))
    r, = regions(d.feature(sid).parameters)
    assert r.hole_ids == tuple(sorted((loop_id(e.id for e in hole), circle.id)))
    assert not contains(r.face, (25, 10, 0)) and not contains(r.face, (10, 10, 0))
    eid = d.add_extrusion(sid, r.outer_id, r.hole_ids, 2)
    assert volume(d.solid_shapes[eid]) == pytest.approx((1200-100-9*pi)*2)
    primitive = Rectangle(-5, -5, 50, 40)
    other, sketch = document((*hole, primitive))
    region, = regions(other.feature(sketch).parameters)
    assert region.outer_id == primitive.id and region.line_ids == tuple(sorted(e.id for e in hole))
    # A crossing inner network must not disappear and fill its enclosing plate.
    bad, sid = document((primitive, *polygon([(0, 0), (10, 10), (0, 10), (10, 0)])))
    with pytest.raises(ValueError):
        regions(bad.feature(sid).parameters)


def test_loop_identity_reorder_reversal_regeneration_and_v8_persistence(tmp_path):
    lines = polygon(TRAPEZOID)
    d, sid = document(lines)
    r, = regions(d.feature(sid).parameters)
    eid = d.add_extrusion(sid, r.outer_id, distance=-5)
    feature = d.feature(sid)
    reverse = tuple(replace(e, x1=e.x2, y1=e.y2, x2=e.x1, y2=e.y1) for e in reversed(lines))
    d.replace_feature(replace(feature, parameters=replace(feature.parameters, entities=reverse)))
    assert d.statuses[eid].valid and d.feature(eid).parameters.outer_id == r.outer_id
    assert volume(d.solid_shapes[eid]) == pytest.approx(300)
    d.save(tmp_path/'polygon.starcad')
    payload = json.loads(d.path.read_text())
    assert payload['version'] == 8 and payload['format'] == 'star-cad'
    assert payload['features'][-1]['parameters']['line_ids'] == sorted(e.id for e in lines)
    assert Document.load(d.path).features == d.features
    for mutate in (lambda p: p.update(version=7),
                   lambda p: p['features'][-1]['parameters'].update(line_ids=['bad']),
                   lambda p: p['features'][-1]['parameters'].update(line_ids=[])):
        bad = copy.deepcopy(payload); mutate(bad)
        with pytest.raises(ValueError):
            deserialize(bad)


def test_individual_vertex_edits_can_open_then_reclose_profile_without_stale_solids(tmp_path):
    lines = polygon(TRAPEZOID)
    d, sid = document(lines)
    r, = regions(d.feature(sid).parameters)
    eid = d.add_extrusion(sid, r.outer_id, distance=2)
    cap = d.add_face_sketch(FaceReference(eid, 'end'))
    c = Circle(5, 2, .5); d.add_entity(cap, c)
    downstream = d.add_extrusion(cap, c.id, distance=1)
    d.update_entity(sid, replace(lines[0], x2=14))
    assert not d.statuses[eid].valid and 'Unresolved line profile' in d.statuses[eid].error
    assert eid not in d.solid_shapes and downstream not in d.solid_shapes
    # Deletion protection retains all source line IDs even while unresolved.
    with pytest.raises(ValueError, match='profile boundary'):
        d.delete(entities=((sid, lines[2].id),))
    d.save(tmp_path/'open.starcad')
    reopened = Document.load(d.path)
    assert not reopened.statuses[eid].valid and reopened.feature(eid).parameters == d.feature(eid).parameters
    d.update_entity(sid, replace(lines[1], x1=14))
    assert all(s.valid for s in d.statuses.values())
    assert volume(d.solid_shapes[eid]) == pytest.approx(132)
    d.undo(); assert not d.statuses[eid].valid
    d.redo(); assert d.statuses[eid].valid


def test_line_sides_have_stable_attachment_identity_and_deletion_protection():
    lines = polygon(TRAPEZOID)
    d, sid = document(lines, 'YZ')
    r, = regions(d.feature(sid).parameters)
    eid = d.add_extrusion(sid, r.outer_id, distance=3)
    for line in lines:
        ref = FaceReference(eid, 'side', line.id, 'line')
        attached = d.add_face_sketch(ref)
        coincident(d.feature(attached).parameters.frame, d.face_maps[eid][reference_key(ref)])
        with pytest.raises(ValueError, match='profile boundary'):
            d.delete(entities=((sid, line.id),))


def test_unknown_or_non_sketch_profile_source_keeps_transaction_error_contract():
    from uuid import uuid4
    d = Document()
    before = d.features
    for source in (str(uuid4()), d.features[0].id):
        with pytest.raises(FeatureError, match='earlier sketch'):
            d.add_extrusion(source, str(uuid4()))
        assert d.features == before and not d.can_undo and d.last_failure

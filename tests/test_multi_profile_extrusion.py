"""One feature over exact, reusable material-region references."""
from copy import deepcopy
from dataclasses import replace
from math import pi
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from hero_cad.document import Document
from hero_cad.features import ExtrudeParameters, ProfileReference, FeatureError
from hero_cad.geometry import volume
from hero_cad.profiles import regions
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, Slot, Line, FaceReference
from hero_cad.attachments import identify_face
from hero_cad.booleans import bounds


def setup(entities=None, face=False):
    d = Document()
    target = d.features[0].id
    sid = d.add_face_sketch(FaceReference(target, '+Z')) if face else d.add_sketch('XY')
    entities = entities or tuple(Circle(x, y, 2) for y in (8, 20) for x in (6, 18, 30))
    for entity in entities:
        d.add_entity(sid, entity)
    return d, sid, target, entities


def select(d, sid):
    return tuple(ProfileReference(r.outer_id, r.hole_ids, r.line_ids) for r in regions(d.feature(sid).parameters))


def assert_solid(d, eid, expected):
    assert d.statuses[eid].valid
    assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()
    assert volume(d.solid_shapes[eid]) == pytest.approx(expected, rel=1e-10)
    assert bounds(d.solid_shapes[eid]) == pytest.approx((0, 40, 0, 30, 0, 20), abs=1e-6)


@pytest.mark.parametrize('distance,extent', [(3, 'distance'), (30, 'distance'), (3, 'through_all')])
def test_six_cuts_one_feature_history_save_reopen_and_reuse(tmp_path, distance, extent):
    d, sid, target, circles = setup()
    before, history = d.features, len(d._undo)
    refs = select(d, sid)
    eid = d.add_multi_extrusion(sid, refs, distance, operation='cut', target_id=target, extent=extent)
    expected = 24000-6*4*pi*min(distance if extent == 'distance' else 20, 20)
    assert_solid(d, eid, expected)
    assert len(d.features) == len(before)+1 and len(d._undo) == history+1
    assert d.feature(eid).references == (sid, target)
    assert len(d.feature(eid).parameters.profiles) == 6
    accepted = d.features
    d.undo(); assert d.features == before
    d.redo(); assert d.features == accepted
    d.save(tmp_path/'six.starcad')
    loaded = Document.load(d.path)
    assert loaded.features == accepted
    assert_solid(loaded, eid, expected)
    assert loaded.feature(sid).parameters.entities == tuple(circles)
    # Previously used region remains selectable and may deepen a shallow pocket.
    if extent == 'distance' and distance == 3:
        reuse = loaded.add_extrusion(sid, circles[0].id, distance=5, operation='cut', target_id=eid)
        assert_solid(loaded, reuse, expected-8*pi)


def test_mixed_profiles_and_unused_region_reuse():
    entities = (Circle(6, 7, 2), Rectangle(14, 5, 4, 5), Slot(25, 7, 2, 6), Circle(6, 22, 1))
    d, sid, target, _ = setup(entities)
    refs = select(d, sid)
    chosen = tuple(p for p in refs if p.outer_id != entities[-1].id)
    eid = d.add_multi_extrusion(sid, chosen, 3, operation='cut', target_id=target)
    expected = 24000-3*(8*pi+44)
    assert_solid(d, eid, expected)
    second = d.add_extrusion(sid, entities[-1].id, distance=4, operation='cut', target_id=eid)
    assert_solid(d, second, expected-4*pi)
    assert d.feature(sid).parameters.entities == entities


@pytest.mark.parametrize('distance', [-3, 3])
def test_four_joined_bosses_and_region_scoped_cap_attachments(tmp_path, distance):
    d, sid, target, entities = setup(tuple(Circle(x, y, 2) for y in (8, 20) for x in (6, 25)), face=distance > 0)
    eid = d.add_multi_extrusion(sid, select(d, sid), distance, operation='join', target_id=target)
    assert volume(d.solid_shapes[eid]) == pytest.approx(24000+16*pi*3)
    assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()
    caps = [(key, face) for key, face in d.source_faces[eid].items() if key[0] == 'end']
    assert len(caps) == 4 and len({key[1] for key, _ in caps}) == 4
    for key, face in caps:
        face = d.source_faces[eid][key]
        ref = identify_face(face, d.face_maps, {f.id:f for f in d.features},
                            active_ids=d.active_body_ids, lineages=d.face_lineages,
                            source_faces=d.source_faces, bodies=d.solid_shapes)
        attached = d.add_face_sketch(ref)
        assert d.statuses[attached].valid
    d.save(tmp_path/'bosses.starcad')
    loaded = Document.load(d.path)
    assert loaded.features == d.features and all(s.valid for s in loaded.statuses.values())


@pytest.mark.parametrize('operation', ['new', 'intersect', 'join', 'cut'])
def test_invalid_multi_operation_is_atomic(operation):
    d, sid, target, _ = setup((Circle(6, 7, 2), Circle(60, 7, 2)))
    before, shape, history = d.features, d.shape, list(d._undo)
    with pytest.raises(FeatureError):
        d.add_multi_extrusion(sid, select(d, sid), 3, operation=operation,
                              **({} if operation == 'new' else {'target_id':target}))
    assert d.features == before and d.shape.IsSame(shape) and d._undo == history


def test_nested_holes_and_island_keep_even_odd_material():
    d, sid, target, _ = setup((Rectangle(3, 3, 30, 24), Circle(12, 12, 5), Circle(12, 12, 2)))
    refs = select(d, sid)
    assert len(refs) == 2 and sum(len(r.hole_ids) for r in refs) == 1
    eid = d.add_multi_extrusion(sid, refs, 3, operation='cut', target_id=target)
    assert_solid(d, eid, 24000-3*(720-21*pi))


def test_dimensions_reorder_and_all_boundary_deletion_guards():
    d, sid, target, circles = setup()
    eid = d.add_multi_extrusion(sid, select(d, sid), 3, operation='cut', target_id=target)
    parameters = d.feature(eid).parameters
    d.update_entity(sid, replace(circles[-1], radius=3))
    assert_solid(d, eid, 24000-3*29*pi)
    sketch = d.feature(sid)
    d.replace_feature(replace(sketch, parameters=replace(sketch.parameters, entities=sketch.parameters.entities[::-1])))
    assert d.feature(eid).parameters == parameters
    for circle in circles:
        with pytest.raises(ValueError, match='references'):
            d.delete(entities=[(sid, circle.id)])
    before = d.features
    with pytest.raises(FeatureError, match='topology changed'):
        d.update_entity(sid, replace(circles[-1], x=circles[0].x, y=circles[0].y))
    assert d.features == before


def test_line_loop_in_multi_feature_unresolved_and_recovers(tmp_path):
    lines = (Line(3, 3, 9, 3), Line(9, 3, 6, 8), Line(6, 8, 3, 3))
    d, sid, target, _ = setup((*lines, Circle(20, 10, 2)))
    eid = d.add_multi_extrusion(sid, select(d, sid), 3, operation='cut', target_id=target)
    expected = 24000-3*(15+4*pi)
    assert_solid(d, eid, expected)
    d.update_entity(sid, replace(lines[0], x2=10))
    assert not d.statuses[eid].valid and eid not in d.solid_shapes
    assert d.active_body_ids == frozenset((target,))
    d.save(tmp_path/'unresolved.starcad')
    loaded = Document.load(d.path)
    assert not loaded.statuses[eid].valid
    loaded.update_entity(sid, lines[0])
    assert_solid(loaded, eid, expected)
    d.undo(); assert_solid(d, eid, expected)
    d.redo(); assert not d.statuses[eid].valid
    for line in lines:
        with pytest.raises(ValueError):
            d.delete(entities=[(sid, line.id)])


def test_v15_canonical_records_and_strict_validation():
    d, sid, target, _ = setup()
    refs = select(d, sid)
    eid = d.add_multi_extrusion(sid, refs[::-1], 3, operation='cut', target_id=target)
    p = d.feature(eid).parameters
    assert tuple(r.outer_id for r in p.profiles) == tuple(sorted(r.outer_id for r in refs))
    data = serialize(d.features)
    assert data['version'] == 15 and deserialize(data) == d.features
    mutations = [lambda x:x.update(version=14),
                 lambda x:x['features'][-1]['parameters'].update(additional_profiles=[]),
                 lambda x:x['features'][-1]['parameters']['additional_profiles'][0].update(line_ids='bad'),
                 lambda x:x['features'][-1]['parameters']['additional_profiles'].append(
                     x['features'][-1]['parameters']['additional_profiles'][0])]
    for mutate in mutations:
        bad = deepcopy(data); mutate(bad)
        with pytest.raises(ValueError): deserialize(bad)
    with pytest.raises(ValueError, match='Duplicate selected profile'):
        ExtrudeParameters(sid, refs[0].outer_id, additional_profiles=(refs[0],))


def test_failed_direct_multi_distance_edit_keeps_last_accepted_feature_and_history():
    d, sid, target, _ = setup()
    eid = d.add_multi_extrusion(sid, select(d, sid), 3, operation='cut', target_id=target)
    feature = d.feature(eid)
    before, shape, undo, redo = d.features, d.shape, tuple(d._undo), tuple(d._redo)
    with pytest.raises(FeatureError):
        d.replace_feature(replace(feature, parameters=replace(feature.parameters, distance=-3)))
    assert d.features == before and d.shape.IsSame(shape)
    assert tuple(d._undo) == undo and tuple(d._redo) == redo and d.statuses[eid].valid

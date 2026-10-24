from dataclasses import replace
from math import pi
import json
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from hero_cad.document import Document
from hero_cad.features import ExtrudeParameters, FeatureError
from hero_cad.geometry import volume
from hero_cad.profiles import regions, contains
from hero_cad.sketch import Circle, Rectangle, Slot, Line


def sketch_document(entities, plane='XY'):
    d = Document()
    sid = d.add_sketch(plane)
    for entity in entities:
        d.add_entity(sid, entity)
    return d, sid


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
@pytest.mark.parametrize('distance', [3.25, -3.25])
@pytest.mark.parametrize('entity,area', [(Rectangle(2, 3, 20, 10, 31), 200),
                                       (Circle(2, 3, 2), 4*pi),
                                       (Slot(2, 3, 2, 10, 37), 40+4*pi)])
def test_simple_extrusions_are_exact_valid_solids(plane, distance, entity, area):
    d, sid = sketch_document([entity], plane)
    eid = d.add_extrusion(sid, entity.id, distance=distance)
    solid = d.solid_shapes[eid]
    assert BRepCheck_Analyzer(solid).IsValid()
    assert volume(solid) == pytest.approx(area*abs(distance), rel=1e-11)
    assert d.feature(eid).references == (sid,)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(solid, box, False, False)
    bounds = box.Get()
    normal_axis = {'XY': 2, 'XZ': 1, 'YZ': 0}[plane]
    end = d.feature(sid).parameters.frame.normal[normal_axis]*distance
    assert (bounds[normal_axis], bounds[normal_axis+3]) == pytest.approx((min(0, end), max(0, end)), abs=1e-7)
    assert volume(d.shape) == pytest.approx(40*30*20+area*abs(distance), rel=1e-11)


def test_holes_and_islands_are_material_regions_not_individual_wires():
    outer, hole, island, separate = Rectangle(0, 0, 40, 30), Circle(10, 10, 5), Circle(10, 10, 2), Slot(60, 0, 2, 5)
    d, sid = sketch_document([hole, separate, island, outer])
    rs = regions(d.feature(sid).parameters)
    assert {r.outer_id for r in rs} == {outer.id, island.id, separate.id}
    plate = next(r for r in rs if r.outer_id == outer.id)
    assert plate.hole_ids == (hole.id,)
    assert contains(plate.face, (30, 15, 0))
    assert not contains(plate.face, (10, 10, 0))
    assert not contains(plate.face, (10, 13, 0))
    a = d.add_extrusion(sid, outer.id, plate.hole_ids, 4)
    b = d.add_extrusion(sid, island.id, (), 4)
    assert volume(d.solid_shapes[a]) == pytest.approx((1200-25*pi)*4, rel=1e-11)
    assert volume(d.solid_shapes[b]) == pytest.approx(4*pi*4, rel=1e-11)
    with pytest.raises(FeatureError, match='topology changed'):
        d.add_extrusion(sid, hole.id, (), 4)
    with pytest.raises(FeatureError, match='Holes will not be filled'):
        d.add_extrusion(sid, outer.id, (), 4)


@pytest.mark.parametrize('pair', [(Circle(0, 0, 3), Circle(4, 0, 3)),
                                  (Circle(0, 0, 3), Circle(6, 0, 3)),
                                  (Circle(0, 0, 3), Circle(0, 0, 3)),
                                  (Rectangle(0, 0, 10, 10), Circle(10, 5, 2))])
def test_ambiguous_overlaps_touching_and_duplicates_do_not_extrude(pair):
    safe = Circle(50, 50, 2)
    d, sid = sketch_document([*pair, safe])
    assert [r.outer_id for r in regions(d.feature(sid).parameters)] == [safe.id]
    for entity in pair:
        with pytest.raises(FeatureError):
            d.add_extrusion(sid, entity.id)
    d.add_extrusion(sid, safe.id)


def test_overlapping_holes_block_ancestor_and_descendant_material():
    outer = Rectangle(-20, -20, 40, 40)
    a, b, island = Circle(0, 0, 8), Circle(10, 0, 8), Circle(0, 0, 1)
    d, sid = sketch_document([outer, a, b, island])
    assert not regions(d.feature(sid).parameters)
    with pytest.raises(FeatureError):
        d.add_extrusion(sid, outer.id, (a.id, b.id))


def test_references_survive_edit_order_regenerate_save_and_history(tmp_path):
    outer, hole = Rectangle(0, 0, 20, 10), Circle(5, 5, 2)
    d, sid = sketch_document([outer, hole])
    eid = d.add_extrusion(sid, outer.id, (hole.id,), 3)
    ref = d.feature(eid)
    edited = replace(outer, width=25)
    d.update_entity(sid, edited)
    d.update_entity(sid, replace(hole, radius=3))
    assert d.feature(eid) == ref
    expected = (250-9*pi)*3
    assert volume(d.solid_shapes[eid]) == pytest.approx(expected)
    feature = d.feature(sid)
    d.replace_feature(replace(feature, parameters=replace(feature.parameters, entities=feature.parameters.entities[::-1])))
    assert volume(d.solid_shapes[eid]) == pytest.approx(expected)
    d.save(tmp_path/'plate.starcad')
    assert json.loads(d.path.read_text())['version'] == 4
    loaded = Document.load(d.path)
    assert loaded.features == d.features
    assert volume(loaded.solid_shapes[eid]) == pytest.approx(expected)
    before = d.features
    undo, shape = list(d._undo), d.shape
    for operation in (lambda: d.delete(features=[sid]), lambda: d.delete(entities=[(sid, hole.id)]),
                      lambda: d.update_entity(sid, replace(hole, x=100)),
                      lambda: d.add_entity(sid, Circle(15, 5, 1))):
        with pytest.raises(ValueError):
            operation()
        assert d.features == before and d._undo == undo and d.shape.IsSame(shape)
    d.delete(features=[eid])
    assert eid not in d.solid_shapes
    d.undo()
    assert d.features == before
    d.redo()
    assert eid not in d.solid_shapes
    d.delete(features=[sid])
    assert not d.sketches


@pytest.mark.parametrize('distance', [0, 1e-8, float('nan'), float('inf'), 100001, True, '5'])
def test_extrusion_distance_validation(distance):
    d, sid = sketch_document([Circle(0, 0, 2)])
    with pytest.raises(ValueError):
        d.add_extrusion(sid, d.feature(sid).parameters.entities[0].id, distance=distance)


def test_line_chains_are_explicitly_deferred_and_malformed_files_rejected(tmp_path):
    outer = Rectangle(0, 0, 20, 10)
    d, sid = sketch_document([outer, Line(2, 2, 4, 2)])
    with pytest.raises(ValueError, match='line-chain'):
        regions(d.feature(sid).parameters)
    d.delete(entities=[(sid, d.feature(sid).parameters.entities[-1].id)])
    eid = d.add_extrusion(sid, outer.id)
    path = tmp_path/'solid.starcad'
    d.save(path)
    good = json.loads(path.read_text())
    for mutate in (lambda x: x['features'][-1]['parameters'].update(hole_ids=['invalid']),
                   lambda x: x['features'][-1].update(references=[]),
                   lambda x: x.update(version=3),
                   lambda x: x['features'][-1]['parameters'].update(sketch_id=d.features[0].id)):
        import copy
        bad = copy.deepcopy(good)
        mutate(bad)
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            Document.load(path)


def test_rotated_plate_with_circle_slot_and_rectangle_holes():
    outer = Rectangle(-30, -20, 60, 40, 17)
    holes = (Circle(-10, 0, 3), Slot(4, 4, 2, 8, 40), Rectangle(-25, 10, 3, 5, 25))
    d, sid = sketch_document([outer, *holes])
    profile = next(r for r in regions(d.feature(sid).parameters) if r.outer_id == outer.id)
    assert set(profile.hole_ids) == {h.id for h in holes}
    eid = d.add_extrusion(sid, outer.id, profile.hole_ids, 2.5)
    assert volume(d.solid_shapes[eid]) == pytest.approx((2400-9*pi-(32+4*pi)-15)*2.5, rel=1e-11)
    assert BRepCheck_Analyzer(d.solid_shapes[eid]).IsValid()

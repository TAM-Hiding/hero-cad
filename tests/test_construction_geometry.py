from dataclasses import replace
import json
from math import pi

import pytest

from hero_cad.booleans import bounds
from hero_cad.document import BoxParameters, Document
from hero_cad.features import FeatureError, OffsetPlaneParameters
from hero_cad.geometry import volume
from hero_cad.profiles import regions
from hero_cad.sketch import Circle, FaceReference, Line, PLANES, Rectangle


@pytest.mark.parametrize(('axis', 'offset'), [('XY', 25), ('XZ', -12), ('YZ', 0)])
def test_origin_plane_sketch_frame_and_history(axis, offset):
    doc = Document()
    plane = doc.add_offset_plane('plane:' + axis, offset)
    origin = PLANES[axis]
    frame = doc.plane_frames[plane]
    assert frame.origin == tuple(offset*n for n in origin.normal)
    assert (frame.u, frame.v, frame.normal) == (origin.u, origin.v, origin.normal)
    assert plane not in doc.solid_shapes
    doc.undo()
    assert plane not in doc.plane_frames
    doc.redo()
    sketch = doc.add_plane_sketch(plane)
    assert doc.feature(sketch).references == (plane,)
    assert doc.feature(sketch).parameters.frame == frame
    with pytest.raises(ValueError, match='references the selected feature'):
        doc.delete(features=[plane])


def test_plane_chain_regenerates_solid_and_round_trips(tmp_path):
    doc = Document()
    parent = doc.add_offset_plane('plane:XY', 25)
    child = doc.add_offset_plane(parent, -2)
    sketch = doc.add_plane_sketch(child)
    entity = Rectangle(2, 3, 4, 5)
    doc.add_entity(sketch, entity)
    extrusion = doc.add_extrusion(sketch, entity.id, distance=7)
    feature = doc.feature(parent)
    assert bounds(doc.solid_shapes[extrusion]) == pytest.approx((2, 6, 3, 8, 23, 30))
    doc.replace_feature(replace(feature, parameters=replace(feature.parameters, offset=40)))
    assert doc.feature(sketch).parameters.entities == (entity,)
    assert doc.plane_frames[child].origin == (0, 0, 38)
    assert bounds(doc.solid_shapes[extrusion]) == pytest.approx((2, 6, 3, 8, 38, 45))
    doc.undo()
    assert bounds(doc.solid_shapes[extrusion]) == pytest.approx((2, 6, 3, 8, 23, 30))
    doc.redo()
    doc.set_plane_visibility(child, False)
    path = tmp_path / 'planes.hcad'
    doc.save(path)
    assert json.loads(path.read_text())['version'] == 16
    loaded = Document.load(path)
    assert loaded.features == doc.features and loaded.plane_frames == doc.plane_frames
    assert loaded.feature(sketch).parameters.plane_id == child
    assert not loaded.feature(child).plane_visible
    assert volume(loaded.solid_shapes[extrusion]) == pytest.approx(140)
    loaded.delete(features=[extrusion, sketch, child])
    assert child not in loaded.plane_frames
    loaded.undo()
    assert child in loaded.plane_frames
    loaded.redo()
    assert child not in loaded.plane_frames


def test_face_plane_moves_and_lost_face_blocks_dependents(tmp_path):
    doc = Document()
    box = doc.features[0].id
    plane = doc.add_offset_plane(FaceReference(box, '+Z'), -5)
    assert doc.plane_frames[plane].origin[2] == 15
    doc.set_box(BoxParameters(height=34))
    assert doc.plane_frames[plane].origin[2] == 29

    source = doc.add_sketch('XY')
    rectangle = Rectangle(1, 2, 3, 4)
    doc.add_entity(source, rectangle)
    body = doc.add_extrusion(source, rectangle.id, distance=10)
    face = FaceReference(body, 'side', rectangle.id, 'edge0')
    side_plane = doc.add_offset_plane(face, 2)
    sketch = doc.add_plane_sketch(side_plane)
    circle = Circle(0, 0, 1)
    doc.add_entity(sketch, circle)
    extrude = doc.add_extrusion(sketch, circle.id, distance=2)
    original_frame = doc.plane_frames[side_plane]
    # The source circle reuses the UUID and material region, but has no planar side.
    doc.update_entity(source, Circle(2, 2, 1, rectangle.id))
    assert doc.statuses[body].valid
    assert side_plane not in doc.plane_frames and not doc.statuses[side_plane].valid
    assert doc.statuses[sketch].blocked_by == side_plane
    assert doc.statuses[extrude].blocked_by == sketch
    assert doc.feature(sketch).parameters.entities == (circle,)
    path = tmp_path / 'unresolved.hcad'
    doc.save(path)
    assert not Document.load(path).statuses[side_plane].valid
    doc.undo()
    assert doc.plane_frames[side_plane] == original_frame
    assert doc.statuses[extrude].valid


def test_plane_cycles_and_invalid_supports_are_rejected():
    doc = Document()
    a = doc.add_offset_plane('plane:XY', 1)
    b = doc.add_offset_plane(a, 2)
    before = doc.features
    for reference in (a, b):
        with pytest.raises(FeatureError, match='cyclic or forward'):
            doc.replace_feature(replace(doc.feature(a), references=(reference,),
                                        parameters=OffsetPlaneParameters(reference, 0)))
        assert doc.features == before
    with pytest.raises(ValueError, match='resolved plane'):
        doc.add_offset_plane(doc.features[0].id, 0)
    with pytest.raises(ValueError, match='finite'):
        doc.add_offset_plane('plane:XY', float('nan'))


def test_construction_profile_exclusion_conversion_and_persistence(tmp_path):
    doc = Document()
    sketch = doc.add_sketch('XY')
    rectangle = Rectangle(0, 0, 10, 10)
    line = Line(5, 0, 5, 10, construction=True)
    circle = Circle(5, 5, 20, construction=True)
    for entity in (rectangle, line, circle):
        doc.add_entity(sketch, entity)
    assert [r.outer_id for r in regions(doc.feature(sketch).parameters)] == [rectangle.id]
    doc.toggle_construction(sketch, [line.id])
    assert not regions(doc.feature(sketch).parameters)
    doc.undo()
    assert doc.feature(sketch).parameters.entities == (rectangle, line, circle)
    doc.redo()
    doc.toggle_construction(sketch, [line.id])
    assert doc.feature(sketch).parameters.entities == (rectangle, line, circle)

    bolt_sketch = doc.add_sketch('XY')
    bolts = (Circle(0, 10, 1), Circle(10, 0, 1), Circle(0, -10, 1))
    guide = Circle(0, 0, 40, construction=True)
    for entity in (*bolts, guide):
        doc.add_entity(bolt_sketch, entity)
    assert {r.outer_id for r in regions(doc.feature(bolt_sketch).parameters)} == {e.id for e in bolts}
    assert {r.outer_id for r in regions(replace(doc.feature(bolt_sketch).parameters, entities=(guide,)))} == set()
    extrusion = doc.add_extrusion(bolt_sketch, bolts[0].id, distance=4)
    assert volume(doc.solid_shapes[extrusion]) == pytest.approx(4*pi)
    doc.toggle_construction(bolt_sketch, [bolts[0].id])
    assert not doc.statuses[extrusion].valid
    doc.undo()
    assert doc.statuses[extrusion].valid
    doc.redo()
    doc.toggle_construction(bolt_sketch, [bolts[0].id])
    assert doc.statuses[extrusion].valid
    path = tmp_path / 'construction.hcad'
    doc.save(path)
    assert Document.load(path).features == doc.features
    doc.delete(entities=[(sketch, line.id), (sketch, circle.id)])
    assert doc.feature(sketch).parameters.entities == (rectangle,)
    doc.undo()
    assert doc.feature(sketch).parameters.entities == (rectangle, line, circle)
    doc.redo()
    assert doc.feature(sketch).parameters.entities == (rectangle,)


def test_ordinary_schema_stays_compact_and_rejects_early_construction_flag():
    from hero_cad.persistence import deserialize, serialize

    doc = Document()
    sketch = doc.add_sketch('XY')
    circle = Circle(0, 0, 2)
    doc.add_entity(sketch, circle)
    ordinary = serialize(doc.features)
    assert ordinary['version'] == 3
    params = ordinary['features'][-1]['parameters']['entities'][0]['parameters']
    assert 'construction' not in params
    assert Document(features=deserialize(ordinary)).feature(sketch).parameters.entities == (circle,)
    params['construction'] = True
    with pytest.raises(ValueError, match='Invalid document fields'):
        deserialize(ordinary)
    ordinary['version'] = 16
    params['construction'] = 1
    with pytest.raises(ValueError, match='must be boolean'):
        deserialize(ordinary)

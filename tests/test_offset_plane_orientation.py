from dataclasses import replace
import json
from math import sqrt

import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_OUT
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt

from hero_cad.attachments import cross, planar_frame, resolve_attachment
from hero_cad.booleans import bounds
from hero_cad.document import BoxParameters, Document
from hero_cad.face_history import subshapes
from hero_cad.features import Feature, OffsetPlaneParameters
from hero_cad.sketch import Circle, FaceReference, Line, Rectangle


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def centroid(face):
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.CentreOfMass().Coord()


def solid_face(doc, owner, handle):
    return next(TopoDS.Face_s(face) for face in subshapes(doc.solid_shapes[owner], TopAbs_FACE)
                if face.IsSame(handle))


def assert_outward(doc, reference, face, expected=None):
    body = doc.solid_shapes[reference.parent_id]
    center = centroid(face)
    for offset in (4., -9.):
        p, frame, display_center = doc.offset_plane_parameters(reference, offset)
        n = frame.normal
        assert dot(frame.u, frame.v) == pytest.approx(0, abs=1e-12)
        assert dot(frame.u, frame.u) == pytest.approx(1)
        assert dot(frame.v, frame.v) == pytest.approx(1)
        assert cross(frame.u, frame.v) == pytest.approx(n)
        if expected is not None:
            assert n == pytest.approx(expected)
        for sign, state in ((1, TopAbs_OUT), (-1, TopAbs_IN)):
            point = gp_Pnt(*(x + sign*.01*y for x, y in zip(center, n)))
            assert BRepClass3d_SolidClassifier(body, point, 1e-7).State() == state
        delta = tuple(a-b for a,b in zip(frame.origin, p.support_frame.origin))
        assert delta == pytest.approx(tuple(offset*x for x in n))
        assert display_center == pytest.approx(tuple(x + offset*y for x, y in zip(center, n)))
    return n


def chamfer(doc, endpoints):
    box = doc.features[0].id
    for edge in subshapes(doc.solid_shapes[box], TopAbs_EDGE):
        _, reference = doc.edge_reference(edge)
        if reference.endpoints == endpoints:
            feature = doc.add_chamfer(box, reference, 2)
            return feature, doc.source_faces[feature]['bevel', None, None]
    raise AssertionError('Expected fixture edge')


def test_equivalent_sloped_faces_and_generated_handle_orientation():
    doc = Document()
    chamfer_id, generated = chamfer(doc, ((0., 0., 0.), (0., 0., 20.)))
    actual = solid_face(doc, chamfer_id, generated)
    assert generated.Orientation() != actual.Orientation()
    plane = BRepAdaptor_Surface(actual).Plane()
    assert not plane.Direct()
    raw_axis = plane.Axis().Direction().Coord()
    assert raw_axis != pytest.approx(cross(plane.XAxis().Direction().Coord(), plane.YAxis().Direction().Coord()))
    expected = (-1/sqrt(2), -1/sqrt(2), 0.)
    reference = doc.face_reference(actual)
    assert reference.face == 'evaluated'
    assert planar_frame(generated).normal == pytest.approx(expected)
    # The two orientation mistakes cancel on this edge. Other edges below
    # isolate each mistake so either partial fix fails the classifier check.
    assert_outward(doc, reference, actual, expected)

    sketch = doc.add_sketch('XY')
    points = ((2, 0), (40, 0), (40, 30), (0, 30), (0, 2))
    lines = [Line(*a, *b) for a,b in zip(points, points[1:] + points[:1])]
    for line in lines:
        doc.add_entity(sketch, line)
    from hero_cad.profiles import regions
    region, = regions(doc.feature(sketch).parameters)
    prism = doc.add_extrusion(sketch, region.outer_id, distance=20)
    side = doc.face_maps[prism]['side', lines[-1].id, 'line']
    assert centroid(side) == pytest.approx(centroid(actual))
    assert_outward(doc, doc.face_reference(side), side, expected)


@pytest.mark.parametrize('endpoints', [
    ((0., 0., 20.), (0., 30., 20.)),   # Direct axes, generated handle has reversed sense.
    ((0., 30., 0.), (0., 30., 20.)),   # Indirect axes, handle orientation already agrees.
    ((0., 30., 20.), (40., 30., 20.)),
])
def test_rotated_chamfers_follow_the_finished_solid(endpoints):
    doc = Document()
    feature, generated = chamfer(doc, endpoints)
    actual = solid_face(doc, feature, generated)
    reference = doc.face_reference(actual)
    normal = assert_outward(doc, reference, actual)
    stored = doc.add_offset_plane(reference, -9)
    assert doc.plane_frames[stored].normal == pytest.approx(normal)


def test_box_caps_and_boolean_cavity():
    doc = Document()
    box = doc.features[0].id
    for key, face in doc.face_maps[box].items():
        assert_outward(doc, doc.face_reference(face), face)
    sketch = doc.add_sketch('XY')
    entity = Rectangle(8, 9, 10, 11)
    doc.add_entity(sketch, entity)
    prism = doc.add_extrusion(sketch, entity.id, distance=-10)
    for key in ('start', 'end'):
        face = doc.face_maps[prism][key, None, None]
        assert_outward(doc, doc.face_reference(face), face)
    end = doc.add_offset_plane(FaceReference(prism, 'end'), 2)
    cap_center = doc.plane_centers[end]
    assert cap_center == pytest.approx((13, 14.5, -12))
    feature = doc.feature(prism)
    doc.replace_feature(replace(feature, parameters=replace(feature.parameters, distance=10)))
    assert doc.plane_centers[end] == pytest.approx((13, 14.5, 12))
    assert doc.plane_frames[end].normal == pytest.approx((0, 0, 1))
    # Cut a pocket from the bottom. Outward from material is down into the pocket.
    pocket = doc.add_extrusion(sketch, entity.id, distance=8, operation='cut', target_id=box)
    floor = next(TopoDS.Face_s(raw) for raw in subshapes(doc.solid_shapes[pocket], TopAbs_FACE)
                 if centroid(TopoDS.Face_s(raw)) == pytest.approx((13, 14.5, 8)))
    reference = doc.face_reference(floor)
    assert reference.face == 'evaluated'
    assert_outward(doc, reference, floor, (0, 0, -1))


def test_centers_follow_upstream_edits_without_moving_local_geometry(tmp_path):
    doc = Document()
    box = doc.features[0].id
    origin = doc.add_offset_plane('plane:XY', 4)
    assert doc.plane_centers[origin] == doc.plane_frames[origin].origin
    plane = doc.add_offset_plane(FaceReference(box, '+Z'), 3)
    child = doc.add_offset_plane(plane, -1)
    sketch = doc.add_plane_sketch(child)
    circle = Circle(4, 5, 1)
    doc.add_entity(sketch, circle)
    prism = doc.add_extrusion(sketch, circle.id, distance=4)
    frame = doc.plane_frames[child]
    solid_bounds = bounds(doc.solid_shapes[prism])
    assert doc.plane_centers[child] == pytest.approx((20, 15, 22))
    doc.set_box(BoxParameters(width=60, depth=50))
    assert doc.plane_centers[plane] == pytest.approx((30, 25, 23))
    assert doc.plane_centers[child] == pytest.approx((30, 25, 22))
    assert doc.plane_frames[child] == frame
    assert doc.feature(sketch).parameters.entities == (circle,)
    assert bounds(doc.solid_shapes[prism]) == pytest.approx(solid_bounds)
    feature = doc.feature(plane)
    doc.replace_feature(replace(feature, parameters=replace(feature.parameters, offset=-3)))
    assert doc.plane_centers[child] == pytest.approx((30, 25, 16))
    doc.undo()
    assert doc.plane_centers[child] == pytest.approx((30, 25, 22))
    doc.redo()
    path = tmp_path/'center.hcad'
    doc.save(path)
    assert 'plane_centers' not in path.read_text()
    assert Document.load(path).plane_centers == doc.plane_centers


@pytest.mark.parametrize('picked', [False, True])
def test_legacy_bevel_plane_and_sketch_keep_sign_and_positions(tmp_path, picked):
    doc = Document()
    endpoints = ((0., 30., 0.), (0., 30., 20.)) if picked else ((0., 0., 20.), (0., 30., 20.))
    owner, generated = chamfer(doc, endpoints)
    ref = doc.face_reference(solid_face(doc, owner, generated)) if picked else FaceReference(owner, 'bevel')
    old_frame = resolve_attachment(ref, doc.face_maps, {f.id: f for f in doc.features},
                                   lineages=doc.face_lineages, source_faces=doc.source_faces, bodies=doc.solid_shapes)
    legacy = Feature('offset_plane', OffsetPlaneParameters(ref, -9, old_frame), (owner,))
    doc.set_features((*doc.features, legacy))
    assert doc.plane_frames[legacy.id] == legacy.parameters.offset_frame(old_frame)
    attached = doc.add_face_sketch(ref)
    sketch = doc.add_plane_sketch(legacy.id)
    circle = Circle(2, 3, 1)
    doc.add_entity(sketch, circle)
    solid = doc.add_extrusion(sketch, circle.id, distance=3)
    new_plane = doc.add_offset_plane(ref, -9)
    assert dot(doc.plane_frames[new_plane].normal, old_frame.normal) == pytest.approx(-1)
    original = bounds(doc.solid_shapes[solid])
    path = tmp_path/'legacy-face.hcad'
    doc.save(path)
    records = {f['id']: f['parameters'] for f in json.loads(path.read_text())['features']}
    assert 'outward' not in records[legacy.id] and records[new_plane]['outward'] is True
    loaded = Document.load(path)
    assert loaded.feature(attached).parameters.frame == old_frame
    assert loaded.plane_frames == doc.plane_frames
    assert bounds(loaded.solid_shapes[solid]) == pytest.approx(original)
    feature = loaded.feature(owner)
    previous = loaded.plane_centers[new_plane]
    loaded.replace_feature(replace(feature, parameters=replace(feature.parameters, distance=3)))
    assert loaded.plane_centers[new_plane] != pytest.approx(previous)
    assert dot(loaded.plane_frames[legacy.id].normal, loaded.plane_frames[new_plane].normal) == pytest.approx(-1)

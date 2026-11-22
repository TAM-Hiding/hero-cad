from dataclasses import replace
import json
from math import acos, pi, sqrt

import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_Circle
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS

from hero_cad.arrangement import shapes
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.profiles import contains, regions
from hero_cad.sketch import Circle, Line, Rectangle, SketchParameters, Slot


def area(face):
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, properties)
    return properties.Mass()


def cells(*entities):
    sketch = SketchParameters('XY', entities)
    available = regions(sketch)
    assert sketch.entities == entities
    assert len({r.outer_id for r in available}) == len(available)
    assert all(BRepCheck_Analyzer(r.face).IsValid() and area(r.face) > 0 for r in available)
    return available


def picked(available, x, y):
    region, = (r for r in available if contains(r.face, (x, y, 0)))
    return region


def lens_area(radius, separation):
    return 2*radius**2*acos(separation/(2*radius)) - separation/2*sqrt(4*radius**2-separation**2)


def test_exact_circle_lens_and_shared_boundary():
    a, b = Circle(0, 0, 5), Circle(6, 0, 5)
    available = cells(a, b)
    assert len(available) == 3
    lens = picked(available, 3, 0)
    assert area(lens.face) == pytest.approx(lens_area(5, 6), rel=1e-10)
    assert area(picked(available, -2, 0).face) == pytest.approx(25*pi-lens_area(5, 6))
    assert not any(contains(r.face, (1, 0, 0)) for r in available)
    assert all(BRepAdaptor_Curve(e).GetType() == GeomAbs_Circle
               for e in shapes(lens.face, TopAbs_EDGE, TopoDS.Edge_s))


def test_overlapping_rectangles_and_shared_collinear_sides():
    available = cells(Rectangle(0, 0, 8, 6), Rectangle(4, 0, 8, 6))
    assert len(available) == 3
    assert sorted(area(r.face) for r in available) == pytest.approx([24, 24, 24])
    adjacent = cells(Rectangle(0, 0, 8, 6), Rectangle(8, 0, 8, 6))
    assert len(adjacent) == 2


@pytest.mark.parametrize(('a', 'b', 'count'), [
    (Rectangle(0, 0, 8, 8), Circle(8, 4, 2), 3),
    (Slot(0, 0, 2, 10), Circle(7, 1, 3), 4),
    (Slot(0, 0, 1, 8), Slot(4, -4, 1, 8, 90), 5),
    (Slot(0, 0, 1, 8), Rectangle(3, -2, 2, 4), 5),
    (Slot(0, 0, 1, 8), Line(4, -2, 4, 2), 2),
    (Circle(0, 0, 5), Line(-7, 0, 7, 0), 2),
])
def test_mixed_analytic_boundaries(a, b, count):
    assert len(cells(a, b)) == count


def test_line_network_dangling_edges_and_construction_exclusion():
    points = ((0, 0), (8, 0), (8, 8), (0, 8))
    loop = tuple(Line(*a, *b) for a,b in zip(points, points[1:] + points[:1]))
    available = cells(*loop, Line(4, -1, 4, 9), Line(4, 4, 7, 4))
    assert sorted(area(r.face) for r in available) == pytest.approx([32, 32])
    available = cells(*loop, Line(4, -1, 4, 5))
    assert [area(r.face) for r in available] == pytest.approx([64])
    available = cells(*loop, Line(4, -1, 4, 9, construction=True))
    assert [area(r.face) for r in available] == pytest.approx([64])
    assert len(cells(Slot(0, 0, 2, 8), Circle(3, 1, 2, construction=True))) == 1


def test_nested_tangent_duplicate_and_small_cells():
    assert sorted(area(r.face) for r in cells(Circle(0, 0, 5), Circle(0, 0, 2))) == pytest.approx([4*pi, 21*pi])
    assert len(cells(Circle(0, 0, 5), Circle(10, 0, 5))) == 2
    assert len(cells(Circle(0, 0, 5), Circle(0, 0, 5))) == 1
    assert len(cells(Circle(0, 0, 5), Circle(9.999, 0, 5))) == 3
    junction = (Line(-10, 0, 10, 0), Line(0, -10, 0, 10), Line(-10, -10, 10, 10))
    assert len(cells(Rectangle(-4, -4, 8, 8), *junction)) == 6


def model():
    doc = Document()
    sid = doc.add_sketch('XY')
    a, b = Circle(10, 10, 5), Circle(16, 10, 5)
    for entity in (a, b):
        doc.add_entity(sid, entity)
    return doc, sid, a, b


def test_parametric_lens_recovery_and_schema(tmp_path):
    doc, sid, a, b = model()
    region = picked(regions(doc.feature(sid).parameters), 13, 10)
    eid = doc.add_extrusion(sid, region.outer_id, distance=4)
    feature = doc.feature(eid)
    initial = volume(doc.solid_shapes[eid])
    assert initial == pytest.approx(4*lens_area(5, 6))
    changed = replace(a, radius=6)
    doc.update_entity(sid, changed)
    later = volume(doc.solid_shapes[eid])
    assert later > initial and doc.feature(eid) == feature
    doc.undo()
    assert volume(doc.solid_shapes[eid]) == pytest.approx(initial)
    doc.redo()
    assert volume(doc.solid_shapes[eid]) == pytest.approx(later)
    doc.update_entity(sid, replace(b, x=40))
    assert not doc.statuses[eid].valid and eid not in doc.solid_shapes
    path = tmp_path/'unresolved.hcad'
    doc.save(path)
    assert json.loads(path.read_text())['version'] == 17
    loaded = Document.load(path)
    assert loaded.feature(eid) == feature and not loaded.statuses[eid].valid
    loaded.update_entity(sid, b)
    assert volume(loaded.solid_shapes[eid]) == pytest.approx(later)
    loaded.toggle_construction(sid, (a.id,))
    assert not loaded.statuses[eid].valid
    loaded.undo()
    assert loaded.statuses[eid].valid
    loaded.delete(entities=[(sid, b.id)])
    assert not loaded.statuses[eid].valid
    loaded.undo()
    assert loaded.statuses[eid].valid
    loaded.add_entity(sid, Circle(13, 10, 1))
    assert not loaded.statuses[eid].valid  # New hole changes the referenced lens boundary.
    loaded.undo()
    assert loaded.statuses[eid].valid
    loaded.save(path)
    assert Document.load(path).feature(eid) == feature


@pytest.mark.parametrize('operation', ['new', 'join', 'cut', 'intersect'])
def test_adjacent_cells_one_feature_and_valid_boolean_result(operation, tmp_path):
    doc, sid, _, _ = model()
    available = regions(doc.feature(sid).parameters)
    selected = (picked(available, 7, 10).reference, picked(available, 13, 10).reference)
    target = doc.features[0].id if operation != 'new' else None
    distance = -4 if operation == 'join' else 4
    eid = doc.add_multi_extrusion(sid, selected, distance, operation=operation, target_id=target)
    expected = 100*pi
    if operation == 'join':
        expected += 24000
    if operation == 'cut':
        expected = 24000-expected
    assert volume(doc.solid_shapes[eid]) == pytest.approx(expected)
    assert BRepCheck_Analyzer(doc.solid_shapes[eid]).IsValid()
    assert len(doc.feature(eid).parameters.profiles) == 2
    path = tmp_path/'multiple.hcad'
    doc.save(path)
    assert Document.load(path).feature(eid) == doc.feature(eid)


def test_dense_arrangement_reports_broad_phase_limit(monkeypatch):
    import hero_cad.arrangement as module

    monkeypatch.setattr(module, 'MAX_EDGE_PAIRS', 2)
    sketch = SketchParameters('XY', (Circle(0, 0, 5), Circle(2, 0, 5), Circle(4, 0, 5)))
    with pytest.raises(ValueError, match='potentially intersecting edge pairs'):
        regions(sketch)

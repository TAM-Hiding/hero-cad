from dataclasses import replace
from math import sqrt
import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from hero_cad.attachments import planar_frame
from hero_cad.document import Document
from hero_cad.sketch import PLANES, Circle, PlaneFrame, Rectangle
from hero_cad.ui.display_geometry import subshapes
from hero_cad.ui.model_references import ModelReferences, ReferencePoint, model_references
from hero_cad.ui.snapping import snap_point


def acquire(refs, point, *, scale=10, previous=None, **options):
    return snap_point(point, tuple(x*scale for x in point), lambda p: tuple(x*scale for x in p),
                      1, model=refs, previous=previous, origin=False, **options)


@pytest.mark.parametrize('name', ['+X','-X','+Y','-Y','+Z','-Z'])
def test_box_boundaries_exact_and_only_coplanar(name):
    doc = Document()
    face = doc.face_maps[doc.features[0].id][name]
    frame = planar_frame(face)
    refs = model_references(subshapes(doc.shape, TopAbs_EDGE), frame)
    assert len(refs.lines) == 4
    for line in refs.lines:
        result = acquire(refs, tuple(x+.1 for x in line.a), grid=True)
        assert result.point == line.a
        assert result.target in ('MODEL ENDPOINT',)
        midpoint = tuple((a+b)/2 for a,b in zip(line.a,line.b))
        result = acquire(refs, midpoint)
        assert result.target == 'MODEL MIDPOINT'
        assert result.point == midpoint
        point = tuple(a+.31*(b-a) for a,b in zip(line.a,line.b))
        result = acquire(refs, point)
        assert result.target == 'MODEL EDGE'
        assert result.point == pytest.approx(point, abs=1e-12)
        world = frame.to_world(result.point)
        assert sum((world[i]-frame.origin[i])*frame.normal[i] for i in range(3)) == pytest.approx(0, abs=1e-12)


def test_arbitrary_frame_lines_and_rotated_circles():
    n = 1/sqrt(2)
    frame = PlaneFrame('test', (12,-7,19), (n,n,0), (0,0,1))
    a,b = (2.123456789123,3.987654321987), (23.25,8.75)
    line = BRepBuilderAPI_MakeEdge(gp_Pnt(*frame.to_world(a)),gp_Pnt(*frame.to_world(b))).Edge()
    circ = gp_Circ(gp_Ax2(gp_Pnt(*frame.to_world((10,12))),gp_Dir(*frame.normal)),3)
    circle = BRepBuilderAPI_MakeEdge(circ).Edge()
    refs = model_references((line,circle),frame)
    assert len(refs.lines) == 1
    assert len(refs.points) == 3  # two endpoints and a circle center, no seam
    result = acquire(refs,(10.1,12.1))
    assert result.target == 'MODEL CENTER'
    assert result.point == pytest.approx((10,12),abs=1e-12)
    assert refs.lines[0].a == pytest.approx(a,abs=1e-12)
    assert refs.lines[0].b == pytest.approx(b,abs=1e-12)


def test_off_plane_crossing_and_tilted_circle_are_excluded():
    edges = [BRepBuilderAPI_MakeEdge(gp_Pnt(1,2,z),gp_Pnt(7,9,w)).Edge()
             for z,w in ((1,1),(-1,1),(0,2))]
    edges.append(BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0,0,3),gp_Dir(0,0,1)),2)).Edge())
    # Both seam endpoints lie on XY, but the circle is perpendicular to XY.
    edges.append(BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0,0,0),gp_Dir(0,1,0)),2)).Edge())
    assert model_references(edges,PLANES['XY']) == ModelReferences()


def test_hole_center_and_inner_straight_boundaries():
    d = Document()
    sid = d.add_sketch('XY')
    outer, hole, rect = Rectangle(0,0,40,30),Circle(11,12,3),Rectangle(21,13,6,4)
    for e in (outer,hole,rect):
        d.add_entity(sid,e)
    body = d.add_extrusion(sid,outer.id,(hole.id,rect.id),distance=7)
    frame = replace(PLANES['XY'],origin=(0,0,7))
    refs = model_references(subshapes(d.solid_shapes[body],TopAbs_EDGE),frame)
    assert len(refs.lines) == 8
    assert acquire(refs,(11.1,12.1)).point == (11,12)
    assert acquire(refs,(24,13)).target == 'MODEL MIDPOINT'
    assert all(p.kind != 'MODEL ENDPOINT' or p.point != (14,12) for p in refs.points)


@pytest.mark.parametrize('scale',[1,10,100])
def test_priority_screen_radius_and_stable_competitors(scale):
    refs = ModelReferences(points=(ReferencePoint((11,12),'MODEL ENDPOINT',0),
                                   ReferencePoint((11+6/scale,12),'MODEL CENTER',1)))
    first = acquire(refs,(11,12),scale=scale)
    assert first.target == 'MODEL ENDPOINT'
    # Equidistant points retain the acquired candidate, then switch decisively.
    retained = acquire(refs,(11+2.5/scale,12),scale=scale,previous=first)
    assert retained == first
    switched = acquire(refs,(11+5/scale,12),scale=scale,previous=first)
    assert switched.target == 'MODEL CENTER'
    assert acquire(refs,(11,12+9/scale),scale=scale,grid=False).target == 'FREE'
    assert acquire(refs,(11,12+7/scale),scale=scale,grid=False).target == 'MODEL ENDPOINT'
    assert acquire(refs,(100,100),scale=scale).target == 'GRID'
    assert acquire(refs,(100.3,100.3),scale=scale,grid=False).target == 'FREE'

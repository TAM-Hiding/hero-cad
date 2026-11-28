from math import cos, sin, radians, hypot
import pytest
from OCP.TopAbs import TopAbs_EDGE
from hero_cad.document import Document
from hero_cad.sketch import Line, Rectangle, Circle, Slot, PlaneFrame
from hero_cad.ui.model_references import model_references, sketch_references, ReferenceArc
from hero_cad.ui.display_geometry import subshapes
from hero_cad.ui.snapping import snap_point


def pick(refs, point, **kwargs):
    return snap_point(point,tuple(x*20 for x in point),lambda p:tuple(x*20 for x in p),1,
                      grid=False,origin=False,model=refs,**kwargs)


@pytest.mark.parametrize('construction',[False,True])
def test_line_endpoints_midpoint_and_exact_location(construction):
    line = Line(2.123456789123,3,16,9,construction=construction)
    refs = sketch_references((line,))
    for p in line.points:
        result = pick(refs,p)
        assert result.point == p and result.target == 'ENDPOINT'
        assert result.entity_id == line.id
    middle = ((line.x1+line.x2)/2,(line.y1+line.y2)/2)
    assert pick(refs,middle).target == 'SKETCH MIDPOINT'
    point = tuple(a+.27*(b-a) for a,b in zip(*line.points))
    result = pick(refs,point)
    assert result.target == 'SKETCH EDGE'
    assert result.point == pytest.approx(point,abs=1e-12)


@pytest.mark.parametrize('angle',[0,31,126])
def test_rotated_rectangle_corners_midpoints_and_center(angle):
    rect = Rectangle(12,-9,20,10,angle)
    refs = sketch_references((rect,))
    for a,b in zip(rect.points,rect.points[1:]):
        assert pick(refs,a).target == 'ENDPOINT'
        midpoint = tuple((x+y)/2 for x,y in zip(a,b))
        result = pick(refs,midpoint)
        assert result.target == 'SKETCH MIDPOINT' and result.point == midpoint
    center = tuple(sum(p[i] for p in rect.points[:4])/4 for i in range(2))
    assert pick(refs,center).target == 'CENTER'
    assert pick(refs,center,sketch_centers=False).target == 'FREE'


@pytest.mark.parametrize('construction',[False,True])
def test_circle_center_and_circumference_are_analytic(construction):
    circle = Circle(11,14,7,construction=construction)
    refs = sketch_references((circle,))
    assert pick(refs,(11,14)).target == 'CENTER'
    for angle in (0,23,81,174,260):
        point = (11+7.1*cos(radians(angle)),14+7.1*sin(radians(angle)))
        result = pick(refs,point)
        assert result.target == 'SKETCH CURVE'
        assert hypot(result.point[0]-11,result.point[1]-14) == pytest.approx(7,abs=1e-12)
        assert result.entity_id == circle.id


@pytest.mark.parametrize('angle',[0,31,146])
def test_slot_centers_tangent_midpoints_and_trimmed_arcs(angle):
    slot = Slot(2,3,2,12,angle)
    refs = sketch_references((slot,))
    for center in ((slot.x,slot.y),slot.second_center):
        assert pick(refs,center).target == 'CENTER'
    for midpoint in refs.midpoints:
        assert pick(refs,midpoint.point).target == 'SKETCH MIDPOINT'
    for arc in refs.arcs:
        p = arc.point(arc.start+arc.sweep/2)
        result = pick(refs,p)
        assert result.target == 'SKETCH CURVE'
        assert result.point == pytest.approx(p,abs=1e-12)
    # A nearest circle point on the forbidden half must not become a slot edge.
    arc = refs.arcs[0]
    opposite = arc.point(arc.start+3*arc.sweep/2)
    candidate = arc.nearest(tuple(x*20 for x in opposite),lambda p:tuple(x*20 for x in p))
    assert candidate == pytest.approx(arc.point(arc.start),abs=1e-10) or candidate == pytest.approx(arc.point(arc.start+arc.sweep),abs=1e-10)


def test_oblique_analytic_circle_nearest_uses_projected_metric():
    arc = ReferenceArc((2,3),5)
    project = lambda p:(11*p[0]+4*p[1],3*p[1])
    cursor = (90,20)
    point = arc.nearest(cursor,project)
    assert hypot(point[0]-2,point[1]-3) == pytest.approx(5,abs=1e-12)
    tangent = (-(point[1]-3),point[0]-2)
    projected_tangent = (11*tangent[0]+4*tangent[1],3*tangent[1])
    residual = tuple(a-b for a,b in zip(project(point),cursor))
    assert sum(a*b for a,b in zip(projected_tangent,residual)) == pytest.approx(0,abs=1e-9)


@pytest.mark.parametrize('solid',[False,True])
@pytest.mark.parametrize('at_origin',[False,True])
@pytest.mark.parametrize('origin',[False,True])
def test_slot_center_classification_is_origin_priority(solid,at_origin,origin):
    slot = Slot(0 if at_origin else 7,0 if at_origin else 11,3,15,17)
    if solid:
        d = Document()
        sid = d.add_sketch('XY')
        d.add_entity(sid,slot)
        body = d.add_extrusion(sid,slot.id,distance=5)
        frame = PlaneFrame('cap',(0,0,5),(1,0,0),(0,1,0))
        refs = model_references(subshapes(d.solid_shapes[body],TopAbs_EDGE),frame)
    else:
        refs = sketch_references((slot,))
    expected = 'MODEL CENTER' if solid else 'CENTER'
    for i,p in enumerate(((slot.x,slot.y),slot.second_center)):
        result = snap_point(p,tuple(x*20 for x in p),lambda p:tuple(x*20 for x in p),1,
                            grid=False,origin=origin,model=refs)
        assert result.point == pytest.approx(p,abs=1e-12)
        assert result.target == ('ORIGIN' if origin and at_origin and i == 0 else expected)

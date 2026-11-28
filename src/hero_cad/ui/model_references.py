"""Transient analytic model and completed-sketch targets in local millimetres."""
from dataclasses import dataclass
from math import dist, atan2, cos, sin, radians, pi
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from hero_cad.sketch import Line, Rectangle, Circle, Slot


PLANE_TOLERANCE = 1e-7


@dataclass(frozen=True)
class ReferencePoint:
    point: tuple
    kind: str
    edge_index: int | None = None
    entity_id: str | None = None
    segment: int | None = None


@dataclass(frozen=True)
class ReferenceLine:
    a: tuple
    b: tuple
    edge_index: int | None = None
    entity_id: str | None = None
    segment: int | None = None

    def nearest(self, cursor, project):
        """Exact affine line interpolation in the orthographic sketch view."""
        a, b = project(self.a), project(self.b)
        if a is None or b is None:
            return None
        delta = tuple(b[i]-a[i] for i in range(2))
        length2 = sum(x*x for x in delta)
        if length2 < 1e-12:
            return None
        t = max(0., min(1., sum((cursor[i]-a[i])*delta[i] for i in range(2))/length2))
        return tuple(self.a[i]+t*(self.b[i]-self.a[i]) for i in range(2))


@dataclass(frozen=True)
class ReferenceArc:
    center: tuple
    radius: float
    start: float = 0.
    sweep: float = 2*pi
    edge_index: int | None = None
    entity_id: str | None = None
    segment: int | None = None

    def point(self, angle):
        return self.center[0]+self.radius*cos(angle), self.center[1]+self.radius*sin(angle)

    def nearest(self, cursor, project):
        """Minimize screen distance on the analytic arc, even in oblique views.

        Orthographic projection gives C+A*cos(t)+B*sin(t). Its stationary
        distances are a quartic in tan(t/2). No display polyline is involved.
        """
        center = project(self.center)
        x, y = project((self.center[0]+self.radius,self.center[1])), project((self.center[0],self.center[1]+self.radius))
        if center is None or x is None or y is None:
            return None
        a,b,d = (tuple(p[i]-center[i] for i in range(2)) for p in (x,y,cursor))
        aa,bb,ab = sum(t*t for t in a),sum(t*t for t in b),sum(t*u for t,u in zip(a,b))
        if abs(a[0]*b[1]-a[1]*b[0]) < 1e-12*max(aa,bb):
            return None  # Edge-on projection cannot identify a unique arc point.
        da,db = -sum(t*u for t,u in zip(d,a)),-sum(t*u for t,u in zip(d,b))
        coefficients = (ab-db,-2*da-2*(bb-aa),-6*ab,-2*da+2*(bb-aa),ab+db)
        scale = max(abs(c) for c in coefficients)
        if scale < 1e-12:
            return None  # No uniquely preferred point on an unresolved tiny curve.
        roots = np.roots(tuple(c/scale for c in coefficients))
        angles = [pi,self.start,self.start+self.sweep]
        angles.extend(2*atan2(float(root.real),1) for root in roots if abs(root.imag) < 1e-8)
        direction = 1 if self.sweep > 0 else -1
        angles = [angle for angle in angles
                  if abs(self.sweep) >= 2*pi-1e-10 or (direction*(angle-self.start)) % (2*pi) <= abs(self.sweep)+1e-10]
        points = [(self.point(angle),project(self.point(angle))) for angle in angles]
        points = [(local,screen) for local,screen in points if screen is not None]
        return min(points,key=lambda p:dist(p[1],cursor),default=(None,None))[0]


@dataclass(frozen=True)
class ModelReferences:
    points: tuple = ()
    midpoints: tuple = ()
    lines: tuple = ()
    arcs: tuple = ()


def model_references(edges, frame):
    """Use only entire coplanar analytic lines/circles, including inner wires.

    A full circle's seam is not a geometric corner. Curves crossing the plane
    and parallel curves on other planes are deliberately excluded.
    """
    points, midpoints, lines, arcs = [], [], [], []
    def on_plane(point):
        return abs(sum((point[i]-frame.origin[i])*frame.normal[i] for i in range(3))) <= PLANE_TOLERANCE

    for index, edge in enumerate(edges):
        if BRep_Tool.Degenerated_s(edge):
            continue
        curve = BRepAdaptor_Curve(edge)
        kind = curve.GetType()
        if kind not in (GeomAbs_Line, GeomAbs_Circle):
            continue
        a, b = (curve.Value(t).Coord() for t in (curve.FirstParameter(), curve.LastParameter()))
        if not on_plane(a) or not on_plane(b):
            continue
        if kind == GeomAbs_Circle:
            circle = curve.Circle()
            normal = circle.Axis().Direction().Coord()
            if max(abs(sum(normal[i]*axis[i] for i in range(3))) for axis in (frame.u, frame.v)) > 1e-10:
                continue
            center = circle.Location().Coord()
            if not on_plane(center):
                continue
            points.append(ReferencePoint(frame.to_local(center), 'MODEL CENTER', index))
            local_center = frame.to_local(center)
            start = frame.to_local(a)
            angle = atan2(start[1]-local_center[1],start[0]-local_center[0])
            sense = 1 if sum(normal[i]*frame.normal[i] for i in range(3)) > 0 else -1
            arcs.append(ReferenceArc(local_center,circle.Radius(),angle,
                                     sense*(curve.LastParameter()-curve.FirstParameter()),index))
        local_a, local_b = frame.to_local(a), frame.to_local(b)
        if dist(a, b) > PLANE_TOLERANCE:
            points.extend(ReferencePoint(p, 'MODEL ENDPOINT', index) for p in (local_a, local_b))
        if kind == GeomAbs_Line:
            midpoints.append(ReferencePoint(tuple((a+b)/2 for a,b in zip(local_a,local_b)), 'MODEL MIDPOINT', index))
            lines.append(ReferenceLine(local_a, local_b, index))
    return ModelReferences(tuple(points), tuple(midpoints), tuple(lines), tuple(arcs))


def sketch_references(entities):
    """Expand completed parameter entities only, including construction curves."""
    points, midpoints, lines, arcs = [], [], [], []

    def line(a,b,identifier,segment):
        points.extend(ReferencePoint(p,'ENDPOINT',entity_id=identifier,segment=segment) for p in (a,b))
        midpoints.append(ReferencePoint(tuple((x+y)/2 for x,y in zip(a,b)),'SKETCH MIDPOINT',entity_id=identifier,segment=segment))
        lines.append(ReferenceLine(a,b,entity_id=identifier,segment=segment))

    for entity in entities:
        identifier = entity.id
        if isinstance(entity,Line):
            line(*entity.points,identifier,0)
        elif isinstance(entity,Rectangle):
            for index,(a,b) in enumerate(zip(entity.points,entity.points[1:])):
                line(a,b,identifier,index)
            center = tuple(sum(p[i] for p in entity.points[:4])/4 for i in range(2))
            points.append(ReferencePoint(center,'CENTER',entity_id=identifier))
        elif isinstance(entity,Circle):
            center = (entity.x,entity.y)
            points.append(ReferencePoint(center,'CENTER',entity_id=identifier))
            arcs.append(ReferenceArc(center,entity.radius,entity_id=identifier,segment=0))
        elif isinstance(entity,Slot):
            a,b = (entity.x,entity.y),entity.second_center
            angle = radians(entity.angle)
            normal = (-sin(angle)*entity.radius,cos(angle)*entity.radius)
            ends = [tuple(c[i]+sign*normal[i] for i in range(2)) for c,sign in ((a,-1),(b,-1),(b,1),(a,1))]
            line(ends[0],ends[1],identifier,0)
            line(ends[2],ends[3],identifier,2)
            points.extend(ReferencePoint(p,'CENTER',entity_id=identifier) for p in (a,b))
            arcs.extend((ReferenceArc(b,entity.radius,angle-pi/2,pi,entity_id=identifier,segment=1),
                         ReferenceArc(a,entity.radius,angle+pi/2,pi,entity_id=identifier,segment=3)))
    return ModelReferences(tuple(points),tuple(midpoints),tuple(lines),tuple(arcs))

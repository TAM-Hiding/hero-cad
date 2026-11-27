"""Transient analytic solid-edge targets in one sketch plane, in millimetres."""
from dataclasses import dataclass
from math import dist
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle


PLANE_TOLERANCE = 1e-7


@dataclass(frozen=True)
class ReferencePoint:
    point: tuple
    kind: str
    edge_index: int


@dataclass(frozen=True)
class ReferenceLine:
    a: tuple
    b: tuple
    edge_index: int

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
class ModelReferences:
    points: tuple = ()
    midpoints: tuple = ()
    lines: tuple = ()


def model_references(edges, frame):
    """Use only entire coplanar analytic lines/circles, including inner wires.

    A full circle's seam is not a geometric corner. Curves crossing the plane
    and parallel curves on other planes are deliberately excluded.
    """
    points, midpoints, lines = [], [], []
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
        local_a, local_b = frame.to_local(a), frame.to_local(b)
        if dist(a, b) > PLANE_TOLERANCE:
            points.extend(ReferencePoint(p, 'MODEL ENDPOINT', index) for p in (local_a, local_b))
        if kind == GeomAbs_Line:
            midpoints.append(ReferencePoint(tuple((a+b)/2 for a,b in zip(local_a,local_b)), 'MODEL MIDPOINT', index))
            lines.append(ReferenceLine(local_a, local_b, index))
    return ModelReferences(tuple(points), tuple(midpoints), tuple(lines))

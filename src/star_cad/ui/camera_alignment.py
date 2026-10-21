"""Read exact planar face geometry for a view operation; never change the model."""
from dataclasses import dataclass
from math import sqrt
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopAbs import TopAbs_REVERSED


@dataclass(frozen=True)
class FaceViewTarget:
    point: tuple
    normal: tuple
    up: tuple


def deterministic_up(normal):
    # Keep world Z upward, except near its poles, where world Y is stable.
    reference = (0., 0., 1.) if abs(normal[2]) < .95 else (0., 1., 0.)
    dot = sum(a*b for a, b in zip(reference, normal))
    up = tuple(reference[i]-dot*normal[i] for i in range(3))
    length = sqrt(sum(x*x for x in up))
    return tuple(x/length for x in up)


def planar_view_target(face, picked_point):
    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane:
        raise ValueError('Face alignment requires a planar face')
    # The adaptor includes the face location; orientation supplies outward sense.
    plane = surface.Plane()
    axis = plane.Axis().Direction()
    sign = -1 if face.Orientation() == TopAbs_REVERSED else 1
    normal = tuple(sign*axis.Coord(i) for i in (1, 2, 3))
    origin = tuple(plane.Location().Coord(i) for i in (1, 2, 3))
    distance = sum((picked_point[i]-origin[i])*normal[i] for i in range(3))
    point = tuple(picked_point[i]-distance*normal[i] for i in range(3))
    return FaceViewTarget(point, normal, deterministic_up(normal))

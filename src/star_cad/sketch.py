"""Exact stored sketch parameters and canonical origin-plane frames (millimetres)."""
from dataclasses import dataclass, field
from math import acos, atan2, ceil, cos, degrees, hypot, isfinite, pi, radians, sin
from uuid import UUID, uuid4


def new_id():
    return str(uuid4())


def valid_id(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('Expected a canonical UUID identifier')


def numbers(*values):
    for value in values:
        if type(value) not in (int, float) or not isfinite(value) or abs(value) > 1e6:
            raise ValueError('Coordinates must be finite numbers within ±1000000 mm/degrees')


@dataclass(frozen=True)
class PlaneFrame:
    name: str
    origin: tuple
    u: tuple
    v: tuple

    @property
    def normal(self):
        a, b = self.u, self.v
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

    def to_world(self, point):
        return tuple(self.origin[i] + point[0]*self.u[i] + point[1]*self.v[i] for i in range(3))

    def to_local(self, point):
        delta = tuple(point[i] - self.origin[i] for i in range(3))
        return tuple(sum(delta[i]*axis[i] for i in range(3)) for axis in (self.u, self.v))


PLANES = {
    'XY': PlaneFrame('XY', (0, 0, 0), (1, 0, 0), (0, 1, 0)),
    'XZ': PlaneFrame('XZ', (0, 0, 0), (1, 0, 0), (0, 0, 1)),
    'YZ': PlaneFrame('YZ', (0, 0, 0), (0, 1, 0), (0, 0, 1)),
}


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        valid_id(self.id)
        numbers(self.x1, self.y1, self.x2, self.y2)
        if hypot(self.x2-self.x1, self.y2-self.y1) < 1e-6:
            raise ValueError('A line must have nonzero length (at least 0.000001 mm)')

    @property
    def points(self):
        return ((self.x1, self.y1), (self.x2, self.y2))


@dataclass(frozen=True)
class Rectangle:
    x: float
    y: float
    width: float
    height: float
    angle: float = 0.0
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        valid_id(self.id)
        numbers(self.x, self.y, self.width, self.height, self.angle)
        if min(self.width, self.height) < 1e-6:
            raise ValueError('Rectangle width and height must be positive (at least 0.000001 mm)')
        for point in self.points:
            numbers(*point)

    @property
    def points(self):
        c, s = cos(radians(self.angle)), sin(radians(self.angle))
        a = (self.x, self.y)
        b = (a[0]+self.width*c, a[1]+self.width*s)
        d = (a[0]-self.height*s, a[1]+self.height*c)
        return (a, b, (b[0]+d[0]-a[0], b[1]+d[1]-a[1]), d, a)


def diagonal_rectangle(a, b):
    return Rectangle(min(a[0], b[0]), min(a[1], b[1]), abs(b[0]-a[0]), abs(b[1]-a[1]))


def edge_rectangle(a, b, cursor):
    dx, dy = b[0]-a[0], b[1]-a[1]
    width = hypot(dx, dy)
    if width < 1e-6:
        raise ValueError('First edge must have nonzero length')
    nx, ny = -dy/width, dx/width
    depth = (cursor[0]-a[0])*nx + (cursor[1]-a[1])*ny
    origin = a if depth >= 0 else (a[0]+depth*nx, a[1]+depth*ny)
    return Rectangle(*origin, width, abs(depth), degrees(atan2(dy, dx)))


def arc_points(x, y, radius, start, sweep):
    """Disposable display samples; curved model geometry remains analytic."""
    step = 2*acos(max(-1, 1-min(0.02/radius, 1)))
    count = max(16, min(4096, ceil(abs(sweep)/step)))
    return tuple((x+radius*cos(start+sweep*i/count), y+radius*sin(start+sweep*i/count))
                 for i in range(count+1))


@dataclass(frozen=True)
class Circle:
    x: float
    y: float
    radius: float
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        valid_id(self.id)
        numbers(self.x, self.y, self.radius)
        if self.radius < 1e-6:
            raise ValueError('Circle radius must be at least 0.000001 mm')
        numbers(self.x-self.radius, self.x+self.radius, self.y-self.radius, self.y+self.radius)

    @property
    def points(self):
        points = arc_points(self.x, self.y, self.radius, 0, 2*pi)
        return points[:-1] + (points[0],)


@dataclass(frozen=True)
class Slot:
    x: float
    y: float
    radius: float
    distance: float
    angle: float = 0.0
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        valid_id(self.id)
        numbers(self.x, self.y, self.radius, self.distance, self.angle)
        if min(self.radius, self.distance) < 1e-6:
            raise ValueError('Slot radius and center distance must be at least 0.000001 mm')
        a, b = (self.x, self.y), self.second_center
        for x, y in (a, b):
            numbers(x-self.radius, x+self.radius, y-self.radius, y+self.radius)

    @property
    def second_center(self):
        angle = radians(self.angle)
        return self.x+self.distance*cos(angle), self.y+self.distance*sin(angle)

    @property
    def points(self):
        angle = radians(self.angle)
        b = self.second_center
        right = arc_points(*b, self.radius, angle-pi/2, pi)
        left = arc_points(self.x, self.y, self.radius, angle+pi/2, pi)
        return (left[-1],) + right + left[:-1] + (left[-1],)


def slot_from_centers(a, b, radius):
    return Slot(*a, radius, hypot(b[0]-a[0], b[1]-a[1]),
                degrees(atan2(b[1]-a[1], b[0]-a[0])))


@dataclass(frozen=True)
class SketchParameters:
    plane: str
    entities: tuple = ()

    def __post_init__(self):
        if not isinstance(self.plane, str) or self.plane not in PLANES:
            raise ValueError('Sketch reference must be XY, XZ or YZ')
        if not isinstance(self.entities, tuple) or any(type(e) not in (Line, Rectangle, Circle, Slot) for e in self.entities):
            raise ValueError('Unsupported sketch entities')
        if len(self.entities) > 10000:
            raise ValueError('A sketch supports at most 10000 entities')
        if len({e.id for e in self.entities}) != len(self.entities):
            raise ValueError('Duplicate sketch entity IDs')

    @property
    def frame(self):
        return PLANES[self.plane]

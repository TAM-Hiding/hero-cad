"""Exact stored sketch parameters and canonical origin-plane frames (millimetres)."""
from dataclasses import dataclass, field
from math import acos, atan2, ceil, cos, degrees, hypot, isfinite, pi, radians, sin
from uuid import UUID, uuid4
import json


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

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise ValueError('Invalid frame name')
        for vector in (self.origin, self.u, self.v):
            if not isinstance(vector, tuple) or len(vector) != 3:
                raise ValueError('Frame vectors must be immutable triples')
            numbers(*vector)
        if any(abs(sum(x*x for x in a)-1) > 1e-10 for a in (self.u, self.v)) or abs(sum(a*b for a,b in zip(self.u,self.v))) > 1e-10:
            raise ValueError('Sketch frame must be orthonormal')

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


def decode_face_origin(token):
    """Canonical construction identity used by existing OCCT face lineage."""
    if not isinstance(token, str) or len(token) > 512:
        raise ValueError('Invalid face ancestry token')
    try:
        identifier, key = json.loads(token)
        valid_id(identifier)
        if isinstance(key, str):
            if key not in ('+X', '-X', '+Y', '-Y', '+Z', '-Z'):
                raise ValueError('Invalid box ancestry')
        elif isinstance(key, list) and len(key) == 3:
            face, boundary, segment = key
            if face == 'curve':
                valid_id(boundary)
                if segment not in ('circle', 'endA', 'endB'):
                    raise ValueError('Invalid curve ancestry')
            else:
                ref = FaceReference(identifier, face, boundary, segment)
                if ref.face not in ('start', 'end', 'side'):
                    raise ValueError('Ancestry must identify construction geometry')
            key = tuple(key)
        else:
            raise ValueError('Invalid face ancestry key')
        if json.dumps([identifier, key], separators=(',', ':')) != token:
            raise ValueError('Noncanonical face ancestry')
        return identifier, key
    except (TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError('Invalid face ancestry token') from error


@dataclass(frozen=True)
class FaceSupport:
    """Source-relative witness, not a second world-space sketch plane."""
    origins: tuple
    root: str
    anchor: tuple
    sense: int
    count: int

    def __post_init__(self):
        if (not isinstance(self.origins, tuple) or not 1 <= len(self.origins) <= 512
                or any(not isinstance(t, str) for t in self.origins)
                or self.origins != tuple(sorted(set(self.origins)))):
            raise ValueError('Expected sorted unique face ancestry')
        for token in self.origins:
            decode_face_origin(token)
        if self.root not in self.origins:
            raise ValueError('Reference root must belong to its ancestry')
        if not isinstance(self.anchor, tuple) or len(self.anchor) != 2:
            raise ValueError('Expected source-local attachment point')
        numbers(*self.anchor)
        if type(self.sense) is not int or self.sense not in (-1, 1):
            raise ValueError('Invalid attachment normal sense')
        if type(self.count) is not int or not 1 <= self.count <= 10000:
            raise ValueError('Invalid ancestral face multiplicity')


@dataclass(frozen=True)
class FaceReference:
    parent_id: str
    face: str
    boundary_id: str | None = None
    segment: str | None = None
    support: FaceSupport | None = None

    def __post_init__(self):
        valid_id(self.parent_id)
        if self.support is not None and (type(self.support) is not FaceSupport or self.face != 'evaluated'):
            raise ValueError('Ancestry support belongs only to evaluated faces')
        if self.face not in ('+X', '-X', '+Y', '-Y', '+Z', '-Z', 'start', 'end', 'side', 'evaluated'):
            raise ValueError('Unsupported semantic face')
        if self.face == 'side':
            valid_id(self.boundary_id)
            if self.segment not in ('edge0', 'edge1', 'edge2', 'edge3', 'tangent0', 'tangent1', 'line'):
                raise ValueError('Unsupported boundary segment')
        elif self.face == 'evaluated':
            if (self.boundary_id is not None or not isinstance(self.segment, str)
                    or len(self.segment) != 64 or any(c not in '0123456789abcdef' for c in self.segment)):
                raise ValueError('Invalid evaluated face identity')
        elif self.boundary_id is not None or self.segment is not None:
            raise ValueError('Only side faces have boundary segments')


@dataclass(frozen=True)
class SketchParameters:
    plane: str
    entities: tuple = ()
    attachment: FaceReference | None = None
    attached_frame: PlaneFrame | None = None

    def __post_init__(self):
        if self.attachment is None:
            if not isinstance(self.plane, str) or self.plane not in PLANES or self.attached_frame is not None:
                raise ValueError('Sketch reference must be XY, XZ or YZ')
        elif type(self.attachment) is not FaceReference or self.plane != 'FACE' or type(self.attached_frame) is not PlaneFrame:
            raise ValueError('Face sketch requires a semantic reference and frame')
        if not isinstance(self.entities, tuple) or any(type(e) not in (Line, Rectangle, Circle, Slot) for e in self.entities):
            raise ValueError('Unsupported sketch entities')
        if len(self.entities) > 10000:
            raise ValueError('A sketch supports at most 10000 entities')
        if len({e.id for e in self.entities}) != len(self.entities):
            raise ValueError('Duplicate sketch entity IDs')

    @property
    def frame(self):
        return self.attached_frame if self.attachment else PLANES[self.plane]

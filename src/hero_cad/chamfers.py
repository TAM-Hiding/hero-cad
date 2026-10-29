"""Single-edge native chamfers and conservative, body-scoped edge witnesses."""
from dataclasses import dataclass
from math import dist, pi
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRep import BRep_Tool
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from hero_cad.sketch import numbers, decode_face_origin
from hero_cad.face_history import subshapes, propagate, primitive_lineage
from hero_cad.booleans import OperationError, one_solid
from hero_cad.geometry import volume


@dataclass(frozen=True)
class EdgeReference:
    """Checked line/circle/arc geometry and two adjacent construction ancestries.

    The owning feature UUID is ChamferParameters.target_id. No enumeration index,
    nearest-edge search or changed-length transport is a persistent identity.
    """
    endpoints: tuple
    neighbors: tuple
    curve_type: str = 'line'
    center: tuple | None = None
    radius: float | None = None
    axis: tuple | None = None
    midpoint: tuple | None = None

    def __post_init__(self):
        if self.curve_type not in ('line', 'circle', 'arc'):
            raise ValueError('Expected line, circle or circular arc geometry')
        if not isinstance(self.endpoints, tuple):
            raise ValueError('Expected immutable edge endpoints')
        if self.curve_type == 'circle':
            if self.endpoints or self.midpoint is not None:
                raise ValueError('A full circle must not store a seam or midpoint')
        else:
            if len(self.endpoints) != 2:
                raise ValueError('Expected two immutable edge endpoints')
            for point in self.endpoints:
                checked_point(point)
            if self.endpoints != tuple(sorted(self.endpoints)) or dist(*self.endpoints) < 1e-6:
                raise ValueError('Expected canonical distinct edge endpoints')
        if self.curve_type == 'line':
            if any(v is not None for v in (self.center, self.radius, self.axis, self.midpoint)):
                raise ValueError('A straight edge cannot contain circular geometry')
        else:
            checked_point(self.center)
            checked_point(self.axis)
            numbers(self.radius)
            if self.radius < 1e-6:
                raise ValueError('Expected a positive circle radius')
            if (abs(sum(x*x for x in self.axis)-1) > 2e-9
                    or self.axis != canonical_axis(self.axis)):
                raise ValueError('Expected a canonical unit circle axis')
            if self.curve_type == 'arc':
                checked_point(self.midpoint)
                tolerance = max(2e-8, self.radius * 3e-9)
                for point in (*self.endpoints, self.midpoint):
                    delta = tuple(x-c for x,c in zip(point, self.center))
                    if (abs(dist(point, self.center)-self.radius) > tolerance
                            or abs(sum(x*n for x,n in zip(delta, self.axis))) > tolerance):
                        raise ValueError('Arc points must lie on the referenced circle')
                if (min(dist(self.midpoint, p) for p in self.endpoints) < 1e-6
                        or abs(dist(self.midpoint, self.endpoints[0])
                               - dist(self.midpoint, self.endpoints[1])) > tolerance):
                    raise ValueError('Expected a circular arc midpoint')
        if (not isinstance(self.neighbors, tuple) or len(self.neighbors) != 2
                or any(not isinstance(tokens, tuple) or not 1 <= len(tokens) <= 512
                       or any(not isinstance(t, str) for t in tokens)
                       or tokens != tuple(sorted(set(tokens))) for tokens in self.neighbors)
                or self.neighbors != tuple(sorted(self.neighbors))):
            raise ValueError('Expected two canonical adjacent face ancestries')
        for tokens in self.neighbors:
            for token in tokens:
                decode_face_origin(token)


def checked_point(point):
    if not isinstance(point, tuple) or len(point) != 3:
        raise ValueError('Expected an immutable coordinate triple')
    numbers(*point)


def rounded_point(point):
    return tuple(round(float(x), 9) for x in point.Coord())


def canonical_axis(axis):
    # Largest component gives a stable sign even when another component is tiny.
    axis = tuple(round(float(x), 9) for x in axis)
    dominant = max(range(3), key=lambda i: abs(axis[i]))
    return tuple(-x for x in axis) if axis[dominant] < 0 else axis


def edge_reference(edge, lineage):
    edge = TopoDS.Edge_s(edge)
    curve = BRepAdaptor_Curve(edge)
    kind = curve.GetType()
    if kind not in (GeomAbs_Line, GeomAbs_Circle):
        raise OperationError('Chamfer supports one straight, circular or circular-arc edge; ellipses and freeform curves are unsupported')
    first, last = curve.FirstParameter(), curve.LastParameter()
    points = tuple(sorted(rounded_point(curve.Value(t)) for t in (first, last)))
    geometry = {}
    if kind == GeomAbs_Circle:
        circle = curve.Circle()
        span = last-first
        if not 0 < span <= 2*pi+1e-12:
            raise OperationError('Chamfer requires a single circular turn or partial arc')
        full = abs(span-2*pi) <= 1e-12 and BRep_Tool.IsClosed_s(edge)
        geometry = dict(curve_type='circle' if full else 'arc',
                        center=rounded_point(circle.Location()), radius=round(circle.Radius(), 9),
                        axis=canonical_axis(circle.Axis().Direction().Coord()),
                        midpoint=None if full else rounded_point(curve.Value((first+last)/2)))
        if full:
            points = ()  # A full circle has no persistent seam/start parameter.
    adjacent = [tuple(sorted(tokens)) for face, tokens in lineage
                if any(edge.IsSame(candidate) for candidate in subshapes(face, TopAbs_EDGE))]
    if len(adjacent) != 2 or any(not tokens for tokens in adjacent):
        raise OperationError('Chamfer requires a manifold edge with two identified adjacent faces')
    try:
        return EdgeReference(points, tuple(sorted(adjacent)), **geometry)
    except ValueError as error:
        raise OperationError(f'Unsupported chamfer edge geometry: {error}') from error


def edge_description(reference):
    if reference.curve_type == 'line':
        return 'Straight edge endpoints: ' + str(reference.endpoints)
    text = f'{"Circle" if reference.curve_type == "circle" else "Circular arc"}: center {reference.center}, radius {reference.radius} mm, axis {reference.axis}'
    if reference.curve_type == 'arc':
        text += f'; endpoints {reference.endpoints}, midpoint {reference.midpoint}'
    return text


def resolve_edge(reference, body, lineage):
    matches = []
    for raw in subshapes(body, TopAbs_EDGE):
        edge = TopoDS.Edge_s(raw)
        try:
            candidate = edge_reference(edge, lineage)
        except OperationError:
            continue
        if candidate == reference:
            matches.append(edge)
    if len(matches) != 1:
        reason = 'ambiguous' if matches else 'missing or changed'
        raise OperationError(f'Unresolved chamfer edge: {reason}; automatic edge substitution refused')
    return matches[0]


def make_chamfer(parameters, body, lineage, identifier):
    """Build on candidate geometry; return validated solid and existing lineage."""
    edge = resolve_edge(parameters.edge, body, lineage)
    try:
        one_solid(body)
        builder = BRepFilletAPI_MakeChamfer(body)
        builder.Add(parameters.distance, edge)
        # OCCT automatically propagates tangent contours. PR35 promises exactly
        # one edge, so reject such a contour rather than chamfer extra edges.
        if builder.NbContours() != 1 or builder.NbEdges(1) != 1:
            raise OperationError('OCCT requires tangent-connected edges; automatic edge-chain propagation is not supported')
        builder.Build()
        if not builder.IsDone() or builder.Shape().IsNull():
            raise OperationError('OCCT could not build this chamfer; reduce the distance or choose another eligible edge')
        result = one_solid(builder.Shape())
        if abs(volume(result)-volume(body)) <= max(1e-15, volume(body)*1e-12):
            raise OperationError('Chamfer did not remove or add measurable material; choose another edge or distance')
        generated = [TopoDS.Face_s(f) for f in builder.Generated(edge) if f.ShapeType() == TopAbs_FACE]
        sources = {('bevel', None, None): generated[0]} if len(generated) == 1 else {}
        ancestry = propagate(builder, result, lineage)
        # Seed only the native builder's generated bevel face. Existing faces
        # retain Modified/Generated ancestry through the established path.
        seeds = primitive_lineage(identifier, sources)
        ancestry = tuple((f, tokens | frozenset(t for face, ts in seeds if f.IsSame(face) for t in ts))
                         for f, tokens in ancestry)
        return result, ancestry, sources
    except OperationError:
        raise
    except Exception as error:
        raise OperationError(f'OCCT chamfer failed: {error}') from error

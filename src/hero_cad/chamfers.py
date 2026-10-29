"""Explicit-edge native chamfers and conservative, body-scoped edge witnesses."""
from dataclasses import dataclass
from math import dist, pi, cos
from hashlib import sha256
import json
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

    The owning feature UUID is ChamferParameters.target_id. No enumeration index
    or nearest-edge search is used. Geometry remains the original witness; two
    unmixed principal box faces may resolve a unique moved straight edge.
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


def edge_neighbors(edge, lineage):
    return tuple(sorted(tuple(sorted(tokens)) for face, tokens in lineage
                        if any(edge.IsSame(candidate) for candidate in subshapes(face, TopAbs_EDGE))))


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
    adjacent = edge_neighbors(edge, lineage)
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


def edge_sort_key(reference):
    def point(values):
        return tuple(0.0 if x == 0 else x for x in values) if values else ()
    return (reference.curve_type, point(reference.center), reference.radius or 0.,
            point(reference.axis), tuple(point(p) for p in reference.endpoints),
            point(reference.midpoint), reference.neighbors)


def bevel_segment(reference):
    return sha256(json.dumps(edge_sort_key(reference), separators=(',', ':')).encode()).hexdigest()


TANGENT_ANGLE = 1e-5  # radians; ~0.00057 degrees, safely above numerical noise.
CHAIN_ENDPOINT_TOLERANCE = 1e-7  # Existing kernel/profile tolerance, in mm.


def tangent_chain(seed, body, lineage):
    """Transient analytic endpoint traversal; never runs a modeling builder.

    Tangents point away from each endpoint, so continuation requires opposite
    directions. Compute choices before visiting; a loop cannot hide a branch.
    """
    entries = []
    for raw in subshapes(body, TopAbs_EDGE):
        edge = TopoDS.Edge_s(raw)
        try:
            edge_reference(edge, lineage)
            curve = BRepAdaptor_Curve(edge)
            ends = []
            for parameter, sense in ((curve.FirstParameter(), 1), (curve.LastParameter(), -1)):
                tangent = curve.DN(parameter, 1)
                if tangent.Magnitude() < 1e-12:
                    raise OperationError('Undefined endpoint tangent')
                tangent.Normalize()
                ends.append((tuple(curve.Value(parameter).Coord()),
                             tuple(sense*x for x in tangent.Coord())))
            entries.append((edge, ends))
        except (ValueError, RuntimeError):
            continue  # Unsupported curves/non-manifold edges are boundaries.
    initial = [i for i,(edge,_) in enumerate(entries) if edge.IsSame(seed)]
    if len(initial) != 1:
        raise OperationError('Select one eligible current edge to expand its tangent chain')
    visited, pending = set(), initial[:]
    while pending:
        i = pending.pop()
        if i in visited:
            continue
        visited.add(i)
        if len(visited) > 256:
            raise OperationError('Tangent chain exceeds the 256-edge chamfer limit')
        for point, tangent in entries[i][1]:
            choices = set()
            for j,(_,ends) in enumerate(entries):
                if i == j:
                    continue
                if any(dist(point,p) <= CHAIN_ENDPOINT_TOLERANCE
                       and sum(a*b for a,b in zip(tangent,t)) <= -cos(TANGENT_ANGLE)
                       for p,t in ends):
                    choices.add(j)
            if len(choices) > 1:
                raise OperationError('Ambiguous tangent-chain junction; selection unchanged. Select edges manually.')
            pending.extend(choices - visited)
    return tuple(entries[i][0] for i in sorted(visited))


def base_edge_identity(reference):
    """Only two unmixed principal faces of one box qualify for transport.

    A Boolean/chamfer face union, bevel, extrusion cap or same-axis face pair
    is not proof of an exterior box edge. No new persistent identity is stored.
    """
    if reference.curve_type != 'line' or any(len(tokens) != 1 for tokens in reference.neighbors):
        return None
    origins = [decode_face_origin(tokens[0]) for tokens in reference.neighbors]
    (owner, a), (other, b) = origins
    if (owner != other or not isinstance(a, str) or not isinstance(b, str)
            or a[1] == b[1]):
        return None
    fixed = ['XYZ'.index(face[1]) for face in (a, b)]
    if any(reference.endpoints[0][axis] != reference.endpoints[1][axis] for axis in fixed):
        return None  # Contradictory curve direction, even if ancestry looks eligible.
    return reference.neighbors


def resolve_edges(references, body, lineage):
    # Classify the target once per collection; this is transient query data,
    # not a geometry cache or a different reference-resolution policy.
    candidates, semantic_candidates = {}, {}
    for raw in subshapes(body, TopAbs_EDGE):
        edge = TopoDS.Edge_s(raw)
        try:
            candidate = edge_reference(edge, lineage)
        except OperationError:
            candidate = None
        neighbors = candidate.neighbors if candidate is not None else edge_neighbors(edge, lineage)
        semantic_candidates.setdefault(neighbors, []).append((candidate, edge))
        if candidate is not None:
            candidates.setdefault(candidate, []).append(edge)
    result = []
    for reference in references:
        matches = candidates.get(reference, ())
        if not matches and base_edge_identity(reference) is not None:
            # Search only this explicit target. Count the whole ancestry pair
            # before filtering curve type: contradictory topology must not turn
            # into an apparently unique line candidate.
            semantic = semantic_candidates.get(reference.neighbors, ())
            if (len(semantic) == 1 and semantic[0][0] is not None
                    and base_edge_identity(semantic[0][0]) == base_edge_identity(reference)):
                matches = (semantic[0][1],)
            elif len(semantic) > 1:
                raise OperationError('Unresolved chamfer edge: ambiguous semantic Base Model edge; automatic edge substitution refused')
        if len(matches) != 1:
            reason = 'ambiguous' if matches else 'missing or changed'
            raise OperationError(f'Unresolved chamfer edge: {reason}; automatic edge substitution refused')
        if any(matches[0].IsSame(edge) for edge in result):
            raise OperationError('Duplicate resolved chamfer edges')
        result.append(matches[0])
    return tuple(result)


def resolve_edge(reference, body, lineage):
    return resolve_edges((reference,), body, lineage)[0]


def make_chamfer(parameters, body, lineage, identifier):
    """Build on candidate geometry; return validated solid and existing lineage."""
    edges = resolve_edges(parameters.edges, body, lineage)
    if any(a.IsSame(b) for i,a in enumerate(edges) for b in edges[i+1:]):
        raise OperationError('Duplicate resolved chamfer edges')
    try:
        one_solid(body)
        builder = BRepFilletAPI_MakeChamfer(body)
        for edge in edges:
            if builder.Contour(edge) == 0:
                builder.Add(parameters.distance, edge)
        covered = [builder.Edge(i,j) for i in range(1,builder.NbContours()+1)
                   for j in range(1,builder.NbEdges(i)+1)]
        if any(not any(edge.IsSame(selected) for selected in edges) for edge in covered):
            raise OperationError('OCCT requires additional tangent-connected edges; edge-chain propagation requires explicit selection. Use Select Tangent Chain or select the full contour manually.')
        if (not covered or any(not any(edge.IsSame(item) for item in covered) for edge in edges)):
            raise OperationError('OCCT could not include every selected chamfer edge; no partial chamfer applied')
        builder.Build()
        if not builder.IsDone() or builder.Shape().IsNull():
            raise OperationError('OCCT could not build this chamfer; reduce the distance or choose another eligible edge')
        result = one_solid(builder.Shape())
        if abs(volume(result)-volume(body)) <= max(1e-15, volume(body)*1e-12):
            raise OperationError('Chamfer did not remove or add measurable material; choose another edge or distance')
        sources = {}
        generated = [(reference, [TopoDS.Face_s(f) for f in builder.Generated(edge)
                                  if f.ShapeType() == TopAbs_FACE])
                     for reference,edge in zip(parameters.edges,edges)]
        for reference, faces in generated:
            # Publish only unique native generated faces. Multi-edge roots use
            # the persistent input witness, never an OCCT enumeration index.
            if len(faces) == 1 and not any(faces[0].IsSame(other) for ref,others in generated
                                          if ref != reference for other in others):
                segment = None if len(edges) == 1 else bevel_segment(reference)
                sources[('bevel', None, segment)] = faces[0]
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


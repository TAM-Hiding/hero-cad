"""Single-edge native chamfers and conservative, body-scoped edge witnesses."""
from dataclasses import dataclass
from math import dist
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
from OCP.GeomAbs import GeomAbs_Line
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from hero_cad.sketch import numbers, decode_face_origin
from hero_cad.face_history import subshapes, propagate, primitive_lineage
from hero_cad.booleans import OperationError, one_solid
from hero_cad.geometry import volume


@dataclass(frozen=True)
class EdgeReference:
    """Exact straight segment and its two adjacent construction ancestries.

    The owning feature UUID is ChamferParameters.target_id. No enumeration index,
    nearest-edge search or changed-length transport is a persistent identity.
    """
    endpoints: tuple
    neighbors: tuple

    def __post_init__(self):
        if (not isinstance(self.endpoints, tuple) or len(self.endpoints) != 2
                or any(not isinstance(p, tuple) or len(p) != 3 for p in self.endpoints)):
            raise ValueError('Expected two immutable edge endpoints')
        for point in self.endpoints:
            numbers(*point)
        if self.endpoints != tuple(sorted(self.endpoints)) or dist(*self.endpoints) < 1e-6:
            raise ValueError('Expected a canonical nonzero straight edge')
        if (not isinstance(self.neighbors, tuple) or len(self.neighbors) != 2
                or any(not isinstance(tokens, tuple) or not 1 <= len(tokens) <= 512
                       or any(not isinstance(t, str) for t in tokens)
                       or tokens != tuple(sorted(set(tokens))) for tokens in self.neighbors)
                or self.neighbors != tuple(sorted(self.neighbors))):
            raise ValueError('Expected two canonical adjacent face ancestries')
        for tokens in self.neighbors:
            for token in tokens:
                decode_face_origin(token)


def edge_reference(edge, lineage):
    edge = TopoDS.Edge_s(edge)
    curve = BRepAdaptor_Curve(edge)
    if curve.GetType() != GeomAbs_Line:
        raise OperationError('Chamfer supports one straight edge; curved edges are not supported')
    points = tuple(sorted(tuple(round(float(x), 9) for x in curve.Value(t).Coord())
                          for t in (curve.FirstParameter(), curve.LastParameter())))
    adjacent = [tuple(sorted(tokens)) for face, tokens in lineage
                if any(edge.IsSame(candidate) for candidate in subshapes(face, TopAbs_EDGE))]
    if len(adjacent) != 2 or any(not tokens for tokens in adjacent):
        raise OperationError('Chamfer requires a manifold edge with two identified adjacent faces')
    return EdgeReference(points, tuple(sorted(adjacent)))


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
            raise OperationError('Chamfer requires a single non-tangent edge; edge-chain propagation is not supported')
        builder.Build()
        if not builder.IsDone() or builder.Shape().IsNull():
            raise OperationError('OCCT could not build this chamfer; reduce the distance or choose another straight edge')
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

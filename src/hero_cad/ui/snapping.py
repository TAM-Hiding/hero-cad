"""Local construction-point snapping with projected screen-distance acceptance."""
from dataclasses import dataclass
from math import floor, hypot
from itertools import chain
from hero_cad.sketch import Circle, Line, Slot


@dataclass(frozen=True)
class SnapResult:
    point: tuple
    target: str = 'FREE'
    edge_index: int | None = None
    entity_id: str | None = None
    segment: int | None = None


def center_targets(entities):
    """Exact local centers from parameters, independent of display tessellation."""
    for entity in entities:
        if isinstance(entity, (Circle, Slot)):
            yield (entity.x, entity.y)
        if isinstance(entity, Slot):
            yield entity.second_center


def construction_endpoints(entities):
    for entity in entities:
        if isinstance(entity, Line) and entity.construction:
            yield from entity.points


def snap_point(point, cursor, project, spacing, *, grid=True, origin=True, centers=(), endpoints=(),
               tolerance=8, model=None, previous=None, sketch_centers=True):
    """project(local_uv) returns screen XY or None for a clipped target.

    No feature/topology references or document edits are created here. The local
    (0,0) is intentional: future offset/attached frames supply their own origin.
    """
    def distance(local):
        projected = project(local)
        return hypot(projected[0]-cursor[0], projected[1]-cursor[1]) if projected else float('inf')

    if model is not None:
        # Choose the nearest precise point. Equal candidates keep traversal order.
        # A two-logical-pixel preference retains an acquired point until another
        # is materially closer, without extending the acquisition radius.
        def choose(candidates):
            accepted = [c for c in candidates if distance(c.point) <= tolerance]
            return min(accepted, key=lambda c: distance(c.point) -
                       (tolerance/4 if c == previous else 0) -
                       (tolerance/4 if c.target in ('ORIGIN','CENTER','MODEL CENTER') else 0), default=None)

        precise = [SnapResult((0., 0.), 'ORIGIN')] if origin else []
        precise.extend(SnapResult(p, 'CENTER') for p in centers)
        precise.extend(SnapResult(p, 'ENDPOINT') for p in endpoints)
        precise.extend(SnapResult(p.point,p.kind,p.edge_index,p.entity_id,p.segment) for p in model.points
                       if sketch_centers or p.entity_id is None or p.kind != 'CENTER')
        result = choose(precise)
        if result is None:
            result = choose(SnapResult(p.point,p.kind,p.edge_index,p.entity_id,p.segment) for p in model.midpoints)
        if result is None:
            edge_points = ((line, line.nearest(cursor, project)) for line in model.lines)
            curve_points = ((arc,arc.nearest(cursor,project)) for arc in model.arcs)
            straight = (SnapResult(p,'SKETCH EDGE' if line.entity_id else 'MODEL EDGE',line.edge_index,line.entity_id,line.segment)
                        for line,p in edge_points if p is not None)
            curved = (SnapResult(p,'SKETCH CURVE' if arc.entity_id else 'MODEL CURVE',arc.edge_index,arc.entity_id,arc.segment)
                      for arc,p in curve_points if p is not None)
            result = choose(chain(straight,curved))
        if result is not None:
            return result
        # Precise targets were already tested. Fall through to the same grid.
        origin, centers, endpoints = False, (), ()

    if origin and distance((0., 0.)) <= tolerance:
        return SnapResult((0., 0.), 'ORIGIN')
    candidate = min(centers, key=distance, default=None)
    if candidate is not None and distance(candidate) <= tolerance:
        return SnapResult(candidate, 'CENTER')
    candidate = min(endpoints, key=distance, default=None)
    if candidate is not None and distance(candidate) <= tolerance:
        return SnapResult(candidate, 'ENDPOINT')
    if grid:
        indices = tuple(floor(c/spacing + 0.5) for c in point)
        # Nearby lattice candidates account for oblique projection/shear.
        candidates = [( (indices[0]+i)*spacing, (indices[1]+j)*spacing)
                      for i in (-1, 0, 1) for j in (-1, 0, 1)]
        candidate = min(candidates, key=distance)
        if distance(candidate) <= tolerance:
            return SnapResult(candidate, 'GRID')
    return SnapResult(point)

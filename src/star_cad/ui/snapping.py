"""Local construction-point snapping with projected screen-distance acceptance."""
from dataclasses import dataclass
from math import floor, hypot


@dataclass(frozen=True)
class SnapResult:
    point: tuple
    target: str = 'FREE'


def snap_point(point, cursor, project, spacing, *, grid=True, origin=True, tolerance=8):
    """project(local_uv) returns screen XY or None for a clipped target.

    No feature/topology references or document edits are created here. The local
    (0,0) is intentional: future offset/attached frames supply their own origin.
    """
    def distance(local):
        projected = project(local)
        return hypot(projected[0]-cursor[0], projected[1]-cursor[1]) if projected else float('inf')

    if origin and distance((0., 0.)) <= tolerance:
        return SnapResult((0., 0.), 'ORIGIN')
    if grid:
        indices = tuple(floor(c/spacing + 0.5) for c in point)
        # Nearby lattice candidates account for oblique projection/shear.
        candidates = [( (indices[0]+i)*spacing, (indices[1]+j)*spacing)
                      for i in (-1, 0, 1) for j in (-1, 0, 1)]
        candidate = min(candidates, key=distance)
        if distance(candidate) <= tolerance:
            return SnapResult(candidate, 'GRID')
    return SnapResult(point)

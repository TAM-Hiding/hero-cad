"""Simple closed line components; no trimming, constraints or stored healing."""
from math import dist
from uuid import NAMESPACE_URL, uuid5
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
from hero_cad.sketch import Line

# Absolute millimetres: same scale as OCCT's confusion/region tolerance.
# Far below the 1e-6 mm minimum line length. Never depends on zoom or pixels.
CONNECT_TOLERANCE = 1e-7


def loop_id(identifiers):
    return str(uuid5(NAMESPACE_URL, 'hero-cad:line-loop:' + ','.join(sorted(identifiers))))


def point_distance(p, a, b):
    delta = (b[0]-a[0], b[1]-a[1])
    t = max(0., min(1., sum((p[i]-a[i])*delta[i] for i in (0, 1))/sum(x*x for x in delta)))
    return dist(p, tuple(a[i]+t*delta[i] for i in (0, 1)))


def segment_distance(a, b, c, d):
    cross = lambda u, v: u[0]*v[1]-u[1]*v[0]
    ab, cd, ac = tuple(b[i]-a[i] for i in (0, 1)), tuple(d[i]-c[i] for i in (0, 1)), tuple(c[i]-a[i] for i in (0, 1))
    denominator = cross(ab, cd)
    if denominator:
        t, u = cross(ac, cd)/denominator, cross(ac, ab)/denominator
        if 0 <= t <= 1 and 0 <= u <= 1:
            return 0.
    return min(point_distance(a, c, d), point_distance(b, c, d),
               point_distance(c, a, b), point_distance(d, a, b))


def line_boundaries(sketch):
    """Return (stable key, wire, member UUIDs) loops and unfilled open edges.

    Only degree-two simple cycles qualify. Unsupported branch/cross/overlap
    arrangements reject profile analysis explicitly, so holes are never lost.
    Endpoints within kernel tolerance share topology only: original line
    parameters and analytic edge curves are never moved or written back.
    """
    lines = sorted((e for e in sketch.entities if isinstance(e, Line)), key=lambda e: e.id)
    points = [p for line in lines for p in line.points]
    parents = list(range(len(points)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for i, p in enumerate(points):
        for j in range(i):
            if dist(p, points[j]) <= CONNECT_TOLERANCE:
                parents[root(i)] = root(j)
    groups = {}
    for i in range(len(points)):
        groups.setdefault(root(i), []).append(i)
    if any(dist(points[a], points[b]) > CONNECT_TOLERANCE
           for group in groups.values() for a in group for b in group):
        raise ValueError('Ambiguous chained endpoint tolerance; endpoints are not all coincident')
    nodes = [(root(2*i), root(2*i+1)) for i in range(len(lines))]
    adjacent = {}
    for i, pair in enumerate(nodes):
        if pair[0] == pair[1]:
            raise ValueError('Degenerate line profile')
        for node in pair:
            adjacent.setdefault(node, []).append(i)
    if any(len(edges) > 2 for edges in adjacent.values()):
        raise ValueError('Branched/shared-boundary line arrangements are unsupported; use separate simple loops')
    for i, line in enumerate(lines):
        for j in range(i):
            shared = set(nodes[i]).intersection(nodes[j])
            other = lines[j]
            if len(shared) == 2:
                raise ValueError('Overlapping or duplicate line segments cannot define a profile')
            if shared:
                node = next(iter(shared))
                a = line.points[1-nodes[i].index(node)]
                b = other.points[1-nodes[j].index(node)]
                if min(point_distance(a, *other.points), point_distance(b, *line.points)) <= CONNECT_TOLERANCE:
                    raise ValueError('Overlapping line segments cannot define a profile')
            elif segment_distance(*line.points, *other.points) <= CONNECT_TOLERANCE:
                raise ValueError('Crossing/touching line segments require trimming; use separate simple loops')
    def edge(index, reverse=False):
        a, b = lines[index].points[::(-1 if reverse else 1)]
        result = BRepBuilderAPI_MakeEdge(gp_Pnt(*sketch.frame.to_world(a)), gp_Pnt(*sketch.frame.to_world(b))).Edge()
        vertices = TopExp_Explorer(result, TopAbs_VERTEX)
        while vertices.More():
            BRep_Builder().UpdateVertex(TopoDS.Vertex_s(vertices.Current()), CONNECT_TOLERANCE)
            vertices.Next()
        return result
    remaining, loops, open_edges = set(range(len(lines))), [], []
    while remaining:
        seed = min(remaining)
        component, pending = set(), [seed]
        while pending:
            i = pending.pop()
            if i in component:
                continue
            component.add(i)
            pending.extend(j for n in nodes[i] for j in adjacent[n] if j not in component)
        remaining.difference_update(component)
        if any(len(adjacent[n]) != 2 for i in component for n in nodes[i]):
            open_edges.extend(edge(i) for i in sorted(component))
            continue
        current, node, ordered = seed, nodes[seed][0], []
        while len(ordered) < len(component):
            reverse = nodes[current][1] == node
            ordered.append((current, reverse))
            node = nodes[current][0 if reverse else 1]
            current = next(j for j in adjacent[node] if j != current)
        polygon = [lines[i].points[1 if reverse else 0] for i, reverse in ordered]
        anchor = polygon[0]
        relative = [(p[0]-anchor[0], p[1]-anchor[1]) for p in polygon]
        area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(relative, relative[1:]+relative[:1]))/2
        if abs(area) <= CONNECT_TOLERANCE**2:
            raise ValueError('Closed line profile has no usable area')
        if area < 0:
            ordered = [(i, not reverse) for i, reverse in reversed(ordered)]
        builder = BRepBuilderAPI_MakeWire()
        for i, reverse in ordered:
            builder.Add(edge(i, reverse))
        if not builder.IsDone() or not builder.Wire().Closed():
            raise ValueError('OCCT could not connect the closed line profile within kernel tolerance')
        members = tuple(sorted(lines[i].id for i in component))
        loops.append((loop_id(members), builder.Wire(), members))
    return loops, open_edges

"""Analytic bounded cells from an OCCT face split and source-edge history."""
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from uuid import NAMESPACE_URL, uuid5

from OCP.Bnd import Bnd_Box
from OCP.BOPAlgo import BOPAlgo_Splitter
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_REVERSED, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pln, gp_Pnt, gp_Trsf, gp_Vec

from hero_cad.geometry import make_sketch
from hero_cad.line_profiles import CONNECT_TOLERANCE, loop_id
from hero_cad.sketch import Line, SketchParameters

MAX_SEGMENTS = 4096
MAX_CELLS = 1024
MAX_EDGE_PAIRS = 8192


@dataclass(frozen=True)
class Cell:
    identifier: str
    face: object
    sources: tuple
    whole_loops: tuple  # Legacy loop IDs if no boundary was split or shared.


def shapes(shape, kind, cast):
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        yield cast(explorer.Current())
        explorer.Next()


def wire_edges(wire):
    explorer = BRepTools_WireExplorer(wire)
    while explorer.More():
        yield explorer.Current()
        explorer.Next()


def source_edges(entities):
    for entity in sorted(entities, key=lambda e: e.id):
        shape = make_sketch(SketchParameters('XY', (entity,)))
        wire = next(shapes(shape, TopAbs_WIRE, TopoDS.Wire_s), None)
        edges = wire_edges(wire) if wire is not None else shapes(shape, TopAbs_EDGE, TopoDS.Edge_s)
        for index, edge in enumerate(edges):
            yield (entity.id, index), edge


def edge_history(splitter, inputs):
    """Map split edges to sorted source curve/segment identities and endpoint events."""
    edges, vertices = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    origins, incidents, ends, totals = defaultdict(list), defaultdict(dict), {}, {}
    for source, edge in inputs:
        pieces = tuple(splitter.Modified(edge)) or (edge,)
        original = BRepAdaptor_Curve(edge)
        curve = BRep_Tool.Curve_s(edge, 0., 0.)
        records = []
        for raw in pieces:
            piece = TopoDS.Edge_s(raw)
            index = edges.Add(piece)
            if edges.Extent() > MAX_SEGMENTS:
                raise ValueError(f'Sketch arrangement exceeds {MAX_SEGMENTS} split edges')
            segment = BRepAdaptor_Curve(piece)
            mid = (segment.FirstParameter() + segment.LastParameter()) / 2
            projection = GeomAPI_ProjectPointOnCurve(segment.Value(mid), curve,
                                                     original.FirstParameter(), original.LastParameter())
            if not projection.NbPoints() or projection.LowerDistance() > CONNECT_TOLERANCE:
                raise ValueError('Cannot trace a split edge to its source curve')
            parameter = projection.LowerDistanceParameter()
            point, tangent, source_tangent = gp_Pnt(), gp_Vec(), gp_Vec()
            segment.D1(mid, point, tangent)
            original.D1(parameter, point, source_tangent)
            sense = 1 if tangent.Dot(source_tangent) > 0 else -1
            records.append((parameter, index, sense))
            # Use the segment's underlying parametric direction for both ends.
            forward = TopoDS.Edge_s(piece.Oriented(TopAbs_FORWARD))
            pair = (vertices.Add(TopExp.FirstVertex_s(forward)), vertices.Add(TopExp.LastVertex_s(forward)))
            ends[index] = pair
            for vertex, parameter in zip(pair, (segment.FirstParameter(), segment.LastParameter())):
                segment.D1(parameter, point, tangent)
                tangent.Normalize()
                incidents[vertex][source] = (sense*tangent.X(), sense*tangent.Y())
        totals[source] = len(records)
        for ordinal, (_, index, sense) in enumerate(sorted(records)):
            origins[index].append((source, ordinal, len(records), sense))
    # Distinguish the two crossing branches of the same source pair without
    # freezing their coordinates. Opposite crossings have opposite signs.
    events = {}
    for index, incident in incidents.items():
        keys = tuple(sorted(incident))
        directions = []
        for a, b in combinations(keys, 2):
            u, v = incident[a], incident[b]
            cross = u[0]*v[1] - u[1]*v[0]
            directions.append(0 if abs(cross) < 1e-9 else 1 if cross > 0 else -1)
        events[index] = keys, tuple(directions)
    return edges, origins, ends, events, totals


def analytic_ends(edge):
    curve = BRepAdaptor_Curve(edge)
    first = curve.Value(curve.FirstParameter())
    last = curve.Value(curve.LastParameter())
    return (last, first) if edge.Orientation() == TopAbs_REVERSED else (first, last)


def arrangement(entities, frame):
    """Split a finite carrier, drop its exterior, and retain valid analytic cells."""
    inputs = tuple(source_edges(entities))
    if not inputs:
        return ()
    bounds, boxes, pairs = Bnd_Box(), [], 0
    for _, edge in inputs:
        edge_box = Bnd_Box()
        BRepBndLib.AddOptimal_s(edge, edge_box, False, False)
        edge_box.SetGap(CONNECT_TOLERANCE)
        pairs += sum(not edge_box.IsOut(other) for other in boxes)
        if pairs > MAX_EDGE_PAIRS:
            raise ValueError(f'Sketch arrangement exceeds {MAX_EDGE_PAIRS} potentially intersecting edge pairs')
        boxes.append(edge_box)
        bounds.Add(edge_box)
    x0, y0, _, x1, y1, _ = bounds.Get()
    margin = max(x1-x0, y1-y0, 1.) * .25
    plane = gp_Pln()
    carrier = BRepBuilderAPI_MakeFace(plane, x0-margin, x1+margin, y0-margin, y1+margin).Face()
    splitter = BOPAlgo_Splitter()
    splitter.SetNonDestructive(True)
    splitter.SetUseOBB(True)
    splitter.AddArgument(carrier)
    for _, edge in inputs:
        splitter.AddTool(edge)
    splitter.Perform()
    if splitter.HasErrors() or splitter.HasWarnings():
        raise ValueError('OCCT could not unambiguously split the sketch boundaries')

    edges, origins, ends, events, totals = edge_history(splitter, inputs)
    entity_edges = defaultdict(set)
    for source, _ in inputs:
        entity_edges[source[0]].add(source)
    line_ids = {e.id for e in entities if isinstance(e, Line)}
    transform = gp_Trsf()
    transform.SetValues(*(coordinate for i in range(3)
                          for coordinate in (frame.u[i], frame.v[i], frame.normal[i], frame.origin[i])))
    cells = defaultdict(list)
    for count, raw in enumerate(shapes(splitter.Shape(), TopAbs_FACE, TopoDS.Face_s), 1):
        if count > MAX_CELLS + 1:
            raise ValueError(f'Sketch arrangement exceeds {MAX_CELLS} bounded cells')
        face = TopoDS.Face_s(raw.Oriented(TopAbs_FORWARD))
        outer = BRepTools.OuterWire_s(face)
        holes = [wire for wire in shapes(face, TopAbs_WIRE, TopoDS.Wire_s)
                 if not wire.IsSame(outer) and next(wire_edges(wire), None) is not None]
        rings, whole, members = [], [], set()
        for wire in (outer, *holes):
            tokens, sources = [], []
            ordered = tuple(wire_edges(wire))
            endpoints = tuple(map(analytic_ends, ordered))
            if any(a[1].Distance(b[0]) > CONNECT_TOLERANCE for a, b in zip(endpoints, endpoints[1:] + endpoints[:1])):
                break  # OCCT may merge vertices farther apart than our line tolerance.
            for edge in ordered:
                index = edges.FindIndex(edge)
                if not index:
                    break  # Carrier edge. Its incident cell is the unbounded exterior.
                first, last = ends[index]
                direction = -1 if edge.Orientation() == TopAbs_REVERSED else 1
                if direction < 0:
                    first, last = last, first
                provenance = tuple((source, ordinal, total, sense*direction)
                                   for source, ordinal, total, sense in origins[index])
                tokens.append((provenance, events[first], events[last]))
                sources.extend(source for source, *_ in provenance)
            else:
                if not tokens:
                    break
                # Normalize the start edge while retaining directed cyclic order.
                first_token = min(tokens)
                rotations = [i for i, token in enumerate(tokens) if token == first_token]
                rings.append(min(tuple(tokens[i:] + tokens[:i]) for i in rotations))
                ids = {source[0] for source in sources}
                members.update(ids)
                complete = (len(sources) == len(tokens) and len(set(sources)) == len(sources)
                            and all(totals[source] == 1 for source in sources)
                            and set(sources) == set().union(*(entity_edges[i] for i in ids)))
                legacy = None
                if complete and ids <= line_ids:
                    legacy = loop_id(ids)
                elif complete and len(ids) == 1 and not ids & line_ids:
                    legacy = next(iter(ids))
                whole.append(legacy)
                continue
            break
        else:
            # Strip INTERNAL dangling edges/wires from the prism input. The
            # splitter's boundary wires retain the original analytic curves.
            builder = BRepBuilderAPI_MakeFace(plane, outer, True)
            for wire in holes:
                builder.Add(wire)
            if not builder.IsDone():
                continue
            clean = builder.Face()
            properties = GProp_GProps()
            BRepGProp.SurfaceProperties_s(clean, properties)
            if properties.Mass() <= CONNECT_TOLERANCE**2 or not BRepCheck_Analyzer(clean).IsValid():
                continue
            key = (rings[0], tuple(sorted(rings[1:])))
            identifier = str(uuid5(NAMESPACE_URL, 'hero-cad:cell-v1:' + repr(key)))
            world = TopoDS.Face_s(BRepBuilderAPI_Transform(clean, transform, False).Shape())
            cells[identifier].append(Cell(identifier, world, tuple(sorted(members)), tuple(whole)))
    # A signature shared by multiple cells has no safe persistent identity.
    return tuple(items[0] for items in cells.values() if len(items) == 1)

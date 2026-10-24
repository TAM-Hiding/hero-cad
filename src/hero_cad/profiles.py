"""Analytic material regions: persistent entity keys, never display tessellation."""
from dataclasses import dataclass, replace
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.TopAbs import TopAbs_EDGE, TopAbs_IN, TopAbs_VERTEX, TopAbs_WIRE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt, gp_Vec
from hero_cad.geometry import make_sketch, volume
from hero_cad.sketch import SketchParameters, Line
from hero_cad.line_profiles import line_boundaries

TOLERANCE = 1e-7


class ProfileError(ValueError):
    """A previously selected line boundary is temporarily open/ambiguous."""


@dataclass(frozen=True)
class Region:
    outer_id: str
    hole_ids: tuple
    face: object
    boundary_ids: tuple = ()
    line_ids: tuple = ()


def contains(face, world):
    return BRepClass_FaceClassifier(face, gp_Pnt(*world), TOLERANCE).State() == TopAbs_IN


def regions(sketch):
    """Even/odd material; reject intersecting boundaries and affected ancestors.

    Simple line cycles and primitives share the same nesting/extrusion pipeline.
    Crossings, overlaps and branch networks require explicit correction.
    """
    if len(sketch.entities) > 256:
        raise ValueError('Profile analysis supports at most 256 entities per sketch')
    loops, faces, sample, members = {}, {}, {}, {}
    boundaries, open_edges = line_boundaries(sketch)
    for entity in sketch.entities:
        if isinstance(entity, Line):
            continue
        shape = make_sketch(replace(sketch, entities=(entity,)))
        ex = TopExp_Explorer(shape, TopAbs_WIRE)
        if ex.More():
            wire = TopoDS.Wire_s(ex.Current())
        else:
            ex = TopExp_Explorer(shape, TopAbs_EDGE)
            wire = BRepBuilderAPI_MakeWire(TopoDS.Edge_s(ex.Current())).Wire()
        boundaries.append((entity.id, wire, (entity.id,)))
    for key, wire, identifiers in boundaries:
        if key in loops:
            raise ValueError('Ambiguous profile boundary identity')
        face = BRepBuilderAPI_MakeFace(wire, True).Face()
        if not BRepCheck_Analyzer(face).IsValid():
            raise ValueError('Invalid closed profile')
        vertex = TopExp_Explorer(wire, TopAbs_VERTEX)
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertex.Current()))
        loops[key], faces[key], members[key] = wire, face, identifiers
        sample[key] = (p.X(), p.Y(), p.Z())
    containers = {key: set() for key in loops}
    bad = set()
    for key, wire in loops.items():
        for edge in open_edges:
            distance = BRepExtrema_DistShapeShape(wire, edge)
            if not distance.IsDone():
                raise ValueError('Could not classify open sketch edges reliably')
            if distance.Value() <= TOLERANCE:
                bad.add(key)
    keys = list(loops)
    for i, a in enumerate(keys):
        for b in keys[i+1:]:
            distance = BRepExtrema_DistShapeShape(loops[a], loops[b])
            if not distance.IsDone():
                raise ValueError('Could not classify profile boundaries reliably')
            if distance.Value() <= TOLERANCE:
                bad.update((a, b))
                continue
            if contains(faces[a], sample[b]):
                containers[b].add(a)
            if contains(faces[b], sample[a]):
                containers[a].add(b)
    # If overlapping children lie in a plate, that plate is ambiguous too.
    for key in tuple(bad):
        bad.update(containers[key])
    bad.update(key for key in keys if containers[key].intersection(bad))
    result = []
    for key in keys:
        if key in bad or len(containers[key]) % 2:
            continue
        holes = tuple(sorted(child for child in keys if key in containers[child]
                             and len(containers[child]) == len(containers[key])+1))
        builder = BRepBuilderAPI_MakeFace(loops[key], True)
        for hole in holes:
            builder.Add(TopoDS.Wire_s(loops[hole].Reversed()))
        face = builder.Face()
        if not builder.IsDone() or not BRepCheck_Analyzer(face).IsValid():
            raise ValueError('Could not construct a valid material region with holes')
        identifiers = tuple(sorted(identifier for boundary in (key, *holes) for identifier in members[boundary]))
        line_ids = tuple(identifier for identifier in identifiers
                         if any(isinstance(e, Line) and e.id == identifier for e in sketch.entities))
        result.append(Region(key, holes, face, identifiers, line_ids))
    return tuple(result)


def resolve_region(sketch, outer_id, hole_ids):
    region = next((r for r in regions(sketch) if r.outer_id == outer_id), None)
    if region is None or region.hole_ids != tuple(sorted(hole_ids)):
        raise ValueError('Selected profile topology changed or is ambiguous; delete the extrusion and reselect its material region. Holes will not be filled silently.')
    return region


def extrude_region(sketch, parameters, *, with_faces=False):
    try:
        region = resolve_region(sketch, parameters.outer_id, parameters.hole_ids)
    except ValueError as error:
        if parameters.line_ids:
            raise ProfileError(f'Unresolved line profile: {error}') from error
        raise
    if parameters.line_ids != region.line_ids:
        raise ValueError('Selected line-profile membership changed; reselect the material region')
    vector = gp_Vec(*(n*parameters.distance for n in sketch.frame.normal))
    builder = BRepPrimAPI_MakePrism(region.face, vector, True)
    shape = builder.Shape()
    if not builder.IsDone() or shape.ShapeType() != TopAbs_SOLID or not BRepCheck_Analyzer(shape).IsValid() or volume(shape) <= 0:
        raise ValueError('OCCT could not build a valid positive-volume extrusion')
    if with_faces:
        from hero_cad.attachments import extrusion_faces
        return shape, extrusion_faces(builder, region, sketch, parameters)
    return shape

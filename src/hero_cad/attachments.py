"""Semantic planar-face naming from feature construction, never face indices."""
from math import cos, sin, radians, dist
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from hero_cad.sketch import PlaneFrame, FaceReference, Rectangle, Slot


class AttachmentError(ValueError):
    pass


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def planar_frame(face, *, anchor=None, up=None):
    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane:
        raise AttachmentError('New Sketch requires an analytic planar face')
    plane = surface.Plane()
    normal = tuple(plane.Axis().Direction().Coord(i) for i in (1, 2, 3))
    if face.Orientation() == TopAbs_REVERSED:
        normal = tuple(-x for x in normal)
    origin = tuple(plane.Location().Coord(i) for i in (1, 2, 3))
    anchor = anchor if anchor is not None else origin
    offset = sum((anchor[i]-origin[i])*normal[i] for i in range(3))
    origin = tuple(anchor[i]-offset*normal[i] for i in range(3))
    if up is None:
        reference = (0., 0., 1.) if abs(normal[2]) < .95 else (0., 1., 0.)
        dot = sum(a*b for a,b in zip(reference, normal))
        up = tuple(reference[i]-dot*normal[i] for i in range(3))
    length = sum(x*x for x in up)**.5
    up = tuple(x/length for x in up)
    return PlaneFrame('FACE', origin, cross(up, normal), up)


def segments(entity):
    """Stable parameter identities, in source-local coordinates."""
    if isinstance(entity, Rectangle):
        return {f'edge{i}': (entity.points[i], entity.points[i+1]) for i in range(4)}
    if isinstance(entity, Slot):
        c, s = cos(radians(entity.angle)), sin(radians(entity.angle))
        a, b, r = (entity.x, entity.y), entity.second_center, entity.radius
        offset = lambda p, sign: (p[0]-sign*r*s, p[1]+sign*r*c)
        return {'tangent0': (offset(a, -1), offset(b, -1)),
                'tangent1': (offset(b, 1), offset(a, 1))}
    return {}


def extrusion_faces(builder, region, sketch, parameters):
    """OCCT prism history associates each exact source edge with its side."""
    result = {('start', None, None): TopoDS.Face_s(builder.FirstShape()),
              ('end', None, None): TopoDS.Face_s(builder.LastShape())}
    edges = []
    explorer = TopExp_Explorer(region.face, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        a = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(edge))
        b = BRep_Tool.Pnt_s(TopExp.LastVertex_s(edge))
        edges.append((edge, (a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())))
        explorer.Next()
    for entity in sketch.entities:
        if entity.id not in (parameters.outer_id, *parameters.hole_ids):
            continue
        for name, (a, b) in segments(entity).items():
            a, b = sketch.frame.to_world(a), sketch.frame.to_world(b)
            matches = [edge for edge, p, q in edges
                       if (dist(a,p) < 1e-7 and dist(b,q) < 1e-7)
                       or (dist(a,q) < 1e-7 and dist(b,p) < 1e-7)]
            if len(matches) != 1:
                continue
            generated = [TopoDS.Face_s(f) for f in builder.Generated(matches[0])
                         if f.ShapeType() == TopAbs_FACE]
            if len(generated) == 1 and BRepAdaptor_Surface(generated[0]).GetType() == GeomAbs_Plane:
                result[('side', entity.id, name)] = generated[0]
    # Prism history can return source-oriented caps for negative sweeps.
    # Use the matching face's orientation in the actual closed result solid.
    actual = []
    explorer = TopExp_Explorer(builder.Shape(), TopAbs_FACE)
    while explorer.More():
        actual.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return {key: next(f for f in actual if f.IsSame(face)) for key,face in result.items()}


def reference_key(reference):
    return reference.face, reference.boundary_id, reference.segment


def resolve_attachment(reference, face_maps, definitions, *, previous_frame=None, previous_source_frame=None):
    parent = definitions.get(reference.parent_id)
    if parent is None or parent.type not in ('box', 'extrude', 'boolean'):
        raise AttachmentError('Attachment parent must be a solid feature')
    key = reference.face if parent.type == 'box' else reference_key(reference)
    face = face_maps.get(parent.id, {}).get(key)
    if face is None:
        raise AttachmentError(f'Unresolved face {reference.face} / {reference.boundary_id or ""} / {reference.segment or ""} on {parent.id}')
    if parent.type == 'box':
        return planar_frame(face)
    source = definitions[parent.parameters.sketch_id].parameters
    if reference.face in ('start', 'end'):
        offset = 0 if reference.face == 'start' else parent.parameters.distance
        anchor = tuple(source.frame.origin[i]+offset*source.frame.normal[i] for i in range(3))
        # Source U stays fixed; V reverses only when outward normal reverses.
        raw = planar_frame(face)
        normal = raw.normal
        if previous_frame is not None:
            # Preserve the initial cap sense through a signed-depth reversal.
            # Transport through the source frame rather than world coordinates.
            sense = 1 if sum(a*b for a,b in zip(previous_frame.normal, previous_source_frame.normal)) > 0 else -1
            normal = tuple(sense*x for x in source.frame.normal)
        up = cross(normal, source.frame.u)
        result = planar_frame(face, anchor=anchor, up=up)
        return PlaneFrame('FACE', result.origin, source.frame.u, up)
    entity = next(e for e in source.entities if e.id == reference.boundary_id)
    a, _ = segments(entity)[reference.segment]
    return planar_frame(face, anchor=source.frame.to_world(a), up=source.frame.normal)


def identify_face(face, face_maps, definitions):
    # Read the analytic plane first to distinguish unsupported curved faces.
    planar_frame(face)
    matches = []
    for parent_id, mapping in face_maps.items():
        for key, candidate in mapping.items():
            if candidate.IsSame(face):
                if definitions[parent_id].type == 'box':
                    matches.append(FaceReference(parent_id, key))
                else:
                    matches.append(FaceReference(parent_id, *key))
    if len(matches) != 1:
        raise AttachmentError('This face has no reliable semantic reference; attachment is unavailable')
    return matches[0]

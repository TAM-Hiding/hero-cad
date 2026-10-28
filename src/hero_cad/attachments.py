"""Semantic planar-face naming from feature construction, never face indices."""
from math import cos, sin, radians, dist
from dataclasses import dataclass, replace
from enum import Enum
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Circle
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_IN, TopAbs_ON
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from hero_cad.sketch import PlaneFrame, FaceReference, FaceSupport, FaceSnapshot, decode_face_origin, Rectangle, Circle, Slot, Line


class ResolutionState(str, Enum):
    RESOLVED = 'resolved'
    AMBIGUOUS = 'ambiguous'
    MISSING = 'missing'


@dataclass(frozen=True)
class FaceResolution:
    state: ResolutionState
    face: object = None
    reason: str = ''
    frame: PlaneFrame | None = None


class AttachmentError(ValueError):
    def __init__(self, message, state=ResolutionState.MISSING):
        self.state = state
        super().__init__(message)


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
    if isinstance(entity, Line):
        return {'line': entity.points}
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
        if entity.id not in region.boundary_ids:
            continue
        # Curved prism walls cannot host sketches, but their exact source
        # identity distinguishes neighboring planar regions after Booleans.
        centers = ({'circle': (entity.x, entity.y)} if isinstance(entity, Circle) else
                   {'endA': (entity.x, entity.y), 'endB': entity.second_center}
                   if isinstance(entity, Slot) else {})
        for name, center in centers.items():
            center = sketch.frame.to_world(center)
            matches = [edge for edge, _, _ in edges
                       if BRepAdaptor_Curve(edge).GetType() == GeomAbs_Circle
                       and dist(BRepAdaptor_Curve(edge).Circle().Location().Coord(), center) < 1e-7
                       and abs(BRepAdaptor_Curve(edge).Circle().Radius()-entity.radius) < 1e-7]
            if len(matches) == 1:
                generated = [TopoDS.Face_s(f) for f in builder.Generated(matches[0])
                             if f.ShapeType() == TopAbs_FACE]
                if len(generated) == 1:
                    result[('curve', entity.id, name)] = generated[0]
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


def resolve_attachment(reference, face_maps, definitions, *, previous_frame=None, previous_source_frame=None,
                       lineages=None, source_faces=None, bodies=None):
    if reference.snapshot is not None:
        resolution = resolve_snapshot(reference, bodies or {}, lineages or {})
        if resolution.state != ResolutionState.RESOLVED:
            raise AttachmentError(resolution.reason, resolution.state)
        return resolution.frame
    if reference.support is not None:
        resolution = resolve_supported_face(reference, face_maps, definitions, lineages or {}, source_faces or {})
        if resolution.state != ResolutionState.RESOLVED:
            raise AttachmentError(resolution.reason, resolution.state)
        return resolution.frame
    parent = definitions.get(reference.parent_id)
    if parent is None or parent.type not in ('box', 'extrude', 'boolean', 'chamfer'):
        raise AttachmentError('Attachment parent must be a solid feature')
    key = reference.face if parent.type == 'box' else reference_key(reference)
    face = face_maps.get(parent.id, {}).get(key)
    if face is None:
        raise AttachmentError(f'Unresolved face {reference.face} / {reference.boundary_id or ""} / {reference.segment or ""} on {parent.id}')
    if reference.face == 'evaluated' or (parent.type == 'chamfer' and reference.face == 'bevel'):
        # OCCT's source plane provides a deterministic model-space anchor.
        # No pick point, camera state, or nearest-face fallback is used.
        return planar_frame(face)
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


def identify_face(face, face_maps, definitions, *, active_ids=None, lineages=None, source_faces=None, point=None, bodies=None):
    # Read the analytic plane first to distinguish unsupported curved faces.
    planar_frame(face)
    # Ownership is checked against actual evaluated bodies, independently of
    # whether their optional semantic/ancestry maps publish the selected face.
    owners = None
    if bodies is not None:
        from hero_cad.face_history import subshapes
        owners = [identifier for identifier,body in bodies.items()
                  if (active_ids is None or identifier in active_ids)
                  and any(face.IsSame(candidate) for candidate in subshapes(body,TopAbs_FACE))]
        if not owners:
            raise AttachmentError('Selected face is missing from the current evaluated geometry')
        if len(owners) != 1:
            raise AttachmentError('Ambiguous owning body for selected face', ResolutionState.AMBIGUOUS)
    matches = []
    for parent_id, mapping in face_maps.items():
        if owners is not None and parent_id not in owners:
            continue
        if active_ids is not None and parent_id not in active_ids:
            continue
        for key, candidate in mapping.items():
            if candidate.IsSame(face):
                if definitions[parent_id].type == 'box':
                    matches.append(FaceReference(parent_id, key))
                else:
                    matches.append(FaceReference(parent_id, *key))
    if len(matches) != 1:
        if owners is None:
            raise AttachmentError('This face has no reliable semantic reference; attachment is unavailable')
        return new_current_reference(owners[0],face,definitions,lineages or {},source_faces or {},bodies,point)
    reference = matches[0]
    if reference.face == 'evaluated' and lineages is not None:
        reference = supported_reference(reference, face, lineages, source_faces or {}, definitions, point=point)
    return reference


def source_frame(token, source_faces, definitions):
    identifier, key = decode_face_origin(token)
    reference = (FaceReference(identifier, key) if isinstance(key, str)
                 else FaceReference(identifier, *key))
    frame = resolve_attachment(reference, source_faces, definitions)
    parent = definitions[identifier]
    if parent.type == 'extrude' and reference.face in ('start', 'end'):
        # Cap coordinates follow the source plane, independent of sweep sign.
        # sense in FaceSupport retains the sketch's initial normal direction.
        source = definitions[parent.parameters.sketch_id].parameters.frame
        return PlaneFrame('FACE', frame.origin, source.u, source.v)
    return frame


def same_plane(a, b):
    return (abs(abs(sum(x*y for x,y in zip(a.normal,b.normal)))-1) < 1e-9
            and abs(sum((a.origin[i]-b.origin[i])*b.normal[i] for i in range(3))) < 1e-7)


def point_state(face, point):
    return BRepClass_FaceClassifier(face, gp_Pnt(*point), 1e-7).State()


def interior_point(face, point=None):
    frame = planar_frame(face)
    if point is not None:
        projected = frame.to_world(frame.to_local(point))
        if point_state(face, projected) == TopAbs_IN:
            return projected
        raise AttachmentError('Attachment point must lie strictly inside the selected face')
    # API callers without a click receive a deterministic interior witness;
    # no centroid assumption (a face may have a hole through its centroid).
    u0,u1,v0,v1 = BRepTools.UVBounds_s(face)
    surface = BRepAdaptor_Surface(face)
    for a in (.5,.25,.75,.125,.875,.0625,.9375):
        for b in (.5,.25,.75,.125,.875,.0625,.9375):
            p = surface.Value(u0+(u1-u0)*a,v0+(v1-v0)*b).Coord()
            if point_state(face,p) == TopAbs_IN:
                return p
    raise AttachmentError('Cannot establish a reliable interior attachment point; select inside the face')


def supported_reference(reference, face, lineages, source_faces, definitions, *, point=None):
    rows = lineages.get(reference.parent_id, ())
    tokens = next((tokens for candidate,tokens in rows if candidate.IsSame(face)), frozenset())
    actual = planar_frame(face)
    for token in sorted(tokens):
        try:
            root = source_frame(token, source_faces, definitions)
        except (ValueError, StopIteration, KeyError):
            continue  # Curved or unsupported construction ancestors are not planes.
        if not same_plane(actual, root):
            continue
        try:
            witness = interior_point(face, point)
        except AttachmentError:
            if point is None:
                return reference  # Thin/complex API-only face: exact legacy identity.
            raise
        sense = 1 if sum(x*y for x,y in zip(actual.normal, root.normal)) > 0 else -1
        support = FaceSupport(tuple(sorted(tokens)), token, root.to_local(witness), sense,
                              sum(other == tokens for _,other in rows))
        return replace(reference, support=support)
    # Exact legacy signatures remain available when OCCT did not expose a
    # supported planar root; no guessed ancestry or world-plane fallback.
    return reference


def resolve_supported_face(reference, face_maps, definitions, lineages, source_faces):
    support = reference.support
    missing = lambda reason: FaceResolution(ResolutionState.MISSING, reason=f'Unresolved face on {reference.parent_id}: {reason}')
    try:
        root = source_frame(support.root, source_faces, definitions)
    except (ValueError, KeyError, StopIteration) as error:
        return missing(f'construction ancestor is missing ({error})')
    rows = lineages.get(reference.parent_id, ())
    tokens = frozenset(support.origins)
    related = [(f,t) for f,t in rows if t == tokens]
    if len(related) < support.count:
        return missing('ancestral regions merged or disappeared; automatic reassignment refused')
    frame = PlaneFrame('FACE', root.origin, root.u, tuple(support.sense*x for x in root.v))
    candidates = []
    for face,_ in related:
        try:
            plane = planar_frame(face)
        except AttachmentError:
            continue
        if same_plane(plane,frame):
            candidates.append(face)
    exact = face_maps.get(reference.parent_id, {}).get(reference_key(reference))
    if exact is not None and any(exact.IsSame(face) for face in candidates):
        return FaceResolution(ResolutionState.RESOLVED, exact, frame=frame)
    witness = root.to_world(support.anchor)
    inside = [face for face in candidates if point_state(face,witness) == TopAbs_IN]
    boundary = [face for face in candidates if point_state(face,witness) == TopAbs_ON]
    if len(inside) == 1 and not boundary:
        return FaceResolution(ResolutionState.RESOLVED, inside[0], frame=frame)
    if len(inside) > 1 or boundary:
        return FaceResolution(ResolutionState.AMBIGUOUS,
                              reason=f'Ambiguous face on {reference.parent_id}: attachment point has no unique interior descendant')
    return missing('no descendant contains the source-local attachment point on its supporting plane')


def new_current_reference(owner, face, definitions, lineages, source_faces, bodies, point):
    """Explicit current selection may establish an identity; recovery may not."""
    from hero_cad.face_geometry import face_digest
    witness = interior_point(face, point)
    reference = FaceReference(owner,'evaluated',segment=face_digest(face))
    supported = supported_reference(reference,face,lineages,source_faces,definitions,point=witness)
    if supported.support is not None:
        result = resolve_supported_face(supported,{},definitions,lineages,source_faces)
    else:
        tokens = next((tokens for candidate,tokens in lineages.get(owner,()) if candidate.IsSame(face)),frozenset())
        supported = replace(reference,snapshot=FaceSnapshot(tuple(witness),tuple(sorted(tokens))))
        result = resolve_snapshot(supported,bodies,lineages)
    if result.state != ResolutionState.RESOLVED or not result.face.IsSame(face):
        raise AttachmentError(result.reason or 'Current face cannot be uniquely verified',result.state)
    return supported


def resolve_snapshot(reference, bodies, lineages):
    """Exact geometry only: no plane/point fallback when a stored face changes."""
    from hero_cad.face_geometry import face_digest
    from hero_cad.face_history import subshapes
    body = bodies.get(reference.parent_id)
    if body is None:
        return FaceResolution(ResolutionState.MISSING,reason='Unresolved face: owning evaluated body is missing')
    matches = []
    for raw in subshapes(body,TopAbs_FACE):
        face = TopoDS.Face_s(raw)
        try:
            if face_digest(face) != reference.segment:
                continue
        except AttachmentError:
            continue
        tokens = next((t for f,t in lineages.get(reference.parent_id,()) if f.IsSame(face)),frozenset())
        if reference.snapshot.origins and tokens != frozenset(reference.snapshot.origins):
            continue
        if point_state(face,reference.snapshot.anchor) == TopAbs_IN:
            matches.append(face)
    if len(matches) == 1:
        return FaceResolution(ResolutionState.RESOLVED,matches[0],frame=planar_frame(matches[0],anchor=(0.,0.,0.)))
    if matches:
        return FaceResolution(ResolutionState.AMBIGUOUS,reason='Ambiguous current-face geometry in the referenced body')
    return FaceResolution(ResolutionState.MISSING,
                          reason='Unresolved face: checked current geometry changed or disappeared; automatic reassignment refused')

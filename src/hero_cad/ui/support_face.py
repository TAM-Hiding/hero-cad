"""Non-interactive support overlay extracted from existing display triangles."""
from hero_cad.attachments import resolve_snapshot, resolve_supported_face, reference_key, ResolutionState
from hero_cad.ui.display_geometry import selected_mesh


def prepare_support_face(window, document, sketch, faces, surface, checked, *, force=False):
    """Resolve/extract into candidate data without changing the live overlay."""
    v, doc = window.viewport, document
    if not v.sketch_face_enabled or sketch is None or not sketch.parameters.attachment:
        return None, False, None
    reference = sketch.parameters.attachment
    if not doc.statuses[sketch.id].valid:
        return None, False, None
    definitions = {f.id: f for f in doc.features}
    if reference.parent_id not in definitions:
        return None, False, None
    parent_index = next(i for i, f in enumerate(doc.features) if f.id == reference.parent_id)
    owner = getattr(doc, '_candidate_owner', doc)
    key = (owner, reference, doc.features[:parent_index + 1], checked)
    if not force and getattr(v, '_support_key', None) == key:
        return key, v._support_available, v.support_mapper.GetInput()
    if reference.snapshot is not None:
        result = resolve_snapshot(reference, doc.solid_shapes, doc.face_lineages)
        face = result.face if result.state == ResolutionState.RESOLVED else None
    elif reference.support is not None:
        result = resolve_supported_face(reference, doc.face_maps, definitions, doc.face_lineages, doc.source_faces)
        face = result.face if result.state == ResolutionState.RESOLVED else None
    else:
        parent = definitions[reference.parent_id]
        token = reference.face if parent.type == 'box' else reference_key(reference)
        face = doc.face_maps.get(parent.id, {}).get(token)
    if face is None:
        return key, False, None
    index = next((i for i, candidate in enumerate(faces) if candidate.IsSame(face)), None)
    if index is None:
        return key, False, None  # Hidden/historical support: never substitute.
    return key, True, selected_mesh(surface, 'face_id', index)


def update_support_face(window):
    v = window.viewport
    key, available, mesh = prepare_support_face(window, window.document, v.sketch.feature,
                                               v.faces, v.mapper.GetInput(), window.show_base_box.isChecked())
    if available and mesh is not v.support_mapper.GetInput():
        v.support_mapper.SetInputData(mesh)
    v._support_key, v._support_available = key, available
    v.support_actor.SetVisibility(available)

"""Non-interactive support overlay extracted from existing display triangles."""
from hero_cad.attachments import resolve_snapshot, resolve_supported_face, reference_key, ResolutionState
from hero_cad.ui.display_geometry import selected_mesh


def update_support_face(window):
    v, doc = window.viewport, window.document
    actor = v.support_actor
    actor.VisibilityOff()
    sketch = v.sketch.feature
    if not v.sketch_face_enabled or sketch is None or not sketch.parameters.attachment:
        return
    reference = sketch.parameters.attachment
    if not doc.statuses[sketch.id].valid:
        return
    definitions = {f.id: f for f in doc.features}
    if reference.parent_id not in definitions:
        return
    # Immutable authoritative definitions up to the support owner invalidate the
    # presentation when relevant geometry changes, but not on leaf sketch edits.
    parent_index = next(i for i, f in enumerate(doc.features) if f.id == reference.parent_id)
    key = (doc, reference, doc.features[:parent_index + 1], window.show_base_box.isChecked())
    if getattr(v, '_support_key', None) == key:
        actor.SetVisibility(v._support_available)
        return
    v._support_key, v._support_available = key, False
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
        return
    index = next((i for i, candidate in enumerate(v.faces) if candidate.IsSame(face)), None)
    if index is None:
        return  # Hidden/historical support has no displayed triangles; never substitute.
    v.support_mapper.SetInputData(selected_mesh(v.mapper.GetInput(), 'face_id', index))
    v._support_available = True
    actor.VisibilityOn()

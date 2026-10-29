"""Read-only presentation of authoritative document history; no evaluation/cache."""
from collections import Counter
from hero_cad.chamfers import edge_description


TYPE_LABELS = {'box': 'Box', 'sketch': 'Sketch', 'extrude': 'Extrusion', 'boolean': 'Combine', 'chamfer': 'Chamfer'}


def feature_history_text(document, identifier):
    """Format one selection in linear history/reference time, without regeneration.

    Names and positions are derived labels, not persistent user names. All
    relationships are direct Feature.references, including canonical planes.
    """
    definitions = {f.id: f for f in document.features}
    feature = definitions[identifier]
    counts, labels, positions = Counter(), {}, {}
    for position, item in enumerate(document.features, 1):
        counts[item.type] += 1
        labels[item.id] = f'{TYPE_LABELS[item.type]} {counts[item.type]}'
        positions[item.id] = position

    def reference_label(ref):
        if ref in definitions:
            return f'#{positions[ref]} · {labels[ref]}'
        if ref in ('plane:XY', 'plane:XZ', 'plane:YZ'):
            return f'{ref[6:]} origin plane'
        return f'Missing reference: {ref}'

    def dependency_role(child, parent_id):
        p = child.parameters
        if child.type == 'sketch':
            if p.attachment and p.attachment.parent_id == parent_id:
                face = {'start': 'Start Face', 'end': 'End Face', 'side': 'Side Face',
                        'evaluated': 'Evaluated Planar Face'}.get(p.attachment.face, p.attachment.face)
                return f'Supporting face · {face}'
            return 'Sketch plane' if parent_id.startswith('plane:') else 'Sketch dependency'
        if child.type == 'extrude':
            if parent_id == p.sketch_id:
                return 'Source profile sketch'
            if parent_id == p.target_id:
                return f'Boolean target body · {p.operation.title()}'
        if child.type == 'boolean':
            return 'Boolean target body' if parent_id == p.target_id else 'Boolean tool body'
        if child.type == 'chamfer':
            return 'Chamfer target body / selected edge'
        return 'Feature dependency'

    status = document.statuses[identifier]
    blocked = [ref for ref in feature.references
               if ref in document.statuses and not document.statuses[ref].valid]
    state = 'Valid' if status.valid else 'Blocked by unresolved dependencies' if blocked else 'Unresolved'
    lines = [labels[identifier], f'Type: {TYPE_LABELS[feature.type]}',
             f'History position: {positions[identifier]} of {len(document.features)}',
             '', f'Status: {state}']
    identifiers = [f'Feature UUID: {identifier}']
    if feature.type != 'sketch':
        role = ('Current resulting body' if identifier in document.active_body_ids else
                'Historical geometry · consumed by a later operation') if status.valid else 'No evaluated output'
        lines.append(f'Geometry: {role}')
    else:
        lines.append('Sketch visibility: ' + ('Shown' if feature.sketch_visible else 'Hidden')
                     + ' (display only; does not suppress evaluation)')
        if not status.valid:
            lines.append('Geometry: No evaluated output')
    if status.reference_state:
        lines.append(f'{"Edge" if feature.type == "chamfer" else "Face"} reference: {status.reference_state.title()}')
    if status.error:
        lines.extend(['', 'Regeneration error:', status.error])

    lines.extend(['', 'Direct parents:'])
    lines.extend(f'{reference_label(ref)} — {dependency_role(feature, ref)}' for ref in feature.references)
    if not feature.references:
        lines.append('None')
    lines.extend(['', 'Direct dependents:'])
    dependents = [f.id for f in document.features if identifier in f.references]
    lines.extend(f'{reference_label(ref)} — {dependency_role(definitions[ref], identifier)}' for ref in dependents)
    if not dependents:
        lines.append('None')

    lines.extend(['', 'Stored parameters:'])
    p = feature.parameters
    number = lambda value: format(value, '.17g')
    vector = lambda values: ', '.join(number(value) for value in values)
    if feature.type == 'box':
        lines.extend([f'Width · X: {number(p.width)} mm', f'Depth · Y: {number(p.depth)} mm',
                      f'Height · Z: {number(p.height)} mm'])
    elif feature.type == 'sketch':
        lines.append(f'Plane: {p.plane}')
        if p.attachment:
            ref = p.attachment
            strategy = 'Checked geometry snapshot' if ref.snapshot else 'Source ancestry and witness' if ref.support else 'Semantic / exact face reference'
            lines.extend([f'Attachment: {strategy}', f'Face: {ref.face}'])
            if ref.boundary_id:
                identifiers.append(f'Boundary ID: {ref.boundary_id}')
            if ref.segment:
                identifiers.append(f'Face segment / signature: {ref.segment}')
        lines.append('Local frame' + (' (last resolved)' if not status.valid and p.attachment else '') + ':')
        lines.extend([f'Origin: ({vector(p.frame.origin)}) mm', f'U direction: ({vector(p.frame.u)})',
                      f'V direction: ({vector(p.frame.v)})'])
        entities = Counter(type(e).__name__ for e in p.entities)
        lines.append(f'Entities: {len(p.entities)}' + (' · ' + ', '.join(f'{n} {kind}' for kind, n in sorted(entities.items())) if entities else ''))
        lines.append('Select a sketch entity in the browser to inspect/edit its dimensions in Edit.')
    elif feature.type == 'extrude':
        lines.extend([f'Source sketch: {reference_label(p.sketch_id)}',
                      f'Operation: {"New Body" if p.operation == "new" else p.operation.title()}',
                      f'Extent: {"Through All" if p.extent == "through_all" else "Distance"}'])
        if p.extent == 'through_all':
            lines.extend([f'Direction: {p.direction:+d} along sketch normal',
                          f'Stored distance: {number(p.distance)} mm (not the evaluated Through All depth)'])
        else:
            lines.append(f'Signed distance: {number(p.distance)} mm')
        if p.target_id:
            lines.append(f'Target: {reference_label(p.target_id)}')
        lines.append(f'Source profile: 1 outer boundary, {len(p.hole_ids)} hole boundaries, {len(p.line_ids)} line members')
        identifiers.extend([f'Outer boundary ID: {p.outer_id}', f'Hole boundary IDs ({len(p.hole_ids)}):'])
        identifiers.extend(p.hole_ids or ('None',))
        identifiers.append(f'Line member IDs ({len(p.line_ids)}):')
        identifiers.extend(p.line_ids or ('None',))
    elif feature.type == 'boolean':
        lines.extend([f'Operation: {p.operation.title()}', f'Target: {reference_label(p.target_id)}', 'Tools:'])
        lines.extend(reference_label(ref) for ref in p.tool_ids)
    elif feature.type == 'chamfer':
        lines.extend([f'Equal distance: {number(p.distance)} mm', f'Target: {reference_label(p.target_id)}',
                      f'Selected edges: {len(p.edges)}',
                      *([edge_description(p.edges[0])] if len(p.edges) == 1 else []),
                      'Edge identity: checked curve geometry and two adjacent face ancestries; no index fallback'])
        for i,edge in enumerate(p.edges,1):
            identifiers.append(f'Edge {i}: ' + edge_description(edge))
            identifiers.append('Adjacent construction-face ancestry:')
            identifiers.extend(', '.join(tokens) for tokens in edge.neighbors)
    lines.extend(['', 'Technical identifiers:', *identifiers])
    return '\n'.join(lines)

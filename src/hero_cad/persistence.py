"""Strict versioned parameter serialization; no native shapes or transient selection."""
from dataclasses import asdict
from hero_cad.features import BoxParameters, ExtrudeParameters, BooleanParameters, ChamferParameters, OffsetPlaneParameters, ProfileReference, Feature
from hero_cad.chamfers import EdgeReference
from hero_cad.sketch import Circle, Line, Rectangle, SketchParameters, Slot, PlaneFrame, FaceReference, FaceSupport, FaceSnapshot


DOCUMENT_EXTENSION = '.hcad'
DOCUMENT_FORMAT = 'hero-cad'


def require_document_extension(path):
    if path.suffix.lower() != DOCUMENT_EXTENSION or not path.stem.strip():
        raise ValueError(f'Use a filename ending in {DOCUMENT_EXTENSION} for HERO-CAD documents')


def fields(data, expected):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise ValueError('Invalid document fields: expected ' + ', '.join(expected))


def serialize(features):
    result, version = [], 3
    for feature in features:
        if feature.type in ('box', 'extrude', 'boolean', 'chamfer'):
            parameters = asdict(feature.parameters)
            if feature.type == 'chamfer':
                version = max(version, 12)
                parameters.pop('edges')
                edges = feature.parameters.edges
                if len(edges) == 1:
                    parameters['edge'] = serialize_edge(edges[0])
                    if edges[0].curve_type != 'line':
                        version = max(version, 13)
                else:
                    version = max(version, 14)
                    parameters['edges'] = [serialize_edge(edge) for edge in edges]
            if feature.type == 'extrude':
                additional = parameters.pop('additional_profiles')
                if feature.parameters.region_sources:
                    version = max(version, 17)
                    parameters['region_sources'] = list(feature.parameters.region_sources)
                else:
                    parameters.pop('region_sources')
                if any(p.region_sources for p in feature.parameters.additional_profiles):
                    version = max(version, 17)
                if additional:
                    version = max(version, 15)
                    parameters['additional_profiles'] = [
                        {'outer_id': p.outer_id, 'hole_ids': list(p.hole_ids), 'line_ids': list(p.line_ids),
                     **({'region_sources': list(p.region_sources)} if p.region_sources else {})}
                        for p in feature.parameters.additional_profiles]
                version = max(version, 8 if feature.parameters.line_ids else 6 if feature.parameters.operation != 'new' else 4)
                if feature.parameters.line_ids:
                    parameters['line_ids'] = list(feature.parameters.line_ids)
                else:
                    parameters.pop('line_ids')
                parameters['hole_ids'] = list(parameters['hole_ids'])
                if feature.parameters.operation == 'new':
                    for key in ('operation', 'target_id', 'extent', 'direction'):
                        parameters.pop(key)
            if feature.type == 'boolean':
                version = max(version, 6)
                parameters['tool_ids'] = list(parameters['tool_ids'])
        elif feature.type == 'offset_plane':
            version = max(version, 16)
            p = feature.parameters
            parameters = {'reference': p.reference, 'offset': p.offset}
            if isinstance(p.reference, FaceReference):
                parameters['reference'] = serialize_face(p.reference)
                if p.outward:
                    parameters['outward'] = True
                if p.support_frame is not None:
                    parameters['support_frame'] = serialize_frame(p.support_frame)
        else:
            sketch = feature.parameters
            parameters = {'plane': sketch.plane,
                          'frame': serialize_frame(sketch.frame),
                          'entities': [{'type': type(e).__name__.lower(),
                                        'parameters': asdict(e)} for e in sketch.entities]}
            if sketch.attachment:
                version = max(version, 8 if sketch.attachment.segment == 'line' else 7 if sketch.attachment.face == 'evaluated' else 5)
                parameters['attachment'] = serialize_face(sketch.attachment)
                if sketch.attachment.face in ('start', 'end') and sketch.attachment.boundary_id is not None:
                    version = max(version, 15)
                if sketch.attachment.snapshot is not None:
                    version = max(version, 10)
                if sketch.attachment.support is not None:
                    version = max(version, 9)
            if sketch.plane_id:
                version = max(version, 16)
                parameters['plane_id'] = sketch.plane_id
            for entity in parameters['entities']:
                if entity['parameters'].pop('construction', False):
                    version = max(version, 16)
                    entity['parameters']['construction'] = True
        if not feature.sketch_visible:
            version = max(version, 11)
        result.append({'id': feature.id, 'type': feature.type, 'parameters': parameters,
                       'references': list(feature.references),
                       **({'sketch_visible': False} if not feature.sketch_visible else {}),
                       **({'plane_visible': False} if not feature.plane_visible else {})})
    return {'format': DOCUMENT_FORMAT, 'version': version, 'units': 'mm', 'features': result}


def deserialize(data):
    if not isinstance(data, dict) or data.get('format') != DOCUMENT_FORMAT:
        raise ValueError('Unsupported document format: expected a HERO-CAD .hcad document')
    if data.get('units') != 'mm':
        raise ValueError('Expected a HERO-CAD document in millimetres')
    version = data.get('version')
    if type(version) is not int or version not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
        raise ValueError('Unsupported document version')
    if version == 1:
        fields(data, ('format', 'version', 'units', 'box'))
        fields(data['box'], ('width', 'depth', 'height'))
        return (Feature('box', BoxParameters(**data['box'])),)
    fields(data, ('format', 'version', 'units', 'features'))
    if not isinstance(data['features'], list) or not 1 <= len(data['features']) <= 1000:
        raise ValueError('Expected 1–1000 ordered features')
    result = []
    for item in data['features']:
        visibility = isinstance(item, dict) and 'sketch_visible' in item
        plane_visibility = isinstance(item, dict) and 'plane_visible' in item
        fields(item, ('id', 'type', 'parameters', 'references')
               + (('sketch_visible',) if visibility and version >= 11 else ())
               + (('plane_visible',) if plane_visibility and version >= 16 else ()))
        if visibility and (item['type'] != 'sketch' or type(item['sketch_visible']) is not bool):
            raise ValueError('Invalid sketch visibility')
        if plane_visibility and (item['type'] != 'offset_plane' or type(item['plane_visible']) is not bool):
            raise ValueError('Invalid construction plane visibility')
        if not isinstance(item['references'], list):
            raise ValueError('Invalid references')
        parameters = item['parameters']
        if item['type'] == 'box':
            fields(parameters, ('width', 'depth', 'height'))
            value = BoxParameters(**parameters)
        elif item['type'] == 'offset_plane' and version >= 16:
            has_frame = isinstance(parameters, dict) and 'support_frame' in parameters
            outward = isinstance(parameters, dict) and 'outward' in parameters
            fields(parameters, ('reference', 'offset') + (('support_frame',) if has_frame else ())
                   + (('outward',) if outward else ()))
            reference = parameters['reference']
            if isinstance(reference, dict):
                reference = deserialize_face(reference, version)
            frame = deserialize_frame('FACE', parameters['support_frame']) if has_frame else None
            value = OffsetPlaneParameters(reference, parameters['offset'], frame, parameters.get('outward', False))
        elif item['type'] == 'sketch':
            attached = version >= 5 and isinstance(parameters, dict) and parameters.get('plane') == 'FACE'
            on_plane = version >= 16 and isinstance(parameters, dict) and parameters.get('plane') == 'CONSTRUCTION'
            fields(parameters, ('plane', 'frame', 'entities')
                   + (('attachment',) if attached else ()) + (('plane_id',) if on_plane else ()))
            if not isinstance(parameters['entities'], list) or len(parameters['entities']) > 10000:
                raise ValueError('Too many sketch entities')
            entities = []
            for entity in parameters['entities']:
                fields(entity, ('type', 'parameters'))
                cls = {'line': Line, 'rectangle': Rectangle}.get(entity['type'])
                if version >= 3:
                    cls = {'circle': Circle, 'slot': Slot}.get(entity['type'], cls)
                if cls is None:
                    raise ValueError('Unsupported sketch entity')
                params = entity['parameters']
                names = tuple(k for k in cls.__dataclass_fields__ if k != 'construction')
                if version >= 16 and cls in (Line, Circle) and isinstance(params, dict) and 'construction' in params:
                    names += ('construction',)
                fields(params, names)
                entities.append(cls(**entity['parameters']))
            stored = deserialize_frame(parameters['plane'], parameters['frame'])
            if attached:
                value = SketchParameters('FACE', tuple(entities), deserialize_face(parameters['attachment'], version), stored)
            elif on_plane:
                value = SketchParameters('CONSTRUCTION', tuple(entities), attached_frame=stored,
                                         plane_id=parameters['plane_id'])
            else:
                value = SketchParameters(parameters['plane'], tuple(entities))
                if stored != value.frame:
                    raise ValueError('Sketch frame must match its referenced origin plane')
        elif item['type'] == 'extrude' and version >= 4:
            extended = version >= 6 and isinstance(parameters, dict) and 'operation' in parameters
            line_profile = version >= 8 and isinstance(parameters, dict) and 'line_ids' in parameters
            expected = ('sketch_id', 'outer_id', 'hole_ids', 'distance')
            if extended:
                expected += ('operation', 'target_id', 'extent', 'direction')
            if line_profile:
                expected += ('line_ids',)
            multiple = version >= 15 and isinstance(parameters, dict) and 'additional_profiles' in parameters
            if multiple:
                expected += ('additional_profiles',)
            cell = version >= 17 and isinstance(parameters, dict) and 'region_sources' in parameters
            if cell:
                expected += ('region_sources',)
            fields(parameters, expected)
            if not isinstance(parameters['hole_ids'], list):
                raise ValueError('Profile holes must be a list')
            values = {**parameters, 'hole_ids': tuple(parameters['hole_ids'])}
            if cell:
                sources = parameters['region_sources']
                if not isinstance(sources, list) or not sources:
                    raise ValueError('Bounded cell source IDs must be a nonempty list')
                values['region_sources'] = tuple(sources)
            if line_profile:
                if not isinstance(parameters['line_ids'], list) or not parameters['line_ids']:
                    raise ValueError('Line-profile membership must be a nonempty list')
                values['line_ids'] = tuple(parameters['line_ids'])
            if multiple:
                records = parameters['additional_profiles']
                if not isinstance(records, list) or not 1 <= len(records) <= 255:
                    raise ValueError('Additional profiles must be a nonempty list')
                additional = []
                for record in records:
                    cell = version >= 17 and isinstance(record, dict) and 'region_sources' in record
                    fields(record, ('outer_id', 'hole_ids', 'line_ids') + (('region_sources',) if cell else ()))
                    sources = record.get('region_sources', [])
                    if (not isinstance(record['hole_ids'], list) or not isinstance(record['line_ids'], list)
                            or not isinstance(sources, list) or cell and not sources):
                        raise ValueError('Profile boundary references must be lists with nonempty cell sources')
                    additional.append(ProfileReference(record['outer_id'], tuple(record['hole_ids']),
                                                       tuple(record['line_ids']), tuple(sources)))
                values['additional_profiles'] = tuple(additional)
            value = ExtrudeParameters(**values)
        elif item['type'] == 'boolean' and version >= 6:
            fields(parameters, ('operation', 'target_id', 'tool_ids'))
            if not isinstance(parameters['tool_ids'], list):
                raise ValueError('Boolean tools must be a list')
            value = BooleanParameters(parameters['operation'], parameters['target_id'], tuple(parameters['tool_ids']))
        elif item['type'] == 'chamfer' and version >= 12:
            multiple = isinstance(parameters, dict) and 'edges' in parameters
            key = 'edges' if multiple and version >= 14 else 'edge'
            fields(parameters, ('target_id', key, 'distance'))
            if multiple:
                records = parameters['edges']
                if not isinstance(records, list) or not 2 <= len(records) <= 256:
                    raise ValueError('Expected 2–256 persisted chamfer edges')
                edges = tuple(deserialize_edge(edge, version) for edge in records)
            else:
                edges = (deserialize_edge(parameters['edge'], version),)
            value = ChamferParameters(parameters['target_id'], edges, parameters['distance'])
        else:
            raise ValueError('Unsupported feature type')
        result.append(Feature(item['type'], value, tuple(item['references']), item['id'], item.get('sketch_visible', True),
                              item.get('plane_visible', True)))
    return tuple(result)


def serialize_frame(frame):
    return {k: list(getattr(frame, k)) for k in ('origin', 'u', 'v')}


def deserialize_frame(name, data):
    fields(data, ('origin', 'u', 'v'))
    if any(not isinstance(axis, list) or len(axis) != 3
           or any(type(n) not in (int, float) for n in axis) for axis in data.values()):
        raise ValueError('Invalid sketch frame')
    return PlaneFrame(name, **{k: tuple(v) for k, v in data.items()})


def serialize_face(reference):
    data = asdict(reference)
    for key in ('support', 'snapshot'):
        if data[key] is None:
            del data[key]
        else:
            data[key]['anchor'] = list(data[key]['anchor'])
            data[key]['origins'] = list(data[key]['origins'])
    return data


def deserialize_face(attachment, version):
    if version < 9 and isinstance(attachment, dict) and 'support' in attachment:
        raise ValueError('Ancestry support requires document version 9')
    enriched = version >= 9 and isinstance(attachment, dict) and 'support' in attachment
    if version < 10 and isinstance(attachment, dict) and 'snapshot' in attachment:
        raise ValueError('Current-face snapshots require document version 10')
    snapshot = version >= 10 and isinstance(attachment, dict) and 'snapshot' in attachment
    fields(attachment, ('parent_id', 'face', 'boundary_id', 'segment')
           + (('support',) if enriched else ()) + (('snapshot',) if snapshot else ()))
    attachment = dict(attachment)
    if snapshot:
        value = attachment['snapshot']
        fields(value, ('anchor', 'origins'))
        if not isinstance(value['anchor'], list) or not isinstance(value['origins'], list):
            raise ValueError('Invalid current-face snapshot')
        attachment['snapshot'] = FaceSnapshot(tuple(value['anchor']),tuple(value['origins']))
    if enriched:
        support = attachment['support']
        fields(support, ('origins', 'root', 'anchor', 'sense', 'count'))
        if not isinstance(support['origins'], list) or not isinstance(support['anchor'], list):
            raise ValueError('Invalid persisted ancestry support')
        attachment['support'] = FaceSupport(**{**support, 'origins': tuple(support['origins']),
                                               'anchor': tuple(support['anchor'])})
    if (version < 15 and attachment['face'] in ('start', 'end')
            and attachment['boundary_id'] is not None):
        raise ValueError('Profile-scoped caps require document version 15')
    if version < 7 and attachment['face'] == 'evaluated':
        raise ValueError('Evaluated face references require document version 7')
    if version < 8 and attachment['segment'] == 'line':
        raise ValueError('Line-profile side references require document version 8')
    if version < 14 and attachment['face'] == 'bevel' and attachment.get('segment') is not None:
        raise ValueError('Multi-edge bevel references require document version 14')
    if version < 12 and attachment['face'] == 'bevel':
        raise ValueError('Chamfer face references require document version 12')
    return FaceReference(**attachment)


def serialize_edge(edge):
    result = {'endpoints': [list(p) for p in edge.endpoints],
              'neighbors': [list(t) for t in edge.neighbors]}
    if edge.curve_type != 'line':
        result.update(curve_type=edge.curve_type, center=list(edge.center), radius=edge.radius,
                      axis=list(edge.axis), midpoint=list(edge.midpoint) if edge.midpoint is not None else None)
    return result


def deserialize_edge(edge, version):
    curved = isinstance(edge, dict) and 'curve_type' in edge
    extra = ('curve_type', 'center', 'radius', 'axis', 'midpoint') if curved and version >= 13 else ()
    fields(edge, ('endpoints', 'neighbors', *extra))
    geometry = {}
    if curved:
        if (edge['curve_type'] not in ('circle', 'arc')
                or any(not isinstance(edge[k], list) for k in ('center', 'axis'))
                or (edge['midpoint'] is not None and not isinstance(edge['midpoint'], list))):
            raise ValueError('Invalid persisted circular chamfer geometry')
        geometry = dict(curve_type=edge['curve_type'], center=tuple(edge['center']),
                        radius=edge['radius'], axis=tuple(edge['axis']),
                        midpoint=tuple(edge['midpoint']) if edge['midpoint'] is not None else None)
    if any(not isinstance(edge[k], list) or any(not isinstance(v, list) for v in edge[k])
           for k in ('endpoints', 'neighbors')):
        raise ValueError('Invalid persisted chamfer edge')
    return EdgeReference(tuple(tuple(p) for p in edge['endpoints']),
                              tuple(tuple(t) for t in edge['neighbors']), **geometry)

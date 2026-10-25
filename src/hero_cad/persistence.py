"""Strict versioned parameter serialization; no native shapes or transient selection."""
from dataclasses import asdict
from hero_cad.features import BoxParameters, ExtrudeParameters, BooleanParameters, Feature
from hero_cad.sketch import Circle, Line, Rectangle, SketchParameters, Slot, PlaneFrame, FaceReference, FaceSupport, FaceSnapshot


def fields(data, expected):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise ValueError('Invalid document fields: expected ' + ', '.join(expected))


def serialize(features):
    result, version = [], 3
    for feature in features:
        if feature.type in ('box', 'extrude', 'boolean'):
            parameters = asdict(feature.parameters)
            if feature.type == 'extrude':
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
        else:
            sketch = feature.parameters
            parameters = {'plane': sketch.plane,
                          'frame': {k: list(getattr(sketch.frame, k)) for k in ('origin', 'u', 'v')},
                          'entities': [{'type': type(e).__name__.lower(),
                                        'parameters': asdict(e)} for e in sketch.entities]}
            if sketch.attachment:
                version = max(version, 8 if sketch.attachment.segment == 'line' else 7 if sketch.attachment.face == 'evaluated' else 5)
                parameters['attachment'] = asdict(sketch.attachment)
                if sketch.attachment.snapshot is None:
                    parameters['attachment'].pop('snapshot')
                else:
                    version = max(version, 10)
                    snapshot = parameters['attachment']['snapshot']
                    snapshot['anchor'] = list(snapshot['anchor'])
                    snapshot['origins'] = list(snapshot['origins'])
                if sketch.attachment.support is None:
                    parameters['attachment'].pop('support')
                else:
                    version = max(version, 9)
                    support = parameters['attachment']['support']
                    support['origins'] = list(support['origins'])
                    support['anchor'] = list(support['anchor'])
        if not feature.sketch_visible:
            version = max(version, 11)
        result.append({'id': feature.id, 'type': feature.type, 'parameters': parameters,
                       'references': list(feature.references),
                       **({'sketch_visible': False} if not feature.sketch_visible else {})})
    return {'format': 'star-cad', 'version': version, 'units': 'mm', 'features': result}


def deserialize(data):
    if not isinstance(data, dict) or data.get('format') != 'star-cad' or data.get('units') != 'mm':
        raise ValueError('Expected a HERO-CAD document in millimetres')
    version = data.get('version')
    if type(version) is not int or version not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
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
        fields(item, ('id', 'type', 'parameters', 'references') + (('sketch_visible',) if visibility and version >= 11 else ()))
        if visibility and (item['type'] != 'sketch' or type(item['sketch_visible']) is not bool):
            raise ValueError('Invalid sketch visibility')
        if not isinstance(item['references'], list):
            raise ValueError('Invalid references')
        parameters = item['parameters']
        if item['type'] == 'box':
            fields(parameters, ('width', 'depth', 'height'))
            value = BoxParameters(**parameters)
        elif item['type'] == 'sketch':
            attached = version >= 5 and isinstance(parameters, dict) and parameters.get('plane') == 'FACE'
            fields(parameters, ('plane', 'frame', 'entities', 'attachment') if attached else ('plane', 'frame', 'entities'))
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
                fields(entity['parameters'], cls.__dataclass_fields__)
                entities.append(cls(**entity['parameters']))
            fields(parameters['frame'], ('origin', 'u', 'v'))
            if any(not isinstance(axis, list) or len(axis) != 3
                   or any(type(n) not in (int, float) for n in axis)
                   for axis in parameters['frame'].values()):
                raise ValueError('Invalid sketch frame')
            stored = PlaneFrame(parameters['plane'], **{k: tuple(v) for k,v in parameters['frame'].items()})
            if attached:
                attachment = parameters['attachment']
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
                if version < 7 and parameters['attachment']['face'] == 'evaluated':
                    raise ValueError('Evaluated face references require document version 7')
                if version < 8 and parameters['attachment']['segment'] == 'line':
                    raise ValueError('Line-profile side references require document version 8')
                value = SketchParameters('FACE', tuple(entities), FaceReference(**attachment), stored)
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
            fields(parameters, expected)
            if not isinstance(parameters['hole_ids'], list):
                raise ValueError('Profile holes must be a list')
            values = {**parameters, 'hole_ids': tuple(parameters['hole_ids'])}
            if line_profile:
                if not isinstance(parameters['line_ids'], list) or not parameters['line_ids']:
                    raise ValueError('Line-profile membership must be a nonempty list')
                values['line_ids'] = tuple(parameters['line_ids'])
            value = ExtrudeParameters(**values)
        elif item['type'] == 'boolean' and version >= 6:
            fields(parameters, ('operation', 'target_id', 'tool_ids'))
            if not isinstance(parameters['tool_ids'], list):
                raise ValueError('Boolean tools must be a list')
            value = BooleanParameters(parameters['operation'], parameters['target_id'], tuple(parameters['tool_ids']))
        else:
            raise ValueError('Unsupported feature type')
        result.append(Feature(item['type'], value, tuple(item['references']), item['id'], item.get('sketch_visible', True)))
    return tuple(result)

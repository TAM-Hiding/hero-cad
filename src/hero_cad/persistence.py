"""Strict versioned parameter serialization; no native shapes or transient selection."""
from dataclasses import asdict
from hero_cad.features import BoxParameters, ExtrudeParameters, BooleanParameters, Feature
from hero_cad.sketch import Circle, Line, Rectangle, SketchParameters, Slot, PlaneFrame, FaceReference


def fields(data, expected):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise ValueError('Invalid document fields: expected ' + ', '.join(expected))


def serialize(features):
    result = []
    for feature in features:
        if feature.type in ('box', 'extrude', 'boolean'):
            parameters = asdict(feature.parameters)
            if feature.type == 'extrude':
                parameters['hole_ids'] = list(parameters['hole_ids'])
                if feature.parameters.operation == 'new':
                    for key in ('operation', 'target_id', 'extent', 'direction'):
                        parameters.pop(key)
            if feature.type == 'boolean':
                parameters['tool_ids'] = list(parameters['tool_ids'])
        else:
            sketch = feature.parameters
            parameters = {'plane': sketch.plane,
                          'frame': {k: list(getattr(sketch.frame, k)) for k in ('origin', 'u', 'v')},
                          'entities': [{'type': type(e).__name__.lower(),
                                        'parameters': asdict(e)} for e in sketch.entities]}
            if sketch.attachment:
                parameters['attachment'] = asdict(sketch.attachment)
        result.append({'id': feature.id, 'type': feature.type, 'parameters': parameters,
                       'references': list(feature.references)})
    return {'format': 'star-cad', 'version': 6 if any(f.type == 'boolean' or (f.type == 'extrude' and f.parameters.operation != 'new') for f in features) else 5 if any(f.type == 'sketch' and f.parameters.attachment for f in features) else 4 if any(f.type == 'extrude' for f in features) else 3, 'units': 'mm', 'features': result}


def deserialize(data):
    if not isinstance(data, dict) or data.get('format') != 'star-cad' or data.get('units') != 'mm':
        raise ValueError('Expected a HERO-CAD document in millimetres')
    version = data.get('version')
    if type(version) is not int or version not in (1, 2, 3, 4, 5, 6):
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
        fields(item, ('id', 'type', 'parameters', 'references'))
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
                fields(parameters['attachment'], ('parent_id', 'face', 'boundary_id', 'segment'))
                value = SketchParameters('FACE', tuple(entities), FaceReference(**parameters['attachment']), stored)
            else:
                value = SketchParameters(parameters['plane'], tuple(entities))
                if stored != value.frame:
                    raise ValueError('Sketch frame must match its referenced origin plane')
        elif item['type'] == 'extrude' and version >= 4:
            extended = version >= 6 and isinstance(parameters, dict) and 'operation' in parameters
            fields(parameters, ('sketch_id', 'outer_id', 'hole_ids', 'distance', 'operation', 'target_id', 'extent', 'direction')
                   if extended else ('sketch_id', 'outer_id', 'hole_ids', 'distance'))
            if not isinstance(parameters['hole_ids'], list):
                raise ValueError('Profile holes must be a list')
            value = ExtrudeParameters(**{**parameters, 'hole_ids': tuple(parameters['hole_ids'])})
        elif item['type'] == 'boolean' and version >= 6:
            fields(parameters, ('operation', 'target_id', 'tool_ids'))
            if not isinstance(parameters['tool_ids'], list):
                raise ValueError('Boolean tools must be a list')
            value = BooleanParameters(parameters['operation'], parameters['target_id'], tuple(parameters['tool_ids']))
        else:
            raise ValueError('Unsupported feature type')
        result.append(Feature(item['type'], value, tuple(item['references']), item['id']))
    return tuple(result)

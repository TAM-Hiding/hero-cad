"""Strict versioned parameter serialization; no native shapes or transient selection."""
from dataclasses import asdict
from star_cad.features import BoxParameters, ExtrudeParameters, Feature
from star_cad.sketch import Circle, Line, Rectangle, SketchParameters, Slot


def fields(data, expected):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise ValueError('Invalid document fields: expected ' + ', '.join(expected))


def serialize(features):
    result = []
    for feature in features:
        if feature.type in ('box', 'extrude'):
            parameters = asdict(feature.parameters)
            if feature.type == 'extrude':
                parameters['hole_ids'] = list(parameters['hole_ids'])
        else:
            sketch = feature.parameters
            parameters = {'plane': sketch.plane,
                          'frame': {k: list(getattr(sketch.frame, k)) for k in ('origin', 'u', 'v')},
                          'entities': [{'type': type(e).__name__.lower(),
                                        'parameters': asdict(e)} for e in sketch.entities]}
        result.append({'id': feature.id, 'type': feature.type, 'parameters': parameters,
                       'references': list(feature.references)})
    return {'format': 'star-cad', 'version': 4 if any(f.type == 'extrude' for f in features) else 3, 'units': 'mm', 'features': result}


def deserialize(data):
    if not isinstance(data, dict) or data.get('format') != 'star-cad' or data.get('units') != 'mm':
        raise ValueError('Expected a STAR-CAD document in millimetres')
    version = data.get('version')
    if type(version) is not int or version not in (1, 2, 3, 4):
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
            fields(parameters, ('plane', 'frame', 'entities'))
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
            value = SketchParameters(parameters['plane'], tuple(entities))
            frame = {k: list(getattr(value.frame, k)) for k in ('origin', 'u', 'v')}
            fields(parameters['frame'], ('origin', 'u', 'v'))
            if any(not isinstance(axis, list) or len(axis) != 3
                   or any(type(n) not in (int, float) for n in axis)
                   for axis in parameters['frame'].values()):
                raise ValueError('Invalid sketch frame')
            if parameters['frame'] != frame:
                raise ValueError('Sketch frame must match its referenced origin plane')
        elif item['type'] == 'extrude' and version == 4:
            fields(parameters, ('sketch_id', 'outer_id', 'hole_ids', 'distance'))
            if not isinstance(parameters['hole_ids'], list):
                raise ValueError('Profile holes must be a list')
            value = ExtrudeParameters(parameters['sketch_id'], parameters['outer_id'], tuple(parameters['hole_ids']), parameters['distance'])
        else:
            raise ValueError('Unsupported feature type')
        result.append(Feature(item['type'], value, tuple(item['references']), item['id']))
    return tuple(result)

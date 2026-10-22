"""Transactional feature history, regeneration and local parameter files (mm)."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import tempfile
from star_cad.features import BoxParameters, ExtrudeParameters, Feature, FeatureError, FeatureStatus
from star_cad.geometry import make_box, make_sketch, compound
from star_cad.profiles import extrude_region
from star_cad.persistence import deserialize, serialize
from star_cad.sketch import SketchParameters


class Document:
    def __init__(self, parameters=None, *, features=None):
        self.features = tuple(features) if features is not None else (Feature('box', parameters or BoxParameters()),)
        self.shape, self.sketch_shapes, self.statuses, self.solid_shapes = self._regenerate(self.features)
        self.last_failure = None
        self.path = None
        self._saved_features = self.features
        self._undo, self._redo = [], []

    @property
    def parameters(self):
        return next(f.parameters for f in self.features if f.type == 'box')

    @property
    def sketches(self):
        return tuple(f for f in self.features if f.type == 'sketch')

    @property
    def dirty(self):
        return self.features != self._saved_features

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def feature(self, identifier):
        return next(f for f in self.features if f.id == identifier)

    def _regenerate(self, features):
        if not 1 <= len(features) <= 1000:
            raise FeatureError('document', 'Expected 1–1000 features')
        known = {'plane:XY', 'plane:XZ', 'plane:YZ'}
        statuses, sketch_shapes, solids, definitions = {}, {}, {}, {}
        if sum(f.type == 'box' for f in features) != 1:
            raise FeatureError('document', 'Exactly one box is supported in this milestone')
        entity_ids = set()
        for feature in features:
            try:
                if feature.id in known:
                    raise ValueError('Duplicate feature identifier')
                if any(ref not in known for ref in feature.references):
                    raise ValueError('Missing, cyclic or forward feature dependency')
                if feature.type == 'box':
                    solids[feature.id] = make_box(**asdict(feature.parameters))
                elif feature.type == 'sketch':
                    if 'plane:' + feature.parameters.plane not in feature.references:
                        raise ValueError('Sketch must reference its origin plane')
                    for entity in feature.parameters.entities:
                        if entity.id in entity_ids or entity.id in known:
                            raise ValueError('Duplicate entity identifier')
                        entity_ids.add(entity.id)
                    sketch_shapes[feature.id] = make_sketch(feature.parameters)
                else:
                    parameters = feature.parameters
                    if feature.references != (parameters.sketch_id,):
                        raise ValueError('Extrusion must reference exactly its source sketch')
                    source = definitions.get(parameters.sketch_id)
                    if source is None or source.type != 'sketch':
                        raise ValueError('Extrusion source must be an earlier sketch')
                    solids[feature.id] = extrude_region(source.parameters, parameters)
                known.add(feature.id)
                definitions[feature.id] = feature
                statuses[feature.id] = FeatureStatus(True)
            except Exception as error:
                raise FeatureError(feature.id, str(error)) from error
        if entity_ids.intersection(f.id for f in features):
            raise FeatureError('document', 'Entity and feature identifiers must be distinct')
        shape = next(iter(solids.values())) if len(solids) == 1 else compound(solids.values())
        return shape, sketch_shapes, statuses, solids

    def set_features(self, features):
        features = tuple(features)
        if features == self.features:
            return
        try:
            shape, sketch_shapes, statuses, solids = self._regenerate(features)
        except FeatureError as error:
            self.last_failure = error
            raise
        self._undo.append(self.features)
        self._redo.clear()
        self.features, self.shape, self.sketch_shapes, self.statuses = features, shape, sketch_shapes, statuses
        self.solid_shapes = solids
        self.last_failure = None

    def set_box(self, parameters):
        box = next(f for f in self.features if f.type == 'box')
        self.replace_feature(replace(box, parameters=parameters))

    def replace_feature(self, feature):
        self.feature(feature.id)  # Reject a nonexistent target.
        self.set_features(tuple(feature if f.id == feature.id else f for f in self.features))

    def add_sketch(self, plane):
        feature = Feature('sketch', SketchParameters(plane), ('plane:' + plane,))
        self.set_features(self.features + (feature,))
        return feature.id

    def add_entity(self, sketch_id, entity):
        feature = self.feature(sketch_id)
        parameters = replace(feature.parameters, entities=feature.parameters.entities + (entity,))
        self.replace_feature(replace(feature, parameters=parameters))

    def update_entity(self, sketch_id, entity):
        feature = self.feature(sketch_id)
        if not any(e.id == entity.id for e in feature.parameters.entities):
            raise ValueError('Unknown sketch entity')
        entities = tuple(entity if e.id == entity.id else e for e in feature.parameters.entities)
        self.replace_feature(replace(feature, parameters=replace(feature.parameters, entities=entities)))

    def add_extrusion(self, sketch_id, outer_id, hole_ids=(), distance=10.0):
        parameters = ExtrudeParameters(sketch_id, outer_id, tuple(sorted(hole_ids)), distance)
        feature = Feature('extrude', parameters, (sketch_id,))
        self.set_features(self.features + (feature,))
        return feature.id

    def delete(self, *, features=(), entities=()):
        """Delete feature IDs and (sketch ID, entity ID) pairs atomically."""
        feature_ids, entity_keys = set(features), set(map(tuple, entities))
        known = {f.id: f for f in self.features}
        if feature_ids - known.keys():
            raise ValueError('Unknown feature to delete')
        if any(known[i].type == 'box' for i in feature_ids):
            raise ValueError('The base box cannot be deleted in this milestone')
        for sketch_id, entity_id in entity_keys:
            if sketch_id not in known or known[sketch_id].type != 'sketch' or not any(
                    e.id == entity_id for e in known[sketch_id].parameters.entities):
                raise ValueError('Unknown sketch entity to delete')
        removed = feature_ids | {e for _, e in entity_keys}
        for feature in self.features:
            if feature.id not in feature_ids and removed.intersection(feature.references):
                raise ValueError(f'Cannot delete: {feature.type} {feature.id} references the selected feature')
            if feature.type == 'extrude' and feature.id not in feature_ids:
                p = feature.parameters
                if any((p.sketch_id, identifier) in entity_keys for identifier in (p.outer_id, *p.hole_ids)):
                    raise ValueError('Cannot delete: extrusion references the selected profile boundary')
        candidate = []
        for feature in self.features:
            if feature.id in feature_ids:
                continue
            if feature.type == 'sketch':
                remaining = tuple(e for e in feature.parameters.entities if (feature.id, e.id) not in entity_keys)
                feature = replace(feature, parameters=replace(feature.parameters, entities=remaining))
            candidate.append(feature)
        self.set_features(candidate)

    def undo(self):
        self._restore(self._undo, self._redo)

    def redo(self):
        self._restore(self._redo, self._undo)

    def _restore(self, source, destination):
        if not source:
            return
        features = source[-1]
        try:
            shape, sketch_shapes, statuses, solids = self._regenerate(features)
        except FeatureError as error:
            self.last_failure = error
            raise
        destination.append(self.features)
        source.pop()
        self.features, self.shape, self.sketch_shapes, self.statuses = features, shape, sketch_shapes, statuses
        self.solid_shapes = solids
        self.last_failure = None

    def save(self, path):
        """Replace only after a complete, flushed file exists in the same directory."""
        path = Path(path).expanduser().absolute()
        payload = serialize(self.features)
        contents = json.dumps(payload, indent=2, allow_nan=False) + '\n'
        if len(contents.encode('utf-8')) > 4 * 1024 * 1024:
            raise ValueError('Document exceeds the 4 MiB format limit')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.path = path
        self._saved_features = self.features

    @classmethod
    def load(cls, path):
        path = Path(path).expanduser().absolute()
        with path.open('rb') as stream:
            contents = stream.read(4 * 1024 * 1024 + 1)
        if len(contents) > 4 * 1024 * 1024:
            raise ValueError('Document exceeds the 4 MiB format limit')
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f'Duplicate document field: {key}')
                result[key] = value
            return result
        data = json.loads(contents.decode('utf-8'), object_pairs_hook=unique_object)
        features = deserialize(data)
        if data['version'] == 1 and len(contents) > 65536:
            raise ValueError('Legacy document exceeds the 64 KiB limit')
        document = cls(features=features)
        document.path = path
        return document

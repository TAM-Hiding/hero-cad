"""Transactional feature history, regeneration and local parameter files (mm)."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import tempfile
from hero_cad.features import BoxParameters, ExtrudeParameters, BooleanParameters, ChamferParameters, Feature, FeatureError, FeatureStatus
from hero_cad.geometry import make_box, make_sketch, compound
from hero_cad.profiles import extrude_region, resolve_region, ProfileError
from hero_cad.persistence import deserialize, serialize
from hero_cad.sketch import SketchParameters
from hero_cad.booleans import combine, through_distance, OperationError
from hero_cad.attachments import AttachmentError, resolve_attachment, identify_face
from hero_cad.face_history import primitive_lineage, evaluated_faces
from hero_cad.chamfers import edge_reference, resolve_edges, make_chamfer, tangent_chain


class Document:
    def __init__(self, parameters=None, *, features=None):
        self.features = tuple(features) if features is not None else (Feature('box', parameters or BoxParameters()),)
        self.shape, self.sketch_shapes, self.statuses, self.solid_shapes = self._regenerate(self.features)
        self.features = self._regenerated_features
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

    def _regenerate(self, features, *, restoring=False):
        if not 1 <= len(features) <= 1000:
            raise FeatureError('document', 'Expected 1–1000 features')
        known = {'plane:XY', 'plane:XZ', 'plane:YZ'}
        statuses, sketch_shapes, solids, definitions = {}, {}, {}, {}
        if sum(f.type == 'box' for f in features) != 1:
            raise FeatureError('document', 'Exactly one box is supported in this milestone')
        entity_ids, active = set(), set()
        # Restored snapshots may contain failed features deleted from the current
        # model. They are accepted history, not newly requested operations.
        existing = {f.id for f in self.features} if hasattr(self, 'statuses') and not restoring else None
        face_maps, lineages, resolved, source_faces = {}, {}, [], {}
        inputs = {f.id: f for f in features}
        for feature in features:
            try:
                if feature.id in known:
                    raise ValueError('Duplicate feature identifier')
                if any(ref not in known for ref in feature.references):
                    raise ValueError('Missing, cyclic or forward feature dependency')
                if feature.type == 'sketch':
                    p = feature.parameters
                    if p.attachment:
                        if feature.references != (p.attachment.parent_id,):
                            raise ValueError('Face sketch must reference exactly its parent feature')
                        if definitions[p.attachment.parent_id].type not in ('box', 'extrude', 'boolean', 'chamfer'):
                            raise ValueError('Attachment parent must be a solid feature')
                    elif 'plane:' + p.plane not in feature.references:
                        raise ValueError('Sketch must reference its origin plane')
                    for entity in p.entities:
                        if entity.id in entity_ids or entity.id in known:
                            raise ValueError('Duplicate entity identifier')
                        entity_ids.add(entity.id)
                if feature.type == 'extrude':
                    expected = (feature.parameters.sketch_id,) + ((feature.parameters.target_id,) if feature.parameters.target_id else ())
                    if feature.references != expected:
                        raise ValueError('Extrusion must reference its source sketch and explicit target')
                    source = definitions.get(feature.parameters.sketch_id)
                    if source is None or source.type != 'sketch':
                        raise ValueError('Extrusion source must be an earlier sketch')
                if feature.type == 'boolean':
                    p = feature.parameters
                    if feature.references != (p.target_id, *p.tool_ids):
                        raise ValueError('Boolean references must match target and tools')
                if feature.type == 'chamfer' and feature.references != (feature.parameters.target_id,):
                    raise ValueError('Chamfer must reference exactly its target body')
                targets = ((feature.parameters.target_id, *feature.parameters.tool_ids) if feature.type == 'boolean'
                           else (feature.parameters.target_id,) if feature.type in ('extrude', 'chamfer') and feature.parameters.target_id else ())
                if any(definitions[t].type not in ('box', 'extrude', 'boolean', 'chamfer') for t in targets):
                    raise ValueError('Operation inputs must be earlier solid features')
                blocked = next((ref for ref in feature.references if ref in statuses and not statuses[ref].valid), None)
                if blocked:
                    if (existing is not None and feature.type == 'chamfer'
                            and (feature.id not in existing or feature != self.feature(feature.id))):
                        raise OperationError('Cannot commit chamfer: target body is unresolved')
                    statuses[feature.id] = FeatureStatus(False, f'Unresolved dependency {blocked}: {statuses[blocked].error}')
                else:
                    try:
                        if feature.type == 'box':
                            solids[feature.id], face_maps[feature.id] = make_box(**asdict(feature.parameters), with_faces=True)
                            source_faces[feature.id] = face_maps[feature.id]
                            lineages[feature.id] = primitive_lineage(feature.id, face_maps[feature.id])
                            active.add(feature.id)
                        elif feature.type == 'sketch':
                            p = feature.parameters
                            if p.attachment:
                                parent = definitions[p.attachment.parent_id]
                                previous_source = inputs[parent.parameters.sketch_id].parameters.frame if parent.type == 'extrude' else None
                                frame = resolve_attachment(p.attachment, face_maps, definitions,
                                                           previous_frame=p.attached_frame,
                                                           previous_source_frame=previous_source,
                                                           lineages=lineages, source_faces=source_faces, bodies=solids)
                                feature = replace(feature, parameters=replace(p, attached_frame=frame))
                            sketch_shapes[feature.id] = make_sketch(feature.parameters)
                        else:
                            if any(t not in active for t in targets):
                                raise OperationError('Target/tool is not a current resulting body')
                            if feature.type == 'boolean':
                                result, lineage = combine(feature.parameters.operation, solids[targets[0]],
                                                          [solids[t] for t in targets[1:]],
                                                          lineages=[lineages[t] for t in targets])
                                faces = evaluated_faces(lineage)
                            elif feature.type == 'chamfer':
                                result, lineage, sources = make_chamfer(feature.parameters, solids[targets[0]],
                                                                       lineages[targets[0]], feature.id)
                                source_faces[feature.id] = sources
                                faces = evaluated_faces(lineage)
                                faces.update(sources)
                            else:
                                p = feature.parameters
                                if p.extent == 'through_all':
                                    p = replace(p, distance=through_distance(source.parameters.frame, solids[p.target_id], p.direction))
                                result, faces = extrude_region(source.parameters, p, with_faces=True)
                                source_faces[feature.id] = faces
                                lineage = primitive_lineage(feature.id, faces)
                                if p.operation != 'new':
                                    result, lineage = combine(p.operation, solids[p.target_id], [result],
                                                              lineages=[lineages[p.target_id], lineage])
                                    faces = evaluated_faces(lineage)
                            solids[feature.id], face_maps[feature.id] = result, faces
                            lineages[feature.id] = lineage
                            active.difference_update(targets)
                            active.add(feature.id)
                        statuses[feature.id] = FeatureStatus(True, reference_state='resolved' if feature.type == 'chamfer' or feature.type == 'sketch' and feature.parameters.attachment else None)
                    except (OperationError, ProfileError) as error:
                        if existing is not None and feature.id not in existing:
                            raise
                        # Direct distance edits must not replace a valid model
                        # with failed output. Upstream invalidation and accepted
                        # history restoration instead preserve unresolved features.
                        if (existing is not None and feature.type == 'chamfer'
                                and feature != self.feature(feature.id)):
                            raise
                        statuses[feature.id] = FeatureStatus(False, str(error))
                    except AttachmentError as error:
                        # Lost semantic faces remain in history, never substituted.
                        statuses[feature.id] = FeatureStatus(False, str(error), error.state.value)
                known.add(feature.id)
                definitions[feature.id] = feature
                resolved.append(feature)
            except Exception as error:
                raise FeatureError(feature.id, str(error)) from error
        if entity_ids.intersection(f.id for f in features):
            raise FeatureError('document', 'Entity and feature identifiers must be distinct')
        # Construct the final display-independent compound before publishing any
        # candidate cache. A failure must preserve the entire previous model.
        try:
            shape = compound(solids[i] for i in solids if i in active)
        except Exception as error:
            raise FeatureError('document', str(error)) from error
        self.active_body_ids = frozenset(active)
        self._regenerated_features, self.face_maps = tuple(resolved), face_maps
        self.face_lineages, self.source_faces = lineages, source_faces
        return shape, sketch_shapes, statuses, solids

    def _leaf_sketch_shapes(self, features):
        """Evaluate one entity-only leaf edit without replacing any solid state.

        Definitions/references remain authoritative. Anything outside this narrow
        boundary (including unresolved history) uses ordered regeneration.
        Return a candidate sketch map; publish nothing until evaluation succeeds.
        """
        if len(features) != len(self.features) or not all(s.valid for s in self.statuses.values()):
            return None
        changes = [(old, new) for old, new in zip(self.features, features) if old != new]
        if len(changes) != 1:
            return None
        old, new = changes[0]
        if old.type != 'sketch' or new.type != 'sketch':
            return None
        if replace(new, parameters=replace(new.parameters, entities=old.parameters.entities)) != old:
            return None
        if any(old.id in f.references for f in features):
            return None
        # Match full regeneration's global entity/feature identifier validation.
        identifiers = {f.id for f in features} | {'plane:XY', 'plane:XZ', 'plane:YZ'}
        for feature in features:
            if feature.type == 'sketch':
                for entity in feature.parameters.entities:
                    if entity.id in identifiers:
                        raise FeatureError(feature.id, 'Duplicate entity identifier')
                    identifiers.add(entity.id)
        try:
            shape = make_sketch(new.parameters)
        except Exception as error:
            raise FeatureError(new.id, str(error)) from error
        return {**self.sketch_shapes, new.id: shape}

    def set_features(self, features):
        features = tuple(features)
        if features == self.features:
            return
        presentation_only = tuple(replace(f, sketch_visible=True) for f in features) == tuple(
            replace(f, sketch_visible=True) for f in self.features)
        try:
            if presentation_only:
                shape, sketch_shapes, statuses, solids = self.shape, self.sketch_shapes, self.statuses, self.solid_shapes
                self._regenerated_features = features
            else:
                sketch_shapes = self._leaf_sketch_shapes(features)
                if sketch_shapes is None:
                    shape, sketch_shapes, statuses, solids = self._regenerate(features)
                else:
                    shape, statuses, solids = self.shape, self.statuses, self.solid_shapes
                    self._regenerated_features = features
        except FeatureError as error:
            self.last_failure = error
            raise
        self._undo.append(self.features)
        self._redo.clear()
        self.features, self.shape, self.sketch_shapes, self.statuses = self._regenerated_features, shape, sketch_shapes, statuses
        self.solid_shapes = solids
        self.last_failure = None

    def set_sketch_visibility(self, identifier, visible):
        feature = self.feature(identifier)
        if feature.type != 'sketch' or type(visible) is not bool:
            raise ValueError('Expected sketch and boolean visibility')
        self.replace_feature(replace(feature, sketch_visible=visible))

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

    def face_reference(self, face, *, point=None):
        return identify_face(face, self.face_maps, {f.id: f for f in self.features},
                             active_ids=self.active_body_ids, lineages=self.face_lineages,
                             source_faces=self.source_faces, point=point, bodies=self.solid_shapes)

    def face_descendants(self, source_reference, evaluated_id):
        """Current faces descended from a semantic construction face at a history stage.

        This is an ancestry query, never a promise that one descendant is the
        intended attachment. Geometry and traversal order are not identities.
        """
        if source_reference.face == 'evaluated':
            raise ValueError('Descendant query requires a construction face reference')
        parent = self.feature(source_reference.parent_id)
        self.feature(evaluated_id)
        key = (source_reference.face if parent.type == 'box' else
               (source_reference.face, source_reference.boundary_id, source_reference.segment))
        token = json.dumps([parent.id, key], separators=(',', ':'))
        return tuple(face for face,tokens in self.face_lineages.get(evaluated_id, ()) if token in tokens)

    def add_face_sketch(self, reference):
        definitions = {f.id: f for f in self.features}
        frame = resolve_attachment(reference, self.face_maps, definitions,
                                   lineages=self.face_lineages, source_faces=self.source_faces, bodies=self.solid_shapes)
        feature = Feature('sketch', SketchParameters('FACE', attachment=reference, attached_frame=frame),
                          (reference.parent_id,))
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

    def add_extrusion(self, sketch_id, outer_id, hole_ids=(), distance=10.0, *,
                      operation='new', target_id=None, extent='distance', direction=1):
        parameters = ExtrudeParameters(sketch_id, outer_id, tuple(sorted(hole_ids)), distance,
                                       operation, target_id, extent, direction)
        refs = (sketch_id,) + ((target_id,) if target_id else ())
        feature = Feature('extrude', parameters, refs)
        try:
            source = next((f for f in self.features if f.id == sketch_id and f.type == 'sketch'), None)
            if source is None:
                raise ValueError('Extrusion source must be an earlier sketch')
            region = resolve_region(source.parameters, outer_id, hole_ids)
        except ValueError as error:
            self.last_failure = FeatureError(feature.id, str(error))
            raise self.last_failure from error
        feature = replace(feature, parameters=replace(parameters, line_ids=region.line_ids))
        self.set_features(self.features + (feature,))
        return feature.id

    def add_boolean(self, operation, target_id, tool_ids):
        parameters = BooleanParameters(operation, target_id, tuple(tool_ids))
        feature = Feature('boolean', parameters, (target_id, *parameters.tool_ids))
        self.set_features(self.features + (feature,))
        return feature.id

    def edge_reference(self, edge):
        target, references = self.edge_references((edge,))
        return target, references[0]

    def edge_references(self, edges):
        from OCP.TopAbs import TopAbs_EDGE
        from hero_cad.face_history import subshapes
        edges = tuple(edges)
        if not edges:
            raise OperationError('Select at least one straight, circular or arc edge on a current solid body')
        if len(edges) > 256:
            raise OperationError('Chamfer supports at most 256 selected edges')
        body_edges = {i: subshapes(self.solid_shapes[i], TopAbs_EDGE) for i in self.active_body_ids}
        targets = []
        for edge in edges:
            owners = [i for i,items in body_edges.items() if any(edge.IsSame(item) for item in items)]
            if len(owners) != 1:
                raise OperationError('Each selected edge must belong to exactly one current solid body')
            targets.append(owners[0])
        if len(set(targets)) != 1:
            raise OperationError('All chamfer edges must belong to the same current solid body')
        target = targets[0]
        references = tuple(edge_reference(edge, self.face_lineages[target]) for edge in edges)
        parameters = ChamferParameters(target, references)
        resolve_edges(parameters.edges, self.solid_shapes[target], self.face_lineages[target])
        return target, parameters.edges

    def tangent_edges(self, seed):
        target, _ = self.edge_reference(seed)
        edges = tangent_chain(seed, self.solid_shapes[target], self.face_lineages[target])
        self.edge_references(edges)  # Reject ambiguous/duplicate witnesses before selection publication.
        return edges

    def add_chamfer(self, target_id, edge, distance=1.0):
        if target_id not in self.active_body_ids:
            raise OperationError('Chamfer target must be a current resolved solid body')
        feature = Feature('chamfer', ChamferParameters(target_id, edge, distance), (target_id,))
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
                if any((p.sketch_id, identifier) in entity_keys for identifier in (p.outer_id, *p.hole_ids, *p.line_ids)):
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
            shape, sketch_shapes, statuses, solids = self._regenerate(features, restoring=True)
        except FeatureError as error:
            self.last_failure = error
            raise
        destination.append(self.features)
        source.pop()
        self.features, self.shape, self.sketch_shapes, self.statuses = self._regenerated_features, shape, sketch_shapes, statuses
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

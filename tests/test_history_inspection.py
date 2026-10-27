from dataclasses import replace

import pytest

from hero_cad.document import Document
from hero_cad.features import Feature
from hero_cad.history_inspection import feature_history_text
from hero_cad.sketch import Circle, FaceReference
from test_history_foundation import failed_boolean


def chain():
    doc = Document()
    box = doc.features[0].id
    sketch = doc.add_face_sketch(FaceReference(box, '+Z'))
    circle = Circle(10, 10, 2)
    doc.add_entity(sketch, circle)
    cut = doc.add_extrusion(sketch, circle.id, operation='cut', target_id=box,
                            extent='through_all', direction=-1)
    return doc, box, sketch, circle, cut


def test_order_direct_relationships_parameters_and_roles():
    doc, box, sketch, circle, cut = chain()
    box_text = feature_history_text(doc, box)
    assert 'History position: 1 of 3' in box_text
    assert 'Historical geometry · consumed' in box_text
    assert 'Direct parents:\nNone' in box_text
    assert 'Direct dependents:\n#2 · Sketch 1 — Supporting face · +Z\n#3 · Extrusion 1 — Boolean target body · Cut' in box_text
    text = feature_history_text(doc, sketch)
    assert 'History position: 2 of 3' in text
    assert 'Direct parents:\n#1 · Box 1' in text
    assert 'Direct dependents:\n#3 · Extrusion 1' in text
    assert 'Attachment: Semantic / exact face reference' in text
    assert 'Face: +Z' in text and 'Entities: 1 · 1 Circle' in text
    text = feature_history_text(doc, cut)
    assert 'Status: Valid' in text and 'Current resulting body' in text
    assert 'Direct parents:\n#2 · Sketch 1 — Source profile sketch\n#1 · Box 1 — Boolean target body · Cut' in text
    assert 'Direct dependents:\nNone' in text
    assert 'Extent: Through All' in text and 'Direction: -1' in text
    assert 'not the evaluated Through All depth' in text
    assert f'Outer boundary ID: {circle.id}' in text
    sid = doc.add_sketch('YZ')
    assert 'Direct parents:\nYZ origin plane' in feature_history_text(doc, sid)
    assert 'History position: 4 of 4' in feature_history_text(doc, sid)


def test_unresolved_and_blocked_are_distinct_from_historical():
    doc, sketch, circle, result = failed_boolean()
    text = feature_history_text(doc, result)
    assert 'Status: Unresolved' in text and 'Geometry: No evaluated output' in text
    assert doc.statuses[result].error in text
    assert 'Historical geometry' not in text
    assert 'Operation: Join' in text and 'Tools:\n#3 · Extrusion 1' in text
    # Existing face-dependent sketches can be blocked by a failed operation.
    doc.update_entity(sketch, circle)
    face = next(iter(doc.face_maps[result].values()))
    attached = doc.add_face_sketch(doc.face_reference(face))
    doc.update_entity(sketch, replace(circle, x=40))
    text = feature_history_text(doc, attached)
    assert 'Status: Blocked by unresolved dependencies' in text
    assert doc.statuses[attached].error in text
    assert 'Local frame (last resolved)' in text
    assert 'Direct parents:\n#4 · Combine 1' in text


def test_inspection_is_read_only_and_never_regenerates(monkeypatch, tmp_path):
    doc, box, sketch, _, _ = chain()
    doc.set_sketch_visibility(sketch, False)
    doc.save(tmp_path / 'history.starcad')
    before = dict(doc.__dict__)
    stacks = list(doc._undo), list(doc._redo)
    def forbidden(*args, **kwargs):
        pytest.fail('Inspection attempted to regenerate')
    monkeypatch.setattr(Document, '_regenerate', forbidden)
    for _ in range(3):
        for feature in doc.features:
            feature_history_text(doc, feature.id)
    text = feature_history_text(doc, sketch)
    assert 'Status: Valid' in text and 'Hidden (display only' in text
    assert doc.__dict__ == before and (doc._undo, doc._redo) == stacks
    assert not doc.dirty


def test_large_history_reports_all_direct_dependents_without_entity_dump():
    doc = Document()
    box = doc.features[0].id
    template = doc.add_face_sketch(FaceReference(box, '+Z'))
    parameters = doc.feature(template).parameters
    children = tuple(Feature('sketch', parameters, (box,)) for _ in range(999))
    doc = Document(features=(doc.features[0], *children))
    text = feature_history_text(doc, box)
    assert 'History position: 1 of 1000' in text
    assert '#2 · Sketch 1' in text and '#1000 · Sketch 999' in text
    assert text.count(' · Sketch ') == 999
    assert 'History position: 1000 of 1000' in feature_history_text(doc, children[-1].id)



def test_signed_distance_precision_and_history_reopen(tmp_path):
    doc = Document()
    sketch = doc.add_sketch('XZ')
    circle = Circle(0, 0, 1)
    doc.add_entity(sketch, circle)
    extrusion = doc.add_extrusion(sketch, circle.id, distance=-1.2345678901234567)
    before = feature_history_text(doc, extrusion)
    assert 'Signed distance: -1.2345678901234567 mm' in before
    f = doc.feature(extrusion)
    doc.replace_feature(replace(f, parameters=replace(f.parameters, distance=-5)))
    assert 'Signed distance: -5 mm' in feature_history_text(doc, extrusion)
    doc.undo()
    assert feature_history_text(doc, extrusion) == before
    doc.redo()
    doc.save(tmp_path / 'history.starcad')
    assert feature_history_text(Document.load(doc.path), extrusion) == feature_history_text(doc, extrusion)


def test_missing_semantic_face_reports_reference_error_and_last_frame():
    from hero_cad.sketch import Rectangle
    doc = Document()
    sketch = doc.add_sketch('XY')
    rectangle = Rectangle(0, 0, 10, 10)
    doc.add_entity(sketch, rectangle)
    extrusion = doc.add_extrusion(sketch, rectangle.id)
    attached = doc.add_face_sketch(FaceReference(extrusion, 'side', rectangle.id, 'edge0'))
    doc.update_entity(sketch, Circle(0, 0, 5, id=rectangle.id))
    text = feature_history_text(doc, attached)
    assert 'Status: Unresolved' in text
    assert 'Face reference: Missing' in text
    assert 'Local frame (last resolved)' in text
    assert doc.statuses[attached].error in text
    assert 'Blocked by' not in text


def joined_transition_chain():
    """A source body with a face sketch/cut, before conversion to Join."""
    from hero_cad.features import BoxParameters
    doc = Document(BoxParameters(10, 10, 10))
    box = doc.features[0].id
    source = doc.add_sketch('XY')
    circle = Circle(5, 5, 2)
    doc.add_entity(source, circle)
    extrusion = doc.add_extrusion(source, circle.id, distance=15)
    attached = doc.add_face_sketch(FaceReference(extrusion, 'end'))
    frame = doc.feature(attached).parameters.frame
    x, y = frame.to_local((5, 5, 15))
    hole = Circle(x, y, .5)
    doc.add_entity(attached, hole)
    cut = doc.add_extrusion(attached, hole.id, distance=-2,
                            operation='cut', target_id=extrusion)
    return doc, box, source, extrusion, attached, cut


def convert_to_join(doc, box, source, extrusion):
    f = doc.feature(extrusion)
    doc.replace_feature(replace(f, references=(source, box),
                                parameters=replace(f.parameters, operation='join', target_id=box)))


def test_new_body_to_join_reports_downstream_faces_and_cuts_without_repair(tmp_path):
    doc, box, source, extrusion, attached, cut = joined_transition_chain()
    assert all(s.valid for s in doc.statuses.values())
    attachment = doc.feature(attached).parameters.attachment
    before = feature_history_text(doc, attached)
    convert_to_join(doc, box, source, extrusion)
    assert doc.statuses[extrusion].valid
    text = feature_history_text(doc, extrusion)
    assert '#2 · Sketch 1 — Source profile sketch' in text
    assert '#1 · Box 1 — Boolean target body · Join' in text
    assert '#4 · Sketch 2 — Supporting face · End Face' in text
    assert '#5 · Extrusion 2 — Boolean target body · Cut' in text
    assert text.index('Technical identifiers:') > text.index('Stored parameters:')
    assert f'Feature UUID: {extrusion}' in text
    assert doc.feature(attached).parameters.attachment == attachment
    assert not doc.statuses[attached].valid
    assert 'Status: Unresolved' in feature_history_text(doc, attached)
    assert doc.statuses[attached].error in feature_history_text(doc, attached)
    assert 'Status: Blocked by unresolved dependencies' in feature_history_text(doc, cut)
    assert doc.statuses[cut].error in feature_history_text(doc, cut)
    failed = [feature_history_text(doc, f.id) for f in doc.features]
    doc.undo()
    assert feature_history_text(doc, attached) == before
    assert all(s.valid for s in doc.statuses.values())
    doc.redo()
    assert [feature_history_text(doc, f.id) for f in doc.features] == failed
    doc.save(tmp_path / 'joined-history.starcad')
    loaded = Document.load(doc.path)
    assert [feature_history_text(loaded, f.id) for f in loaded.features] == failed
    assert loaded.feature(attached).parameters.attachment == attachment


def test_combine_reports_target_and_tool_roles_in_both_directions():
    doc, _, _, result = failed_boolean()
    p = doc.feature(result).parameters
    text = feature_history_text(doc, result)
    assert '#1 · Box 1 — Boolean target body' in text
    assert '#3 · Extrusion 1 — Boolean tool body' in text
    assert '#4 · Combine 1 — Boolean target body' in feature_history_text(doc, p.target_id)
    assert '#4 · Combine 1 — Boolean tool body' in feature_history_text(doc, p.tool_ids[0])

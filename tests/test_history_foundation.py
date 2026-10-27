"""History regressions using real OCCT results and failure injection at commit."""
from dataclasses import replace

import pytest
from OCP.BRepCheck import BRepCheck_Analyzer

from hero_cad.document import Document
from hero_cad.features import BoxParameters, FeatureError
from hero_cad.geometry import volume
from hero_cad.sketch import Circle, FaceReference


def failed_boolean():
    doc = Document(BoxParameters(10, 10, 10))
    sketch = doc.add_sketch('XY')
    circle = Circle(5, 5, 2)
    doc.add_entity(sketch, circle)
    tool = doc.add_extrusion(sketch, circle.id, distance=15)
    result = doc.add_boolean('join', doc.features[0].id, (tool,))
    doc.update_entity(sketch, replace(circle, x=40))
    assert not doc.statuses[result].valid
    return doc, sketch, circle, result


def test_delete_failed_operation_undo_redo_and_reopen(tmp_path):
    doc, sketch, circle, result = failed_boolean()
    failed_features, failed_status = doc.features, doc.statuses[result]
    doc.delete(features=(result,))
    doc.undo()
    assert doc.features == failed_features
    assert doc.statuses[result] == failed_status
    assert result not in doc.solid_shapes
    doc.redo()
    assert result not in {f.id for f in doc.features}
    doc.undo()
    doc.save(tmp_path / 'failed-history.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == doc.features
    assert loaded.statuses[result] == failed_status
    loaded.update_entity(sketch, circle)
    assert loaded.statuses[result].valid
    assert BRepCheck_Analyzer(loaded.solid_shapes[result]).IsValid()


def test_delete_unresolved_line_extrusion_restores_downstream_chain():
    from hero_cad.profiles import regions
    from hero_cad.sketch import Line
    doc = Document()
    sketch = doc.add_sketch('XY')
    lines = (Line(0, 0, 10, 0), Line(10, 0, 0, 10), Line(0, 10, 0, 0))
    for line in lines:
        doc.add_entity(sketch, line)
    region, = regions(doc.feature(sketch).parameters)
    extrusion = doc.add_extrusion(sketch, region.outer_id, distance=2)
    cap = doc.add_face_sketch(FaceReference(extrusion, 'end'))
    circle = Circle(2, 2, .5)
    doc.add_entity(cap, circle)
    downstream = doc.add_extrusion(cap, circle.id, distance=1)
    doc.update_entity(sketch, replace(lines[0], x2=11))
    before = doc.features
    assert all(not doc.statuses[i].valid for i in (extrusion, cap, downstream))
    doc.delete(features=(extrusion, cap, downstream))
    doc.undo()
    assert doc.features == before
    assert all(not doc.statuses[i].valid for i in (extrusion, cap, downstream))
    assert all(i not in doc.solid_shapes for i in (extrusion, downstream))
    assert cap not in doc.sketch_shapes
    doc.redo()
    assert all(i not in doc.statuses for i in (extrusion, cap, downstream))
    doc.undo()
    doc.update_entity(sketch, lines[0])
    assert all(s.valid for s in doc.statuses.values())
    assert volume(doc.solid_shapes[extrusion]) == pytest.approx(100)


@pytest.mark.parametrize('action', ['edit', 'undo', 'redo'])
def test_final_shape_failure_preserves_all_published_state(monkeypatch, action):
    import hero_cad.document as module
    doc = Document()
    sketch = doc.add_sketch('XY')
    circle = Circle(0, 0, 2)
    doc.add_entity(sketch, circle)
    extrusion = doc.add_extrusion(sketch, circle.id)
    if action != 'undo':
        doc.undo()  # Failed candidate would add another active body.
    names = ('features', 'shape', 'sketch_shapes', 'statuses', 'solid_shapes',
             'active_body_ids', 'face_maps', 'face_lineages', 'source_faces',
             '_regenerated_features')
    before = {name: getattr(doc, name) for name in names}
    stacks = list(doc._undo), list(doc._redo)
    def fail(shapes):
        raise ValueError('final compound failure')
    monkeypatch.setattr(module, 'compound', fail)
    with pytest.raises(FeatureError, match='final compound failure'):
        if action == 'undo':
            doc.undo()  # Would remove the current extrusion body.
        elif action == 'redo':
            doc.redo()
        else:
            doc.add_extrusion(sketch, circle.id)
    for name, value in before.items():
        assert getattr(doc, name) is value, name
    assert (doc._undo, doc._redo) == stacks
    assert doc.last_failure.feature_id == 'document'


def test_new_invalid_operation_still_rejected():
    doc, _, _, result = failed_boolean()
    feature = doc.feature(result)
    doc.delete(features=(result,))
    before, history = doc.features, list(doc._undo)
    with pytest.raises(FeatureError, match='overlap'):
        doc.add_boolean(feature.parameters.operation, feature.parameters.target_id,
                        feature.parameters.tool_ids)
    assert doc.features == before and doc._undo == history


def test_face_dependency_chain_updates_and_batch_delete_is_undoable(tmp_path):
    doc = Document(BoxParameters(10, 10, 10))
    box = doc.features[0].id
    sketch = doc.add_face_sketch(FaceReference(box, '+Z'))
    circle = Circle(5, 5, 2)
    doc.add_entity(sketch, circle)
    cut = doc.add_extrusion(sketch, circle.id, distance=-3,
                            operation='cut', target_id=box)
    doc.set_box(BoxParameters(10, 10, 20))
    assert doc.feature(sketch).parameters.frame.origin[2] == pytest.approx(20)
    from math import pi
    assert volume(doc.solid_shapes[cut]) == pytest.approx(2000 - 12*pi)
    with pytest.raises(ValueError, match='references'):
        doc.delete(features=(sketch,))
    before = doc.features
    doc.delete(features=(sketch, cut))
    assert doc.active_body_ids == {box}
    doc.undo()
    assert doc.features == before and doc.active_body_ids == {cut}
    doc.save(tmp_path / 'chain.starcad')
    loaded = Document.load(doc.path)
    assert loaded.features == before
    assert BRepCheck_Analyzer(loaded.solid_shapes[cut]).IsValid()
    assert volume(loaded.shape) == pytest.approx(volume(doc.shape))

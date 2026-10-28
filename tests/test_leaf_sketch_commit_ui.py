import pytest
from PySide6.QtCore import QSignalBlocker
from hero_cad.document import Document, BoxParameters
from hero_cad.sketch import Circle, Line, FaceReference
from test_sketch_ui import window
from test_viewport import project


def test_commits_reuse_mesh_picking_and_support_then_history_rebuilds(qtbot, monkeypatch):
    w = window(qtbot)
    w.show_base_box.setChecked(True)
    d, v = w.document, w.viewport
    box = d.features[0].id
    sid = d.add_face_sketch(FaceReference(box, '+Z'))
    w.refresh()
    v.sketch.enter(sid)
    mesh, wire = v.mapper.GetInput(), v.edge_mapper.GetInput()
    faces, edges = v.faces, v.edges
    support = v.support_mapper.GetInput()
    frame = d.feature(sid).parameters.frame
    calls = []
    display = w.display_solids
    def tracked(*a, **kw):
        calls.append(True)
        return display(*a, **kw)
    monkeypatch.setattr(w, 'display_solids', tracked)
    for entity in (Line(50, 50, 55, 55), Circle(60, 60, 2)):
        w.entity_created(entity)
        assert not calls
        assert v.mapper.GetInput() is mesh and v.edge_mapper.GetInput() is wire
        assert v.faces is faces and v.edges is edges
        assert v.support_mapper.GetInput() is support and v.support_actor.GetVisibility()
        assert d.feature(sid).parameters.frame == frame
        assert v.actor.GetProperty().GetOpacity() == pytest.approx(.35)
    # Numeric edit of an existing unused entity goes through the same safe path.
    w.entity_fields['radius'].setValue(3)
    assert w.apply_dimensions()
    assert d.feature(sid).parameters.entities[-1].radius == 3
    assert not calls
    w.finish_sketch()
    v.orient('Front')
    v.set_selection_mode('face')
    v.pick_at(*project(v, (20, 0, 10)))
    assert v.selection.kind == 'face'
    reference = d.face_reference(v.selection.shape)
    assert reference.parent_id == box
    v.set_selection_mode('edge')
    v.pick_at(*project(v, (20, 0, 0)))
    assert v.selection.kind == 'edge'
    assert v.selection.shape.IsSame(edges[v.selection.index])
    # A picked face can still establish a real attached sketch.
    added = d.add_face_sketch(reference)
    assert d.statuses[added].valid
    w.refresh()
    calls.clear()
    w.undo()
    w.redo()
    assert len(calls) == 2
    assert v.faces is not faces and v.edges is not edges
    v.orient('Front')
    v.set_selection_mode('face')
    v.pick_at(*project(v, (20, 0, 10)))
    assert d.face_reference(v.selection.shape) == reference
    v.set_selection_mode('edge')
    v.pick_at(*project(v, (20, 0, 0)))
    assert v.selection.kind == 'edge'
    assert v.selection.shape.IsSame(v.edges[v.selection.index])


def test_reuse_guard_rebuilds_for_visibility_document_and_solid_changes(qtbot, monkeypatch):
    w = window(qtbot)
    calls = []
    display = w.display_solids
    def tracked(*a, **kw):
        calls.append(True)
        return display(*a, **kw)
    monkeypatch.setattr(w, 'display_solids', tracked)
    w.document.set_box(BoxParameters(width=55))
    w.refresh(reuse_unchanged_solids=True)
    assert len(calls) == 1
    w.document = Document(features=w.document.features)
    w.refresh(reuse_unchanged_solids=True)
    assert len(calls) == 2
    w._base_box_visibility_explicit = True
    with QSignalBlocker(w.show_base_box):
        w.show_base_box.setChecked(not w.show_base_box.isChecked())
    w.refresh(reuse_unchanged_solids=True)
    assert len(calls) == 3


def test_consumed_entity_commit_rebuilds_presentation(qtbot, monkeypatch):
    w = window(qtbot)
    sid = w.document.add_sketch('XY')
    c = Circle(5, 5, 2)
    w.document.add_entity(sid, c)
    w.document.add_extrusion(sid, c.id)
    w.refresh()
    w.viewport.sketch.enter(sid)
    mesh = w.viewport.mapper.GetInput()
    w.entity_created(Line(50, 50, 55, 55))
    assert w.viewport.mapper.GetInput() is not mesh

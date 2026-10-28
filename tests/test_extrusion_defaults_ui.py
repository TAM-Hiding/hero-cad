"""Context defaults exercise the real preview/commit/history pipeline."""
from math import pi
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.geometry import volume
from hero_cad.sketch import Circle, Rectangle, FaceReference
from test_sketch_ui import window
from test_boolean_ui import choose
from test_booleans import cylinder


def face_profile(qtbot, *, x=5):
    w = window(qtbot)
    w.show_base_box.setChecked(False)
    w.show_base_box.setChecked(True)
    d = w.document
    d.set_box(BoxParameters(10,10,10))
    owner = d.features[0].id
    sid = d.add_face_sketch(FaceReference(owner,'+Z'))
    circle = Circle(x,5,2)
    d.add_entity(sid,circle)
    w.refresh()
    return w, owner, (sid,circle.id,())


@pytest.mark.parametrize('quick',[False,True])
def test_attached_join_preview_commit_undo_redo_and_reopen(qtbot,tmp_path,quick):
    w,owner,source = face_profile(qtbot)
    d,p = w.document,w.operation_panel
    before,count = d.features,len(d._undo)
    p.open(source=source,quick=quick)
    assert p.operation.currentData() == 'join'
    assert p.target.currentData() == owner and p.target.isEnabled()
    assert not p.target.isHidden()
    assert p.distance.value() == 10 and p.direction.currentData() == -1
    assert p.preview() and d.features == before and len(d._undo) == count
    assert p.commit()
    result = d.features[-1]
    assert result.parameters.operation == 'join' and result.parameters.target_id == owner
    assert d.active_body_ids == {result.id}
    assert BRepCheck_Analyzer(d.solid_shapes[result.id]).IsValid()
    assert volume(d.solid_shapes[result.id]) == pytest.approx(1000+40*pi)
    accepted = d.features
    assert len(d._undo) == count+1
    w.undo(); assert d.features == before
    w.redo(); assert d.features == accepted
    d.save(tmp_path/'join.starcad')
    loaded = Document.load(d.path)
    assert loaded.features == accepted and loaded.active_body_ids == d.active_body_ids


@pytest.mark.parametrize('extra_body',[False,True])
def test_origin_plane_has_no_inferred_target(qtbot,extra_body):
    w = window(qtbot)
    w.show_base_box.setChecked(False)
    w.show_base_box.setChecked(True)
    d = w.document
    if extra_body:
        cylinder(d,x=50)
    sid = d.add_sketch('XY'); c = Circle(5,5,2); d.add_entity(sid,c)
    w.refresh()
    p = w.operation_panel; p.open(source=(sid,c.id,()))
    assert p.target.count() == (2 if extra_body else 1)
    assert p.operation.currentData() == 'new' and p.definition().parameters.target_id is None
    choose(p.operation,'join')
    assert p.target.isEnabled()


def test_explicit_owner_wins_over_other_eligible_bodies(qtbot):
    w = window(qtbot); d = w.document
    w.show_base_box.setChecked(False)
    w.show_base_box.setChecked(True)
    _,_,owner = cylinder(d,x=50)
    sid = d.add_face_sketch(FaceReference(owner,'end'))
    c = Circle(50,5,1); d.add_entity(sid,c); w.refresh()
    p = w.operation_panel; p.open(source=(sid,c.id,()))
    assert p.target.count() == 2 and p.target.itemData(0) != owner
    assert p.operation.currentData() == 'join' and p.target.currentData() == owner
    assert p.preview() and p.commit()


@pytest.mark.parametrize('operation,distance',[('new',5),('join',5),('cut',-5)])
def test_manual_choice_survives_fields_preview_and_existing_feature_edit(qtbot,operation,distance):
    w,owner,source = face_profile(qtbot)
    p = w.operation_panel; p.open(source=source,quick=True)
    choose(p.operation,operation)
    p.quick_distance.setText(str(distance))
    choose(p.direction,1)
    p.advanced.setChecked(True)
    assert p.operation.currentData() == operation
    assert p.preview() and p.apply_input()
    feature = w.document.features[-1]
    target = None if operation == 'new' else owner
    assert feature.parameters.operation == operation and feature.parameters.target_id == target
    # Editing must preserve even New Body on an otherwise eligible attached sketch.
    w.edit_operation()
    assert p.operation.currentData() == operation and p.target.currentData() == target
    p.distance.setValue(distance*0.5)
    assert p.preview() and p.commit()
    stored = w.document.feature(feature.id).parameters
    assert stored.operation == operation and stored.target_id == target
    # A manual choice is local to that invocation, not a persisted preference.
    if operation == 'new':
        p.open(source=source)
        assert p.operation.currentData() == 'join' and p.target.currentData() == owner


def test_invalid_auto_join_never_commits_and_can_be_changed_manually(qtbot):
    w,owner,source = face_profile(qtbot,x=30)
    d,p = w.document,w.operation_panel
    before,count = d.features,len(d._undo)
    p.open(source=source,quick=True)
    assert p.operation.currentData() == 'join'
    assert not p.preview() and not p.apply_input()
    assert p.candidate is None and not p.apply_button.isEnabled()
    assert p.feedback.text() and d.features == before and len(d._undo) == count
    choose(p.operation,'new')
    assert p.apply_input() and d.features[-1].parameters.operation == 'new'


def test_hidden_or_consumed_attachment_owner_is_not_substituted(qtbot):
    w,owner,source = face_profile(qtbot)
    d,p = w.document,w.operation_panel
    w.show_base_box.setChecked(False)
    p.open(source=source)
    assert p.operation.currentData() == 'new' and p.target.count() == 0
    p.cancel(); w.show_base_box.setChecked(False)
    w.show_base_box.setChecked(True)
    d.add_extrusion(source[0],source[1],distance=5,operation='join',target_id=owner)
    w.refresh(); p.open(source=source)
    assert d.statuses[source[0]].valid and owner not in d.active_body_ids
    assert p.target.count() == 1 and p.operation.currentData() == 'new'


def test_unresolved_attachment_cannot_suggest_join(qtbot):
    w = window(qtbot); d = w.document
    source = d.add_sketch('XY'); rect = Rectangle(0,0,20,10)
    d.add_entity(source,rect); owner = d.add_extrusion(source,rect.id)
    sid = d.add_face_sketch(FaceReference(owner,'side',rect.id,'edge0'))
    c = Circle(1,2,.5); d.add_entity(sid,c)
    d.update_entity(source,Circle(0,0,5,id=rect.id)); w.refresh()
    assert not d.statuses[sid].valid and owner in d.active_body_ids
    p = w.operation_panel; p.open(source=(sid,c.id,()))
    assert p.operation.currentData() == 'new'
    before = d.features
    assert not p.preview() and not p.commit() and d.features == before

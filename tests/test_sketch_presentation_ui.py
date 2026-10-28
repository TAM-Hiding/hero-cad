from PySide6.QtCore import QSettings
from hero_cad.preferences import Preferences
from hero_cad.ui.preferences_dialog import PreferencesDialog
from hero_cad.sketch import FaceReference, Line
from test_sketch_ui import window


def test_sketch_preferences_live_and_persistent(qtbot, tmp_path):
    w = window(qtbot)
    store = w.preference_store
    sid = w.document.add_sketch('XY')
    w.refresh()
    w.viewport.sketch.enter(sid)
    assert w.viewport.actor.GetProperty().GetOpacity() == .35
    store.set('viewport/v1/sketch_opacity', 18)
    assert w.viewport.actor.GetProperty().GetOpacity() == .18
    store.set('viewport/v1/sketch_xray', False)
    assert w.viewport.actor.GetProperty().GetOpacity() == 1
    dialog = PreferencesDialog(store)
    qtbot.addWidget(dialog)
    assert not dialog.controls['viewport/v1/sketch_opacity'].isEnabled()
    assert store.get('viewport/v1/sketch_opacity') == 18
    restored = Preferences(store.settings)
    assert restored.get('viewport/v1/sketch_opacity') == 18
    assert not restored.get('viewport/v1/sketch_xray')
    w.viewport.sketch.finish()
    assert w.viewport.actor.GetProperty().GetOpacity() == 1
    assert not w.viewport.support_actor.GetVisibility()


def test_support_lifecycle_and_mesh_reuse(qtbot):
    w = window(qtbot)
    w.show_base_box.setChecked(True)
    box = w.document.features[0].id
    a = w.document.add_face_sketch(FaceReference(box, '+Z'))
    b = w.document.add_face_sketch(FaceReference(box, '+X'))
    origin = w.document.add_sketch('XY')
    w.refresh()
    frame = w.document.feature(a).parameters.frame
    w.viewport.sketch.enter(a)
    v = w.viewport
    assert v.support_actor.GetVisibility()
    assert not v.support_actor.GetPickable()
    mesh = v.support_mapper.GetInput()
    assert mesh.GetNumberOfCells() > 0
    w.document.add_entity(a, Line(0, 0, 1, 1))
    w.refresh()
    assert v.support_mapper.GetInput() is mesh
    assert w.document.feature(a).parameters.frame == frame
    v.sketch.enter(b)
    assert v.support_actor.GetVisibility()
    assert v.support_mapper.GetInput() is not mesh
    w.preference_store.set('viewport/v1/sketch_face', False)
    assert not v.support_actor.GetVisibility()
    w.preference_store.set('viewport/v1/sketch_face', True)
    assert v.support_actor.GetVisibility()
    v.sketch.enter(origin)
    assert not v.support_actor.GetVisibility()
    v.sketch.finish()
    assert not v.support_actor.GetVisibility()


def test_unresolved_support_clears_overlay(qtbot):
    from dataclasses import replace
    from test_history_inspection import joined_transition_chain, convert_to_join
    w = window(qtbot)
    w.document, box, source, extrusion, attached, cut = joined_transition_chain()
    w.refresh()
    w.viewport.sketch.enter(attached)
    convert_to_join(w.document, box, source, extrusion)
    w.refresh()
    assert not w.document.statuses[attached].valid
    assert not w.viewport.support_actor.GetVisibility()
    assert w.document.statuses[attached].error


def test_explicit_xray_outside_sketch_unchanged(qtbot):
    w = window(qtbot)
    w.viewport.set_xray_mode('Orange')
    assert w.viewport.actor.GetProperty().GetOpacity() == .85
    sid = w.document.add_sketch('XY')
    w.refresh()
    w.viewport.sketch.enter(sid)
    assert w.viewport.actor.GetProperty().GetOpacity() == .35
    w.preference_store.set('viewport/v1/sketch_xray', False)
    assert w.viewport.actor.GetProperty().GetOpacity() == 1
    w.viewport.sketch.finish()
    w.viewport.apply_solid_style()
    assert w.viewport.actor.GetProperty().GetOpacity() == .85

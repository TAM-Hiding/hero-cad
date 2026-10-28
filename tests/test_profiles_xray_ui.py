from dataclasses import replace
import numpy as np
import pytest
from PySide6.QtCore import Qt
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.sketch import Circle
from hero_cad.profiles import regions
from test_line_profiles import DOVETAIL, TRIANGLE, polygon, document
from test_sketch_ui import window, enter, click, pixel
from test_sketch_visibility import capture


@pytest.mark.parametrize('operation', ['new', 'cut'])
def test_draw_line_dovetail_finish_pick_preview_commit_and_reopen(qtbot, operation, tmp_path):
    w = window(qtbot)
    v, d = w.viewport, w.document
    sid = enter(w, 'XZ')
    assert v.actor.GetVisibility() and v.actor.GetProperty().GetOpacity() == .35
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(1)
    frame = d.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Line')
    for a, b in zip(DOVETAIL, DOVETAIL[1:]+DOVETAIL[:1]):
        click(qtbot, v, frame, a)
        click(qtbot, v, frame, b)
    assert len(d.feature(sid).parameters.entities) == 4
    assert all(tuple(e.points[0]) == a and tuple(e.points[1]) == b
               for e, a, b in zip(d.feature(sid).parameters.entities, DOVETAIL, DOVETAIL[1:]+DOVETAIL[:1]))
    w.finish_sketch()
    v.orient('Front')
    w.profile_action.setChecked(True)
    click(qtbot, v, frame, (7, 7))
    assert v.profiles.selection and v.profiles.selection[0] == sid
    w.extrude_action.trigger()
    panel = w.operation_panel
    panel.operation.setCurrentIndex(panel.operation.findData(operation))
    panel.distance.setValue(-30)
    if operation == 'cut':
        panel.target.setCurrentIndex(panel.target.findData(d.features[0].id))
    assert panel.preview() and panel.commit()
    eid = d.features[-1].id
    assert d.feature(eid).parameters.line_ids
    assert volume(d.solid_shapes[eid]) == pytest.approx(48*30 if operation == 'new' else 40*30*20-48*30)
    before = d.features
    w.undo(); w.redo()
    assert d.features == before
    d.save(tmp_path/'dovetail.starcad')
    assert Document.load(d.path).features == d.features


def test_independent_profile_picks_open_chains_and_live_line_vertex_edits(qtbot):
    w = window(qtbot)
    lines = polygon(TRIANGLE)
    w.document, sid = document((*lines, *polygon([(20, 0), (30, 0), (30, 10), (20, 10)])))
    w.refresh(fit=True)
    v, d = w.viewport, w.document
    v.sketch.enter(sid)
    frame = d.feature(sid).parameters.frame
    w.profile_action.setChecked(True)
    keys = []
    for point in ((3, 2), (25, 5)):
        click(qtbot, v, frame, point)
        keys.append(v.profiles.selection[1].outer_id)
    assert len(set(keys)) == 2
    click(qtbot, v, frame, (3, 2))
    w.extrude_action.trigger()
    assert w.operation_panel.preview() and w.operation_panel.commit()
    eid = d.features[-1].id
    w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
    w.edit_sketch()
    w.browser.setCurrentItem(w.browser_items[('entity', sid, lines[0].id)])
    w.entity_fields['x2'].setValue(14)
    w.entity_apply.click()
    assert not d.statuses[eid].valid and eid not in d.solid_shapes
    w.browser.setCurrentItem(w.browser_items[('entity', sid, lines[1].id)])
    w.entity_fields['x1'].setValue(14)
    w.entity_apply.click()
    assert d.statuses[eid].valid and volume(d.solid_shapes[eid]) == pytest.approx(56*10)


@pytest.mark.parametrize('mode', ['Off', 'Celadon', 'Orange'])
def test_xray_menu_toolbar_sketch_transitions_and_history_do_not_reset_mode(qtbot, mode, tmp_path):
    w = window(qtbot)
    v, d = w.viewport, w.document
    before, history = d.features, len(d._undo)
    w.xray_actions[mode].trigger()
    assert v.xray_mode == mode == w.xray_choice.currentText()
    assert [name for name, action in w.xray_actions.items() if action.isChecked()] == [mode]
    assert v.actor.GetProperty().GetOpacity() == (1 if mode == 'Off' else .85)
    assert d.features == before and len(d._undo) == history and not d.dirty
    sid = enter(w)
    assert v.xray_mode == mode and v.actor.GetProperty().GetOpacity() == w.preference_store.get('viewport/v1/sketch_opacity') / 100
    assert v.sketch.actor.GetProperty().GetOpacity() == 1
    d.add_entity(sid, Circle(10, 10, 2)); w.refresh()
    assert v.actor.GetProperty().GetOpacity() == w.preference_store.get('viewport/v1/sketch_opacity') / 100
    # Sketch opacity takes precedence over explicit model X-Ray modes while
    # editing. The selected mode remains synchronized and resumes on Finish.
    for opacity in (0, 23, 100):
        w.preference_store.set('viewport/v1/sketch_opacity', opacity)
        assert v.actor.GetProperty().GetOpacity() == opacity / 100
        assert v.xray_mode == mode == w.xray_choice.currentText()
        assert w.xray_actions[mode].isChecked()
    w.preference_store.set('viewport/v1/sketch_xray', False)
    assert v.actor.GetProperty().GetOpacity() == 1
    assert w.preference_store.get('viewport/v1/sketch_opacity') == 100
    w.preference_store.set('viewport/v1/sketch_opacity', 23)
    assert v.actor.GetProperty().GetOpacity() == 1
    w.preference_store.set('viewport/v1/sketch_xray', True)
    assert v.actor.GetProperty().GetOpacity() == .23
    w.finish_sketch()
    assert v.xray_mode == mode and v.actor.GetProperty().GetOpacity() == (1 if mode == 'Off' else .85)
    w.undo(); w.redo()
    d.save(tmp_path/'xray.starcad')
    w.document = Document.load(d.path); w.refresh()
    assert v.xray_mode == mode
    assert 'xray' not in d.path.read_text().lower()
    for name in ('Orange', 'Off', 'Celadon'):
        w.xray_choice.setCurrentText(name)
        assert v.xray_mode == name and w.xray_actions[name].isChecked()


@pytest.mark.parametrize('mode', ['Celadon', 'Orange'])
def test_xray_selection_and_preview_color_remain_distinct_render(qtbot, mode):
    w = window(qtbot)
    v, d = w.viewport, w.document
    v.orient('Front')
    normal = capture(v)
    w.xray_choice.setCurrentText(mode)
    shown = capture(v)
    assert np.count_nonzero(np.max(abs(normal-shown), axis=2) > 2) > 1000
    point = pixel(v, (20, 0, 10))
    qtbot.mouseClick(v, Qt.LeftButton, pos=point)
    assert v.selection and v.selection.kind == 'face'
    selected = capture(v)
    assert np.count_nonzero(np.max(abs(shown-selected), axis=2) > 8) > 1000
    if mode == 'Orange':
        assert v.highlight_actor.GetProperty().GetColor() != v.actor.GetProperty().GetColor()
    # A candidate preview owns a separate actor and must ignore global X-Ray.
    d2, sid = document(polygon(TRIANGLE))
    w.document = d2; w.refresh(fit=True)
    r, = regions(d2.feature(sid).parameters)
    w.operation_panel.open(source=(sid, r.outer_id, r.hole_ids))
    assert w.operation_panel.preview()
    actor = w.operation_panel.actor
    style = actor.GetProperty().GetColor(), actor.GetProperty().GetOpacity()
    for name in ('Off', 'Celadon', 'Orange'):
        w.xray_choice.setCurrentText(name)
        assert (actor.GetProperty().GetColor(), actor.GetProperty().GetOpacity()) == style
        assert actor.GetVisibility() and v.mapper.GetInput().GetNumberOfPoints() == 0
    w.operation_panel.cancel()
    assert v.actor.GetProperty().GetOpacity() == .85 and v.xray_mode == 'Orange'


def test_xray_and_navigation_reuse_display_meshes(qtbot, monkeypatch):
    import hero_cad.ui.viewport as module
    w = window(qtbot)
    v = w.viewport
    surface, edges = v.mapper.GetInput(), v.edge_mapper.GetInput()
    def unexpected(*_args, **_kwargs):
        raise AssertionError('Camera or X-Ray mode unnecessarily rebuilt the B-rep mesh')
    monkeypatch.setattr(module, 'tessellate', unexpected)
    camera = v.renderer.GetActiveCamera()
    for mode in ('Celadon', 'Orange', 'Off'):
        w.xray_choice.setCurrentText(mode)
        camera.Azimuth(15); camera.Elevation(5)
        camera.SetParallelScale(camera.GetParallelScale()*.8)
        v.clamp_zoom(); v.GetRenderWindow().Render()
        assert v.mapper.GetInput() is surface and v.edge_mapper.GetInput() is edges

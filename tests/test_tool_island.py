from dataclasses import replace
import json
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, QSettings
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopAbs import TopAbs_FACE
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.sketch import Circle, Slot, Line
from hero_cad.ui.display_geometry import subshapes, Selection
from hero_cad.ui.main_window import MainWindow
from hero_cad.ui.tool_island import ToolIsland
from test_sketch_ui import window, enter, pixel, hover, click


def ready(qtbot, w):
    qtbot.waitUntil(lambda: w.tool_island._ready)
    QApplication.processEvents()
    return w.tool_island


def press(qtbot, w, identifier):
    island = ready(qtbot, w)
    button = island.buttons[identifier]
    island.scroll.ensureWidgetVisible(button)
    QApplication.processEvents()
    qtbot.mouseClick(button, Qt.LeftButton)


def drag(qtbot, island, delta):
    start = QPoint(24, 12)
    origin = island.header.mapToGlobal(start)
    qtbot.mousePress(island.header, Qt.LeftButton, pos=start)
    move = QMouseEvent(QEvent.MouseMove, QPointF(start+delta), QPointF(origin+delta),
                       Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(island.header, move)
    qtbot.mouseRelease(island.header, Qt.LeftButton, pos=start+delta)


def test_initial_island_is_viewport_child_and_commands_explain_disabled_state(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    assert island.parentWidget() is w.viewport and island.isVisible()
    assert island.preset == 'Medium' and not island.collapsed
    assert island.x() == w.viewport.width()-island.width()-16 and island.y() == 16
    assert island.buttons['sketch.new'].defaultAction() is w.new_sketch_action
    assert not w.new_sketch_action.isEnabled()
    assert 'Select an origin plane' in w.new_sketch_action.toolTip()
    before = w.document.features
    assert not w.commands.execute('sketch.new')
    assert w.document.features == before
    assert not any('fillet' in key for key in island.buttons)
    assert island.buttons['model.chamfer'].defaultAction() is w.chamfer_action
    assert not w.chamfer_action.isEnabled()
    assert 'Select one or more straight, circular or arc edges' in w.chamfer_action.toolTip()


@pytest.mark.parametrize('preset,columns', [('Compact', 1), ('Medium', 2), ('Expanded', 3)])
def test_presets_reflow_without_clipped_buttons_or_document_changes(qtbot, preset, columns):
    w = window(qtbot); island = ready(qtbot, w)
    before = w.document.features, len(w.document._undo)
    island.size_choice.setCurrentText(preset)
    QApplication.processEvents()
    assert island.size() == island.PRESETS[preset]
    xs = {island.buttons[key].x() for key in island.visible_commands}
    assert len(xs) == columns
    for key in island.visible_commands:
        button = island.buttons[key]
        assert button.x() >= 0 and button.geometry().right() < island.contents.width()
        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text().replace('&', ''))+8
    assert (w.document.features, len(w.document._undo)) == before and not w.document.dirty


def test_header_drag_bounds_and_no_camera_or_model_changes(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    before = w.document.features
    camera = w.viewport.renderer.GetActiveCamera()
    view = camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale()
    old = island.pos()
    drag(qtbot, island, QPoint(-70, 45))
    assert island.pos() == old+QPoint(-70, 45)
    drag(qtbot, island, QPoint(5000, 5000))
    assert island.geometry().right() < w.viewport.width() and island.geometry().bottom() < w.viewport.height()
    drag(qtbot, island, QPoint(-5000, -5000))
    assert island.pos() == QPoint(0, 0)
    assert (camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale()) == view
    assert w.document.features == before and not w.document.dirty


def test_collapse_preserves_position_dimensions_and_survives_context_changes(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    island.set_preset('Expanded'); island.place(QPoint(40, 50))
    expanded = island.size(), island.pos()
    qtbot.mouseClick(island.collapse_button, Qt.LeftButton)
    assert island.collapsed and island.size().width() == 142 and island.pos() == expanded[1]
    assert not island.body.isVisible()
    enter(w)
    assert island.collapsed and island.context == 'sketch' and island.pos() == expanded[1]
    w.finish_sketch()
    assert island.collapsed and island.context == 'model'
    qtbot.mouseClick(island.collapse_button, Qt.LeftButton)
    assert not island.collapsed and (island.size(), island.pos()) == expanded


def test_real_settings_restore_layout_and_view_menu_hide_show(qtbot, tmp_path):
    path = str(tmp_path/'layout.ini')
    w = MainWindow(settings=QSettings(path, QSettings.IniFormat))
    qtbot.addWidget(w); w.show(); qtbot.waitExposed(w)
    island = ready(qtbot, w)
    island.set_preset('Compact'); island.place(QPoint(30, 60)); island.set_collapsed(True)
    w.island_action.trigger()
    assert not w.island_action.isChecked() and not island.isVisible()
    # Read in a fresh interpreter too: restoration must not rely on Qt's
    # in-process settings cache or keeping the first window alive.
    import subprocess, sys
    script = '''
import json,sys
from PySide6.QtCore import QSettings
s=QSettings(sys.argv[1],QSettings.IniFormat)
print(json.dumps({k:s.value('tool_island/v1/'+k) for k in ('size','x','y','collapsed','visible')}))
'''
    persisted = json.loads(subprocess.check_output([sys.executable, '-c', script, path], text=True))
    assert persisted == {'size': 'Compact', 'x': '30', 'y': '60', 'collapsed': 'true', 'visible': 'false'}
    other = MainWindow(settings=QSettings(path, QSettings.IniFormat))
    qtbot.addWidget(other); other.show(); qtbot.waitExposed(other)
    restored = ready(qtbot, other)
    assert restored.preset == 'Compact' and restored.collapsed and restored.pos() == QPoint(30, 60)
    assert not restored.isVisible() and not other.island_action.isChecked()
    other.island_action.trigger()
    assert restored.isVisible() and restored.collapsed
    other.document.save(tmp_path/'model.starcad')
    assert 'tool_island' not in other.document.path.read_text()
    assert not other.document.dirty


def test_viewport_resize_clamps_without_losing_preferred_size_or_position(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    island.place(QPoint(80, 70))
    old_size = w.viewport.size()
    w.viewport.setFixedSize(230, 210); QApplication.processEvents()
    assert island.geometry().right() < w.viewport.width() and island.geometry().bottom() < w.viewport.height()
    assert island.preset == 'Medium' and island.preferred_position == QPoint(80, 70)
    w.viewport.setFixedSize(old_size); QApplication.processEvents()
    assert island.pos() == QPoint(80, 70) and island.size() == island.PRESETS['Medium']


def test_small_window_keeps_header_and_one_command_column_usable(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    w.resize(500, 220); QApplication.processEvents()
    assert w.viewport.width() >= 224 and w.viewport.height() >= 180
    assert island.geometry().right() < w.viewport.width() and island.geometry().bottom() < w.viewport.height()
    assert island.collapse_button.mapTo(island, QPoint(0, 0)).x()+island.collapse_button.width() <= island.width()
    assert island.scroll.height() >= 30


def test_corrupt_preferences_fall_back_and_out_of_bounds_positions_stay_accessible(qtbot, tmp_path):
    settings = QSettings(str(tmp_path/'bad.ini'), QSettings.IniFormat)
    for key, value in {'size': 'Giant', 'x': 999999, 'y': -999, 'collapsed': 'bad', 'visible': 'bad'}.items():
        settings.setValue(ToolIsland.PREFIX+key, value)
    w = MainWindow(settings=settings); qtbot.addWidget(w); w.show(); qtbot.waitExposed(w)
    island = ready(qtbot, w)
    assert island.preset == 'Medium' and not island.collapsed and island.isVisible()
    assert island.y() == 0 and island.geometry().right() < w.viewport.width()


def test_origin_sketch_tool_actions_share_toolbar_and_one_history_transaction(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    w.browser.setCurrentItem(w.browser_items[('plane', 'XY')])
    assert island.buttons['sketch.new'].isEnabled() and w.new_sketch_action.isEnabled()
    island.place(QPoint(40, 50))  # Context changes must retain any still-accessible placement.
    old = island.geometry()
    count = len(w.document._undo)
    spy = QSignalSpy(w.new_sketch_action.triggered)
    press(qtbot, w, 'sketch.new')
    assert spy.count() == 1 and len(w.document.sketches) == 1 and len(w.document._undo) == count+1
    assert island.context == 'sketch' and island.geometry() == old
    for name in ('Line', 'Rectangle', 'Circle', 'Select'):
        w.tool_choice.setCurrentText(name)
        assert w.viewport.sketch.controller.name == name.lower()
        assert island.buttons['tool.'+name.lower()].isChecked()
    press(qtbot, w, 'tool.line')
    assert w.tool_choice.currentText() == 'Line'
    # Selecting a browser entry updates context, not the active construction tool.
    w.browser.setCurrentItem(w.browser_items[('sketch', w.viewport.sketch.active_id)])
    assert w.viewport.sketch.controller.name == 'line' and island.geometry() == old
    grid = w.grid_action.isChecked()
    press(qtbot, w, 'sketch.grid')
    assert w.grid_action.isChecked() != grid and w.viewport.sketch.guides.grid_visible != grid
    press(qtbot, w, 'sketch.finish')
    assert w.viewport.sketch.active_id is None and island.context == 'model'


def test_slot_button_reuses_shift_circle_geometry_and_updates_toolbar(qtbot):
    w = window(qtbot); sid = enter(w)
    island = ready(qtbot, w)
    press(qtbot, w, 'tool.slot')
    assert w.tool_choice.currentText() == 'Slot' and w.viewport.sketch.controller.name == 'slot'
    island.set_collapsed(True)
    w.auto_grid_action.setChecked(False); w.manual_grid_spacing.setValue(1)
    v = w.viewport; frame = w.document.feature(sid).parameters.frame
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((2, 0))))
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((2, 0))))
    click(qtbot, v, frame, (10, 0))
    entity, = w.document.feature(sid).parameters.entities
    assert isinstance(entity, Slot) and entity.radius == 2 and entity.distance == 10
    assert island.collapsed and w.tool_actions['slot'].isChecked()
    qtbot.keyClick(v, Qt.Key_Escape)
    assert w.tool_choice.currentText() == 'Select' and w.tool_actions['select'].isChecked()


def test_selected_planar_face_priority_clear_and_disabled_curved_face(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    face = w.document.face_maps[w.document.features[0].id]['+Z']
    old = island.geometry()
    w.viewport.select_face(face)
    assert island.context == 'face' and w.new_sketch_action.isEnabled() and island.geometry() == old
    w.viewport.clear_selection()
    assert island.context == 'model' and not w.new_sketch_action.isEnabled()
    w.viewport.select_face(face)
    press(qtbot, w, 'sketch.new')
    assert w.document.sketches[-1].parameters.attachment.parent_id == w.document.features[0].id
    w.finish_sketch()
    sid = w.document.add_sketch('XY'); circle = Circle(0, 0, 5)
    w.document.add_entity(sid, circle); eid = w.document.add_extrusion(sid, circle.id)
    w.refresh()
    curved = next(f for f in subshapes(w.document.solid_shapes[eid], TopAbs_FACE)
                  if BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane)
    w.viewport.select_face(curved)
    assert not w.new_sketch_action.isEnabled() and 'planar' in w.new_sketch_action.toolTip()
    assert not w.commands.execute('sketch.new')


def test_profile_and_extrude_island_actions_share_existing_preview_and_commit(qtbot):
    w = window(qtbot); sid = enter(w)
    d, v = w.document, w.viewport
    c = Circle(10, 10, 2); d.add_entity(sid, c); w.refresh()
    frame = d.feature(sid).parameters.frame
    press(qtbot, w, 'profile.select')
    assert w.profile_action.isChecked()
    click(qtbot, v, frame, (10, 10))
    assert w.extrude_action.isEnabled() and w.tool_island.buttons['model.extrude'].isEnabled()
    spy = QSignalSpy(w.extrude_action.triggered)
    before, count = d.features, len(d._undo)
    press(qtbot, w, 'model.extrude')
    assert spy.count() == 1 and w.operation_panel.active and d.features == before
    assert w.operation_panel.preview() and w.operation_panel.commit()
    assert len(d.features) == len(before)+1 and len(d._undo) == count+1


def test_existing_shortcuts_use_shared_actions_once(qtbot):
    w = window(qtbot); ready(qtbot, w)
    w.activateWindow(); w.viewport.setFocus(); qtbot.wait(50)
    w.document.set_box(BoxParameters(41, 30, 20)); w.refresh()
    spy = QSignalSpy(w.undo_action.triggered)
    qtbot.keyClick(w.viewport, Qt.Key_Z, Qt.ControlModifier)
    assert spy.count() == 1 and w.document.parameters.width == 40
    fit = QSignalSpy(w.fit_action.triggered)
    qtbot.keyClick(w.viewport, Qt.Key_F)
    assert fit.count() == 1
    assert w.tool_island.buttons['view.fit'].defaultAction() is w.fit_action


def test_mouse_over_island_is_consumed_and_outside_is_still_viewport(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    v = w.viewport; camera = v.renderer.GetActiveCamera()
    before = camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale()
    p = QPointF(3, island.height()-3)
    event = QWheelEvent(p, QPointF(island.mapToGlobal(p.toPoint())), QPoint(), QPoint(0, 120),
                        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(island, event)
    qtbot.mouseDClick(island, Qt.RightButton, Qt.ShiftModifier, pos=p.toPoint())
    assert (camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale()) == before
    inner = QApplication.widgetAt(island.header.mapToGlobal(QPoint(8, 8)))
    assert inner is not v and (inner is island or island.isAncestorOf(inner))
    outside = QPoint(30, v.height()-30)
    assert QApplication.widgetAt(v.mapToGlobal(outside)) is v
    wheel = QWheelEvent(QPointF(outside), QPointF(v.mapToGlobal(outside)), QPoint(), QPoint(0, 120),
                        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(v, wheel)
    assert camera.GetParallelScale() < before[2]


def test_combine_action_is_shared_without_duplicate_model_operations(qtbot):
    w = window(qtbot); ready(qtbot, w)
    d = w.document
    sid = d.add_sketch('XY'); c = Circle(5, 5, 2)
    d.add_entity(sid, c); eid = d.add_extrusion(sid, c.id, distance=25)
    w.refresh()
    from PySide6.QtCore import QSignalBlocker
    with QSignalBlocker(w.browser):
        w.browser.clearSelection()
        w.browser_items[('box', d.features[0].id)].setSelected(True)
        w.browser_items[('extrude', eid)].setSelected(True)
    w.update_actions()
    assert w.combine_action.isEnabled()
    assert w.tool_island.buttons['model.combine'].defaultAction() is w.combine_action
    before = d.features, len(d._undo)
    spy = QSignalSpy(w.combine_action.triggered)
    press(qtbot, w, 'model.combine')
    assert spy.count() == 1 and w.operation_panel.active
    assert (d.features, len(d._undo)) == before
    w.operation_panel.cancel()
    with pytest.raises(ValueError, match='Duplicate command'):
        w.commands.register('model.combine', w.combine_action)


def test_actual_widget_hit_outside_collapsed_island_retains_face_and_edge_selection(qtbot):
    w = window(qtbot); island = ready(qtbot, w)
    island.set_collapsed(True); island.place(QPoint(0, 0))
    v = w.viewport; v.orient('Front')
    for mode, world in (('face', (20, 0, 10)), ('edge', (0, 0, 10))):
        v.set_selection_mode(mode)
        point = pixel(v, world)
        target = QApplication.widgetAt(v.mapToGlobal(point))
        assert target is v
        qtbot.mouseClick(target, Qt.LeftButton, pos=point)
        assert v.selection and v.selection.kind == mode
    assert island.collapsed


def test_island_layout_and_xray_survive_new_document_and_history(qtbot, monkeypatch):
    w = window(qtbot); island = ready(qtbot, w)
    island.set_preset('Compact'); island.set_collapsed(True); island.place(QPoint(20, 40))
    w.xray_choice.setCurrentText('Orange')
    enter(w)
    w.finish_sketch(); w.undo(); w.redo()
    monkeypatch.setattr(w, 'confirm_replace', lambda: True)
    w.new_document()
    assert island.collapsed and island.preset == 'Compact' and island.pos() == QPoint(20, 40)
    assert w.viewport.xray_mode == 'Orange' and w.viewport.actor.GetProperty().GetOpacity() == .85

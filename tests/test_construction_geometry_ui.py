import pytest
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog

from hero_cad.sketch import Circle, Line
from hero_cad.ui.dimension_spinbox import DimensionSpinBox
from test_sketch_ui import click, enter, hover, pixel, window


def offset_dialog(qtbot, w, offset, *, accept=True):
    def interact():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            assert w.construction_planes.preview[1].GetVisibility()
            field = dialog.findChild(DimensionSpinBox)
            field.selectAll()
            qtbot.keyClicks(field.lineEdit(), str(offset))
            assert field.value() == offset
            assert field.text() == f'{offset} mm'
            assert w.construction_planes.preview[0].GetInput().GetNumberOfPolys() == 1
            if accept:
                dialog.accept()
        finally:
            if dialog and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, interact)


def test_offset_preview_edit_visibility_and_sketch_camera(qtbot):
    w = window(qtbot)
    v = w.viewport
    w.browser.setCurrentItem(w.browser_items[('plane', 'XY')])
    before = w.document.features
    offset_dialog(qtbot, w, 25, accept=False)
    w.offset_plane_action.trigger()
    assert w.document.features == before
    assert not w.construction_planes.preview[1].GetVisibility()

    offset_dialog(qtbot, w, 25)
    w.offset_plane_action.trigger()
    plane = w.document.features[-1].id
    assert w.document.plane_frames[plane].origin == (0, 0, 25)
    assert w.browser_key == ('offset_plane', plane)
    assert w.construction_planes.selected[1].GetVisibility()
    assert not w.construction_planes.selected[1].GetPickable()
    assert w.visible_volume == 24000

    offset_dialog(qtbot, w, -7)
    w.edit_offset_plane()
    assert w.document.plane_frames[plane].origin == (0, 0, -7)
    item = w.browser_items['offset_plane', plane]
    position = QPoint(w.browser.columnViewportPosition(1) + 5, w.browser.visualItemRect(item).center().y())
    qtbot.mouseClick(w.browser.viewport(), Qt.LeftButton, pos=position)
    assert not w.document.feature(plane).plane_visible
    assert not w.construction_planes.selected[1].GetVisibility()
    assert not w.construction_planes.normal[1].GetVisibility()
    w.undo()
    assert w.document.feature(plane).plane_visible
    w.redo()

    w.new_sketch_action.trigger()
    sketch = v.sketch.active_id
    assert w.document.feature(sketch).parameters.plane_id == plane
    assert v.renderer.GetActiveCamera().GetDirectionOfProjection() == pytest.approx((0, 0, -1))
    assert v.sketch.origin_actor.GetPosition() == (0, 0, -7)
    w.finish_sketch()
    assert v.sketch.active_id is None


def test_construction_shortcut_creation_snaps_selection_and_deletion(qtbot, tmp_path):
    w = window(qtbot)
    v = w.viewport
    w.activateWindow()
    v.setFocus()
    qtbot.waitUntil(w.isActiveWindow)
    qtbot.keyClick(v, Qt.Key_X)
    assert not v.sketch.construction_mode and not w.construction_shortcut.isEnabled()

    sid = enter(w)
    frame = w.document.feature(sid).parameters.frame
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(1)
    v.setFocus()
    qtbot.keyClick(v, Qt.Key_X)
    assert w.construction_action.isChecked()
    w.tool_choice.setCurrentText('Line')
    click(qtbot, v, frame, (-14, -10))
    click(qtbot, v, frame, (-6, -10))
    line = w.document.feature(sid).parameters.entities[-1]
    assert isinstance(line, Line) and line.construction
    assert line.points == ((-14, -10), (-6, -10))

    hover(v, pixel(v, frame.to_world(line.points[1])) + QPoint(2, 0))
    assert v.sketch.snap_result.target == 'ENDPOINT'
    assert v.sketch.snap_result.point == line.points[1]

    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((10, 3))))
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((13, 7))))
    circle = w.document.feature(sid).parameters.entities[-1]
    assert isinstance(circle, Circle) and circle.construction and circle.radius == 5
    hover(v, pixel(v, frame.to_world((10, 3))) + QPoint(2, 0))
    assert v.sketch.snap_result.target == 'CENTER'
    assert v.sketch.snap_result.point == (10, 3)
    assert v.sketch.foreground_mapper.GetInput().GetNumberOfLines() > 2
    assert v.sketch.hit_mesh.GetNumberOfLines() == 2

    w.tool_choice.setCurrentText('Select')
    w.viewport.set_display_mode('CAD Wireframe')
    w.viewport.set_xray_mode('Orange')
    click(qtbot, v, frame, (15, 3))
    assert v.sketch.entity_id == circle.id and v.sketch.highlight_actor.GetVisibility()
    assert v.sketch.highlight_mapper.GetInput().GetNumberOfLines() > 1
    v.setFocus()
    qtbot.keyClick(v, Qt.Key_X)
    converted = w.document.feature(sid).parameters.entities[-1]
    assert (converted.id, converted.radius, converted.construction) == (circle.id, 5, False)
    w.undo()
    assert w.document.feature(sid).parameters.entities[-1] == circle
    w.redo()
    item = w.browser_items['entity', sid, circle.id]
    w.browser.setCurrentItem(item)
    w.browser.setFocus()
    menu = w.context_menu(('entity', sid, circle.id))
    next(action for action in menu.actions() if action.text() == 'Toggle Construction').trigger()
    assert w.document.feature(sid).parameters.entities[-1] == circle
    qtbot.keyClick(w.browser, Qt.Key_Delete)
    assert w.document.feature(sid).parameters.entities == (line,)
    w.undo()
    assert w.document.feature(sid).parameters.entities == (line, circle)
    w.finish_sketch()
    w.browser.setCurrentItem(w.browser_items['sketch', sid])
    w.edit_sketch()
    assert not w.construction_action.isChecked()

    path = tmp_path / 'references.hcad'
    w.document.save(path)
    assert w.document.load(path).feature(sid).parameters.entities == (line, circle)

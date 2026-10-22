from dataclasses import replace
from math import pi
import pytest
from PySide6.QtCore import Qt, QPoint
from star_cad.document import Document
from star_cad.geometry import volume
from star_cad.sketch import Circle, Rectangle, Slot
from test_sketch_ui import window, enter, click, pixel


def extrude(w, distance):
    w.extrude_action.trigger()
    w.operation_panel.distance.setValue(distance)
    assert w.operation_panel.preview()
    assert w.operation_panel.commit()


def plate(qtbot, plane='XY'):
    w = window(qtbot)
    sid = enter(w, plane)
    outer, hole = Rectangle(0, 0, 20, 10), Circle(5, 5, 2)
    for entity in (outer, hole):
        w.document.add_entity(sid, entity)
    w.refresh()
    w.profile_action.setChecked(True)
    return w, sid, outer, hole


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_click_material_hole_extrude_edit_source_and_reopen(qtbot, monkeypatch, tmp_path, plane):
    w, sid, outer, hole = plate(qtbot, plane)
    v, frame = w.viewport, w.document.feature(sid).parameters.frame
    click(qtbot, v, frame, (5, 5))
    assert v.profiles.selection is None and not w.extrude_action.isEnabled()
    click(qtbot, v, frame, (16, 5))
    assert v.profiles.selection[0] == sid
    assert v.profiles.selection[1].hole_ids == (hole.id,)
    assert v.profiles.actor.GetVisibility() and v.profiles.mapper.GetInput().GetNumberOfPolys() > 0
    assert w.extrude_action.isEnabled()
    extrude(w, 3.0)
    feature = w.document.features[-1]
    assert feature.type == 'extrude'
    assert v.sketch.active_id is None and not w.show_base_box.isChecked()
    assert volume(w.document.solid_shapes[feature.id]) == pytest.approx((200-4*pi)*3)
    assert w.entity_context == ('extrude', feature.id)
    w.entity_fields['distance'].setValue(-4.25)
    w.entity_apply.click()
    assert w.document.feature(feature.id).parameters.distance == -4.25
    w.browser.setCurrentItem(w.browser_items[('extrude', feature.id)])
    w.edit_sketch()
    assert v.sketch.active_id == sid
    w.browser.setCurrentItem(w.browser_items[('entity', sid, outer.id)])
    w.entity_fields['width'].setValue(25)
    w.entity_apply.click()
    assert volume(w.document.solid_shapes[feature.id]) == pytest.approx((250-4*pi)*4.25)
    assert w.document.feature(feature.id).parameters.outer_id == outer.id
    w.finish_sketch()
    path = tmp_path/f'plate-{plane}.starcad'
    w.document.save(path)
    loaded = Document.load(path)
    assert loaded.features == w.document.features
    w.undo()
    assert volume(w.document.solid_shapes[feature.id]) == pytest.approx((200-4*pi)*4.25)
    w.redo()
    assert volume(w.document.solid_shapes[feature.id]) == pytest.approx((250-4*pi)*4.25)


def test_profile_cancel_invalid_depth_context_and_delete(qtbot, monkeypatch):
    w, sid, outer, hole = plate(qtbot)
    v, frame = w.viewport, w.document.feature(sid).parameters.frame
    before = w.document.features
    click(qtbot, v, frame, (15, 5))
    w.extrude_action.trigger()
    w.operation_panel.cancel()
    assert w.document.features == before
    w.extrude_action.trigger()
    w.operation_panel.distance.setValue(0)
    assert not w.operation_panel.preview()
    w.operation_panel.cancel()
    assert w.document.features == before
    assert 'nonzero' in w.operation_panel.feedback.text()
    qtbot.mouseClick(v, Qt.RightButton, pos=pixel(v, frame.to_world((15, 5))))
    assert [a.text() for a in w._context_menu.actions()] == ['Extrude…']
    w._context_menu.actions()[0].trigger()
    w._context_menu.close()
    w.operation_panel.distance.setValue(8)
    assert w.operation_panel.preview() and w.operation_panel.commit()
    eid = w.document.features[-1].id
    w.browser.setCurrentItem(w.browser_items[('extrude', eid)])
    w.browser.setFocus()
    qtbot.keyClick(w.browser, Qt.Key_Delete)
    assert eid not in w.document.solid_shapes
    assert not v.profiles.actor.GetVisibility()
    w.undo()
    assert eid in w.document.solid_shapes
    assert not w.show_base_box.isChecked()  # Undo restores a visible part too.


def test_profile_mode_filter_independence_ambiguity_and_gesture_conflicts(qtbot):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    w, sid, outer, hole = plate(qtbot)
    v, frame = w.viewport, w.document.feature(sid).parameters.frame
    v.set_selection_mode('edge')
    click(qtbot, v, frame, (15, 5))
    assert v.profiles.selection
    p = QPoint(200, 180)
    qtbot.mousePress(v, Qt.RightButton, Qt.ShiftModifier, pos=p)
    moved = p+QPoint(50, 30)
    QApplication.sendEvent(v, QMouseEvent(QEvent.MouseMove, QPointF(moved), QPointF(v.mapToGlobal(moved)),
                                         Qt.NoButton, Qt.RightButton, Qt.ShiftModifier))
    qtbot.mouseRelease(v, Qt.RightButton, Qt.ShiftModifier, pos=moved)
    assert not hasattr(w, '_context_menu')
    assert v.profiles.selection
    w.tool_choice.setCurrentText('Circle')
    assert not w.profile_action.isChecked() and v.profiles.selection is None
    w.tool_choice.setCurrentText('Select')
    w.document.add_entity(sid, Circle(7, 5, 2))  # Overlaps the first hole.
    w.refresh()
    w.profile_action.setChecked(True)
    click(qtbot, v, frame, (15, 5))
    assert v.profiles.selection is None and not w.extrude_action.isEnabled()
    assert 'unambiguous' in w.statusBar().currentMessage()


def test_plate_hole_and_profile_highlight_render(qtbot, monkeypatch):
    import numpy as np
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    w, sid, outer, hole = plate(qtbot)
    v, frame = w.viewport, w.document.feature(sid).parameters.frame
    v.setFixedSize(640, 480)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)
    click(qtbot, v, frame, (15, 5))

    def pixels():
        v.GetRenderWindow().Render()
        capture = vtkWindowToImageFilter()
        capture.SetInput(v.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        out = capture.GetOutput()
        return vtk_to_numpy(out.GetPointData().GetScalars()).reshape(out.GetDimensions()[1], out.GetDimensions()[0], -1).astype(int)

    selected = pixels()
    orange = (selected[:, :, 0] > selected[:, :, 2]+15) & (selected[:, :, 0] > 60)
    assert np.count_nonzero(orange) > 1000
    extrude(w, 3.0)
    v.orient('Top')
    solid = pixels()
    cyan = (solid[:, :, 2] > 100) & (solid[:, :, 1] > 90)
    assert np.count_nonzero(cyan) > 3000  # Nonblank shaded plate.
    def patch(world):
        v.renderer.SetWorldPoint(*world, 1)
        v.renderer.WorldToDisplay()
        x, y, _ = v.renderer.GetDisplayPoint()
        return solid[round(y)-2:round(y)+3, round(x)-2:round(x)+3, :3]
    background = np.array(v.renderer.GetBackground())*255
    assert np.max(abs(patch((5, 5, 3))-background)) < 4  # Through-hole, not a filled disk.
    assert np.mean(patch((15, 5, 3))[:, :, 2]) > 100


def test_profile_picking_in_model_view_and_open_recreates_new_body(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    w = window(qtbot)
    sid = enter(w)
    circle = Circle(60, 0, 3)
    w.document.add_entity(sid, circle)
    w.refresh()
    w.finish_sketch()
    v, frame = w.viewport, w.document.feature(sid).parameters.frame
    v.fit()
    w.selection_choice.setCurrentIndex(1)
    w.profile_action.setChecked(True)
    click(qtbot, v, frame, (60, 0))
    assert v.profiles.selection[1].outer_id == circle.id
    extrude(w, 5.0)
    eid = w.document.features[-1].id
    path = tmp_path/'reopen.starcad'
    w.document.save(path)
    w.new_document()
    assert w.show_base_box.isChecked() and w.show_base_box.isEnabled()
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    w.open_document()
    assert not w.show_base_box.isChecked() and w.show_base_box.isEnabled()
    assert volume(w.document.solid_shapes[eid]) == pytest.approx(45*pi)
    assert w.visible_volume == pytest.approx(45*pi)

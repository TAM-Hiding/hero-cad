from math import hypot
import pytest
from PySide6.QtCore import QPoint, QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from star_cad.document import Document
from star_cad.ui.main_window import MainWindow


def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def pixel(v, world):
    v.renderer.SetWorldPoint(*world, 1)
    v.renderer.WorldToDisplay()
    x, y, _ = v.renderer.GetDisplayPoint()
    width, height = v.GetRenderWindow().GetSize()
    return QPoint(round(x*v.width()/width), round((height-1-y)*v.height()/height))


def enter(w, plane='XY'):
    w.browser.setCurrentItem(w.browser_items[('plane', plane)])
    assert w.new_sketch_action.isEnabled()
    w.new_sketch_action.trigger()
    assert w.viewport.sketch.active_id
    assert w.viewport.sketch.axes_actor.GetVisibility()
    assert w.viewport.sketch.origin_actor.GetVisibility()
    assert w.viewport.renderer.GetActiveCamera().GetParallelProjection()
    return w.viewport.sketch.active_id


def click(qtbot, v, frame, point, modifier=Qt.NoModifier):
    qtbot.mouseClick(v, Qt.LeftButton, modifier, pos=pixel(v, frame.to_world(point)))


def hover(v, point):
    # QTest.mouseMove without buttons relies on a native cursor event, which
    # Qt's offscreen platform does not deliver. Send a real Qt hover move.
    event = QMouseEvent(QEvent.MouseMove, QPointF(point), QPointF(v.mapToGlobal(point)),
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(v, event)


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_mouse_line_numeric_edit_save_and_reenter(qtbot, tmp_path, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    assert v.renderer.GetActiveCamera().GetDirectionOfProjection() == pytest.approx(tuple(-n for n in frame.normal))
    w.tool_choice.setCurrentText('Line')
    click(qtbot, v, frame, (1, 2))
    hover(v, pixel(v, frame.to_world((14, 9))))
    assert v.sketch.preview_actor.GetVisibility()
    click(qtbot, v, frame, (14, 9))
    entities = w.document.feature(identifier).parameters.entities
    assert len(entities) == 1 and not v.selections
    entity = entities[0]
    assert entity.x1 == pytest.approx(1, abs=0.1)
    w.entity_fields['x2'].setValue(17.123456789)
    w.entity_fields['y2'].setValue(-4.987654321)
    qtbot.mouseClick(w.entity_apply, Qt.LeftButton)
    edited = w.document.feature(identifier).parameters.entities[0]
    assert edited.x2 == 17.123456789 and edited.id == entity.id
    w.undo_action.trigger()
    assert w.document.feature(identifier).parameters.entities[0] == entity
    w.redo_action.trigger()
    assert w.document.feature(identifier).parameters.entities[0] == edited
    path = tmp_path/'sketch.starcad'
    w.document.save(path)
    assert Document.load(path).features == w.document.features
    w.finish_sketch_action.trigger()
    assert not v.sketch.active_id and v.actor.GetVisibility()
    w.browser.setCurrentItem(w.browser_items[('sketch', identifier)])
    w.edit_sketch_action.trigger()
    assert v.sketch.active_id == identifier
    w.tool_choice.setCurrentText('Select')
    mid = ((edited.x1+edited.x2)/2, (edited.y1+edited.y2)/2)
    click(qtbot, v, frame, mid)
    assert w.entity_context == (identifier, entity.id)


def test_both_rectangle_gestures_and_shift_context(qtbot):
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.tool_choice.setCurrentText('Rectangle')
    a, b = pixel(v, frame.to_world((-12, -8))), pixel(v, frame.to_world((-3, 2)))
    qtbot.mousePress(v, Qt.LeftButton, pos=a)
    qtbot.mouseMove(v, b)
    assert v.sketch.preview_actor.GetVisibility()
    qtbot.mouseRelease(v, Qt.LeftButton, pos=b)
    assert len(w.document.feature(identifier).parameters.entities) == 1
    click(qtbot, v, frame, (2, 3), Qt.ShiftModifier)
    assert v.sketch.controller.tool.stage == 'edge'
    click(qtbot, v, frame, (8, 11))
    assert v.sketch.controller.tool.stage == 'depth'
    qtbot.mouseMove(v, pixel(v, frame.to_world((0, 17))))
    click(qtbot, v, frame, (0, 17))
    entities = w.document.feature(identifier).parameters.entities
    assert len(entities) == 2 and not v.selections
    rectangle = entities[1]
    assert rectangle.angle != 0
    u = tuple(rectangle.points[1][i]-rectangle.points[0][i] for i in range(2))
    side = tuple(rectangle.points[3][i]-rectangle.points[0][i] for i in range(2))
    assert sum(u[i]*side[i] for i in range(2)) == pytest.approx(0, abs=1e-10)
    w.entity_fields['width'].setValue(12.5)
    w.entity_fields['height'].setValue(8.25)
    w.apply_dimensions()
    edited = w.document.feature(identifier).parameters.entities[1]
    assert (edited.width, edited.height, edited.angle) == (12.5, 8.25, rectangle.angle)
    click(qtbot, v, frame, (0, 0), Qt.ShiftModifier)
    qtbot.keyClick(v, Qt.Key_Escape)
    assert w.tool_choice.currentText() == 'Select'
    assert not v.sketch.preview_actor.GetVisibility()
    assert len(w.document.feature(identifier).parameters.entities) == 2


def test_shift_mixed_selection_and_shift_right_pan(qtbot):
    w = window(qtbot)
    v = w.viewport
    v.orient('Front')
    camera = v.renderer.GetActiveCamera()
    focal = camera.GetFocalPoint()
    point = pixel(v, (20, 0, 10))
    qtbot.mouseClick(v, Qt.LeftButton, pos=point)
    assert len(v.selections) == 1
    w.selection_choice.setCurrentIndex(1)
    edge = pixel(v, (20, 0, 0))
    qtbot.mouseClick(v, Qt.LeftButton, Qt.ShiftModifier, pos=edge)
    assert {s.kind for s in v.selections} == {'face', 'edge'}
    assert camera.GetFocalPoint() == focal
    qtbot.mouseClick(v, Qt.LeftButton, Qt.ShiftModifier, pos=edge)
    assert len(v.selections) == 1 and v.selection.kind == 'face'
    start = QPoint(v.width()//2, v.height()//2)
    qtbot.mousePress(v, Qt.RightButton, Qt.ShiftModifier, pos=start)
    qtbot.mouseMove(v, start+QPoint(50, 25))
    qtbot.mouseRelease(v, Qt.RightButton, Qt.ShiftModifier, pos=start+QPoint(50, 25))
    assert camera.GetFocalPoint() != focal
    assert camera.GetDirectionOfProjection() == pytest.approx((0, 1, 0))
    qtbot.keyClick(v, Qt.Key_Escape)
    assert not v.selections


@pytest.mark.parametrize('zoom', [0.5, 1, 2])
def test_edge_hit_radius_is_screen_based(qtbot, zoom):
    w = window(qtbot)
    v = w.viewport
    v.orient('Front')
    camera = v.renderer.GetActiveCamera()
    camera.SetParallelScale(v.model_span*zoom)
    v.clamp_zoom()
    v.set_selection_mode('edge')
    w.pick_radius.setValue(6)
    v.renderer.SetWorldPoint(20, 0, 0, 1)
    v.renderer.WorldToDisplay()
    x, y, _ = v.renderer.GetDisplayPoint()
    factor = v.GetRenderWindow().GetSize()[1]/v.height()
    v.pick_at(x, y-4*factor)
    assert v.selection and v.selection.kind == 'edge'
    assert v.edge_actor.GetProperty().GetLineWidth() == 1
    v.pick_at(x, y-8*factor)
    assert v.selection is None
    w.pick_radius.setValue(10)
    v.pick_at(x, y-8*factor)
    assert v.selection is not None


def test_sketch_undo_creation_restores_solid_mode(qtbot):
    w = window(qtbot)
    enter(w, 'YZ')
    w.undo_action.trigger()
    assert not w.document.sketches
    assert w.viewport.sketch.active_id is None and w.viewport.actor.GetVisibility()
    w.redo_action.trigger()
    assert len(w.document.sketches) == 1


def test_sketch_escape_and_blank_click_clear_property_selection(qtbot):
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.tool_choice.setCurrentText('Line')
    click(qtbot, v, frame, (1, 2))
    click(qtbot, v, frame, (10, 12))
    w.tool_choice.setCurrentText('Select')
    assert w.entity_context
    qtbot.keyClick(v, Qt.Key_Escape)
    assert w.entity_context is None and not v.sketch.highlight_actor.GetVisibility()
    click(qtbot, v, frame, (5.5, 7))
    assert w.entity_context
    click(qtbot, v, frame, (-20, -20))
    assert w.entity_context is None


def test_sketch_render_preview_and_highlight(qtbot):
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    import numpy as np
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.tool_choice.setCurrentText('Line')
    click(qtbot, v, frame, (-12, 8))
    hover(v, pixel(v, frame.to_world((12, 8))))

    def pixels():
        capture = vtkWindowToImageFilter()
        capture.SetInput(v.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        return vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars()).astype(int)

    p = pixels()
    assert np.count_nonzero((p[:, 1] > 200) & (p[:, 0] > 130) & (p[:, 2] > 130)) > 30
    click(qtbot, v, frame, (12, 8))
    p = pixels()
    assert np.count_nonzero((p[:, 0] > 220) & (p[:, 1] > 100) & (p[:, 2] < 100)) > 30
    w.tool_choice.setCurrentText('Select')
    qtbot.keyClick(v, Qt.Key_Escape)
    p = pixels()
    assert np.count_nonzero((p[:, 0] < 150) & (p[:, 1] > 180) & (p[:, 2] > 200)) > 30
    background = np.array([23, 31, 41])
    assert np.count_nonzero(np.max(np.abs(p - background), axis=1) < 3) > len(p)*0.6

from PySide6.QtCore import Qt, QPoint, QPointF
from hero_cad.document import Document
from hero_cad.sketch import Circle, Line
from test_sketch_ui import window, enter, click, pixel, hover
import pytest


def type_dimension(qtbot, v, text, key=Qt.Key_Return):
    qtbot.keyClicks(v, text[:1])
    assert v.dimensions.input.isVisible()
    qtbot.keyClicks(v.dimensions.input, text[1:])
    qtbot.keyClick(v.dimensions.input, key)


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_interactive_circle_slot_exact_entry_and_cancel(qtbot, tmp_path, plane):
    w = window(qtbot)
    sid = enter(w, plane)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, f.to_world((0, 0))))
    hover(v, pixel(v, f.to_world((8, 6))))
    assert v.dimensions.isVisible() and 'Radius' in v.dimensions.label.text()
    qtbot.keyClicks(v, '0')
    assert v.dimensions.input.isVisible()
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, f.to_world((8, 6))))
    assert not w.document.feature(sid).parameters.entities
    qtbot.keyClicks(v.dimensions.input, '.0201234567890123')
    qtbot.keyClick(v.dimensions.input, Qt.Key_Return)
    circle = w.document.feature(sid).parameters.entities[0]
    assert circle.radius == 0.0201234567890123
    qtbot.mousePress(v, Qt.LeftButton, Qt.ShiftModifier, pos=pixel(v, f.to_world((10, 10))))
    hover(v, pixel(v, f.to_world((15, 10))))
    type_dimension(qtbot, v, '2.1234567890123')
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, f.to_world((15, 10))))
    assert v.sketch.controller.tool.stage == 'center'
    hover(v, pixel(v, f.to_world((18, 16))))
    type_dimension(qtbot, v, '12.3456789012345')
    slot = w.document.feature(sid).parameters.entities[1]
    assert slot.radius == 2.1234567890123 and slot.distance == 12.3456789012345
    before = w.document.features
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, f.to_world((-5, -5))))
    hover(v, pixel(v, f.to_world((-8, -8))))
    type_dimension(qtbot, v, '-1')
    assert v.dimensions.input.isVisible() and w.document.features == before
    qtbot.keyClick(v.dimensions.input, Qt.Key_Escape)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, f.to_world((-8, -8))))
    assert w.document.features == before and not v.sketch.preview_actor.GetVisibility()
    w.document.save(tmp_path/f'{plane}.starcad')
    assert Document.load(w.document.path).features == before
    w.undo()
    assert len(w.document.feature(sid).parameters.entities) == 1
    w.redo()
    assert w.document.features == before


def test_dimensions_tab_rectangle_and_line_direction(qtbot):
    w = window(qtbot)
    sid = enter(w)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Rectangle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, f.to_world((0, 0))))
    hover(v, pixel(v, f.to_world((-8, -6))))
    type_dimension(qtbot, v, '7.1234567890123', Qt.Key_Tab)
    assert 'Depth' in v.dimensions.input.placeholderText()
    qtbot.keyClicks(v.dimensions.input, '4.1234567890123')
    qtbot.keyClick(v.dimensions.input, Qt.Key_Return)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, f.to_world((-8, -6))))
    rectangle = w.document.feature(sid).parameters.entities[-1]
    assert rectangle.width == 7.1234567890123 and rectangle.height == 4.1234567890123
    w.tool_choice.setCurrentText('Line')
    click(qtbot, v, f, (0, 0))
    hover(v, pixel(v, f.to_world((6, 8))))
    type_dimension(qtbot, v, '5')
    line = w.document.feature(sid).parameters.entities[-1]
    assert line.x2 == pytest.approx(3, abs=.05) and line.y2 == pytest.approx(4, abs=.05)


def populated(qtbot):
    w = window(qtbot)
    sid = enter(w)
    entities = [Circle(-10, 0, 3), Circle(10, 0, 3), Line(-10, -10, 10, -10)]
    for e in entities:
        w.document.add_entity(sid, e)
    w.refresh()
    return w, sid, entities


def test_viewport_multiselect_context_and_delete_undo(qtbot):
    w, sid, es = populated(qtbot)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    click(qtbot, v, f, (-7, 0))
    click(qtbot, v, f, (13, 0), Qt.ShiftModifier)
    assert v.sketch.entity_ids == {es[0].id, es[1].id}
    assert len(w.selected_keys()) == 2
    qtbot.mouseClick(v, Qt.RightButton, pos=pixel(v, f.to_world((-7, 0))))
    assert len(w.selected_keys()) == 2
    assert [a.text() for a in w._context_menu.actions()] == ['Edit Parameters', 'Edit Sketch', 'Delete']
    w._context_menu.close()
    before, n = w.document.features, len(w.document._undo)
    v.setFocus()
    qtbot.keyClick(v, Qt.Key_Delete)
    assert w.document.feature(sid).parameters.entities == (es[2],)
    assert len(w.document._undo) == n+1 and not v.sketch.entity_ids
    assert not v.sketch.preview_actor.GetVisibility()
    w.undo()
    assert w.document.features == before
    w.redo()
    assert w.document.feature(sid).parameters.entities == (es[2],)


def test_browser_multi_delete_context_selection_and_entire_sketch(qtbot):
    w, sid, es = populated(qtbot)
    first = w.browser_items[('entity', sid, es[0].id)]
    second = w.browser_items[('entity', sid, es[1].id)]
    w.browser.setCurrentItem(first)
    second.setSelected(True)
    w.browser_context_menu(w.browser.visualItemRect(first).center())
    assert len(w.selected_keys()) == 2
    w._context_menu.close()
    third = w.browser_items[('entity', sid, es[2].id)]
    w.browser_context_menu(w.browser.visualItemRect(third).center())
    assert w.selected_keys() == {('entity', sid, es[2].id)}
    w._context_menu.close()
    w.browser.setFocus()
    qtbot.keyClick(w.browser, Qt.Key_Backspace)
    assert w.document.feature(sid).parameters.entities == tuple(es[:2])
    w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
    w.delete_selected()
    assert not w.document.sketches and w.viewport.sketch.active_id is None
    w.undo()
    assert len(w.document.feature(sid).parameters.entities) == 2


def test_parameter_text_delete_does_not_delete_geometry(qtbot):
    w, sid, es = populated(qtbot)
    w.browser.setCurrentItem(w.browser_items[('entity', sid, es[0].id)])
    field = w.entity_fields['radius']
    field.setFocus()
    before = w.document.features
    qtbot.keyClick(field, Qt.Key_Backspace)
    assert w.document.features == before


def test_context_unselected_and_referenced_sketch_rejection(qtbot):
    from dataclasses import replace
    w, sid, es = populated(qtbot)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    w.browser.setCurrentItem(w.browser_items[('entity', sid, es[0].id)])
    qtbot.mouseClick(v, Qt.RightButton, pos=pixel(v, f.to_world((13, 0))))
    assert w.selected_keys() == {('entity', sid, es[1].id)}
    w._context_menu.close()
    dependent = w.document.add_sketch('XZ')
    feature = w.document.feature(dependent)
    w.document.replace_feature(replace(feature, references=('plane:XZ', sid)))
    w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
    before = w.document.features
    w.browser.setFocus()
    w.delete_selected()
    assert w.document.features == before
    assert 'references' in w.statusBar().currentMessage()


def test_dimension_input_survives_pan_and_shift_right_never_opens_menu(qtbot):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    w = window(qtbot)
    sid = enter(w)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v, Qt.LeftButton, Qt.ShiftModifier, pos=pixel(v, f.to_world((0, 0))))
    hover(v, pixel(v, f.to_world((8, 6))))
    type_dimension(qtbot, v, '2')
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, f.to_world((8, 6))))
    assert v.sketch.controller.tool.stage == 'center'
    p = QPoint(250, 200)
    qtbot.mousePress(v, Qt.RightButton, Qt.ShiftModifier, pos=p)
    moved = p+QPoint(50, 30)
    event = QMouseEvent(QEvent.MouseMove, QPointF(moved), QPointF(v.mapToGlobal(moved)),
                        Qt.NoButton, Qt.RightButton, Qt.ShiftModifier)
    QApplication.sendEvent(v, event)
    qtbot.mouseRelease(v, Qt.RightButton, Qt.ShiftModifier, pos=moved)
    assert not hasattr(w, '_context_menu')
    assert v.sketch.controller.tool.stage == 'center'
    assert v.sketch.controller.tool.radius == 2
    hover(v, pixel(v, f.to_world((12, 9))))
    type_dimension(qtbot, v, '15')
    slot = w.document.feature(sid).parameters.entities[-1]
    assert slot.radius == 2 and slot.distance == 15


def test_multi_selection_delete_and_undo_render(qtbot):
    import numpy as np
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    w, sid, es = populated(qtbot)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    # Different property forms can resize docks. Hold the render size fixed so
    # image comparisons measure deletion rather than window-layout changes.
    v.setFixedSize(640, 480)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)

    def pixels():
        # Read the frame actually presented by the action: capturing must not
        # repair a missing redraw and conceal stale deleted geometry.
        capture = vtkWindowToImageFilter()
        capture.ShouldRerenderOff()
        capture.SetInput(v.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        return vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars()).astype(int)

    v.GetRenderWindow().Render()
    baseline = pixels()
    cyan = lambda p: (p[:, 2] > 130) & (p[:, 1]-p[:, 0] > 40) & (p[:, 2]-p[:, 0] > 60)
    assert np.count_nonzero(cyan(baseline)) > 100
    click(qtbot, v, f, (-7, 0))
    click(qtbot, v, f, (13, 0), Qt.ShiftModifier)
    selected = pixels()
    orange = (selected[:, 0] > 150) & (selected[:, 0]-selected[:, 1] > 40) & (selected[:, 1]-selected[:, 2] > 40)
    assert np.count_nonzero(orange) > 100
    qtbot.mouseClick(v, Qt.RightButton, pos=pixel(v, f.to_world((-7, 0))))
    w._context_menu.actions()[-1].trigger()
    w._context_menu.close()
    deleted = pixels()
    assert w.document.feature(sid).parameters.entities == (es[2],)
    assert np.count_nonzero(cyan(deleted)) > 30  # Remaining line, not a blank frame.
    assert np.count_nonzero(np.max(abs(deleted-baseline), axis=1) > 5) > 100
    w.undo()
    assert np.max(abs(pixels()-baseline)) < 3
    w.redo()
    assert np.max(abs(pixels()-deleted)) < 3


@pytest.mark.parametrize('text', ['0', '-1', 'nan', 'inf', 'invalid'])
def test_invalid_dimension_text_stays_uncommitted(qtbot, text):
    w = window(qtbot)
    sid = enter(w)
    v, f = w.viewport, w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, f.to_world((0, 0))))
    hover(v, pixel(v, f.to_world((4, 3))))
    v.dimensions.begin(text)
    qtbot.keyClick(v.dimensions.input, Qt.Key_Return)
    assert v.dimensions.input.isVisible()
    assert not w.document.feature(sid).parameters.entities
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, f.to_world((4, 3))))
    assert not w.document.feature(sid).parameters.entities
    qtbot.keyClick(v.dimensions.input, Qt.Key_Escape)
    assert not v.sketch.controller.tool and not v.sketch.preview_actor.GetVisibility()


def test_context_retains_batch_when_pending_properties_rebuild_tree(qtbot):
    w, sid, es = populated(qtbot)
    w.browser.setCurrentItem(w.browser_items[('entity', sid, es[0].id)])
    w.browser_items[('entity', sid, es[1].id)].setSelected(True)
    w.entity_fields['radius'].setValue(4)
    w.viewport_context_menu((sid, es[1].id), w.viewport.mapToGlobal(QPoint(20, 20)))
    assert w.document.feature(sid).parameters.entities[0].radius == 4
    assert w.selected_keys() == {('entity', sid, es[0].id), ('entity', sid, es[1].id)}
    w._context_menu.close()


def test_plain_right_drag_retains_camera_zoom_without_context_menu(qtbot):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    w, sid, es = populated(qtbot)
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    before, scale = w.document.features, camera.GetParallelScale()
    p = QPoint(220, 200)
    qtbot.mousePress(v, Qt.RightButton, pos=p)
    moved = p+QPoint(10, 50)
    QApplication.sendEvent(v, QMouseEvent(QEvent.MouseMove, QPointF(moved), QPointF(v.mapToGlobal(moved)),
                                         Qt.NoButton, Qt.RightButton, Qt.NoModifier))
    qtbot.mouseRelease(v, Qt.RightButton, pos=moved)
    assert camera.GetParallelScale() != scale
    assert w.document.features == before and not hasattr(w, '_context_menu')

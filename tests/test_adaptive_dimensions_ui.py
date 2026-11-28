from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
import pytest
from test_sketch_ui import window, enter, pixel, hover


def start(w,qtbot,tool='Rectangle'):
    sid = enter(w)
    v = w.viewport
    w.tool_island.set_collapsed(True)
    w.tool_choice.setCurrentText(tool)
    w.snap_grid_action.setChecked(False)
    w.snap_origin_action.setChecked(False)
    frame = w.document.feature(sid).parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((2,3))))
    hover(v,pixel(v,frame.to_world((8,7))))
    assert v.dimensions.isVisible()
    return sid,frame


@pytest.mark.parametrize('tool',['Line','Rectangle','Circle','Slot'])
def test_popup_moves_only_on_cursor_approach_and_forwards_native_child_move(qtbot,tool):
    w = window(qtbot)
    sid,frame = start(w,qtbot,tool)
    v,popup = w.viewport,w.viewport.dimensions
    original = popup.pos()
    hover(v,pixel(v,frame.to_world((9,8))))
    assert (popup.pos()-original).manhattanLength() <= 2  # viewport-edge text-width clamp
    original = popup.pos()
    old_cursor = popup.input.mapTo(v,popup.input.rect().center())
    global_cursor = v.mapToGlobal(old_cursor)
    event = QMouseEvent(QEvent.MouseMove,QPointF(popup.input.rect().center()),QPointF(global_cursor),
                        Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
    expected = v.sketch.point_at(old_cursor.x(),v.height()-1-old_cursor.y())
    QApplication.sendEvent(popup.input,event)
    assert popup.pos() != original
    assert not popup.geometry().adjusted(-14,-14,14,14).contains(old_cursor)
    assert v.sketch.controller.tool.last_point == pytest.approx(expected,abs=1e-10)
    assert not w.document.feature(sid).parameters.entities
    after = popup.pos()
    hover(v,old_cursor+QPoint(1,0))
    assert popup.pos() == after
    qtbot.keyClick(v,Qt.Key_Escape)
    assert not popup.isVisible()


def test_ctrl_mouse_entry_and_keyboard_entry_stay_stationary_and_keep_precision(qtbot):
    w = window(qtbot)
    sid,frame = start(w,qtbot,'Circle')
    v,popup = w.viewport,w.viewport.dimensions
    before = popup.pos()
    cursor = popup.input.mapTo(v,popup.input.rect().center())
    popup.update_values(cursor,Qt.ControlModifier)
    assert popup.pos() == before
    qtbot.mouseClick(popup.input,Qt.LeftButton,Qt.ControlModifier)
    assert popup.editing
    value = '0.0201234567890123'
    qtbot.keyClicks(popup.input,value)
    assert '0.020123457' in popup.label.text()
    assert popup.pos() == before
    hover(v,pixel(v,frame.to_world((-10,-10))))
    assert popup.pos() == before
    qtbot.keyClick(popup.input,Qt.Key_Return)
    assert w.document.feature(sid).parameters.entities[0].radius == float(value)
    assert not popup.isVisible()


def test_numeric_popup_remains_accessible_after_viewport_resize(qtbot):
    w = window(qtbot)
    w.resize(1600,1000)
    QApplication.processEvents()
    _,frame = start(w,qtbot)
    v,popup = w.viewport,w.viewport.dimensions
    popup.move(v.width()-popup.width()-10,v.height()-popup.height()-10)
    QApplication.setActiveWindow(w)
    popup.begin('12.123456789')
    assert popup.input.hasFocus()
    w.resize(950,650)
    QApplication.processEvents()
    assert v.rect().contains(popup.geometry())
    assert popup.editing
    assert popup.input.text() == '12.123456789'
    assert popup.input.hasFocus()
    before = popup.pos()
    hover(v,pixel(v,frame.to_world((10,10))))
    assert popup.pos() == before


@pytest.mark.parametrize('preset',['Compact','Expanded'])
@pytest.mark.parametrize('opacity',[50,100])
def test_adaptive_moves_restore_island_native_pixels(qtbot,preset,opacity):
    import numpy as np
    from test_dimension_overlay_ui import native_pixels
    w = window(qtbot)
    sid = enter(w)
    v,popup,island = w.viewport,w.viewport.dimensions,w.tool_island
    island.set_preset(preset)
    island.place(QPoint(220,110))
    w.dimension_opacity.setValue(opacity)
    w.tool_choice.setCurrentText('Slot')
    QApplication.processEvents()
    rect = island.geometry().translated(v.pos())
    baseline = native_pixels(w)
    frame = w.document.feature(sid).parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((2,3))))
    hover(v,pixel(v,frame.to_world((7,6))))
    popup.cursor_position = QPoint(170,150)
    popup.anchor_pending = False
    popup.update_values()
    for _ in range(6):
        point = popup.geometry().center()
        popup.update_values(point,Qt.NoModifier)
        QApplication.processEvents()
        assert not popup.geometry().adjusted(-14,-14,14,14).contains(point)
    popup.hide()
    QApplication.processEvents()
    actual = native_pixels(w)
    crop = (slice(rect.y()+35,rect.bottom()-10),slice(rect.x()+5,rect.right()-5))
    assert np.array_equal(actual[crop],baseline[crop])

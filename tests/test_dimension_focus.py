from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from test_sketch_ui import window, enter, pixel, hover


def test_construction_claims_keyboard_focus_after_tool_picker(qtbot):
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Circle')
    w.activateWindow()
    QApplication.processEvents()
    w.tool_choice.setFocus()
    assert QApplication.focusWidget() is w.tool_choice
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((8, 6))))
    assert QApplication.focusWidget() is v
    qtbot.keyClicks(QApplication.focusWidget(), '2')
    assert QApplication.focusWidget() is v.dimensions.input
    assert v.sketch.controller.tool.preview_entity.radius == 2
    qtbot.keyClicks(QApplication.focusWidget(), '.125')
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((8, 6))))
    assert w.document.feature(sid).parameters.entities[-1].radius == 2.125


def test_tab_focus_live_preview_and_release_waits_for_enter(qtbot):
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.activateWindow()
    QApplication.processEvents()
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((8, 6))))
    assert v.dimensions.input.isVisible() and not v.dimensions.editing
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    assert QApplication.focusWidget() is v.dimensions.input and v.dimensions.editing
    qtbot.keyClicks(QApplication.focusWidget(), '2.125')
    assert v.sketch.controller.tool.preview_entity.radius == 2.125
    assert not w.document.feature(sid).parameters.entities
    position = v.dimensions.pos()
    hover(v, pixel(v, frame.to_world((-15, -10))))
    assert v.dimensions.pos() == position
    assert v.sketch.controller.tool.preview_entity.radius == 2.125
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((-15, -10))))
    assert not w.document.feature(sid).parameters.entities
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert w.document.feature(sid).parameters.entities[-1].radius == 2.125
    assert QApplication.focusWidget() is v


def test_visible_editor_can_be_clicked_and_escape_cancels_live_preview(qtbot):
    from PySide6.QtCore import QPoint
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.activateWindow()
    QApplication.processEvents()
    w.tool_choice.setCurrentText('Line')
    qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    anchor = v.dimensions.pos()
    hover(v, pixel(v, frame.to_world((6, 8))))
    assert v.dimensions.pos() == anchor  # The field can be reached by the pointer.
    field = v.dimensions.input
    assert v.childAt(field.mapTo(v, QPoint(5, 5))) is field
    qtbot.mouseClick(field, Qt.LeftButton)
    assert QApplication.focusWidget() is field and v.dimensions.editing
    qtbot.keyClicks(QApplication.focusWidget(), '5')
    assert v.sketch.controller.tool.preview[-1] == (3, 4)
    assert not w.document.feature(sid).parameters.entities
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    assert not w.document.feature(sid).parameters.entities
    assert not v.dimensions.isVisible() and not v.sketch.preview_actor.GetVisibility()


def test_rectangle_fields_update_preview_before_commit(qtbot):
    from star_cad.sketch import Rectangle
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.activateWindow()
    QApplication.processEvents()
    w.tool_choice.setCurrentText('Rectangle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((6, 8))))
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    qtbot.keyClicks(QApplication.focusWidget(), '7.125')
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    qtbot.keyClicks(QApplication.focusWidget(), '4.25')
    assert v.sketch.controller.preview == Rectangle(0, 0, 7.125, 4.25).points
    assert not w.document.feature(sid).parameters.entities
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    rectangle = w.document.feature(sid).parameters.entities[-1]
    assert rectangle.width == 7.125 and rectangle.height == 4.25
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((6, 8))))


def test_popup_offset_opacity_hide_and_restore(qtbot):
    from PySide6.QtCore import QPoint
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    v.setFixedSize(900, 600)
    frame = w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Line')
    qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    popup = v.dimensions
    popup.anchor_pending = True
    popup.update_values(QPoint(20, 30))
    assert popup.pos() == QPoint(118, 98)  # Original 18px + 80 right / 50 down.
    before = w.document.features
    w.dimension_opacity.setValue(50)
    assert popup.opacity_effect.opacity() == 0.5 and popup.isVisible()
    assert w.dimension_opacity_value.text() == '50%'
    assert w.document.features == before
    w.dimension_opacity.setValue(0)
    assert not popup.isVisible() and not popup.begin('5')
    assert w.dimension_opacity_value.text() == 'Off'
    hover(v, pixel(v, frame.to_world((6, 8))))
    assert not popup.isVisible()
    qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v, frame.to_world((6, 8))))
    assert len(w.document.feature(sid).parameters.entities) == 1
    # It stays off on the next shape; restoring opacity reveals its live values.
    qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v, frame.to_world((-5, -5))))
    w.dimension_opacity.setValue(100)
    assert popup.isVisible() and popup.opacity_effect.opacity() == 1.0
    popup.anchor_pending = True
    popup.update_values(QPoint(890, 590))
    assert popup.x()+popup.width() <= v.width()
    assert popup.y()+popup.height() <= v.height()


def test_hiding_editor_releases_focus_and_mouse_placement(qtbot):
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.activateWindow()
    QApplication.processEvents()
    w.tool_choice.setCurrentText('Circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((6, 8))))
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    assert v.dimensions.editing
    w.dimension_opacity.setValue(0)
    assert not v.dimensions.editing and not v.dimensions.isVisible()
    assert QApplication.focusWidget() is not v.dimensions.input
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((6, 8))))
    assert len(w.document.feature(sid).parameters.entities) == 1

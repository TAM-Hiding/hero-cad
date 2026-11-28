"""Check actual native pixels exposed beneath the numeric overlay."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt, QCoreApplication, QEvent
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from test_sketch_ui import window, pixel, hover
from test_model_references_ui import attached


def native_pixels(w):
    # QWidget.grab() repaints into a new image and can conceal stale native
    # contents. Capture the live X window after its ordinary paint events.
    image = w.screen().grabWindow(w.winId()).toImage().convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.width(),4).copy()


@pytest.mark.parametrize('preset',['Compact','Medium','Expanded'])
@pytest.mark.parametrize('tool',['Line','Rectangle','Circle','Slot'])
@pytest.mark.parametrize('opacity',[50,100])
def test_numeric_overlay_restores_island_native_pixels(qtbot,preset,tool,opacity):
    w = window(qtbot)
    attached(w)
    v,popup,island = w.viewport,w.viewport.dimensions,w.tool_island
    island.set_preset(preset)
    island.place(QPoint(220,110))
    w.dimension_opacity.setValue(opacity)
    w.tool_choice.setCurrentText(tool)
    QApplication.processEvents()
    rect = island.geometry().translated(v.pos())
    baseline = native_pixels(w)
    frame = v.sketch.feature.parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((2,3))))
    hover(v,pixel(v,frame.to_world((7,6))))
    assert popup.isVisible()
    before = w.document.features,tuple(w.document._undo)
    for i in range(12):
        # Force stage/size-driven positions through the island controls.
        popup.cursor_position = QPoint(140+4*i,125+2*i)
        popup.anchor_pending = False
        popup.update_values()
        QApplication.processEvents()
    popup.hide()
    QApplication.processEvents()
    actual = native_pixels(w)
    crop = (slice(rect.y()+35,rect.bottom()-10),slice(rect.x()+5,rect.right()-5))
    assert np.array_equal(actual[crop],baseline[crop])
    assert (w.document.features,tuple(w.document._undo)) == before
    v.sketch.set_tool('select')
    assert not popup.isVisible()
    # Reflow, resize and zoom retain usable controls and a clean lifecycle.
    w.resize(w.width()+40,w.height()+30)
    v.renderer.GetActiveCamera().SetParallelScale(45)
    v.GetRenderWindow().Render()
    assert island.isVisible() and island.size_choice.currentText() == preset


@pytest.mark.parametrize('tool',['Line','Rectangle','Circle','Slot'])
def test_complete_numeric_operation_and_cancel_clear_overlay(qtbot,tool):
    w = window(qtbot)
    sid = attached(w)
    w.tool_choice.setCurrentText(tool)
    v,popup = w.viewport,w.viewport.dimensions
    frame = v.sketch.feature.parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((2,3))))
    end = pixel(v,frame.to_world((7,6)))
    hover(v,end)
    if tool == 'Line':
        qtbot.mouseRelease(v,Qt.LeftButton,pos=end)
        qtbot.mouseClick(v,Qt.LeftButton,pos=end)
    else:
        qtbot.mouseRelease(v,Qt.LeftButton,pos=end)
        if tool == 'Slot':
            end = pixel(v,frame.to_world((14,8)))
            hover(v,end)
            qtbot.mouseClick(v,Qt.LeftButton,pos=end)
    assert len(w.document.feature(sid).parameters.entities) == 1
    assert not popup.isVisible()
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((10,10))))
    hover(v,pixel(v,frame.to_world((14,14))))
    assert popup.isVisible()
    qtbot.keyClick(v,Qt.Key_Escape)
    assert not popup.isVisible()
    assert len(w.document.feature(sid).parameters.entities) == 1


def test_overlay_filter_survives_window_destruction(qtbot):
    from hero_cad.ui.main_window import MainWindow
    # This window is intentionally destroyed here. Only register the surviving
    # second window with qtbot, and let initial deferred layout finish first.
    first = MainWindow()
    first.show()
    qtbot.waitExposed(first)
    qtbot.waitUntil(lambda: first.tool_island._ready)
    attached(first)
    first.tool_choice.setCurrentText('Slot')
    v = first.viewport
    frame = v.sketch.feature.parameters.frame
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((2,3))))
    hover(v,pixel(v,frame.to_world((7,6))))
    assert v.dimensions.isVisible()
    first.close()
    first.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    QApplication.processEvents()
    second = window(qtbot)
    attached(second)
    assert second.viewport.sketch.active_id

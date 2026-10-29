"""Operation presentation geometry/focus; no screenshot-pixel assertions."""
import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDockWidget, QWidget
from hero_cad.features import ChamferParameters
from hero_cad.geometry import volume
from hero_cad.sketch import Circle
from hero_cad.ui.operation_appearance import (
    OPERATION_STYLE, INLINE_STYLE, ORANGE, INPUT, BUTTON, FOCUS, HOVER,
    opening_position, place_operation, fit_operation_size,
)
from hero_cad.face_history import subshapes
from OCP.TopAbs import TopAbs_EDGE
from test_sketch_ui import window, enter, pixel, hover
from test_sketch_editing_ui import type_dimension


def chamfer_parameters(w):
    box = w.document.features[0].id
    edge = subshapes(w.document.solid_shapes[box], TopAbs_EDGE)[0]
    owner, reference = w.document.edge_reference(edge)
    return ChamferParameters(owner, reference)


def wait_open(qtbot, panel):
    qtbot.waitUntil(lambda: not panel.open_timer.isActive())
    qtbot.waitUntil(lambda: panel.isVisible() and QApplication.focusWidget() in
                   (panel.quick_distance, panel.distance.lineEdit(), panel.distance, panel.operation))


def island_rect(w):
    return QRect(w.tool_island.mapToGlobal(QPoint()), w.tool_island.size())


@pytest.mark.parametrize('preset', ['Compact','Medium','Expanded'])
def test_actual_island_size_left_alignment_gap_and_focus(qtbot, preset):
    w = window(qtbot)
    w.tool_island.set_preset(preset)
    w.tool_island.place(QPoint(40,12))
    original_style = w.tool_island.styleSheet()
    w.operation_panel.open_chamfer(chamfer_parameters(w))
    p = w.operation_panel
    wait_open(qtbot,p)
    frame, anchor = p.frameGeometry(), island_rect(w)
    assert frame.left() == anchor.left()
    assert 2 <= frame.top() - (anchor.top()+anchor.height()) <= 5
    assert p.screen().availableGeometry().contains(frame)
    assert w.tool_island.styleSheet() == original_style
    assert p.quick_distance.hasFocus() and p.quick_distance.selectedText() == '1'
    # Immediate typing and Enter retain the existing chamfer confirmation path.
    qtbot.keyClicks(p.quick_distance,'2')
    qtbot.keyClick(p.quick_distance,Qt.Key_Return)
    assert w.document.features[-1].type == 'chamfer'
    assert w.document.features[-1].parameters.distance == 2


def test_new_open_uses_moved_island_but_active_dialog_is_independent(qtbot):
    w = window(qtbot)
    w.tool_island.set_collapsed(True)
    w.tool_island.place(QPoint(50,30))
    p = w.operation_panel
    parameters = chamfer_parameters(w)
    p.open_chamfer(parameters)
    wait_open(qtbot,p)
    original = p.pos()
    w.tool_island.place(QPoint(100,90))
    assert p.pos() == original
    moved = original + QPoint(25,25)
    p.move(moved)
    p.resize(p.width()+30,p.height()+20)
    manual_size = p.size()
    p.quick_distance.setText('3.25')  # Validation/layout must not move the window.
    QApplication.processEvents()
    assert p.pos() == moved
    assert p.size() == manual_size
    p.quick_distance.setText('invalid')
    p.quick_distance.setText('3.25')
    p.resize(p.width()+10,p.height()+15)
    recovered_size = p.size()
    p.quick_distance.setText('4.25')
    QApplication.processEvents()
    assert p.pos() == moved and p.size() == recovered_size
    p.cancel()
    p.open_chamfer(parameters)
    wait_open(qtbot,p)
    assert p.frameGeometry().left() == island_rect(w).left()
    assert p.frameGeometry().top() == island_rect(w).top()+island_rect(w).height()+3
    assert p.pos() != moved


def test_screen_bottom_prefers_above_and_horizontal_clamp(qtbot):
    w = window(qtbot)
    p = w.operation_panel
    p.open_chamfer(chamfer_parameters(w))
    wait_open(qtbot,p)
    screen = p.screen().availableGeometry()
    # Moving the main window places the island near the actual screen bottom.
    anchor = island_rect(w)
    w.move(w.pos()+QPoint(screen.right()-anchor.right(),screen.bottom()-anchor.bottom()-2))
    QApplication.processEvents()
    place_operation(p,w.tool_island,p.requested_size())
    frame, anchor = p.frameGeometry(), island_rect(w)
    assert screen.contains(frame)
    assert frame.bottom()+4 == anchor.top()  # 3 logical pixels, exclusive bottom.
    assert frame.left() <= anchor.left()


@pytest.mark.parametrize('area,anchor,expected', [
    (QRect(0,0,1280,1024),QRect(40,20,292,352),QPoint(40,375)),
    (QRect(0,0,1280,1024),QRect(1100,800,142,40),QPoint(930,597)),
    (QRect(-1280,0,1280,1024),QRect(-1200,20,292,352),QPoint(-1200,375)),
    (QRect(0,0,400,300),QRect(10,100,142,40),QPoint(10,0)),
])
def test_global_coordinates_and_no_room_fallback(area,anchor,expected):
    assert opening_position(anchor,QSize(350,200),area) == expected


def test_constrained_screen_scrolls_form_without_hiding_title_or_controls(qtbot):
    w = window(qtbot)
    sid = w.document.add_sketch('XY')
    c = Circle(60,0,2)
    w.document.add_entity(sid,c)
    w.refresh()
    p = w.operation_panel
    p.open(source=(sid,c.id,()))
    wait_open(qtbot,p)
    area = QRect(0,0,360,230)
    fit_operation_size(p,p.requested_size(),area,opening=True)
    p.move(area.topLeft())
    QApplication.processEvents()
    assert area.contains(p.frameGeometry())
    assert p.scroll.verticalScrollBar().maximum() > 0
    p.scroll.ensureWidgetVisible(p.apply_button)
    QApplication.processEvents()
    button_rect = QRect(p.apply_button.mapTo(p.scroll.viewport(),QPoint()),p.apply_button.size())
    assert p.scroll.viewport().rect().contains(button_rect.center())
    # QDockWidget can itself use a frameless Tool window on X11. Preserve Qt's
    # native choice rather than requiring a platform-specific flag value.
    native = QDockWidget(w)
    native.setWidget(QWidget())
    native.setFloating(True)
    assert p.isFloating()
    assert p.windowFlags() & Qt.FramelessWindowHint == native.windowFlags() & Qt.FramelessWindowHint
    assert p.features() & QDockWidget.DockWidgetMovable


def test_shared_style_is_scoped_to_operation_and_inline_controls(qtbot):
    w = window(qtbot)
    snapshots = [widget.styleSheet() for widget in (w.tool_island,w.browser,w.property_tabs,w.menuBar(),w.viewport)]
    p = w.operation_panel
    p.open_chamfer(chamfer_parameters(w))
    wait_open(qtbot,p)
    assert p.styleSheet() == OPERATION_STYLE
    assert ORANGE in p.styleSheet() and BUTTON in p.styleSheet()
    assert f'background: {FOCUS}' in p.styleSheet() and f'background: {HOVER}' in p.styleSheet()
    assert 'border-radius: 8px' in p.styleSheet()
    assert p.apply_button.property('operationRole') == 'primary'
    assert p.cancel_button.property('operationRole') is None
    assert p.surface.palette().color(QPalette.Window).name().upper() == ORANGE
    assert p.quick_distance.palette().color(QPalette.Base).name().upper() == INPUT
    assert w.viewport.dimensions.styleSheet() == INLINE_STYLE
    assert snapshots == [widget.styleSheet() for widget in (w.tool_island,w.browser,w.property_tabs,w.menuBar(),w.viewport)]


def test_advanced_extrusion_focus_preserves_explicit_preview_and_combine(qtbot):
    w = window(qtbot)
    sid = w.document.add_sketch('XY')
    c = Circle(10,10,2)
    w.document.add_entity(sid,c)
    w.refresh()
    p = w.operation_panel
    p.open(source=(sid,c.id,()))
    wait_open(qtbot,p)
    assert p.isFloating() and p.windowTitle() == 'Extrude'
    assert p.styleSheet() == OPERATION_STYLE
    before = w.document.features
    qtbot.keyClicks(QApplication.focusWidget(),'5')
    qtbot.keyClick(QApplication.focusWidget(),Qt.Key_Return)
    assert p.active and w.document.features == before  # Advanced path still requires Preview/Apply.
    assert p.distance.value() == 5
    assert p.preview() and p.commit()
    eid = w.document.features[-1].id
    box = w.document.features[0].id
    p.open(bodies=(box,eid))
    wait_open(qtbot,p)
    assert p.isFloating() and p.windowTitle() == 'Combine'
    assert p.operation.hasFocus() and p.styleSheet() == OPERATION_STYLE
    p.operation.setCurrentIndex(p.operation.findData('cut'))
    assert p.preview() and p.commit()
    assert w.document.features[-1].type == 'boolean'
    assert volume(w.document.shape) < 24000


def test_inline_slot_distance_keeps_geometry_anchor_precision_and_escape(qtbot):
    w = window(qtbot)
    w.activateWindow()
    QApplication.processEvents()
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.tool_choice.setCurrentText('Slot')
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((10,10))))
    hover(v,pixel(v,frame.to_world((15,10))))
    type_dimension(qtbot,v,'2')
    qtbot.mouseRelease(v,Qt.LeftButton,pos=pixel(v,frame.to_world((15,10))))
    hover(v,pixel(v,frame.to_world((25,10))))
    dim = v.dimensions
    assert 'distance' in dim.label.text().lower()
    anchor = dim.cursor_position
    expected = QPoint(max(0,min(anchor.x()+98,v.width()-dim.width())),
                      max(0,min(anchor.y()+68,v.height()-dim.height())))
    assert dim.pos() == expected and dim.styleSheet() == INLINE_STYLE
    original = dim.pos()
    w.tool_island.place(QPoint(0,0))
    assert dim.pos() == original
    type_dimension(qtbot,v,'12.34567890123')
    slot = w.document.feature(sid).parameters.entities[-1]
    assert slot.radius == 2 and slot.distance == 12.34567890123
    before = w.document.features
    qtbot.mousePress(v,Qt.LeftButton,pos=pixel(v,frame.to_world((-5,-5))))
    hover(v,pixel(v,frame.to_world((10,-5))))
    assert dim.names  # Keep the radius above the existing snap tolerance.
    qtbot.keyClick(v,Qt.Key_Tab)
    assert dim.input.hasFocus()
    qtbot.keyClick(dim.input,Qt.Key_Escape)
    assert w.document.features == before and not dim.isVisible()

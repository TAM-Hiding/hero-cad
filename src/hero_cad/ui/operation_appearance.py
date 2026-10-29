"""Bounded presentation helpers for operation windows and inline numeric entry."""
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QGuiApplication

# Slightly lighter than the suggested orange so dark labels stay readable.
ORANGE = '#B87743'
SECONDARY_ORANGE = '#874923'
INPUT = '#263B46'
BUTTON = '#426879'
HOVER = '#56899B'
FOCUS = '#65B8D0'
TEXT = '#171D22'
LIGHT_TEXT = '#F0F3F4'
ACCENT = '#D08B50'
GAP = 3


def _controls(scope, padding):
    return f'''
        {scope} QLabel {{ color: {TEXT}; background: transparent; border: none; }}
        {scope} QLineEdit, {scope} QDoubleSpinBox, {scope} QComboBox {{
            color: {LIGHT_TEXT}; background: {INPUT}; border: 1px solid {ACCENT};
            border-radius: 4px; padding: {padding}px;
            selection-background-color: {FOCUS}; selection-color: {TEXT};
        }}
        {scope} QLineEdit:hover, {scope} QDoubleSpinBox:hover, {scope} QComboBox:hover {{
            border: 1px solid {HOVER};
        }}
        {scope} QLineEdit:focus, {scope} QDoubleSpinBox:focus, {scope} QComboBox:focus {{
            border: 1px solid {FOCUS};
        }}
        {scope} QAbstractItemView {{ background: {INPUT}; color: {LIGHT_TEXT};
            selection-background-color: {FOCUS}; selection-color: {TEXT}; }}
        {scope} QPushButton {{ color: {LIGHT_TEXT}; background: {BUTTON};
            border: 1px solid {ACCENT}; border-radius: 5px; padding: 5px 8px; }}
        {scope} QPushButton[operationRole="primary"] {{ background: {INPUT};
            border: 1px solid {FOCUS}; font-weight: 600; }}
        {scope} QPushButton:hover {{ background: {HOVER}; }}
        {scope} QPushButton:focus, {scope} QPushButton:pressed, {scope} QPushButton:checked {{
            background: {FOCUS}; color: {TEXT}; border-color: {INPUT}; }}
        {scope} QPushButton:disabled, {scope} QLineEdit:disabled,
        {scope} QDoubleSpinBox:disabled, {scope} QComboBox:disabled {{
            background: #78563F; color: #E2D0BD; border-color: #AD805B; }}
    '''


OPERATION_STYLE = f'''
    QDockWidget#operationDialog {{ background: {SECONDARY_ORANGE}; color: {LIGHT_TEXT}; }}
    QDockWidget#operationDialog::title {{ background: {SECONDARY_ORANGE};
        color: {LIGHT_TEXT}; padding: 5px; border-radius: 6px; }}
    QScrollArea#operationScroll, QWidget#operationScrollViewport {{
        background: {SECONDARY_ORANGE}; border: none; }}
    QWidget#operationSurface {{ background: {ORANGE}; border: 1px solid {ACCENT}; border-radius: 8px; }}
''' + _controls('QWidget#operationSurface', 4)

INLINE_STYLE = f'''
    QWidget#constructionDimensions {{ background: {ORANGE}; border: 1px solid {ACCENT}; border-radius: 6px; }}
''' + _controls('QWidget#constructionDimensions', 3)


def operation_screen(panel, island):
    center = island.mapToGlobal(island.rect().center())
    return QGuiApplication.screenAt(center) or panel.window.screen()


def opening_position(anchor, frame_size, available):
    """Qt logical/global coordinates, including the top-level native frame."""
    x = anchor.left()
    y = anchor.top() + anchor.height() + GAP
    if y + frame_size.height() > available.top() + available.height():
        y = anchor.top() - GAP - frame_size.height()
    return QPoint(max(available.left(), min(x, available.right()-frame_size.width()+1)),
                  max(available.top(), min(y, available.bottom()-frame_size.height()+1)))


def fit_operation_size(panel, requested, available, *, opening=False):
    frame = panel.frameGeometry()
    extra = frame.size() - panel.size()
    # Layout growth can scroll inside the space below the current origin;
    # it must not move an independently positioned operation window.
    origin = available.topLeft() if opening else frame.topLeft()
    width = max(1, available.right() - max(origin.x(), available.left()) + 1 - extra.width())
    height = max(1, available.bottom() - max(origin.y(), available.top()) + 1 - extra.height())
    panel.resize(QSize(min(requested.width(), width), min(requested.height(), height)))


def place_operation(panel, island, requested):
    area = operation_screen(panel, island).availableGeometry()
    fit_operation_size(panel, requested, area, opening=True)
    anchor = QRect(island.mapToGlobal(QPoint(0, 0)), island.size())
    panel.move(opening_position(anchor, panel.frameGeometry().size(), area))

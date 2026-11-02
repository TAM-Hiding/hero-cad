"""Small presentation-only decorations for the existing feature browser."""
from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from PySide6.QtWidgets import QApplication, QStyle


def feature_icon(feature, status='valid', palette=None):
    color = None
    if feature.type == 'sketch':
        color = '#E6A04B'
    elif feature.type == 'extrude':
        color = {'join': '#42B8D5', 'cut': '#D95C5C', 'new': '#65B879'}.get(
            feature.parameters.operation)
    elif feature.type == 'chamfer':
        color = '#B59BDE'
    status_color = palette.overrides().get('history.'+status) if palette is not None else None
    return _color_icon(color, status, status_color)


@lru_cache(maxsize=128)
def _color_icon(color, status='valid', status_color=None):
    if color is None and status == 'valid' and status_color is None:
        return QIcon()  # Keep the theme's existing neutral presentation.
    pixmap = QPixmap(4 if status == 'valid' and status_color is None else 22, 14)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    if color:
        painter.fillRect(0, 0, 4, 14, QColor(color))
    if status != 'valid':
        symbol = (QStyle.SP_MessageBoxWarning if status == 'unresolved'
                  else QStyle.SP_DialogCancelButton)
        painter.setOpacity(1 if status == 'unresolved' else .5)
        painter.drawPixmap(7, 0, QApplication.style().standardIcon(symbol).pixmap(14, 14))
    if status_color:
        painter.setPen(QColor(status_color))
        painter.drawText(7, 0, 15, 14, Qt.AlignCenter, {'valid':'✓', 'unresolved':'!', 'blocked':'×'}[status])
    painter.end()
    icon = QIcon()
    # Keep operation identity intact under the native selection highlight.
    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Active, QIcon.Disabled):
        icon.addPixmap(pixmap, mode)
    return icon


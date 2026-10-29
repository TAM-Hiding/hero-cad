"""Small presentation-only decorations for the existing feature browser."""
from functools import lru_cache

from PySide6.QtGui import QColor, QIcon, QPixmap


def feature_icon(feature):
    color = None
    if feature.type == 'sketch':
        color = '#E6A04B'
    elif feature.type == 'extrude':
        color = {'join': '#42B8D5', 'cut': '#D95C5C', 'new': '#65B879'}.get(
            feature.parameters.operation)
    elif feature.type == 'chamfer':
        color = '#B59BDE'
    return _color_icon(color)


@lru_cache(maxsize=6)
def _color_icon(color):
    if color is None:
        return QIcon()  # Keep the theme's existing neutral presentation.
    pixmap = QPixmap(4, 14)
    pixmap.fill(QColor(color))
    icon = QIcon()
    # Keep operation identity intact under the native selection highlight.
    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Active, QIcon.Disabled):
        icon.addPixmap(pixmap, mode)
    return icon

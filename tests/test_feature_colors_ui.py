from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from hero_cad.ui.feature_icons import feature_icon
from test_history_inspection import joined_transition_chain, convert_to_join
from test_sketch_ui import window


def color(icon, mode=QIcon.Normal):
    return icon.pixmap(22, 14, mode).toImage().pixelColor(2, 7).name()


@pytest.mark.parametrize('kind,operation,expected', [
    ('sketch', None, '#e6a04b'), ('extrude', 'join', '#42b8d5'),
    ('extrude', 'cut', '#d95c5c'), ('extrude', 'new', '#65b879'),
    ('unknown', None, None), ('box', None, None),
    ('extrude', 'intersect', None), ('boolean', 'cut', None),
])
def test_decoration_colors_and_neutral_fallback(qapp, kind, operation, expected):
    icon = feature_icon(SimpleNamespace(type=kind, parameters=SimpleNamespace(operation=operation)))
    if expected is None:
        assert icon.isNull()
    else:
        assert color(icon) == expected
        assert color(icon, QIcon.Selected) == expected


def test_browser_colors_survive_selection_edits_and_failed_dependencies(qtbot):
    w = window(qtbot)
    w.document, box, source, extrusion, attached, cut = joined_transition_chain()
    w.refresh()
    for identifier, expected in ((source, '#e6a04b'), (extrusion, '#65b879'), (cut, '#d95c5c')):
        feature = w.document.feature(identifier)
        item = w.browser_items[(feature.type, identifier)]
        w.browser.setCurrentItem(item)
        assert w.browser_key == (feature.type, identifier)
        assert color(item.icon(0)) == expected
        assert item.foreground(0).style() == Qt.NoBrush
        assert item.background(0).style() == Qt.NoBrush
    assert w.browser_items[('box', box)].parent().text(0) == 'Body 1'
    assert w.browser_items[('sketch', source)].childCount() == 1
    assert w.browser_items[('sketch', source)].text(1) == '●'
    convert_to_join(w.document, box, source, extrusion)
    w.refresh()
    assert w.browser_key == ('extrude', cut)
    assert color(w.browser_items[('extrude', extrusion)].icon(0)) == '#42b8d5'
    for kind, identifier, expected in (('sketch', attached, '#e6a04b'), ('extrude', cut, '#d95c5c')):
        item = w.browser_items[(kind, identifier)]
        assert not w.document.statuses[identifier].valid
        assert ('BLOCKED' if w.document.statuses[identifier].blocked_by else 'UNRESOLVED') in item.text(0)
        assert w.document.statuses[identifier].error in item.toolTip(0)
        assert color(item.icon(0)) == expected


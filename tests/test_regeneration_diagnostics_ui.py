from PySide6.QtCore import Qt
from hero_cad.history_inspection import feature_history_text
from test_sketch_ui import window
from test_regeneration_diagnostics import failing_branches, fail


def test_browser_diagnostics_navigation_and_undo_redo(qtbot):
    w = window(qtbot)
    w.document,box,first,sid,cut,source,circle,body,second = failing_branches()
    w.refresh()
    assert not w.first_failure_action.isEnabled()
    valid_icon = w.browser_items[('chamfer',first)].icon(0).cacheKey()
    # Keep compact browser expansion intact while status changes.
    sketch_item = w.browser_items[('sketch',source)]
    sketch_item.setExpanded(True)
    fail(w.document,box,source,circle)
    w.refresh()
    assert w.browser_items[('sketch',source)].isExpanded()
    failed = w.browser_items[('chamfer',first)]
    blocked = w.browser_items[('extrude',cut)]
    assert 'UNRESOLVED' in failed.text(0) and failed.font(0).bold()
    assert 'BLOCKED' in blocked.text(0) and not blocked.font(0).bold()
    assert failed.icon(0).cacheKey() != valid_icon
    assert 'OCCT' in failed.toolTip(0) and first in blocked.toolTip(0)
    assert 'UNRESOLVED' in w.browser_items[('chamfer',second)].text(0)
    assert 'UNRESOLVED' not in w.browser_items[('extrude',body)].text(0)
    w.browser.setCurrentItem(w.browser_items[('extrude',body)])
    w.property_tabs.parentWidget().hide()
    w.first_failure_action.trigger()
    assert w.browser_key == ('chamfer',first)
    assert w.browser.currentItem() is failed
    assert w.property_tabs.currentWidget() is w.history_inspector
    assert w.property_tabs.parentWidget().isVisible()
    assert w.history_inspector.toPlainText() == feature_history_text(w.document,first)
    assert not w.browser.visualItemRect(failed).isEmpty()
    w.browser.setCurrentItem(blocked)
    assert 'Blocked by: #2' in w.history_inspector.toPlainText()
    w.undo();w.undo()
    assert not w.first_failure_action.isEnabled()
    assert 'BLOCKED' not in w.browser_items[('extrude',cut)].text(0)
    assert 'Status: Valid' in w.history_inspector.toPlainText()
    w.redo();w.redo()
    assert w.first_failure_action.isEnabled()
    assert 'BLOCKED' in w.browser_items[('extrude',cut)].text(0)

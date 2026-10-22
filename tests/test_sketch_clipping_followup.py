"""Empty-plane clipping after extrusion, including tool/first-click transitions."""
import pytest
from PySide6.QtCore import Qt
from star_cad.sketch import Circle
from test_sketch_ui import window, pixel, hover


def setup_empty(qtbot, plane):
    w = window(qtbot)
    sid = w.document.add_sketch('XY')
    circle = Circle(0, 0, .02)
    w.document.add_entity(sid, circle)
    w.document.add_extrusion(sid, circle.id, distance=.01)
    w.refresh(fit=True)
    old = w.viewport.renderer.GetActiveCamera().GetClippingRange()
    empty = w.document.add_sketch(plane)
    w.refresh()
    w.viewport.sketch.enter(empty)
    return w, empty, old


def depth(v, world):
    v.renderer.SetWorldPoint(*world, 1)
    v.renderer.WorldToDisplay()
    return v.renderer.GetDisplayPoint()[2]


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
@pytest.mark.parametrize('grid', [True, False])
def test_empty_sketch_plane_visible_before_and_after_first_click(qtbot, plane, grid):
    w, sid, old_clip = setup_empty(qtbot, plane)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    camera = v.renderer.GetActiveCamera()
    # The previous tiny-part far plane cannot reach the new eye's 10 mm plane.
    assert old_clip[1] < 1 and camera.GetDistance() >= 10
    assert 0 < depth(v, frame.origin) < 1
    w.grid_action.setChecked(grid)
    w.tool_choice.setCurrentText('Line')
    qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    assert 0 < depth(v, frame.origin) < 1
    assert not v.actor.GetVisibility() and not v.edge_actor.GetVisibility()
    hover(v, pixel(v, frame.to_world((1, 1))))
    assert 0 < depth(v, frame.to_world((1, 1))) < 1
    assert v.sketch.preview_actor.GetVisibility()
    assert not w.document.feature(sid).parameters.entities
    qtbot.keyClick(v, Qt.Key_Escape)
    assert 0 < depth(v, frame.origin) < 1


def test_render_repairs_stale_clipping_without_changing_view(qtbot):
    w, sid, _ = setup_empty(qtbot, 'XY')
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    camera.Azimuth(35)
    camera.Elevation(17)
    camera.OrthogonalizeViewUp()
    focus, up, direction, scale = camera.GetFocalPoint(), camera.GetViewUp(), camera.GetDirectionOfProjection(), camera.GetParallelScale()
    camera.SetClippingRange(.01, .02)
    assert depth(v, (0, 0, 0)) > 1
    v.GetRenderWindow().Render()
    assert 0 < depth(v, (0, 0, 0)) < 1
    assert camera.GetFocalPoint() == focus
    assert camera.GetViewUp() == up
    assert camera.GetDirectionOfProjection() == pytest.approx(direction)
    assert camera.GetParallelScale() == scale


def test_empty_grid_and_created_curve_remain_visible_render(qtbot):
    import numpy as np
    from test_sketch_visibility import capture, cyan
    w, sid, _ = setup_empty(qtbot, 'XY')
    v = w.viewport
    w.axes_action.setChecked(False)
    shown = capture(v)
    w.grid_action.setChecked(False)
    hidden = capture(v)
    assert np.count_nonzero(np.max(abs(shown-hidden), axis=2) > 3) > 100
    w.grid_action.setChecked(True)
    w.tool_choice.setCurrentText('Circle')
    frame = w.document.feature(sid).parameters.frame
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((1, 0))))
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((1, 0))))
    w.tool_choice.setCurrentText('Select')
    v.sketch.select_entity(None)
    assert np.count_nonzero(cyan(capture(v))) > 40

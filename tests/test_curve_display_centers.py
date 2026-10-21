from math import hypot
from dataclasses import replace
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from star_cad.sketch import Circle, Line, Slot
from star_cad.document import Document
from star_cad.ui.curve_display import MAX_SEGMENTS, PIXEL_ERROR, display_points, segment_count
from star_cad.ui.snapping import center_targets, snap_point
from test_sketch_ui import window, enter, pixel, hover


@pytest.mark.parametrize('ppm', [1, 1000, 10000, 100000])
@pytest.mark.parametrize('entity', [Circle(0, 0, .02), Slot(0, 0, .02, .08, 31)])
def test_tiny_curves_projected_deviation(ppm, entity):
    count = segment_count(entity, ppm)
    points = display_points(entity, count)
    assert points[0] == points[-1]
    if isinstance(entity, Circle):
        segments = list(zip(points, points[1:]))
        centers = [(entity.x, entity.y)]*len(segments)
    else:
        # First/last and middle bridge are analytic straight sides. Inspect arcs.
        half = count//2
        right = points[1:half+2]
        left = points[half+2:]
        segments = list(zip(right, right[1:]))+list(zip(left, left[1:]))
        centers = [entity.second_center]*(len(right)-1)+[(entity.x, entity.y)]*(len(left)-1)
    for (a, b), center in zip(segments, centers):
        midpoint = tuple((a[i]+b[i])/2 for i in range(2))
        deviation = (entity.radius-hypot(midpoint[0]-center[0], midpoint[1]-center[1]))*ppm
        assert -1e-8 <= deviation <= PIXEL_ERROR+1e-8
    assert count <= MAX_SEGMENTS


def test_tessellation_is_bounded_and_straight_entities_are_unchanged():
    circle = Circle(0, 0, .02)
    assert segment_count(circle, 100000) > segment_count(circle, 1000)
    assert segment_count(Circle(0, 0, 100000), 1e12) == MAX_SEGMENTS
    line = Line(1, 2, 3, 4)
    assert display_points(line, segment_count(line, 1000)) == line.points


def test_exact_center_targets_and_priority_without_grid():
    circle = Circle(1.123456789123, 2.987654321987, .02)
    slot = Slot(-3.123456789123, 9.987654321987, .02, 7.123456789123, 37.123456789123)
    targets = tuple(center_targets((Line(0, 0, 1, 1), circle, slot)))
    assert targets == ((circle.x, circle.y), (slot.x, slot.y), slot.second_center)
    for point in targets:
        result = snap_point(point, point, lambda p:p, 1, grid=False, origin=False, centers=targets)
        assert result.target == 'CENTER' and result.point == point
    # Grid lies exactly at cursor, but an entity center within tolerance wins.
    result = snap_point((1, 3), (1, 3), lambda p:p, 1, origin=False, centers=((circle.x, circle.y),))
    assert result.target == 'CENTER' and result.point == (circle.x, circle.y)
    assert snap_point((0, 0), (0, 0), lambda p:p, 1, centers=((.1, .1),)).target == 'ORIGIN'
    result = snap_point((1, 3), (1, 3), lambda p:p, 1, origin=False, centers=())
    assert result.target == 'GRID'
    assert snap_point((20, 20), (20, 20), lambda p:p, 1, grid=False, origin=False, centers=targets).target == 'FREE'


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_adaptive_mesh_reuse_precision_and_picking(qtbot, tmp_path, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v, sketch = w.viewport, w.viewport.sketch
    circle = Circle(12.123456789123, -9.987654321987, .02)
    slot = Slot(12.18, -9.98, .02, .08, 31)
    w.document.add_entity(identifier, circle)
    w.document.add_entity(identifier, slot)
    w.refresh()
    frame = w.document.feature(identifier).parameters.frame
    camera = v.renderer.GetActiveCamera()
    center = frame.to_world((circle.x, circle.y))
    direction = camera.GetDirectionOfProjection()
    camera.SetFocalPoint(*center)
    camera.SetPosition(*(center[i]-direction[i]*100 for i in range(3)))
    camera.SetParallelScale(.1)
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    coarse = sketch.mapper.GetInput().GetNumberOfPoints()
    camera.SetParallelScale(.01)
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    mesh = sketch.mapper.GetInput()
    assert mesh.GetNumberOfPoints() > coarse
    assert mesh.GetCell(0).GetNumberOfPoints() > 32
    mtime = mesh.GetMTime()
    camera.Azimuth(17)
    camera.Elevation(8)
    camera.SetFocalPoint(*(p+.0001 for p in camera.GetFocalPoint()))
    camera.SetPosition(*(p+.0001 for p in camera.GetPosition()))
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    assert sketch.mapper.GetInput().GetMTime() == mtime
    sketch.select_entity(circle.id)
    assert sketch.highlight_mapper.GetInput().GetCell(0).GetNumberOfPoints() == mesh.GetCell(0).GetNumberOfPoints()
    # Picking uses the same finer display data, including points between former facets.
    import math
    point = (circle.x+.02*math.cos(.17), circle.y+.02*math.sin(.17))
    p = pixel(v, frame.to_world(point))
    width, height = v.GetRenderWindow().GetSize()
    sketch.pick(p.x()*width/v.width(), height-1-p.y()*height/v.height())
    assert sketch.entity_id == circle.id
    points_before_resize = sketch.mapper.GetInput().GetNumberOfPoints()
    v.GetRenderWindow().SetSize(width*2, height*2)
    sketch.prepare_display()
    assert sketch.mapper.GetInput().GetNumberOfPoints() > points_before_resize
    v.GetRenderWindow().SetSize(width, height)
    sketch.prepare_display()
    assert sketch.mapper.GetInput().GetNumberOfPoints() == points_before_resize
    path = tmp_path/'same-precision.starcad'
    before = w.document.features
    w.document.save(path)
    assert Document.load(path).features == before
    assert w.document.features == before
    assert not w.document.dirty


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
@pytest.mark.parametrize('zoom', [20, 40])
def test_center_snapping_mouse_coordinates_and_independence(qtbot, plane, zoom):
    w = window(qtbot)
    identifier = enter(w, plane)
    v, sketch = w.viewport, w.viewport.sketch
    circle = Circle(12.123456789123, -9.987654321987, .02)
    slot = Slot(18.123456789123, 5.987654321987, .02, 7.123456789123, 37.123456789123)
    w.document.add_entity(identifier, circle)
    w.document.add_entity(identifier, slot)
    w.refresh()
    frame = w.document.feature(identifier).parameters.frame
    v.renderer.GetActiveCamera().SetParallelScale(zoom)
    v.clamp_zoom()
    w.grid_action.setChecked(False)
    w.snap_grid_action.setChecked(False)
    w.snap_origin_action.setChecked(False)
    w.tool_choice.setCurrentText('Line')
    targets = ((circle.x, circle.y), (slot.x, slot.y), slot.second_center)
    for target in targets:
        hover(v, pixel(v, frame.to_world(target))+QPoint(3, 0))
        assert sketch.snap_result.target == 'CENTER'
        assert sketch.snap_result.point == target
        assert 'SNAP: CENTER' in w.statusBar().currentMessage()
        assert sketch.snap_actor.GetProperty().GetColor() == pytest.approx((.35, .65, 1))
    hover(v, pixel(v, frame.to_world(targets[0]))+QPoint(12, 0))
    assert sketch.snap_result.target == 'FREE'
    for target in targets[:2]:
        qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v, frame.to_world(target))+QPoint(3, 0))
    line = w.document.feature(identifier).parameters.entities[-1]
    assert line.points == targets[:2]
    QApplication.processEvents()
    w.snap_center_action.setChecked(False)
    hover(v, pixel(v, frame.to_world(targets[0])))
    assert sketch.snap_result.target == 'FREE'
    w.snap_center_action.setChecked(True)
    # Edited centers must be picked up from current parameters, not a stale mesh.
    edited = replace(circle, x=30.123456789123)
    w.document.update_entity(identifier, edited)
    w.refresh()
    hover(v, pixel(v, frame.to_world((edited.x, edited.y))))
    assert sketch.snap_result.point == (edited.x, edited.y) and sketch.snap_result.target == 'CENTER'
    w.undo_action.trigger()
    hover(v, pixel(v, frame.to_world(targets[0])))
    assert sketch.snap_result.point == targets[0] and sketch.snap_result.target == 'CENTER'


def test_curved_preview_adapts_on_zoom_and_shift_stays_latched(qtbot):
    w = window(qtbot)
    identifier = enter(w)
    v, sketch = w.viewport, w.viewport.sketch
    frame = w.document.feature(identifier).parameters.frame
    w.snap_grid_action.setChecked(False)
    w.tool_choice.setCurrentText('Circle')
    start = pixel(v, frame.to_world((0, 0)))
    qtbot.mousePress(v, Qt.LeftButton, Qt.ShiftModifier, pos=start)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((3, 0))))
    assert sketch.controller.tool.stage == 'center'
    hover(v, pixel(v, frame.to_world((8, 8))))
    before = sketch.preview_mapper.GetInput().GetNumberOfPoints()
    camera = v.renderer.GetActiveCamera()
    camera.SetParallelScale(camera.GetParallelScale()/8)
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    assert sketch.preview_mapper.GetInput().GetNumberOfPoints() > before
    assert sketch.controller.tool.stage == 'center'
    qtbot.keyClick(v, Qt.Key_Escape)
    assert not sketch.preview_actor.GetVisibility()


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_tiny_circle_render_smooth_between_old_facets(qtbot, plane):
    from math import pi, cos, sin
    from test_sketch_visibility import capture, cyan
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    circle = Circle(12.123, -9.987, .02)
    w.document.add_entity(identifier, circle)
    w.refresh()
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)
    frame = w.document.feature(identifier).parameters.frame
    camera = v.renderer.GetActiveCamera()
    center = frame.to_world((circle.x, circle.y))
    camera.SetFocalPoint(*center)
    camera.SetPosition(*(center[i]+frame.normal[i]*10 for i in range(3)))
    camera.SetViewUp(*frame.v)
    camera.SetParallelScale(.025)
    v.clamp_zoom()
    image = capture(v)
    assert v.sketch.mapper.GetInput().GetCell(0).GetNumberOfPoints() >= 65
    # The legacy 16-sided circle missed these exact analytic arc locations
    # by several pixels at this magnification.
    for i in range(16):
        angle = (i+.5)*2*pi/16
        p = (circle.x+.02*cos(angle), circle.y+.02*sin(angle))
        v.renderer.SetWorldPoint(*frame.to_world(p), 1)
        v.renderer.WorldToDisplay()
        x, y, z = v.renderer.GetDisplayPoint()
        x, y = round(x), round(y)
        assert 2 <= x < image.shape[1]-2 and 2 <= y < image.shape[0]-2
        assert 0 < z < 1
        assert cyan(image[y-2:y+3, x-2:x+3]).any(), (plane, i)


def test_center_indicator_render(qtbot):
    import numpy as np
    from test_sketch_visibility import capture
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    circle = Circle(10, 8, 2)
    w.document.add_entity(identifier, circle)
    w.refresh()
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)
    w.snap_grid_action.setChecked(False)
    w.tool_choice.setCurrentText('Line')
    frame = w.document.feature(identifier).parameters.frame
    hover(v, pixel(v, frame.to_world((10, 8)))+QPoint(2, 0))
    assert v.sketch.snap_result.target == 'CENTER'
    image = capture(v)
    blue = (image[..., 2] > 200) & (image[..., 2]-image[..., 1] > 50) & (image[..., 0] < 150)
    assert np.count_nonzero(blue) > 10

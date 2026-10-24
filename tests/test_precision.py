from math import isclose
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from hero_cad.document import Document
from hero_cad.sketch import Circle, Slot, PlaneFrame
from hero_cad.ui.snapping import snap_point
from test_sketch_ui import window, enter, pixel, click, hover


def depths(v):
    mesh = v.sketch.mapper.GetInput()
    result = []
    for i in range(mesh.GetNumberOfPoints()):
        v.renderer.SetWorldPoint(*mesh.GetPoint(i), 1)
        v.renderer.WorldToDisplay()
        result.append(v.renderer.GetDisplayPoint())
    return result


def test_reproduce_near_plane_failure_and_preserve_projection(qtbot):
    w = window(qtbot)
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    old_position, old_focal = camera.GetPosition(), camera.GetFocalPoint()
    identifier = enter(w)
    w.document.add_entity(identifier, Circle(0, 0, 150))
    w.document.add_entity(identifier, Slot(-30, 0, 10, 60, 20))
    w.refresh()
    w.finish_sketch_action.trigger()
    # Isolate clipping from occlusion and guides, then recreate the legacy
    # restored-camera state with its former ResetCameraClippingRange call.
    v.actor.VisibilityOff()
    v.edge_actor.VisibilityOff()
    w.axes_action.setChecked(False)
    camera.SetFocalPoint(*old_focal)
    camera.SetPosition(*old_position)
    camera.SetParallelScale(210)
    v.renderer.ResetCameraClippingRange()
    before = depths(v)
    assert any(p[2] < 0 for p in before)
    v.clamp_zoom()
    after = depths(v)
    assert all(0 < p[2] < 1 for p in after)
    for a, b in zip(before, after):
        assert a[:2] == pytest.approx(b[:2], abs=1e-8)
    assert camera.GetFocalPoint() == old_focal
    assert camera.GetParallelScale() == 210


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_large_curves_stay_in_depth_range_after_navigation(qtbot, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    w.document.add_entity(identifier, Circle(0, 0, 150))
    w.document.add_entity(identifier, Slot(-30, 0, 10, 60, 37))
    w.refresh()
    w.finish_sketch_action.trigger()
    camera = v.renderer.GetActiveCamera()
    for _ in range(4):
        camera.Azimuth(47)
        camera.Elevation(13)
        camera.OrthogonalizeViewUp()
        camera.SetParallelScale(camera.GetParallelScale()*2)
        v.clamp_zoom()
        assert all(0 < p[2] < 1 for p in depths(v))
    start = QPoint(v.width()//2, v.height()//2)
    qtbot.mousePress(v, Qt.MiddleButton, pos=start)
    qtbot.mouseMove(v, start+QPoint(40, 25))
    qtbot.mouseRelease(v, Qt.MiddleButton, pos=start+QPoint(40, 25))
    assert all(0 < p[2] < 1 for p in depths(v))
    v.fit()
    assert all(0 < p[2] < 1 for p in depths(v))


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_major_minor_grid_exact_intervals_and_density(qtbot, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v, guides = w.viewport, w.viewport.sketch.guides
    frame = w.document.feature(identifier).parameters.frame
    features = w.document.features
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(1)
    assert guides.spacing == 1 and guides.major_spacing == 10
    for mapper, major in ((guides.grid_mapper, True), (guides.minor_mapper, False)):
        mesh = mapper.GetInput()
        assert mesh.GetNumberOfCells() > 0
        for i in range(mesh.GetNumberOfCells()):
            cell = mesh.GetCell(i)
            a, b = (frame.to_local(mesh.GetPoint(cell.GetPointId(j))) for j in (0, 1))
            constant = a[0] if isclose(a[0], b[0]) else a[1]
            index = round(constant/guides.spacing)
            assert constant == pytest.approx(index*guides.spacing)
            assert (index % 10 == 0) == major
    w.grid_action.setChecked(False)
    assert not guides.grid_actor.GetVisibility() and not guides.minor_actor.GetVisibility()
    w.auto_grid_action.setChecked(True)
    v.renderer.GetActiveCamera().SetParallelScale(1)
    fine = guides.spacing
    v.renderer.GetActiveCamera().SetParallelScale(1000)
    assert guides.spacing > fine and guides.major_spacing == pytest.approx(10*guides.spacing)
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(.000001)
    w.grid_action.setChecked(True)
    assert sum(m.GetInput().GetNumberOfCells() for m in (guides.grid_mapper, guides.minor_mapper)) <= 404
    assert w.document.features == features


@pytest.mark.parametrize('scale', [.5, 1, 2])
@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_screen_tolerance_and_origin_priority(qtbot, scale, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(5)
    v.renderer.GetActiveCamera().SetParallelScale(30*scale)
    v.clamp_zoom()
    w.tool_choice.setCurrentText('Line')
    target = pixel(v, frame.to_world((5, 5)))
    hover(v, target+QPoint(4, 0))
    assert v.sketch.snap_result.target == 'GRID'
    assert v.sketch.snap_result.point == (5, 5)
    assert v.sketch.snap_actor.GetVisibility() and 'SNAP: GRID' in w.statusBar().currentMessage()
    hover(v, target+QPoint(12, 0))
    assert v.sketch.snap_result.target == 'FREE'
    assert not v.sketch.snap_actor.GetVisibility()
    w.grid_action.setChecked(False)
    hover(v, target+QPoint(4, 0))
    assert v.sketch.snap_result.target == 'GRID'
    w.snap_grid_action.setChecked(False)
    hover(v, target)
    assert v.sketch.snap_result.target == 'FREE'
    origin = pixel(v, frame.to_world((0, 0)))
    hover(v, origin+QPoint(4, 0))
    assert v.sketch.snap_result.target == 'ORIGIN' and v.sketch.snap_result.point == (0, 0)
    assert v.sketch.snap_actor.GetProperty().GetPointSize() == 9
    w.snap_origin_action.setChecked(False)
    hover(v, origin)
    assert v.sketch.snap_result.target == 'FREE'


def test_origin_is_local_to_supplied_frame():
    frame = PlaneFrame('future-offset', (30, -40, 50), (0, 1, 0), (0, 0, 1))
    project = lambda uv: frame.to_world(uv)[1:]
    result = snap_point((.1, .1), (-39.9, 50.1), project, 1, grid=False)
    assert result.target == 'ORIGIN'
    assert frame.to_world(result.point) == (30, -40, 50)
    # Origin gets priority even though an ordinary grid intersection is closer.
    result = snap_point((1, 1), (1, 1), lambda p: p, 1, tolerance=8)
    assert result.target == 'ORIGIN'


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_snapped_tools_numeric_edits_and_persistence(qtbot, tmp_path, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(1)
    def near(point):
        return pixel(v, frame.to_world(point))+QPoint(2, 0)
    def press(point, modifier=Qt.NoModifier):
        qtbot.mousePress(v, Qt.LeftButton, modifier, pos=near(point))
    def release(point):
        qtbot.mouseRelease(v, Qt.LeftButton, pos=near(point))
    def tap(point, modifier=Qt.NoModifier):
        qtbot.mouseClick(v, Qt.LeftButton, modifier, pos=near(point))
    def settle():
        QApplication.processEvents()
    w.tool_choice.setCurrentText('Line')
    tap((2, 3)); tap((7, 9)); settle()
    line = w.document.feature(identifier).parameters.entities[-1]
    assert line.points == ((2, 3), (7, 9))
    w.tool_choice.setCurrentText('Rectangle')
    press((-10, -8)); release((-4, -2)); settle()
    rectangle = w.document.feature(identifier).parameters.entities[-1]
    assert (rectangle.x, rectangle.y, rectangle.width, rectangle.height) == (-10, -8, 6, 6)
    tap((10, 2), Qt.ShiftModifier); tap((13, 6)); tap((9, 9)); settle()
    rectangle = w.document.feature(identifier).parameters.entities[-1]
    assert rectangle.width == pytest.approx(5)
    w.tool_choice.setCurrentText('Circle')
    press((0, 0)); release((3, 4)); settle()
    circle = w.document.feature(identifier).parameters.entities[-1]
    assert isinstance(circle, Circle) and (circle.x, circle.y, circle.radius) == (0, 0, 5)
    press((10, 10), Qt.ShiftModifier); release((13, 14)); tap((16, 18)); settle()
    slot = w.document.feature(identifier).parameters.entities[-1]
    assert isinstance(slot, Slot) and slot.radius == 5 and slot.distance == 10
    assert slot.second_center == pytest.approx((16, 18))
    before = w.document.features
    w.grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(2.5)
    assert w.document.features == before
    w.entity_fields['radius'].setValue(2.123456789)
    w.entity_apply.click()
    edited = w.document.feature(identifier).parameters.entities[-1]
    assert edited.radius == 2.123456789
    w.undo_action.trigger()
    assert w.document.features == before
    w.redo_action.trigger()
    path = tmp_path/'snapped.starcad'
    w.document.save(path)
    assert Document.load(path).features == w.document.features
    assert not w.document.dirty

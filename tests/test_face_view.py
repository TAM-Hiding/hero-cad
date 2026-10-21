from math import radians, sqrt, tan
import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from PySide6.QtCore import QPoint, Qt
from star_cad.ui.camera_alignment import deterministic_up, planar_view_target
from test_sketch_ui import window, pixel


def transformed_box():
    x, y = gp_Trsf(), gp_Trsf()
    x.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(1,0,0)), radians(31))
    y.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(0,1,0)), radians(-23))
    transform = y.Multiplied(x)
    transform.SetTranslationPart(gp_Vec(7, -11, 13))
    shape = BRepPrimAPI_MakeBox(40,30,20).Shape().Moved(TopLoc_Location(transform))
    def world(point):
        p = gp_Pnt(*point).Transformed(transform)
        return (p.X(), p.Y(), p.Z())
    d = gp_Dir(0,0,1).Transformed(transform)
    return shape, world, (d.X(), d.Y(), d.Z())


def camera_state(camera):
    return (camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp(),
            camera.GetParallelScale(), camera.GetParallelProjection(), camera.GetViewAngle(),
            camera.GetClippingRange(), camera.GetUseHorizontalViewAngle())


def project(v, point):
    v.renderer.SetWorldPoint(*point, 1)
    v.renderer.WorldToDisplay()
    return v.renderer.GetDisplayPoint()[:2]


def double_click(qtbot, v, point, modifier=Qt.ShiftModifier):
    # Native sequence: press, release, double-click (second press), release.
    qtbot.mouseClick(v, Qt.RightButton, modifier, pos=point)
    qtbot.mouseDClick(v, Qt.RightButton, modifier, pos=point)
    qtbot.mouseRelease(v, Qt.RightButton, modifier, pos=point)


def angled_window(qtbot):
    w = window(qtbot)
    v = w.viewport
    shape, world, normal = transformed_box()
    v.set_shape(shape)
    camera = v.renderer.GetActiveCamera()
    camera.SetFocalPoint(*world((20,15,10)))
    camera.SetPosition(*world((100,-100,150)))
    camera.SetViewUp(0,0,1)
    camera.SetParallelScale(38)
    v.clamp_zoom()
    v.GetRenderWindow().Render()
    return w, shape, world, normal


def test_exact_planar_target_location_orientation_and_projection():
    shape, world, expected_normal = transformed_box()
    from star_cad.ui.display_geometry import subshapes
    from OCP.TopAbs import TopAbs_FACE
    faces = subshapes(shape, TopAbs_FACE)
    # Locate the transformed top plane by its known geometric point/normal.
    target = next(planar_view_target(f, world((23,12,20))) for f in faces
                  if planar_view_target(f, world((23,12,20))).normal == pytest.approx(expected_normal))
    assert target.point == pytest.approx(world((23,12,20)), abs=1e-10)
    top = next(f for f in faces if planar_view_target(f, world((23,12,20))).normal == pytest.approx(expected_normal))
    offset = tuple(target.point[i]+.1*expected_normal[i] for i in range(3))
    assert planar_view_target(top, offset).point == pytest.approx(target.point, abs=1e-10)
    reversed_target = planar_view_target(TopoDS.Face_s(top.Reversed()), offset)
    assert reversed_target.normal == pytest.approx(tuple(-n for n in expected_normal))
    assert reversed_target.up == pytest.approx(target.up)


@pytest.mark.parametrize('normal', [(0,0,1),(0,0,-1),(0,1,0),(1,0,0),(.3,.4,sqrt(.75))])
def test_up_is_deterministic_unit_and_perpendicular(normal):
    up = deterministic_up(normal)
    assert sum(up[i]*normal[i] for i in range(3)) == pytest.approx(0, abs=1e-12)
    assert sum(v*v for v in up) == pytest.approx(1)
    assert up == deterministic_up(normal)
    if abs(normal[2]) == 1:
        assert up == (0,1,0)


def test_double_click_uses_face_filter_independent_preserves_selection_and_view(qtbot):
    w, shape, world, normal = angled_window(qtbot)
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    v.pick_at(*project(v, world((25,12,20))))
    w.selection_choice.setCurrentIndex(1)
    v.pick_at(*project(v, world((20,0,20))), additive=True)
    assert {s.kind for s in v.selections} == {'face', 'edge'}
    selected, selection = tuple(v.selections), v.selection
    highlights = v.highlight_mapper.GetInput()
    parameters, doc_shape = w.document.features, w.document.shape
    old_state = camera_state(camera)
    point = pixel(v, world((25,12,20)))
    width, height = v.GetRenderWindow().GetSize()
    hit = v.face_pick_at(point.x()*width/v.width(), height-1-point.y()*height/v.height())
    expected = planar_view_target(*hit)
    assert not w.previous_view_action.isEnabled()
    double_click(qtbot, v, point)
    assert camera.GetParallelProjection()
    assert camera.GetDirectionOfProjection() == pytest.approx(tuple(-n for n in normal), abs=1e-10)
    assert camera.GetFocalPoint() == pytest.approx(expected.point, abs=1e-10)
    assert camera.GetViewUp() == pytest.approx(expected.up, abs=1e-10)
    assert camera.GetParallelScale() == old_state[3]
    assert tuple(v.selections) == selected and v.selection is selection
    assert v.highlight_mapper.GetInput() is highlights
    assert w.document.features == parameters and w.document.shape is doc_shape
    assert not w.document.dirty
    assert w.previous_view_action.isEnabled()
    assert 'perpendicular' in w.statusBar().currentMessage()
    # Follow-up pan is not stuck in a consumed double-click or VTK button state.
    aligned_focal = camera.GetFocalPoint()
    start = QPoint(v.width()//2, v.height()//2)
    qtbot.mousePress(v, Qt.RightButton, Qt.ShiftModifier, pos=start)
    qtbot.mouseMove(v, start+QPoint(40,20))
    qtbot.mouseRelease(v, Qt.RightButton, Qt.ShiftModifier, pos=start+QPoint(40,20))
    assert camera.GetFocalPoint() != aligned_focal
    assert camera.GetDirectionOfProjection() == pytest.approx(tuple(-n for n in normal))
    assert camera.GetParallelScale() == old_state[3]
    w.previous_view_action.trigger()
    assert camera_state(camera) == old_state
    assert not w.previous_view_action.isEnabled()
    assert not v.previous_view()


@pytest.mark.parametrize('horizontal', [False, True])
def test_perspective_scale_conversion_and_full_restore(qtbot, horizontal):
    w, _, world, normal = angled_window(qtbot)
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    camera.ParallelProjectionOff()
    camera.SetViewAngle(37)
    camera.SetUseHorizontalViewAngle(horizontal)
    v.renderer.ResetCameraClippingRange()
    point = pixel(v, world((25,12,20)))
    width, height = v.GetRenderWindow().GetSize()
    face, picked = v.face_pick_at(point.x()*width/v.width(), height-1-point.y()*height/v.height())
    target = planar_view_target(face, picked)
    direction, position = camera.GetDirectionOfProjection(), camera.GetPosition()
    depth = sum((target.point[i]-position[i])*direction[i] for i in range(3))
    expected_scale = depth*tan(radians(37)/2)*(height/width if horizontal else 1)
    previous = camera_state(camera)
    double_click(qtbot, v, point)
    assert camera.GetParallelProjection()
    assert camera.GetParallelScale() == pytest.approx(expected_scale)
    assert camera.GetDirectionOfProjection() == pytest.approx(tuple(-n for n in normal))
    assert v.previous_view()
    assert camera_state(camera) == previous


def test_nonplanar_miss_and_hidden_solid_rejected_without_changing_view(qtbot):
    w = window(qtbot)
    v = w.viewport
    v.orient('Top')
    assert v.align_face_at(*project(v, (20,15,20)))
    prior_slot = v._previous_view
    v.set_shape(BRepPrimAPI_MakeCylinder(10,20).Shape())
    camera = v.renderer.GetActiveCamera()
    camera.SetFocalPoint(0,0,10)
    camera.SetPosition(100,0,10)
    camera.SetViewUp(0,0,1)
    camera.SetParallelScale(25)
    v.clamp_zoom()
    previous = camera_state(camera)
    point = pixel(v, (10,0,10))
    double_click(qtbot, v, point)
    assert 'planar face' in w.statusBar().currentMessage()
    assert camera_state(camera) == previous and v._previous_view is prior_slot
    double_click(qtbot, v, QPoint(1,1))
    assert 'No visible face' in w.statusBar().currentMessage()
    assert camera_state(camera) == previous
    v.actor.VisibilityOff()
    double_click(qtbot, v, point)
    assert 'No visible face' in w.statusBar().currentMessage()
    assert camera_state(camera) == previous and v._previous_view is prior_slot


def test_shift_right_drag_and_micro_motion_do_not_align(qtbot):
    w, _, world, _ = angled_window(qtbot)
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    point = pixel(v, world((25,12,20)))
    focal, direction, scale = camera.GetFocalPoint(), camera.GetDirectionOfProjection(), camera.GetParallelScale()
    qtbot.mousePress(v, Qt.RightButton, Qt.ShiftModifier, pos=point)
    qtbot.mouseMove(v, point+QPoint(1,1))
    assert camera.GetFocalPoint() == focal
    qtbot.mouseMove(v, point+QPoint(45,25))
    qtbot.mouseRelease(v, Qt.RightButton, Qt.ShiftModifier, pos=point+QPoint(45,25))
    assert camera.GetFocalPoint() != focal
    assert camera.GetDirectionOfProjection() == pytest.approx(direction)
    assert camera.GetParallelScale() == scale
    assert v._previous_view is None
    # A drag must not qualify as the first click in a synthetic double-click.
    qtbot.mouseDClick(v, Qt.RightButton, Qt.ShiftModifier, pos=point)
    qtbot.mouseRelease(v, Qt.RightButton, Qt.ShiftModifier, pos=point)
    assert v._previous_view is None
    # A genuine subsequent click/double-click still works after panning.
    point = pixel(v, world((25,12,20)))
    before = camera_state(camera)
    double_click(qtbot, v, point)
    assert v._previous_view is not None
    assert v.previous_view() and camera_state(camera) == before


def test_plain_right_double_click_does_not_align(qtbot):
    w, _, world, _ = angled_window(qtbot)
    v = w.viewport
    point = pixel(v, world((25,12,20)))
    double_click(qtbot, v, point, Qt.NoModifier)
    assert v._previous_view is None and not w.previous_view_action.isEnabled()


def test_gesture_rejection_preserves_active_shift_slot(qtbot):
    from test_sketch_ui import enter
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    w.tool_choice.setCurrentText('Circle')
    frame = w.document.feature(identifier).parameters.frame
    qtbot.mousePress(v, Qt.LeftButton, Qt.ShiftModifier, pos=pixel(v, frame.to_world((0,0))))
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((3,0))))
    assert v.sketch.controller.tool.stage == 'center'
    previous = w.document.features
    double_click(qtbot, v, pixel(v, frame.to_world((0,0))))
    assert 'No visible face' in w.statusBar().currentMessage()
    assert v.sketch.controller.tool.stage == 'center'
    assert w.document.features == previous and v._previous_view is None


def test_angled_face_alignment_and_previous_view_render(qtbot):
    import numpy as np
    from test_sketch_visibility import capture
    w, _, world, normal = angled_window(qtbot)
    v = w.viewport
    w.axes_action.setChecked(False)
    before = capture(v)
    point = pixel(v, world((25,12,20)))
    double_click(qtbot, v, point)
    assert v.renderer.GetActiveCamera().GetDirectionOfProjection() == pytest.approx(tuple(-n for n in normal))
    after = capture(v)
    surface = (after[..., 2] > after[..., 0]+15) & (after[..., 0] > 60)
    assert np.count_nonzero(surface) > 5000
    # Two known tangent directions of the compound-angle face project at 90°.
    p = project(v, world((25,12,20)))
    a, b = project(v, world((26,12,20))), project(v, world((25,13,20)))
    u, d = (a[0]-p[0], a[1]-p[1]), (b[0]-p[0], b[1]-p[1])
    assert u[0]*d[0]+u[1]*d[1] == pytest.approx(0, abs=1e-8)
    assert sum(x*x for x in u) == pytest.approx(sum(x*x for x in d), abs=1e-8)
    w.previous_view_action.trigger()
    restored = capture(v)
    assert np.max(abs(restored-before)) <= 3

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from hero_cad.sketch import Circle, Slot
from test_sketch_ui import window, enter, pixel, click, hover


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_circle_slot_gestures_and_numeric_edit(qtbot, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.tool_choice.setCurrentText('Circle')
    start, end = pixel(v, frame.to_world((0, 0))), pixel(v, frame.to_world((4, 0)))
    qtbot.mousePress(v, Qt.LeftButton, pos=start)
    qtbot.mouseMove(v, end)
    assert v.sketch.preview_actor.GetVisibility()
    qtbot.mouseRelease(v, Qt.LeftButton, pos=end)
    circle = w.document.feature(identifier).parameters.entities[0]
    assert isinstance(circle, Circle) and circle.radius == pytest.approx(4, abs=.15)
    QApplication.processEvents()  # New property fields may resize the viewport.
    start, end = pixel(v, frame.to_world((0, 0))), pixel(v, frame.to_world((4, 0)))
    qtbot.mousePress(v, Qt.LeftButton, Qt.ShiftModifier, pos=start)
    qtbot.mouseMove(v, end)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=end)
    assert v.sketch.controller.tool.stage == 'center'
    hover(v, pixel(v, frame.to_world((8, 8))))
    assert v.sketch.preview_actor.GetVisibility()
    click(qtbot, v, frame, (8, 8))
    slot = w.document.feature(identifier).parameters.entities[-1]
    assert isinstance(slot, Slot) and slot.angle == pytest.approx(45, abs=1)
    w.entity_fields['radius'].setValue(2.5)
    w.entity_fields['distance'].setValue(15.25)
    w.entity_fields['angle'].setValue(31.5)
    w.entity_apply.click()
    edited = w.document.feature(identifier).parameters.entities[-1]
    assert (edited.radius, edited.distance, edited.angle) == (2.5, 15.25, 31.5)
    assert edited.id == slot.id
    w.undo_action.trigger()
    assert w.document.feature(identifier).parameters.entities[-1] == slot
    w.finish_sketch_action.trigger()
    w.edit_sketch_action.trigger()
    w.tool_choice.setCurrentText('Select')
    click(qtbot, v, frame, slot.points[len(slot.points)//4])
    assert w.entity_context == (identifier, slot.id)


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_view_guides_toggle_plane_and_camera(qtbot, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v, guides = w.viewport, w.viewport.sketch.guides
    features = w.document.features
    assert guides.grid_actor.GetVisibility()
    frame = w.document.feature(identifier).parameters.frame
    mesh = guides.grid_mapper.GetInput()
    assert 5 < mesh.GetNumberOfCells() <= 320
    for i in range(mesh.GetNumberOfPoints()):
        p = mesh.GetPoint(i)
        assert sum(p[j]*frame.normal[j] for j in range(3)) == pytest.approx(0)
    camera = v.renderer.GetActiveCamera()
    camera.SetParallelScale(camera.GetParallelScale()*10)
    assert guides.spacing > 1
    focal, scale = camera.GetFocalPoint(), camera.GetParallelScale()
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)
    assert not guides.grid_actor.GetVisibility()
    assert all(not actor.GetVisibility() for _, actor in guides.axes)
    assert camera.GetFocalPoint() == focal and camera.GetParallelScale() == scale
    assert w.document.features == features
    w.finish_sketch_action.trigger()
    w.edit_sketch_action.trigger()
    assert not guides.grid_actor.GetVisibility()
    assert all(not actor.GetVisibility() for _, actor in guides.axes)
    w.grid_action.setChecked(True)
    w.axes_action.setChecked(True)
    assert guides.grid_actor.GetVisibility()
    for axis, (mapper, actor) in enumerate(guides.axes):
        assert actor.GetVisibility() and not actor.GetUseBounds() and not actor.GetPickable()
        a, b = mapper.GetInput().GetPoint(0), mapper.GetInput().GetPoint(1)
        assert a[axis] < 0 < b[axis]
        assert all(a[i] == b[i] == 0 for i in range(3) if i != axis)
    assert guides.axes[0][1].GetProperty().GetColor()[0] > .9
    assert guides.axes[1][1].GetProperty().GetColor()[1] > .7
    assert guides.axes[2][1].GetProperty().GetColor()[2] == 1
    w.finish_sketch_action.trigger()
    assert not guides.grid_actor.GetVisibility()
    assert all(actor.GetVisibility() for _, actor in guides.axes)


def test_curves_and_grid_render(qtbot):
    import numpy as np
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    frame = w.document.feature(identifier).parameters.frame
    w.document.add_entity(identifier, Circle(-12, -10, 3))
    slot = Slot(-12, 10, 2, 16, 0)
    w.document.add_entity(identifier, slot)
    w.refresh()
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)

    def pixels():
        v.GetRenderWindow().Render()
        capture = vtkWindowToImageFilter()
        capture.SetInput(v.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        return vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars()).astype(int)

    plain = pixels()
    cyan = (plain[:, 2] > 130) & (plain[:, 1]-plain[:, 0] > 40) & (plain[:, 2]-plain[:, 0] > 60)
    assert np.count_nonzero(cyan) > 50
    click(qtbot, v, frame, (-4, 8))  # Straight side of the slot.
    assert w.entity_context == (identifier, slot.id)
    selected = pixels()
    orange = (selected[:, 0] > 150) & (selected[:, 0]-selected[:, 1] > 40) & (selected[:, 1]-selected[:, 2] > 40)
    assert np.count_nonzero(orange) > 50
    w.grid_action.setChecked(True)
    grid = pixels()
    assert np.count_nonzero(np.max(abs(grid-selected), axis=1) > 5) > 100
    w.grid_action.setChecked(False)
    assert np.max(abs(pixels()-selected)) < 3

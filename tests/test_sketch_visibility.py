"""Rendered clipping and real-depth regression checks; requires working OpenGL."""
import numpy as np
import pytest
from math import cos, pi, sin
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from hero_cad.sketch import Circle, Slot
from test_sketch_ui import window, enter


def capture(v):
    v.GetRenderWindow().Render()
    image = vtkWindowToImageFilter()
    image.SetInput(v.GetRenderWindow())
    image.ReadFrontBufferOff()
    image.Update()
    output = image.GetOutput()
    width, height, _ = output.GetDimensions()
    return vtk_to_numpy(output.GetPointData().GetScalars()).reshape(height, width, 3).astype(int)


def cyan(pixels):
    return ((pixels[..., 2] > 130) & (pixels[..., 1]-pixels[..., 0] > 40)
            & (pixels[..., 2]-pixels[..., 0] > 60))


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
def test_large_circle_slots_render_after_finish_orbit_zoom_fit(qtbot, plane):
    w = window(qtbot)
    identifier = enter(w, plane)
    v = w.viewport
    w.document.add_entity(identifier, Circle(0, 0, 150))
    w.document.add_entity(identifier, Slot(-30, 0, 10, 60, 37))
    w.refresh()
    w.finish_sketch_action.trigger()
    w.axes_action.setChecked(False)
    # Isolate unobstructed curves from the box; a separate test checks occlusion.
    v.actor.VisibilityOff()
    v.edge_actor.VisibilityOff()
    camera = v.renderer.GetActiveCamera()
    camera.SetParallelScale(220)
    for _ in range(3):
        camera.Azimuth(31)
        camera.Elevation(7)
        camera.OrthogonalizeViewUp()
        v.clamp_zoom()
        pixels = capture(v)
        frame = w.document.feature(identifier).parameters.frame
        checked = 0
        # Sample exact model positions, independent of display quality bands.
        for index in range(32):
            angle = 2*pi*index/32
            point = frame.to_world((150*cos(angle), 150*sin(angle)))
            v.renderer.SetWorldPoint(*point, 1)
            v.renderer.WorldToDisplay()
            x, y, depth = v.renderer.GetDisplayPoint()
            assert 0 < depth < 1
            x, y = round(x), round(y)
            if 3 <= x < pixels.shape[1]-3 and 3 <= y < pixels.shape[0]-3:
                assert cyan(pixels[y-3:y+4, x-3:x+4]).any(), (plane, index, x, y)
                checked += 1
        assert checked > 20
        assert np.count_nonzero(cyan(pixels)) > 100
        camera.SetParallelScale(camera.GetParallelScale()*1.15)
    v.fit()
    assert np.count_nonzero(cyan(capture(v))) > 100


def test_visible_solids_occlude_sketch_and_hidden_solids_do_not(qtbot):
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    w.document.add_entity(identifier, Circle(20, 15, 8))
    w.refresh()
    # In sketch mode the box is hidden, so its former depth must not occlude.
    w.grid_action.setChecked(False)
    w.axes_action.setChecked(False)
    assert not v.actor.GetVisibility()
    assert np.count_nonzero(cyan(capture(v))) > 50
    w.finish_sketch_action.trigger()
    v.orient('Top')
    # The XY circle lies underneath the top face of the box (z=20).
    assert v.actor.GetVisibility()
    assert np.count_nonzero(cyan(capture(v))) == 0
    v.actor.VisibilityOff()
    v.edge_actor.VisibilityOff()
    v.clamp_zoom()
    assert np.count_nonzero(cyan(capture(v))) > 50
    v.actor.VisibilityOn()
    v.edge_actor.VisibilityOn()
    v.clamp_zoom()
    assert np.count_nonzero(cyan(capture(v))) == 0


def test_major_minor_grid_and_snap_marker_render(qtbot):
    from PySide6.QtCore import QPoint
    from test_sketch_ui import pixel, hover
    w = window(qtbot)
    identifier = enter(w)
    v = w.viewport
    w.axes_action.setChecked(False)
    w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(1)
    w.grid_action.setChecked(False)
    plain = capture(v)
    w.grid_action.setChecked(True)
    grid = capture(v)
    assert np.count_nonzero(np.max(abs(grid-plain), axis=2) > 5) > 100
    w.viewport.sketch.guides.minor_actor.VisibilityOff()
    major_only = capture(v)
    assert np.count_nonzero(np.max(abs(grid-major_only), axis=2) > 2) > 100
    w.grid_action.setChecked(False)
    w.tool_choice.setCurrentText('Line')
    frame = w.document.feature(identifier).parameters.frame
    hover(v, pixel(v, frame.to_world((5, 5)))+QPoint(2, 0))
    assert v.sketch.snap_result.target == 'GRID'
    marker = capture(v)
    gold = (marker[..., 0] > 180) & (marker[..., 1] > 130) & (marker[..., 2] < 100)
    assert np.count_nonzero(gold) > 5
    hover(v, pixel(v, frame.to_world((0, 0)))+QPoint(2, 0))
    assert v.sketch.snap_result.target == 'ORIGIN'
    marker = capture(v)
    magenta = (marker[..., 0] > 180) & (marker[..., 2] > 150) & (marker[..., 1] < 130)
    assert np.count_nonzero(magenta) > 5

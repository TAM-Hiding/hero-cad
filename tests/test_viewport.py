from math import isfinite
import pytest
from PySide6.QtCore import QPoint, Qt
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from star_cad.document import BoxParameters, Document
from star_cad.ui.display_geometry import edge_mesh, selected_mesh, subshapes, tessellate
from star_cad.ui.main_window import MainWindow


def project(viewport, point):
    viewport.renderer.SetWorldPoint(*point, 1)
    viewport.renderer.WorldToDisplay()
    return viewport.renderer.GetDisplayPoint()[:2]


def make_window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_edges_are_unique_cad_boundaries_not_triangle_diagonals():
    shape = Document().shape
    wire = edge_mesh(shape)
    assert len(subshapes(shape, TopAbs_EDGE)) == wire.GetNumberOfCells() == 12
    assert wire.GetNumberOfPolys() == 0
    ids = wire.GetCellData().GetArray('edge_id')
    assert {ids.GetValue(i) for i in range(12)} == set(range(12))
    for i in range(12):
        cell = wire.GetCell(i)
        a = wire.GetPoint(cell.GetPointId(0))
        b = wire.GetPoint(cell.GetPointId(cell.GetNumberOfPoints() - 1))
        assert sum(abs(a[j] - b[j]) > 1e-7 for j in range(3)) == 1
    surface = tessellate(shape)
    assert len(subshapes(shape, TopAbs_FACE)) == 6
    assert {surface.GetCellData().GetArray('face_id').GetValue(i) for i in range(12)} == set(range(6))
    assert selected_mesh(surface, 'face_id', 0).GetNumberOfCells() == 2
    assert selected_mesh(wire, 'edge_id', 0).GetNumberOfCells() == 1


def test_display_mesh_handles_located_curved_shape():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf, gp_Vec
    shape = BRepPrimAPI_MakeCylinder(5, 12).Shape()
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(10, 20, 30))
    shape = shape.Moved(TopLoc_Location(transform))
    wire = edge_mesh(shape)
    assert wire.GetBounds() == pytest.approx((5, 15, 15, 25, 30, 42), abs=0.1)
    assert tessellate(shape).GetBounds() == pytest.approx(wire.GetBounds(), abs=0.1)


def test_face_edge_picking_and_regeneration(qtbot):
    w = make_window(qtbot)
    v = w.viewport
    v.orient('Front')
    x, y = project(v, (20, 0, 10))
    # Exercise the Qt click path, including logical/device-pixel conversion.
    width, height = v.GetRenderWindow().GetSize()
    point = QPoint(round(x * v.width() / width), round((height - 1 - y) * v.height() / height))
    qtbot.mouseClick(v, Qt.LeftButton, pos=point)
    assert v.selection.kind == 'face'
    face = BRepAdaptor_Surface(v.selection.shape)
    assert face.Plane().Location().Y() == pytest.approx(0)
    assert v.highlight_mapper.GetInput().GetNumberOfCells() == 2
    assert v.highlight_actor.GetVisibility()
    assert 'Selected face' in w.statusBar().currentMessage()
    w.selection_choice.setCurrentIndex(1)
    assert v.selection.kind == 'face'  # Changing filters preserves mixed-selection capability.
    x, y = project(v, (20, 0, 0))
    v.pick_at(x, y)
    assert v.selection.kind == 'edge'
    assert v.selection.shape.IsSame(v.edges[v.selection.index])
    assert v.highlight_mapper.GetInput().GetNumberOfCells() == 1
    qtbot.keyClick(v, Qt.Key_Escape)
    assert v.selection is None and not v.highlight_actor.GetVisibility()
    v.pick_at(x, y)
    assert v.selection is not None
    w.fields['width'].setValue(50)
    w.apply_dimensions()
    assert v.selection is None and not v.highlight_actor.GetVisibility()
    v.pick_at(1, 1)
    assert v.selection is None


def test_rear_edge_is_not_selected_through_face(qtbot):
    w = make_window(qtbot)
    v = w.viewport
    v.orient('Isometric')
    v.set_selection_mode('edge')
    x, y = project(v, (0, 30, 10))
    v.pick_at(x, y)
    assert v.selection is None
    x, y = project(v, (40, 0, 10))
    v.pick_at(x, y)
    assert v.selection is not None and v.selection.kind == 'edge'


def test_drag_does_not_select(qtbot):
    w = make_window(qtbot)
    v = w.viewport
    start = QPoint(v.width() // 2, v.height() // 2)
    qtbot.mousePress(v, Qt.LeftButton, pos=start)
    qtbot.mouseMove(v, start + QPoint(50, 30))
    qtbot.mouseRelease(v, Qt.LeftButton, pos=start + QPoint(50, 30))
    assert v.selection is None


@pytest.mark.parametrize('view,direction', [('Front', (0, 1, 0)), ('Top', (0, 0, -1)), ('Right', (-1, 0, 0))])
def test_orientation_and_zoom_limits_follow_geometry(qtbot, view, direction):
    w = make_window(qtbot)
    v = w.viewport
    v.orient(view)
    camera = v.renderer.GetActiveCamera()
    assert camera.GetDirectionOfProjection() == pytest.approx(direction)
    small, large = v.zoom_limits
    for value, expected in [(1e-100, small), (1e100, large)]:
        camera.SetParallelScale(value)
        v.clamp_zoom()
        assert camera.GetParallelScale() == pytest.approx(expected)
        assert all(isfinite(x) and x > 0 for x in camera.GetClippingRange())
    v.set_shape(Document(BoxParameters(0.001, 0.002, 0.003)).shape, fit=True)
    assert v.zoom_limits[0] < small
    assert v.zoom_limits[0] <= camera.GetParallelScale() <= v.zoom_limits[1]
    v.fit()
    assert v.zoom_limits[0] < camera.GetParallelScale() < v.zoom_limits[1]


def test_camera_controls_bounded_zoom_and_highlight_render(qtbot):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    import numpy as np
    w = make_window(qtbot)
    v = w.viewport
    camera = v.renderer.GetActiveCamera()
    origin = QPointF(v.width() / 2, v.height() / 2)
    for sign, count in [(1, 65), (-1, 160)]:
        for _ in range(count):
            event = QWheelEvent(origin, origin, QPoint(), QPoint(0, 120 * sign),
                                Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(v, event)
            assert v.zoom_limits[0] <= camera.GetParallelScale() <= v.zoom_limits[1]
        expected = v.zoom_limits[0 if sign > 0 else 1]
        assert camera.GetParallelScale() == pytest.approx(expected)
    v.orient('Front')
    x, y = project(v, (20, 0, 10))
    def center_pixels():
        capture = vtkWindowToImageFilter()
        capture.SetInput(v.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        output = capture.GetOutput()
        width, height, _ = output.GetDimensions()
        pixels = vtk_to_numpy(output.GetPointData().GetScalars()).reshape(height, width, 3)
        return pixels[round(y)-3:round(y)+4, round(x)-3:round(x)+4].astype(int)
    plain = center_pixels()
    # The former triangle diagonal crossed this planar-face center.
    assert plain[:, :, 2].mean() > plain[:, :, 0].mean() > 60
    assert np.max(np.ptp(plain, axis=(0, 1))) < 8
    v.pick_at(x, y)
    assert v.selection.kind == 'face'
    highlighted = center_pixels()
    assert highlighted[:, :, 0].mean() > highlighted[:, :, 1].mean() > highlighted[:, :, 2].mean()
    v.clear_selection()
    assert np.abs(center_pixels() - plain).max() < 3
    v.set_selection_mode('edge')
    x, y = project(v, (20, 0, 0))
    v.pick_at(x, y)
    assert v.selection.kind == 'edge'
    # Wider patch around the thin selected boundary must contain orange pixels.
    pixels = center_pixels()
    assert np.any((pixels[:, :, 0] > 200) & (pixels[:, :, 1] > 100) & (pixels[:, :, 2] < 100))

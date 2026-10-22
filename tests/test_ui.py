import pytest
from PySide6.QtCore import Qt
from star_cad.geometry import volume
from star_cad.ui.main_window import MainWindow
from star_cad.ui.viewport import tessellate
from star_cad.document import Document


def test_tessellation_matches_solid_bounds():
    mesh = tessellate(Document().shape)
    assert mesh.GetNumberOfCells() == 12
    assert mesh.GetBounds() == pytest.approx((0, 40, 0, 30, 0, 20))


def test_window_edit_and_fit(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.fields['width'].setValue(55.125)
    qtbot.mouseClick(window.apply_button, Qt.LeftButton)
    assert window.document.parameters.width == 55.125
    assert volume(window.document.shape) == pytest.approx(55.125 * 30 * 20)
    assert window.viewport.mapper.GetInput().GetBounds() == pytest.approx((0, 55.125, 0, 30, 0, 20))
    window.viewport.fit()
    assert window.browser.currentItem().text(0) == 'Box · current body'


def test_camera_controls_and_render(qtbot):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    import numpy as np

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    viewport = window.viewport
    camera = viewport.renderer.GetActiveCamera()
    start = QPoint(viewport.width() // 2, viewport.height() // 2)
    position = camera.GetPosition()
    qtbot.mousePress(viewport, Qt.LeftButton, pos=start)
    qtbot.mouseMove(viewport, start + QPoint(60, 35))
    qtbot.mouseRelease(viewport, Qt.LeftButton, pos=start + QPoint(60, 35))
    assert camera.GetPosition() != position
    focal = camera.GetFocalPoint()
    qtbot.mousePress(viewport, Qt.MiddleButton, pos=start)
    qtbot.mouseMove(viewport, start + QPoint(35, 20))
    qtbot.mouseRelease(viewport, Qt.MiddleButton, pos=start + QPoint(35, 20))
    assert camera.GetFocalPoint() != focal
    scale = camera.GetParallelScale()
    event = QWheelEvent(QPointF(start), QPointF(viewport.mapToGlobal(start)),
                        QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase, False)
    QApplication.sendEvent(viewport, event)
    assert camera.GetParallelScale() < scale
    viewport.fit()
    image = vtkWindowToImageFilter()
    image.SetInput(viewport.GetRenderWindow())
    image.ReadFrontBufferOff()
    image.Update()
    pixels = vtk_to_numpy(image.GetOutput().GetPointData().GetScalars())
    # A blank background must not count as a successful viewport render.
    background = np.array([23, 31, 41])  # renderer background, rounded to bytes
    assert np.mean(np.max(np.abs(pixels.astype(int) - background), axis=1) <= 2) > 0.25
    # Require a substantial shaded blue-gray surface, not random framebuffer data.
    surface = ((pixels[:, 0] > 60) & (pixels[:, 0] < 230)
               & (pixels[:, 2] > pixels[:, 0]) & (pixels[:, 2] > 100))
    assert np.mean(surface) > 0.03

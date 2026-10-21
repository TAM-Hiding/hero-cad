"""OCCT display, bounded orthographic camera and transient subshape selection."""
from math import dist, isfinite
from PySide6.QtCore import Qt, Signal
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401 registers rendering backend
import vtkmodules.vtkInteractionStyle  # noqa: F401
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import vtkActor, vtkCellPicker, vtkPolyDataMapper, vtkRenderer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from star_cad.ui.display_geometry import (
    Selection, edge_mesh, selected_mesh, subshapes, tessellate,
)


class Viewport(QVTKRenderWindowInteractor):
    selectionChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection = None
        self.selection_mode = 'face'
        self._press = None
        self._dragged = False
        self.model_span = 1.0
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.09, 0.12, 0.16)
        self.GetRenderWindow().AddRenderer(self.renderer)
        style = vtkInteractorStyleTrackballCamera()
        self.SetInteractorStyle(style)
        style.AddObserver('InteractionEvent', lambda *_: self.clamp_zoom())
        self.mapper, self.actor = self.add_actor((0.65, 0.79, 0.86))
        # Surface triangles are shaded only. Real B-rep edges are a separate actor.
        self.actor.GetProperty().EdgeVisibilityOff()
        self.edge_mapper, self.edge_actor = self.add_actor((0.13, 0.20, 0.25))
        self.edge_actor.GetProperty().LightingOff()
        self.edge_actor.GetProperty().SetLineWidth(1)
        self.edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.edge_mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0, -1)
        self.highlight_mapper, self.highlight_actor = self.add_actor((1.0, 0.65, 0.15))
        self.highlight_actor.PickableOff()
        self.highlight_actor.VisibilityOff()
        self.highlight_actor.UseBoundsOff()
        self.highlight_actor.GetProperty().LightingOff()
        self.highlight_actor.GetProperty().SetLineWidth(2)
        self.highlight_mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.highlight_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        self.highlight_mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0, -2)
        camera = self.renderer.GetActiveCamera()
        camera.SetPosition(1, -1, 1)
        camera.SetViewUp(0, 0, 1)
        camera.ParallelProjectionOn()
        self.Initialize()

    def add_actor(self, color):
        mapper, actor = vtkPolyDataMapper(), vtkActor()
        mapper.ScalarVisibilityOff()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        self.renderer.AddActor(actor)
        return mapper, actor

    def set_shape(self, shape, fit=False):
        # Build display data before replacing current mappings.
        surface, wire = tessellate(shape), edge_mesh(shape)
        self.faces = subshapes(shape, TopAbs_FACE)
        self.edges = subshapes(shape, TopAbs_EDGE)
        self.mapper.SetInputData(surface)
        self.edge_mapper.SetInputData(wire)
        bounds = surface.GetBounds()
        self.model_span = max(dist(bounds[::2], bounds[1::2]), 0.001)
        self.clear_selection(render=False)
        if fit:
            self.renderer.ResetCamera()
        self.clamp_zoom()
        self.GetRenderWindow().Render()

    @property
    def zoom_limits(self):
        # Parallel scale is half the visible height in model units.
        return self.model_span * 1e-4, self.model_span * 1e3

    def clamp_zoom(self):
        camera = self.renderer.GetActiveCamera()
        lower, upper = self.zoom_limits
        scale = camera.GetParallelScale()
        if not isfinite(scale):
            scale = upper
        camera.SetParallelScale(max(lower, min(upper, scale)))
        self.renderer.ResetCameraClippingRange()

    def wheelEvent(self, event):
        super().wheelEvent(event)
        self.clamp_zoom()
        self.GetRenderWindow().Render()

    def fit(self):
        self.renderer.ResetCamera()
        self.clamp_zoom()
        self.GetRenderWindow().Render()

    def orient(self, name):
        directions = {'Isometric': ((1, -1, 1), (0, 0, 1)),
                      'Front': ((0, -1, 0), (0, 0, 1)),
                      'Top': ((0, 0, 1), (0, 1, 0)),
                      'Right': ((1, 0, 0), (0, 0, 1))}
        direction, up = directions[name]
        camera = self.renderer.GetActiveCamera()
        focal = camera.GetFocalPoint()
        camera.SetPosition(*(focal[i] + direction[i] * self.model_span for i in range(3)))
        camera.SetViewUp(*up)
        self.fit()

    def set_selection_mode(self, mode):
        if mode not in ('face', 'edge'):
            raise ValueError('Selection mode must be face or edge')
        self.selection_mode = mode
        self.clear_selection()

    def clear_selection(self, render=True):
        self.selection = None
        self.highlight_actor.VisibilityOff()
        self.selectionChanged.emit(None)
        if render:
            self.GetRenderWindow().Render()

    def pick_at(self, x, y):
        """Pick in VTK display pixels (origin bottom left)."""
        target = self.actor if self.selection_mode == 'face' else self.edge_actor
        picker = vtkCellPicker()
        picker.PickFromListOn()
        picker.AddPickList(target)
        picker.SetTolerance(0.008 if self.selection_mode == 'edge' else 0.0005)
        if not picker.Pick(x, y, 0, self.renderer) or picker.GetCellId() < 0:
            self.clear_selection()
            return
        if self.selection_mode == 'edge':
            # Do not select rear edges through an opaque front face.
            front = vtkCellPicker()
            front.PickFromListOn()
            front.AddPickList(self.actor)
            front.SetTolerance(0.0005)
            self.renderer.SetWorldPoint(*picker.GetPickPosition(), 1)
            self.renderer.WorldToDisplay()
            edge_x, edge_y, _ = self.renderer.GetDisplayPoint()
            if front.Pick(edge_x, edge_y, 0, self.renderer):
                direction = self.renderer.GetActiveCamera().GetDirectionOfProjection()
                delta = tuple(picker.GetPickPosition()[i] - front.GetPickPosition()[i] for i in range(3))
                if sum(delta[i] * direction[i] for i in range(3)) > self.model_span * 1e-5:
                    self.clear_selection()
                    return
        name = self.selection_mode + '_id'
        mesh = self.mapper.GetInput() if self.selection_mode == 'face' else self.edge_mapper.GetInput()
        index = mesh.GetCellData().GetArray(name).GetValue(picker.GetCellId())
        shapes = self.faces if self.selection_mode == 'face' else self.edges
        self.selection = Selection(self.selection_mode, index, shapes[index])
        self.highlight_mapper.SetInputData(selected_mesh(mesh, name, index))
        self.highlight_actor.VisibilityOn()
        self.selectionChanged.emit(self.selection)
        self.GetRenderWindow().Render()

    def mousePressEvent(self, event):
        self._press = event.position().toPoint() if event.button() == Qt.LeftButton else None
        self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and (event.position().toPoint() - self._press).manhattanLength() > 4:
            self._dragged = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        click = self._press is not None and not self._dragged and event.modifiers() == Qt.NoModifier
        self._press = None
        super().mouseReleaseEvent(event)
        if click and event.button() == Qt.LeftButton:
            width, height = self.GetRenderWindow().GetSize()
            self.pick_at(event.position().x() * width / max(self.width(), 1),
                         height - 1 - event.position().y() * height / max(self.height(), 1))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

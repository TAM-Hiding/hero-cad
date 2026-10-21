"""OCCT display, bounded orthographic camera and transient subshape selection."""
from math import dist, isfinite
from itertools import product
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from vtkmodules.vtkFiltersCore import vtkAppendPolyData
from star_cad.ui.picking import candidates
from star_cad.ui.sketch_view import SketchView
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
    entityCreated = Signal(object)
    sketchEntityPicked = Signal(object)
    toolChanged = Signal(str)
    toolHintChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection = None
        self.selections = []
        self.edge_tolerance_px = 6
        self.selection_mode = 'face'
        self._press = None
        self._dragged = False
        self._additive = False
        self._shift_right_pan = False
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
        self.sketch = SketchView(self)

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
        return self.model_span * 1.25e-4, self.model_span * 1e3

    def clamp_zoom(self):
        camera = self.renderer.GetActiveCamera()
        lower, upper = self.zoom_limits
        scale = camera.GetParallelScale()
        if not isfinite(scale):
            scale = upper
        camera.SetParallelScale(max(lower, min(upper, scale)))
        self.update_clipping()

    def update_clipping(self):
        """Keep orthographic geometry in front of the eye without changing its scale.

        Restoring a camera saved before a large sketch was made can put that
        camera inside the new scene. Resetting near/far alone cannot include
        geometry behind a positive near plane. Guides intentionally do not
        contribute bounds; a live preview does contribute clipping bounds.
        """
        bounds = list(self.renderer.ComputeVisiblePropBounds())
        sketch = getattr(self, 'sketch', None)
        if sketch and sketch.preview_actor.GetVisibility():
            preview = sketch.preview_actor.GetBounds()
            if preview and all(isfinite(n) for n in preview) and preview[0] <= preview[1]:
                if bounds[0] > bounds[1]:
                    bounds = list(preview)
                else:
                    for i in range(3):
                        bounds[2*i] = min(bounds[2*i], preview[2*i])
                        bounds[2*i+1] = max(bounds[2*i+1], preview[2*i+1])
        if not all(isfinite(n) for n in bounds) or any(bounds[i] > bounds[i+1] for i in (0, 2, 4)):
            return
        camera = self.renderer.GetActiveCamera()
        if camera.GetParallelProjection():
            position, direction = camera.GetPosition(), camera.GetDirectionOfProjection()
            corners = product(*[(bounds[i], bounds[i+1]) for i in (0, 2, 4)])
            nearest = min(sum((p[i]-position[i])*direction[i] for i in range(3)) for p in corners)
            margin = max(dist(bounds[::2], bounds[1::2])*0.02, 0.001)
            if nearest < margin:
                camera.SetPosition(*(position[i]-direction[i]*(margin-nearest) for i in range(3)))
        self.renderer.ResetCameraClippingRange(bounds)

    def wheelEvent(self, event):
        self.sketch.clear_snap()
        super().wheelEvent(event)
        self.clamp_zoom()
        self.toolHintChanged.emit(self.sketch.controller.hint)
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

    def clear_selection(self, render=True):
        self.selections = []
        self.selection = None
        self.highlight_actor.VisibilityOff()
        self.selectionChanged.emit(None)
        if render:
            self.GetRenderWindow().Render()

    def line_candidates(self, mesh, x, y):
        scale = self.GetRenderWindow().GetSize()[1] / max(self.height(), 1)
        return candidates(self.renderer, mesh, x, y, self.edge_tolerance_px * scale)

    def visible_edge(self, point):
        front = vtkCellPicker()
        front.PickFromListOn()
        front.AddPickList(self.actor)
        front.SetTolerance(0.0005)
        self.renderer.SetWorldPoint(*point, 1)
        self.renderer.WorldToDisplay()
        x, y, _ = self.renderer.GetDisplayPoint()
        if not front.Pick(x, y, 0, self.renderer):
            return True
        direction = self.renderer.GetActiveCamera().GetDirectionOfProjection()
        return sum((point[i]-front.GetPickPosition()[i])*direction[i] for i in range(3)) <= self.model_span*1e-5

    def pick_at(self, x, y, additive=False):
        """Pick in device pixels. Shift toggles the current subshape in the set."""
        name = self.selection_mode + '_id'
        if self.selection_mode == 'edge':
            mesh = self.edge_mapper.GetInput()
            hit = next((hit for hit in self.line_candidates(mesh, x, y) if self.visible_edge(hit[1])), None)
            cell_id = hit[2] if hit else -1
        else:
            mesh = self.mapper.GetInput()
            picker = vtkCellPicker()
            picker.PickFromListOn()
            picker.AddPickList(self.actor)
            picker.SetTolerance(0.0005)
            cell_id = picker.GetCellId() if picker.Pick(x, y, 0, self.renderer) else -1
        if cell_id < 0:
            if not additive:
                self.clear_selection()
            return
        index = mesh.GetCellData().GetArray(name).GetValue(cell_id)
        shapes = self.faces if self.selection_mode == 'face' else self.edges
        selected = Selection(self.selection_mode, index, shapes[index])
        if not additive:
            self.selections = [selected]
        elif any(s.kind == selected.kind and s.index == index for s in self.selections):
            self.selections = [s for s in self.selections if (s.kind, s.index) != (selected.kind, index)]
        else:
            self.selections.append(selected)
        self.selection = self.selections[-1] if self.selections else None
        if self.selections:
            append = vtkAppendPolyData()
            for item in self.selections:
                data = self.mapper.GetInput() if item.kind == 'face' else self.edge_mapper.GetInput()
                append.AddInputData(selected_mesh(data, item.kind+'_id', item.index))
            append.Update()
            self.highlight_mapper.SetInputData(append.GetOutput())
        self.highlight_actor.SetVisibility(bool(self.selections))
        self.selectionChanged.emit(self.selection)
        self.GetRenderWindow().Render()

    def display_position(self, event):
        width, height = self.GetRenderWindow().GetSize()
        return (event.position().x()*width/max(self.width(), 1),
                height-1-event.position().y()*height/max(self.height(), 1))

    def navigation_event(self, event):
        # Shift-right is a latched pan gesture; VTK receives a middle drag.
        if self._shift_right_pan:
            button = Qt.MiddleButton if event.button() == Qt.RightButton else event.button()
            buttons = (event.buttons() & ~Qt.RightButton) | (Qt.MiddleButton if event.buttons() & Qt.RightButton else Qt.NoButton)
            return QMouseEvent(event.type(), event.position(), event.globalPosition(), button,
                               buttons, event.modifiers() & ~Qt.ShiftModifier)
        return event

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self.sketch.controller.tool:
            self.sketch.clear_snap()
        if event.button() == Qt.RightButton and event.modifiers() & Qt.ShiftModifier:
            self._shift_right_pan = True
        if event.button() == Qt.LeftButton and self.sketch.active_id and self.sketch.controller.tool:
            self.sketch.event('press', *self.display_position(event), bool(event.modifiers() & Qt.ShiftModifier))
            return
        self._press = event.position().toPoint() if event.button() == Qt.LeftButton else None
        self._dragged = False
        self._additive = bool(event.modifiers() & Qt.ShiftModifier) and event.button() == Qt.LeftButton
        if not self._additive:
            super().mousePressEvent(self.navigation_event(event))

    def mouseMoveEvent(self, event):
        if self.sketch.active_id and self.sketch.controller.tool and not (event.buttons() & (Qt.MiddleButton | Qt.RightButton)):
            self.sketch.event('move', *self.display_position(event), bool(event.modifiers() & Qt.ShiftModifier))
            return
        if self._press is not None and (event.position().toPoint()-self._press).manhattanLength() > 4:
            self._dragged = True
        if not self._additive:
            super().mouseMoveEvent(self.navigation_event(event))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.sketch.active_id and self.sketch.controller.tool:
            self.sketch.event('release', *self.display_position(event), bool(event.modifiers() & Qt.ShiftModifier))
            return
        click = self._press is not None and not self._dragged
        self._press = None
        additive = self._additive
        if not additive:
            super().mouseReleaseEvent(self.navigation_event(event))
        self._additive = False
        if event.button() == Qt.RightButton:
            self._shift_right_pan = False
        if click and event.button() == Qt.LeftButton:
            if self.sketch.active_id:
                self.sketch.pick(*self.display_position(event))
            else:
                self.pick_at(*self.display_position(event), additive=additive)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.sketch.active_id and self.sketch.controller.tool:
                self.sketch.set_tool('select')
            else:
                self.clear_selection()
                self.sketch.select_entity(None)
                self.sketchEntityPicked.emit(None)
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event):
        self.sketch.clear_snap()
        self.toolHintChanged.emit(self.sketch.controller.hint)
        self.GetRenderWindow().Render()
        super().leaveEvent(event)

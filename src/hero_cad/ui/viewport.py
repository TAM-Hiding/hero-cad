"""OCCT display, bounded orthographic camera and transient subshape selection."""
from math import dist, isfinite, radians, tan
from itertools import product
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from hero_cad.ui.camera_alignment import planar_view_target
from vtkmodules.vtkFiltersCore import vtkAppendPolyData
from hero_cad.ui.picking import candidates
from hero_cad.ui.sketch_view import SketchView
from hero_cad.ui.construction_dimensions import ConstructionDimensions
from hero_cad.ui.profile_view import ProfileView
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401 registers rendering backend
import vtkmodules.vtkInteractionStyle  # noqa: F401
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import vtkActor, vtkCamera, vtkCellPicker, vtkPolyDataMapper, vtkRenderer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from hero_cad.ui.display_geometry import (
    Selection, edge_mesh, selected_mesh, subshapes, tessellate,
)


class Viewport(QVTKRenderWindowInteractor):
    selectionChanged = Signal(object)
    entityCreated = Signal(object)
    sketchEntityPicked = Signal(object)
    toolChanged = Signal(str)
    toolHintChanged = Signal(str)
    viewFeedback = Signal(str)
    previousViewAvailable = Signal(bool)
    xrayChanged = Signal(str)
    sketchContextRequested = Signal(object, object)
    faceContextRequested = Signal(object, object)
    deleteRequested = Signal()
    cancelRequested = Signal()
    profilePicked = Signal(object)
    profileContextRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection = None
        self.selections = []
        self.edge_tolerance_px = 6
        self.selection_mode = 'face'
        self.display_mode = 'Shaded with CAD Edges'
        self.xray_mode = 'Off'
        self.contrast_mode = 'Auto'
        self.planar_normals = []
        self.solid_visible = True
        self._press = None
        self._dragged = False
        self._additive = False
        self._shift_right_pan = False
        self._right_press = None
        self._right_dragged = False
        self._last_right_dragged = False
        self._consume_right_release = False
        self._previous_view = None
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
        # Editing/explicit sketch inspection gets a foreground pass; model
        # solids and ordinary finished sketches retain their real depth buffer.
        self.GetRenderWindow().SetNumberOfLayers(2)
        self.sketch_renderer = vtkRenderer()
        self.sketch_renderer.SetLayer(1)
        self.sketch_renderer.SetInteractive(False)
        self.sketch_renderer.SetPreserveColorBuffer(True)
        self.sketch_renderer.SetPreserveDepthBuffer(False)
        self.sketch_renderer.SetActiveCamera(camera)
        self.GetRenderWindow().AddRenderer(self.sketch_renderer)
        self.Initialize()
        self.sketch = SketchView(self)
        self.dimensions = ConstructionDimensions(self)
        self.profiles = ProfileView(self)
        # VTK and direct camera changes can render before InteractionEvent.
        # Repair clipping after display preparation, immediately before drawing.
        self.renderer.AddObserver('StartEvent', lambda *_: self.update_clipping() if self.sketch.feature else None)
        self.renderer.AddObserver('StartEvent', lambda *_: self.apply_solid_style())

    def add_actor(self, color):
        mapper, actor = vtkPolyDataMapper(), vtkActor()
        mapper.ScalarVisibilityOff()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        self.renderer.AddActor(actor)
        return mapper, actor

    def sketch_foreground(self, actor, enabled):
        destination = self.sketch_renderer if enabled else self.renderer
        if not destination.HasViewProp(actor):
            self.renderer.RemoveActor(actor)
            self.sketch_renderer.RemoveActor(actor)
            destination.AddActor(actor)

    def set_shape(self, shape, fit=False):
        # Build display data before replacing current mappings.
        surface, wire = tessellate(shape), edge_mesh(shape)
        self.faces = subshapes(shape, TopAbs_FACE)
        self.planar_normals = []
        for face in self.faces:
            try:
                self.planar_normals.append(planar_view_target(face, (0, 0, 0)).normal)
            except ValueError:
                pass
        self.edges = subshapes(shape, TopAbs_EDGE)
        self.mapper.SetInputData(surface)
        self.edge_mapper.SetInputData(wire)
        self.apply_display_mode()
        bounds = surface.GetBounds()
        self.model_span = max(dist(bounds[::2], bounds[1::2]), 0.001) if surface.GetNumberOfPoints() else self.model_span
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
        if sketch and sketch.feature:
            # An empty sketch has no model bounds. Its origin/grid are excluded
            # from Fit, but the editable plane still needs a valid depth range.
            # Include its current viewport footprint for clipping only, even
            # when the grid is hidden. This also avoids slicing an oblique grid
            # down to the depth span of a small curve on the same plane.
            camera = self.renderer.GetActiveCamera()
            frame = sketch.feature.parameters.frame
            center = frame.to_local(camera.GetFocalPoint())
            half = max(camera.GetParallelScale(), .001)*max(self.width()/max(self.height(), 1), 1)*1.5
            plane = [frame.to_world((center[0]+u*half, center[1]+v*half))
                     for u in (-1, 1) for v in (-1, 1)]
            plane_bounds = [value for i in range(3) for value in (min(p[i] for p in plane), max(p[i] for p in plane))]
            if bounds[0] > bounds[1]:
                bounds = plane_bounds
            else:
                for i in range(3):
                    bounds[2*i] = min(bounds[2*i], plane_bounds[2*i])
                    bounds[2*i+1] = max(bounds[2*i+1], plane_bounds[2*i+1])
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

    def set_display_mode(self, mode):
        if mode not in ('Shaded with CAD Edges', 'Shaded', 'CAD Wireframe', 'Mesh Debug'):
            raise ValueError('Unknown display mode')
        self.display_mode = mode
        self.viewFeedback.emit(f'Display mode: {mode}')
        self.apply_display_mode()
        self.GetRenderWindow().Render()

    def set_solid_visibility(self, visible):
        self.solid_visible = bool(visible)
        self.apply_display_mode()

    def set_xray_mode(self, mode):
        if mode not in ('Off', 'Celadon', 'Orange'):
            raise ValueError('Unknown X-Ray mode')
        self.xray_mode = mode
        self.apply_solid_style()
        self.sketch.guides.update()
        self.xrayChanged.emit(mode)
        self.GetRenderWindow().Render()

    def set_contrast_mode(self, mode):
        if mode not in ('Off', 'Auto', 'Always'):
            raise ValueError('Unknown geometry contrast mode')
        self.contrast_mode = mode
        self.apply_solid_style()
        self.GetRenderWindow().Render()

    def high_contrast(self):
        if self.contrast_mode != 'Auto':
            return self.contrast_mode == 'Always'
        if getattr(self, 'sketch', None) and self.sketch.active_id:
            return True
        camera = self.renderer.GetActiveCamera()
        direction = camera.GetDirectionOfProjection()
        # Within two degrees of a principal or actual analytic planar normal.
        normals = [(1,0,0), (0,1,0), (0,0,1), *self.planar_normals]
        return bool(camera.GetParallelProjection() and any(
            abs(sum(a*b for a,b in zip(direction,n))) >= .999390827 for n in normals))

    def apply_solid_style(self):
        editing = bool(getattr(self, 'sketch', None) and self.sketch.active_id)
        explicit = self.xray_mode != 'Off'
        opacity = .85 if explicit else .35 if editing else 1.
        self.actor.GetProperty().SetOpacity(opacity)
        self.edge_actor.GetProperty().SetOpacity(opacity)
        contrast = self.high_contrast()
        self.edge_actor.GetProperty().SetColor(*((.055, .075, .095) if contrast else (.13, .20, .25)))
        # Opaque dark boundaries contrast against pale solids, retaining real depth.
        if contrast:
            self.edge_actor.GetProperty().SetOpacity(1.)
        self.actor.GetProperty().SetColor(*((1., .65, .15) if self.xray_mode == 'Orange' else (.65, .79, .86)))
        # A brighter warm selection distinguishes it from orange reference bodies.
        self.highlight_actor.GetProperty().SetColor(*((1., .93, .65) if self.xray_mode == 'Orange' else (1., .65, .15)))

    def apply_display_mode(self):
        self.apply_solid_style()
        self.actor.SetVisibility(self.solid_visible and self.display_mode != 'CAD Wireframe')
        self.edge_actor.SetVisibility(self.solid_visible and self.display_mode in ('Shaded with CAD Edges', 'CAD Wireframe'))
        self.actor.GetProperty().EdgeVisibilityOff()
        if self.display_mode == 'Mesh Debug':
            self.actor.GetProperty().SetRepresentationToWireframe()
        else:
            self.actor.GetProperty().SetRepresentationToSurface()

    def surface_pick(self, x, y):
        if not self.actor.GetVisibility() and not (self.display_mode == 'CAD Wireframe' and self.edge_actor.GetVisibility()):
            return None
        visible = self.actor.GetVisibility()
        representation = self.actor.GetProperty().GetRepresentation()
        try:
            # Pick the authoritative face mapping even when surfaces are not drawn.
            self.actor.VisibilityOn()
            self.actor.GetProperty().SetRepresentationToSurface()
            picker = vtkCellPicker()
            picker.PickFromListOn()
            picker.AddPickList(self.actor)
            picker.SetTolerance(0.0005)
            if not picker.Pick(x, y, 0, self.renderer) or picker.GetCellId() < 0:
                return None
            return picker.GetCellId(), picker.GetPickPosition()
        finally:
            self.actor.SetVisibility(visible)
            self.actor.GetProperty().SetRepresentation(representation)

    def face_pick_at(self, x, y):
        hit = self.surface_pick(x, y)
        if hit is None:
            return None
        cell, point = hit
        index = self.mapper.GetInput().GetCellData().GetArray('face_id').GetValue(cell)
        return self.faces[index], point

    def align_face_at(self, x, y):
        hit = self.face_pick_at(x, y)
        if hit is None:
            self.viewFeedback.emit('No visible face at cursor')
            return False
        try:
            target = planar_view_target(*hit)
        except ValueError as error:
            self.viewFeedback.emit(str(error))
            return False
        camera = self.renderer.GetActiveCamera()
        previous = vtkCamera()
        previous.DeepCopy(camera)
        scale = camera.GetParallelScale()
        if not camera.GetParallelProjection():
            direction, position = camera.GetDirectionOfProjection(), camera.GetPosition()
            depth = sum((target.point[i]-position[i])*direction[i] for i in range(3))
            scale = max(depth, .001)*tan(radians(camera.GetViewAngle())/2)
            if camera.GetUseHorizontalViewAngle():
                width, height = self.GetRenderWindow().GetSize()
                scale *= max(height, 1)/max(width, 1)
        distance = max(camera.GetDistance(), .001)
        camera.SetFocalPoint(*target.point)
        camera.SetPosition(*(target.point[i]+target.normal[i]*distance for i in range(3)))
        camera.SetViewUp(*target.up)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(scale)
        self.clamp_zoom()
        self._previous_view = previous
        self.previousViewAvailable.emit(True)
        self.viewFeedback.emit('View aligned perpendicular to planar face')
        self.GetRenderWindow().Render()
        return True

    def previous_view(self):
        if self._previous_view is None:
            return False
        self.renderer.GetActiveCamera().DeepCopy(self._previous_view)
        self._previous_view = None
        self.previousViewAvailable.emit(False)
        self.viewFeedback.emit('Previous view restored')
        self.GetRenderWindow().Render()
        return True

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
        if self.display_mode == 'CAD Wireframe':
            return True
        self.renderer.SetWorldPoint(*point, 1)
        self.renderer.WorldToDisplay()
        hit = self.surface_pick(*self.renderer.GetDisplayPoint()[:2])
        if hit is None:
            return True
        direction = self.renderer.GetActiveCamera().GetDirectionOfProjection()
        return sum((point[i]-hit[1][i])*direction[i] for i in range(3)) <= self.model_span*1e-5

    def pick_at(self, x, y, additive=False):
        """Pick in device pixels. Shift toggles the current subshape in the set."""
        name = self.selection_mode + '_id'
        if self.selection_mode == 'edge':
            mesh = self.edge_mapper.GetInput()
            hit = next((hit for hit in self.line_candidates(mesh, x, y) if self.visible_edge(hit[1])), None)
            cell_id = hit[2] if hit else -1
        else:
            mesh = self.mapper.GetInput()
            hit = self.surface_pick(x,y)
            cell_id = hit[0] if hit else -1
        if cell_id < 0:
            if not additive:
                self.clear_selection()
            return
        index = mesh.GetCellData().GetArray(name).GetValue(cell_id)
        shapes = self.faces if self.selection_mode == 'face' else self.edges
        selected = Selection(self.selection_mode, index, shapes[index], tuple(hit[1]))
        if not additive:
            self.selections = [selected]
        elif any(s.kind == selected.kind and s.index == index for s in self.selections):
            self.selections = [s for s in self.selections if (s.kind, s.index) != (selected.kind, index)]
        else:
            self.selections.append(selected)
        self.show_selection()

    def show_selection(self):
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

    def select_face(self, face, point=None):
        index = next(i for i, f in enumerate(self.faces) if f.IsSame(face))
        if not any(s.kind == 'face' and s.index == index for s in self.selections):
            self.selections = [Selection('face', index, self.faces[index], point)]
        else:
            selected = next(s for s in self.selections if s.kind == 'face' and s.index == index)
            # Keep the batch, but make the contextual face the current target.
            self.selections = [s for s in self.selections if s is not selected]
            self.selections.append(Selection('face', index, selected.shape,
                                             point if point is not None else selected.point))
        self.show_selection()

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
        if event.button() == Qt.LeftButton and self.dimensions.editing:
            return
        if event.button() == Qt.RightButton and not event.modifiers() & Qt.ShiftModifier:
            self._context_press = event.position().toPoint()
            self._context_dragged = False
            super().mousePressEvent(event)
            return
        if event.button() != Qt.LeftButton or not self.sketch.controller.tool:
            self.sketch.clear_snap()
        if event.button() == Qt.RightButton and event.modifiers() & Qt.ShiftModifier:
            self._shift_right_pan = True
            self._right_press = event.position().toPoint()
            self._right_dragged = False
        if event.button() == Qt.LeftButton and self.sketch.active_id and self.sketch.controller.tool:
            self.setFocus(Qt.MouseFocusReason)
            self.sketch.event('press', *self.display_position(event), bool(event.modifiers() & Qt.ShiftModifier))
            self.dimensions.update_values(event.position())
            return
        self._press = event.position().toPoint() if event.button() == Qt.LeftButton else None
        self._dragged = False
        self._additive = bool(event.modifiers() & Qt.ShiftModifier) and event.button() == Qt.LeftButton
        if not self._additive:
            super().mousePressEvent(self.navigation_event(event))

    def mouseMoveEvent(self, event):
        if self.dimensions.editing and not event.buttons() & (Qt.MiddleButton | Qt.RightButton):
            return
        if getattr(self, '_context_press', None) is not None and event.buttons() & Qt.RightButton:
            if (event.position().toPoint()-self._context_press).manhattanLength() >= QApplication.startDragDistance():
                self._context_dragged = True
            if self._context_dragged:
                super().mouseMoveEvent(event)
            return
        if self._consume_right_release and event.buttons() & Qt.RightButton:
            return
        if self._shift_right_pan and self._right_press is not None:
            if (event.position().toPoint()-self._right_press).manhattanLength() >= QApplication.startDragDistance():
                self._right_dragged = True
            if not self._right_dragged:
                return
        if self.sketch.active_id and self.sketch.controller.tool and not (event.buttons() & (Qt.MiddleButton | Qt.RightButton)):
            self.sketch.event('move', *self.display_position(event), bool(event.modifiers() & Qt.ShiftModifier))
            self.dimensions.update_values(event.position())
            return
        if self._press is not None and (event.position().toPoint()-self._press).manhattanLength() > 4:
            self._dragged = True
        if not self._additive:
            super().mouseMoveEvent(self.navigation_event(event))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dimensions.editing:
            return
        if event.button() == Qt.RightButton and getattr(self, '_context_press', None) is not None:
            start, self._context_press = self._context_press, None
            super().mouseReleaseEvent(event)
            if not self._context_dragged and (event.position().toPoint()-start).manhattanLength() < QApplication.startDragDistance():
                if self.profiles.active:
                    self.profiles.pick(*self.display_position(event))
                    if self.profiles.selection:
                        self.profileContextRequested.emit(event.globalPosition().toPoint())
                else:
                    hit = self.sketch.hit(*self.display_position(event))
                    face = self.face_pick_at(*self.display_position(event)) if not self.sketch.active_id else None
                    if face is not None and hit is None:
                        self.faceContextRequested.emit(face, event.globalPosition().toPoint())
                    else:
                        self.sketchContextRequested.emit(hit, event.globalPosition().toPoint())
            return
        if event.button() == Qt.RightButton and self._consume_right_release:
            self._consume_right_release = False
            return
        if event.button() == Qt.LeftButton and self.sketch.active_id and self.sketch.controller.tool:
            self.sketch.event('release', *self.display_position(event), bool(event.modifiers() & Qt.ShiftModifier))
            self.dimensions.update_values(event.position())
            return
        click = self._press is not None and not self._dragged
        self._press = None
        additive = self._additive
        if not additive:
            super().mouseReleaseEvent(self.navigation_event(event))
        self._additive = False
        if event.button() == Qt.RightButton:
            self._last_right_dragged = self._right_dragged if self._shift_right_pan else False
            self._shift_right_pan = False
            self._right_press = None
        if click and event.button() == Qt.LeftButton:
            if self.profiles.active:
                self.profiles.pick(*self.display_position(event))
            elif self.sketch.active_id or self.sketch.hit(*self.display_position(event)):
                self.sketch.pick(*self.display_position(event), additive=additive)
            else:
                self.pick_at(*self.display_position(event), additive=additive)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.RightButton and event.modifiers() & Qt.ShiftModifier and not self._last_right_dragged:
            # Qt sends press/release/double-click/release. The double-click
            # replaces the second press; consume its release rather than send
            # an unmatched VTK button-up. End any synthetic preceding pan first.
            if self._shift_right_pan:
                super().mouseReleaseEvent(self.navigation_event(event))
            self._shift_right_pan = False
            self._right_press = self._press = None
            self._additive = False
            self._consume_right_release = True
            self.align_face_at(*self.display_position(event))
            event.accept()
            return
        self.mousePressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key_W, Qt.Key_S, Qt.Key_P):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_W, Qt.Key_S, Qt.Key_P) and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            event.accept()
            return
        if event.key() == Qt.Key_Tab and self.sketch.active_id and self.sketch.controller.tool:
            if self.dimensions.begin():
                event.accept()
                return
        if (self.sketch.active_id and self.sketch.controller.tool
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
                and event.text() and event.text()[0] in '0123456789.+-'):
            if self.dimensions.begin(event.text()):
                event.accept()
                return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.deleteRequested.emit()
            return
        if event.key() == Qt.Key_Escape:
            self.cancelRequested.emit()
            self.profiles.clear()
            if self.sketch.active_id and self.sketch.controller.tool:
                self.sketch.set_tool('select')
            else:
                self.clear_selection()
                self.sketch.select_entity(None)
                self.sketchEntityPicked.emit(None)
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sketch'):
            self.sketch.guides.update()
            self.GetRenderWindow().Render()

    def focusNextPrevChild(self, next):
        # QWidget normally consumes Tab before keyPressEvent for focus traversal.
        if hasattr(self, 'dimensions') and self.sketch.active_id and self.sketch.controller.tool and self.dimensions.names:
            return self.dimensions.begin()
        return super().focusNextPrevChild(next)

    def leaveEvent(self, event):
        self.sketch.clear_snap()
        self.toolHintChanged.emit(self.sketch.controller.hint)
        self.GetRenderWindow().Render()
        super().leaveEvent(event)

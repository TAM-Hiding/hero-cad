"""Sketch display and planar input adapter; construction logic lives in tools.py."""
from math import dist
from vtkmodules.vtkRenderingCore import vtkCamera
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
from star_cad.tools import ToolController, ToolEvent
from star_cad.ui.display_geometry import paths_mesh


class SketchView:
    def __init__(self, viewport):
        self.viewport = viewport
        self.features = ()
        self.active_id = None
        self.entity_id = None
        self.controller = ToolController()
        self.saved_camera = None
        self.origin_mapper, self.origin_actor = viewport.add_actor((0.8, 0.85, 0.9))
        points = vtkPoints()
        points.InsertNextPoint(0, 0, 0)
        cells = vtkCellArray()
        cells.InsertNextCell(1)
        cells.InsertCellPoint(0)
        origin = vtkPolyData()
        origin.SetPoints(points)
        origin.SetVerts(cells)
        self.origin_mapper.SetInputData(origin)
        self.origin_actor.GetProperty().SetPointSize(5)
        self.origin_actor.GetProperty().LightingOff()
        self.origin_actor.PickableOff()
        self.origin_actor.UseBoundsOff()
        self.origin_actor.VisibilityOff()
        self.mapper, self.actor = viewport.add_actor((0.4, 0.85, 0.95))
        self.preview_mapper, self.preview_actor = viewport.add_actor((0.65, 0.95, 0.7))
        self.axes_mapper, self.axes_actor = viewport.add_actor((0.25, 0.38, 0.46))
        self.highlight_mapper, self.highlight_actor = viewport.add_actor((1.0, 0.65, 0.15))
        for mapper, actor in ((self.mapper, self.actor), (self.preview_mapper, self.preview_actor),
                              (self.axes_mapper, self.axes_actor), (self.highlight_mapper, self.highlight_actor)):
            mapper.SetInputData(paths_mesh([]))
            actor.GetProperty().LightingOff()
            actor.GetProperty().SetLineWidth(1)
            actor.PickableOff()
        for actor in (self.preview_actor, self.axes_actor, self.highlight_actor):
            actor.UseBoundsOff()
        self.highlight_actor.GetProperty().SetLineWidth(2)
        self.actor.VisibilityOff()
        self.axes_actor.VisibilityOff()
        self.highlight_actor.VisibilityOff()
        self.preview_actor.VisibilityOff()
        self.mapping = []

    @property
    def feature(self):
        return next((f for f in self.features if f.id == self.active_id), None)

    def update(self, features):
        self.features = tuple(features)
        if self.active_id and self.feature is None:
            self.finish()
        paths, self.mapping = [], []
        for feature in self.features:
            if self.active_id and feature.id != self.active_id:
                continue
            for entity in feature.parameters.entities:
                paths.append([feature.parameters.frame.to_world(p) for p in entity.points])
                self.mapping.append((feature.id, entity.id))
        mesh = paths_mesh(paths)
        self.mapper.SetInputData(mesh)
        self.actor.SetVisibility(bool(paths))
        if paths:
            bounds = mesh.GetBounds()
            self.viewport.model_span = max(self.viewport.model_span, dist(bounds[::2], bounds[1::2]))
        if self.entity_id:
            self.select_entity(self.entity_id)

    def enter(self, identifier):
        if not any(f.id == identifier for f in self.features):
            raise ValueError('Unknown sketch')
        if self.active_id is None:
            self.saved_camera = vtkCamera()
            self.saved_camera.DeepCopy(self.viewport.renderer.GetActiveCamera())
        self.active_id = identifier
        self.set_tool('select')
        self.viewport.clear_selection(render=False)
        self.viewport.actor.VisibilityOff()
        self.viewport.edge_actor.VisibilityOff()
        self.update(self.features)
        frame = self.feature.parameters.frame
        camera = self.viewport.renderer.GetActiveCamera()
        camera.SetFocalPoint(*frame.origin)
        camera.SetPosition(*(frame.origin[i]+frame.normal[i]*max(self.viewport.model_span*2, 10) for i in range(3)))
        camera.SetViewUp(*frame.v)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(max(self.viewport.model_span*0.6, 10))
        if self.feature.parameters.entities:
            self.viewport.renderer.ResetCamera()
        extent = max(self.viewport.model_span, 20)
        axes = [[frame.to_world(p) for p in path] for path in
                (((-extent, 0), (extent, 0)), ((0, -extent), (0, extent)))]
        self.axes_mapper.SetInputData(paths_mesh(axes))
        self.axes_actor.VisibilityOn()
        self.origin_actor.VisibilityOn()
        self.viewport.clamp_zoom()
        self.viewport.GetRenderWindow().Render()

    def finish(self):
        self.active_id = None
        self.entity_id = None
        self.set_tool('select')
        self.axes_actor.VisibilityOff()
        self.origin_actor.VisibilityOff()
        self.highlight_actor.VisibilityOff()
        self.viewport.actor.VisibilityOn()
        self.viewport.edge_actor.VisibilityOn()
        if self.saved_camera:
            self.viewport.renderer.GetActiveCamera().DeepCopy(self.saved_camera)
            self.saved_camera = None
        self.update(self.features)
        self.viewport.clamp_zoom()
        self.viewport.GetRenderWindow().Render()

    def set_tool(self, name):
        self.controller.set_tool(name)
        self.preview_actor.VisibilityOff()
        self.viewport.toolChanged.emit(name)
        self.viewport.toolHintChanged.emit(self.controller.hint)
        self.viewport.GetRenderWindow().Render()

    def point_at(self, x, y):
        if self.feature is None:
            return None
        renderer = self.viewport.renderer
        points = []
        for z in (0, 1):
            renderer.SetDisplayPoint(x, y, z)
            renderer.DisplayToWorld()
            p = renderer.GetWorldPoint()
            points.append(tuple(p[i]/p[3] for i in range(3)))
        frame = self.feature.parameters.frame
        direction = tuple(points[1][i]-points[0][i] for i in range(3))
        divisor = sum(direction[i]*frame.normal[i] for i in range(3))
        if abs(divisor) < 1e-12:
            return None
        t = sum((frame.origin[i]-points[0][i])*frame.normal[i] for i in range(3))/divisor
        return frame.to_local(tuple(points[0][i]+t*direction[i] for i in range(3)))

    def event(self, phase, x, y, shift=False):
        point = self.point_at(x, y)
        if point is None:
            return
        entity = self.controller.handle(ToolEvent(phase, point, shift))
        preview = self.controller.preview
        self.preview_mapper.SetInputData(paths_mesh(
            [[self.feature.parameters.frame.to_world(p) for p in preview]] if preview else []))
        self.preview_actor.SetVisibility(bool(preview))
        self.viewport.toolHintChanged.emit(self.controller.hint)
        if entity is not None:
            self.viewport.entityCreated.emit(entity)
        self.viewport.GetRenderWindow().Render()

    def pick(self, x, y):
        hits = self.viewport.line_candidates(self.mapper.GetInput(), x, y)
        self.entity_id = self.mapping[hits[0][2]][1] if hits else None
        self.select_entity(self.entity_id)
        self.viewport.sketchEntityPicked.emit(self.entity_id)

    def select_entity(self, identifier):
        self.entity_id = identifier
        paths = []
        for feature in self.features:
            for entity in feature.parameters.entities:
                if entity.id == identifier:
                    paths.append([feature.parameters.frame.to_world(p) for p in entity.points])
        self.highlight_mapper.SetInputData(paths_mesh(paths))
        self.highlight_actor.SetVisibility(bool(paths))
        self.viewport.GetRenderWindow().Render()

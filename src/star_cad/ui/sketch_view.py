"""Sketch display and planar input adapter; construction logic lives in tools.py."""
from math import dist
from vtkmodules.vtkRenderingCore import vtkCamera
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
from star_cad.tools import ToolController, ToolEvent
from star_cad.ui.display_geometry import paths_mesh
from star_cad.ui.guides import ViewGuides
from star_cad.ui.snapping import center_targets, snap_point
from star_cad.ui.curve_display import display_points, segment_count


class SketchView:
    def __init__(self, viewport):
        self.viewport = viewport
        self.features = ()
        self.active_id = None
        self.entity_id = None
        self.entity_ids = set()
        self.controller = ToolController()
        self.saved_camera = None
        self.snap_result = None
        self.snap_mapper, self.snap_actor = viewport.add_actor((1.0, 0.85, 0.25))
        self.snap_actor.GetProperty().SetPointSize(7)
        self.snap_actor.GetProperty().LightingOff()
        self.snap_actor.PickableOff()
        self.snap_actor.UseBoundsOff()
        self.snap_actor.VisibilityOff()
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
        self.highlight_mapper, self.highlight_actor = viewport.add_actor((1.0, 0.65, 0.15))
        for mapper, actor in ((self.mapper, self.actor), (self.preview_mapper, self.preview_actor),
                              (self.highlight_mapper, self.highlight_actor)):
            mapper.SetInputData(paths_mesh([]))
            actor.GetProperty().LightingOff()
            actor.GetProperty().SetLineWidth(1)
            actor.PickableOff()
        for actor in (self.preview_actor, self.highlight_actor):
            actor.UseBoundsOff()
        self.highlight_actor.GetProperty().SetLineWidth(2)
        self.actor.VisibilityOff()
        self.highlight_actor.VisibilityOff()
        self.preview_actor.VisibilityOff()
        self.mapping = []
        self._path_cache = {}
        self._display_key = self._highlight_key = self._preview_key = None
        self.guides = ViewGuides(viewport)
        self.axes_mapper, self.axes_actor = self.guides.axes[0]
        viewport.GetRenderWindow().AddObserver('StartEvent', lambda *_: self.prepare_display())

    @property
    def feature(self):
        return next((f for f in self.features if f.id == self.active_id), None)

    def update(self, features):
        self.clear_snap()
        self.features = tuple(features)
        if self.active_id and self.feature is None:
            self.finish()
        keep = {e.id for f in self.features for e in f.parameters.entities}
        self.entity_ids.intersection_update(keep)
        if self.entity_id not in keep:
            self.entity_id = None
        self._path_cache = {k: v for k, v in self._path_cache.items() if k in keep}
        self.prepare_display()
        if self.actor.GetVisibility():
            bounds = self.mapper.GetInput().GetBounds()
            self.viewport.model_span = max(self.viewport.model_span, dist(bounds[::2], bounds[1::2]))
        self.guides.update()
        self.viewport.clamp_zoom()

    @property
    def pixels_per_mm(self):
        camera = self.viewport.renderer.GetActiveCamera()
        return max(self.viewport.GetRenderWindow().GetSize()[1], 1)/(2*camera.GetParallelScale())

    def world_path(self, feature, entity, count):
        key = (feature.parameters.plane, entity, count)
        previous = self._path_cache.get(entity.id)
        if previous is None or previous[0] != key:
            path = tuple(feature.parameters.frame.to_world(p) for p in display_points(entity, count))
            self._path_cache[entity.id] = (key, path)
        return self._path_cache[entity.id][1]

    def prepare_display(self):
        """Refresh quality bands before rendering, never recursively render here."""
        ppm = self.pixels_per_mm
        visible = tuple(f for f in self.features if not self.active_id or f.id == self.active_id)
        rows = [(f, e, segment_count(e, ppm)) for f in visible for e in f.parameters.entities]
        key = (visible, tuple(count for _, _, count in rows))
        if key != self._display_key:
            self.mapper.SetInputData(paths_mesh([self.world_path(f, e, n) for f, e, n in rows]))
            self.mapping = [(f.id, e.id) for f, e, _ in rows]
            self.actor.SetVisibility(bool(rows))
            self._display_key = key
        highlight_key = (key, frozenset(self.entity_ids))
        if highlight_key != self._highlight_key:
            paths = [self.world_path(f, e, n) for f, e, n in rows if e.id in self.entity_ids]
            self.highlight_mapper.SetInputData(paths_mesh(paths))
            self.highlight_actor.SetVisibility(bool(paths))
            self._highlight_key = highlight_key
        tool = self.controller.tool
        preview_entity = tool.preview_entity if tool else None
        preview = self.controller.preview
        count = segment_count(preview_entity, ppm)
        preview_key = (self.active_id, preview_entity, count, preview if preview_entity is None else ())
        if preview_key != self._preview_key:
            path = display_points(preview_entity, count) if preview_entity else preview
            paths = [[self.feature.parameters.frame.to_world(p) for p in path]] if self.feature and path else []
            self.preview_mapper.SetInputData(paths_mesh(paths))
            self.preview_actor.SetVisibility(bool(paths))
            self._preview_key = preview_key

    def enter(self, identifier):
        self.viewport.profiles.clear()
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
        self.guides.update()
        self.origin_actor.VisibilityOn()
        self.viewport.clamp_zoom()
        self.viewport.GetRenderWindow().Render()

    def finish(self):
        self.viewport.profiles.clear()
        self.active_id = None
        self.entity_id = None
        self.entity_ids.clear()
        self.set_tool('select')
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
        if hasattr(self.viewport, 'dimensions'):
            self.viewport.dimensions.reset()
        self.clear_snap()
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
            self.clear_snap()
            self.viewport.toolHintChanged.emit(self.controller.hint)
            self.viewport.GetRenderWindow().Render()
            return
        self.guides.update()
        frame = self.feature.parameters.frame
        def project(local):
            self.viewport.renderer.SetWorldPoint(*frame.to_world(local), 1)
            self.viewport.renderer.WorldToDisplay()
            p = self.viewport.renderer.GetDisplayPoint()
            return p[:2] if 0 <= p[2] <= 1 else None
        scale = self.viewport.GetRenderWindow().GetSize()[1]/max(self.viewport.height(), 1)
        self.snap_result = snap_point(point, (x, y), project, self.guides.spacing,
                                      grid=self.guides.snap_grid, origin=self.guides.snap_origin,
                                      centers=center_targets(self.feature.parameters.entities) if self.guides.snap_center else (),
                                      tolerance=8*scale)
        point = self.snap_result.point
        self.show_snap(frame)
        entity = self.controller.handle(ToolEvent(phase, point, shift))
        self.complete_event(entity)

    def complete_event(self, entity):
        self.prepare_display()
        self.viewport.update_clipping()
        self.viewport.toolHintChanged.emit(self.controller.hint)
        if entity is not None:
            self.viewport.entityCreated.emit(entity)
        self.viewport.dimensions.update_values()
        self.viewport.GetRenderWindow().Render()

    def numeric_preview(self):
        self.clear_snap()
        tool = self.controller.tool
        if tool and tool.last_point is not None:
            self.controller.handle(ToolEvent('move', tool.last_point))
            self.complete_event(None)

    def numeric_commit(self):
        tool = self.controller.tool
        if tool and tool.last_point is not None:
            entity = self.controller.handle(ToolEvent(tool.numeric_phase(), tool.last_point))
            self.complete_event(entity)

    def clear_snap(self):
        self.snap_result = None
        self.snap_actor.VisibilityOff()

    @property
    def precision_hint(self):
        interval = f'Grid: {self.guides.major_spacing:g} / {self.guides.spacing:g} mm'
        if self.snap_result:
            u, v = self.snap_result.point
            return f'U: {u:.9g} mm | V: {v:.9g} mm | SNAP: {self.snap_result.target} | {interval}'
        return interval

    def show_snap(self, frame):
        result = self.snap_result
        self.snap_actor.SetVisibility(result.target != 'FREE')
        if result.target == 'FREE':
            return
        points, cells = vtkPoints(), vtkCellArray()
        points.SetDataTypeToDouble()
        points.InsertNextPoint(*frame.to_world(result.point))
        cells.InsertNextCell(1)
        cells.InsertCellPoint(0)
        mesh = vtkPolyData()
        mesh.SetPoints(points)
        mesh.SetVerts(cells)
        self.snap_mapper.SetInputData(mesh)
        colors = {'ORIGIN': (1., .35, .9), 'CENTER': (.35, .65, 1.), 'GRID': (1., .85, .25)}
        self.snap_actor.GetProperty().SetColor(*colors[result.target])
        self.snap_actor.GetProperty().SetPointSize(7 if result.target == 'GRID' else 9)

    def hit(self, x, y):
        self.prepare_display()
        hits = self.viewport.line_candidates(self.mapper.GetInput(), x, y)
        hit = next((h for h in hits if not self.viewport.actor.GetVisibility() or self.viewport.visible_edge(h[1])), None)
        return self.mapping[hit[2]] if hit else None

    def pick(self, x, y, additive=False):
        hit = self.hit(x, y)
        identifier = hit[1] if hit else None
        if additive and identifier:
            self.entity_ids.symmetric_difference_update({identifier})
            self.entity_id = identifier if identifier in self.entity_ids else next(iter(self.entity_ids), None)
        else:
            self.entity_ids = {identifier} if identifier else set()
            self.entity_id = identifier
        self.select_entity(self.entity_id)
        current = next((row for row in self.mapping if row[1] == self.entity_id), None)
        self.viewport.sketchEntityPicked.emit(current)

    def select_entity(self, identifier):
        self.entity_id = identifier
        if identifier is None:
            self.entity_ids.clear()
        elif identifier not in self.entity_ids:
            self.entity_ids = {identifier}
        self.prepare_display()
        self.viewport.GetRenderWindow().Render()

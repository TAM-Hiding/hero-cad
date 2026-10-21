"""Disposable view guides, excluded from picking, fitting and document history."""
from math import ceil, floor, log10
from star_cad.ui.display_geometry import paths_mesh


class ViewGuides:
    def __init__(self, viewport):
        self.viewport = viewport
        self.axes_visible = True
        self.grid_visible = True
        self.spacing = 1.0
        self.axes = []
        for color in ((0.95, 0.22, 0.18), (0.95, 0.8, 0.16), (0.22, 0.5, 1.0)):
            self.axes.append(self.actor(color))
        self.grid_mapper, self.grid_actor = self.actor((0.16, 0.22, 0.29))
        # Place the grid behind entity lines, without moving its model plane.
        self.grid_mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.grid_mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0, 2)
        self.grid_actor.VisibilityOff()
        viewport.renderer.GetActiveCamera().AddObserver('ModifiedEvent', lambda *_: self.update())

    def actor(self, color):
        mapper, actor = self.viewport.add_actor(color)
        mapper.SetInputData(paths_mesh([]))
        actor.GetProperty().LightingOff()
        actor.GetProperty().SetLineWidth(1)
        actor.PickableOff()
        actor.UseBoundsOff()
        return mapper, actor

    def update(self):
        v = self.viewport
        camera = v.renderer.GetActiveCamera()
        extent = max(v.model_span, camera.GetParallelScale()*2, 20)
        for i, (mapper, actor) in enumerate(self.axes):
            a, b = [0., 0., 0.], [0., 0., 0.]
            a[i], b[i] = -extent, extent
            mapper.SetInputData(paths_mesh([(a, b)]))
            actor.SetVisibility(self.axes_visible)
        sketch = getattr(v, 'sketch', None)
        frame = sketch.feature.parameters.frame if sketch and sketch.feature else None
        self.grid_actor.SetVisibility(bool(frame) and self.grid_visible)
        if not frame or not self.grid_visible:
            return
        # About 45 logical pixels per grid cell; use familiar 1/2/5 mm steps.
        desired = max(2*camera.GetParallelScale()*45/max(v.height(), 1), 1e-8)
        power = 10**floor(log10(desired))
        self.spacing = next(k*power for k in (1, 2, 5, 10) if k*power >= desired)
        center = frame.to_local(camera.GetFocalPoint())
        aspect = max(v.width(), 1)/max(v.height(), 1)
        half = camera.GetParallelScale()*max(aspect, 1)*1.5
        # Bounded size, even if the sketch view has been orbited.
        ranges = [(floor((c-half)/self.spacing), ceil((c+half)/self.spacing)) for c in center]
        paths = []
        for axis in (0, 1):
            lo, hi = ranges[axis]
            for index in range(lo, min(hi+1, lo+160)):
                a, b = list(center), list(center)
                a[axis] = b[axis] = index*self.spacing
                a[1-axis], b[1-axis] = center[1-axis]-half, center[1-axis]+half
                paths.append((frame.to_world(a), frame.to_world(b)))
        self.grid_mapper.SetInputData(paths_mesh(paths))

    def set_axes_visible(self, visible):
        self.axes_visible = bool(visible)
        self.update()
        self.viewport.GetRenderWindow().Render()

    def set_grid_visible(self, visible):
        self.grid_visible = bool(visible)
        self.update()
        self.viewport.GetRenderWindow().Render()

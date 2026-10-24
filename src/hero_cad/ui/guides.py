"""Disposable view guides and session-only grid settings."""
from math import ceil, floor, log10
from hero_cad.ui.display_geometry import paths_mesh


class ViewGuides:
    def __init__(self, viewport):
        self.viewport = viewport
        self.axes_visible = True
        self.grid_visible = True
        self.snap_grid = True
        self.snap_origin = True
        self.snap_center = True
        self.automatic = True
        self.manual_spacing = 1.0  # minor interval in mm
        self.spacing = 1.0
        self.major_spacing = 10.0
        self.axes = []
        for color in ((0.95, 0.22, 0.18), (0.95, 0.8, 0.16), (0.22, 0.5, 1.0)):
            self.axes.append(self.actor(color))
        self.grid_mapper, self.grid_actor = self.actor((0.22, 0.30, 0.38))
        self.minor_mapper, self.minor_actor = self.actor((0.135, 0.18, 0.24))
        for mapper, actor in ((self.grid_mapper, self.grid_actor), (self.minor_mapper, self.minor_actor)):
            # The modest offset applies only to guide lines, behind sketch lines.
            mapper.SetResolveCoincidentTopologyToPolygonOffset()
            mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0, 2)
            actor.VisibilityOff()
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
        # Spacing is kept current even with the grid hidden: snapping is independent.
        if self.automatic:
            desired = max(2*camera.GetParallelScale()*100/max(v.height(), 1), 1e-8)
            power = 10**floor(log10(desired))
            self.major_spacing = next(k*power for k in (1, 2, 5, 10) if k*power >= desired)
            self.spacing = self.major_spacing/10
        else:
            self.spacing = self.manual_spacing
            self.major_spacing = self.spacing*10
        sketch = getattr(v, 'sketch', None)
        frame = sketch.feature.parameters.frame if sketch and sketch.feature else None
        # In face-edit context, opaque foreground lattice lines can otherwise
        # erase coincident source curves on a parallel plane behind the plate.
        context = bool(sketch and sketch.feature and sketch.feature.parameters.attachment)
        for actor in (self.grid_actor, self.minor_actor):
            actor.GetProperty().SetOpacity(.4 if context else 1.)
        visible = bool(frame) and self.grid_visible
        self.grid_actor.SetVisibility(visible)
        self.minor_actor.SetVisibility(visible)
        if not visible:
            return
        center = frame.to_local(camera.GetFocalPoint())
        aspect = max(v.width(), 1)/max(v.height(), 1)
        half = camera.GetParallelScale()*max(aspect, 1)*1.5
        major, minor = [], []
        for axis in (0, 1):
            # Cap displayed lines at dense manual settings; all intervals remain
            # exact multiples of the chosen model-space minor interval.
            lo, hi = floor((center[axis]-half)/self.spacing), ceil((center[axis]+half)/self.spacing)
            stride = 1 if hi-lo <= 200 else 10**ceil(log10((hi-lo)/200))
            first = ceil(lo/stride)*stride
            for index in range(first, hi+1, stride):
                a, b = list(center), list(center)
                a[axis] = b[axis] = index*self.spacing
                a[1-axis], b[1-axis] = center[1-axis]-half, center[1-axis]+half
                (major if index % 10 == 0 else minor).append((frame.to_world(a), frame.to_world(b)))
        self.grid_mapper.SetInputData(paths_mesh(major))
        self.minor_mapper.SetInputData(paths_mesh(minor))

    def set_option(self, name, value):
        setattr(self, name, value)
        self.update()
        sketch = getattr(self.viewport, 'sketch', None)
        if sketch:
            sketch.clear_snap()
            self.viewport.toolHintChanged.emit(sketch.controller.hint)
        self.viewport.GetRenderWindow().Render()

    def set_axes_visible(self, visible):
        self.set_option('axes_visible', bool(visible))

    def set_grid_visible(self, visible):
        self.set_option('grid_visible', bool(visible))

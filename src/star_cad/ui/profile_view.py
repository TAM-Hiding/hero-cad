"""Click-inside analytic material regions; independent of edge/face filters."""
from star_cad.profiles import regions, contains
from star_cad.ui.display_geometry import tessellate


class ProfileView:
    def __init__(self, viewport):
        self.viewport = viewport
        self.active = False
        self.selection = None
        self.cache = {}
        self.mapper, self.actor = viewport.add_actor((1., .65, .15))
        self.actor.GetProperty().SetOpacity(.3)
        self.actor.GetProperty().LightingOff()
        self.actor.PickableOff()
        self.actor.UseBoundsOff()
        self.mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        self.actor.VisibilityOff()

    def clear(self):
        self.selection = None
        self.actor.VisibilityOff()
        self.viewport.profilePicked.emit(None)

    def set_mode(self, active):
        self.active = bool(active)
        self.clear()
        if active and self.viewport.sketch.active_id:
            self.viewport.sketch.set_tool('select')
        self.viewport.GetRenderWindow().Render()

    def pick(self, x, y):
        self.clear()
        v = self.viewport
        candidates, errors = [], []
        renderer = v.renderer
        ray = []
        for z in (0, 1):
            renderer.SetDisplayPoint(x, y, z)
            renderer.DisplayToWorld()
            p = renderer.GetWorldPoint()
            ray.append(tuple(p[i]/p[3] for i in range(3)))
        direction = tuple(ray[1][i]-ray[0][i] for i in range(3))
        for feature in v.sketch.features:
            if v.sketch.active_id and feature.id != v.sketch.active_id:
                continue
            frame = feature.parameters.frame
            divisor = sum(direction[i]*frame.normal[i] for i in range(3))
            if abs(divisor) < 1e-12:
                continue
            t = sum((frame.origin[i]-ray[0][i])*frame.normal[i] for i in range(3))/divisor
            if not 0 <= t <= 1:
                continue
            world = tuple(ray[0][i]+t*direction[i] for i in range(3))
            if v.actor.GetVisibility() and not v.visible_edge(world):
                continue
            if feature.id not in self.cache:
                try:
                    self.cache[feature.id] = regions(feature.parameters)
                except ValueError as error:
                    self.cache[feature.id] = str(error)
            available = self.cache[feature.id]
            if isinstance(available, str):
                errors.append(available)
                continue
            for region in available:
                if contains(region.face, world):
                    candidates.append((t, feature.id, region))
        candidates.sort(key=lambda row: row[:2])
        if not candidates or (len(candidates) > 1 and abs(candidates[0][0]-candidates[1][0]) < 1e-8):
            v.viewFeedback.emit(errors[0] if errors else 'No unambiguous material region here. Holes, overlapping/touching loops and line chains cannot be filled; enter the intended sketch if profiles coincide.')
        else:
            _, sketch_id, region = candidates[0]
            self.selection = (sketch_id, region)
            self.mapper.SetInputData(tessellate(region.face))
            self.actor.VisibilityOn()
            v.profilePicked.emit(self.selection)
            v.viewFeedback.emit(f'Material profile selected · {len(region.hole_ids)} hole(s) · Extrude… creates a new body')
        v.GetRenderWindow().Render()

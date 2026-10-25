"""Click-inside analytic material regions; independent of edge/face filters."""
from hero_cad.profiles import regions, contains
from hero_cad.ui.display_geometry import tessellate


class ProfileView:
    def __init__(self, viewport):
        self.viewport = viewport
        self.active = False
        self.scope_id = None
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

    def set_mode(self, active, *, sketch_id=None):
        self.active = bool(active)
        self.scope_id = sketch_id if active else None
        self.clear()
        if active and self.viewport.sketch.active_id:
            self.viewport.sketch.set_tool('select')
        self.viewport.sketch.prepare_display()
        if active:
            self.viewport.viewFeedback.emit('Select Profile: selected sketch only, through reference bodies.' if self.scope_id
                                           else 'Select Profile: visible regions. Select a sketch in the browser to access hidden profiles.')
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
        scope = v.sketch.active_id or self.scope_id
        for feature in v.sketch.features:
            if not scope and not feature.sketch_visible:
                continue
            if scope and feature.id != scope:
                continue
            frame = feature.parameters.frame
            divisor = sum(direction[i]*frame.normal[i] for i in range(3))
            if abs(divisor) < 1e-12:
                continue
            t = sum((frame.origin[i]-ray[0][i])*frame.normal[i] for i in range(3))/divisor
            if not 0 <= t <= 1:
                continue
            world = tuple(ray[0][i]+t*direction[i] for i in range(3))
            if not scope and v.actor.GetVisibility() and not v.visible_edge(world):
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
            v.viewFeedback.emit(errors[0] if errors else 'No unambiguous material region here. Holes, overlapping/touching loops and open line chains cannot be filled; select its sketch in the browser then Select Profile, or edit the sketch.')
        else:
            _, sketch_id, region = candidates[0]
            self.selection = (sketch_id, region)
            self.mapper.SetInputData(tessellate(region.face))
            # Keep the orange material region readable through the new
            # translucent body context; model-view highlighting stays subtle.
            v.sketch_foreground(self.actor, bool(scope))
            self.actor.GetProperty().SetOpacity(.6 if scope else .3)
            self.actor.VisibilityOn()
            v.profilePicked.emit(self.selection)
            v.viewFeedback.emit(f'Material profile selected · {len(region.hole_ids)} hole(s) · Extrude… creates a new body')
        v.GetRenderWindow().Render()

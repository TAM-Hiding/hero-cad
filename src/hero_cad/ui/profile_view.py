"""Click-inside analytic material regions; independent of edge/face filters."""
from hero_cad.profiles import regions, contains
from hero_cad.ui.display_geometry import tessellate


class ProfileView:
    def __init__(self, viewport):
        self.viewport = viewport
        self.active = False
        self.scope_id = None
        self.selections = ()
        self.cache = {}
        self.mapper, self.actor = viewport.add_actor((1., .65, .15))
        self.actor.GetProperty().SetOpacity(.3)
        self.actor.GetProperty().LightingOff()
        self.actor.PickableOff()
        self.actor.UseBoundsOff()
        self.mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        self.actor.VisibilityOff()
        self.hovered = None
        self.hover_mapper, self.hover_actor = viewport.add_actor(self.actor.GetProperty().GetColor())
        self.hover_actor.GetProperty().SetOpacity(.16)
        self.hover_actor.GetProperty().LightingOff()
        self.hover_actor.PickableOff()
        self.hover_actor.UseBoundsOff()
        self.hover_mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.hover_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        self.hover_actor.VisibilityOff()

    @property
    def selection(self):
        """First region retained for existing command availability/signals."""
        return self.selections[0] if self.selections else None

    @selection.setter
    def selection(self, value):
        self.selections = (value,) if value else ()

    def clear(self):
        self.selections = ()
        self.clear_hover()
        self.mapper.SetInputData(None)
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

    def clear_hover(self):
        self.hovered = None
        self.hover_actor.VisibilityOff()
        self.hover_mapper.SetInputData(None)

    def hover(self, x, y):
        scope, hit, _ = self.find(x, y)
        if hit in self.selections:
            hit = None
        if hit == self.hovered:
            return
        self.clear_hover()
        if hit:
            self.hovered = hit
            self.hover_mapper.SetInputData(tessellate(hit[1].face))
            self.viewport.sketch_foreground(self.hover_actor, bool(scope))
            self.hover_actor.VisibilityOn()
        self.viewport.GetRenderWindow().Render()

    def find(self, x, y):
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
            return scope, None, errors[0] if errors else 'Click inside an unambiguous bounded region. Shared edges and open chains are not selectable.'
        _, sketch_id, region = candidates[0]
        return scope, (sketch_id, region), ''

    def pick(self, x, y, *, additive=False, context=False):
        if not additive and not context:
            self.clear()
        else:
            self.clear_hover()
        v = self.viewport
        scope, hit, error = self.find(x, y)
        if hit is None:
            v.viewFeedback.emit(error)
        else:
            sketch_id, region = hit
            if additive and self.selection and self.selection[0] != sketch_id:
                v.viewFeedback.emit('Select profiles from one sketch. Click without Shift to switch sketches.')
                v.GetRenderWindow().Render()
                return
            key = (sketch_id, region.outer_id)
            present = any((sid, r.outer_id) == key for sid, r in self.selections)
            if context:
                if not present:
                    self.selections = ((sketch_id, region),)
            elif present:
                self.selections = tuple((sid, r) for sid, r in self.selections if (sid, r.outer_id) != key)
            else:
                self.selections += ((sketch_id, region),)
            from hero_cad.geometry import compound
            self.mapper.SetInputData(tessellate(compound(tuple(r.face for _, r in self.selections))))
            # Keep the orange material region readable through the new
            # translucent body context; model-view highlighting stays subtle.
            v.sketch_foreground(self.actor, bool(scope))
            self.actor.GetProperty().SetOpacity(.6 if scope else .3)
            self.actor.SetVisibility(bool(self.selections))
            v.profilePicked.emit(self.selection)
            v.viewFeedback.emit(f'{len(self.selections)} material profile(s) selected · Shift-click adds/removes · Extrude…')
        v.GetRenderWindow().Render()

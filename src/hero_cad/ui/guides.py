"""Disposable view guides; the window supplies persisted appearance preferences."""
from math import ceil, floor, log10
from vtkmodules.vtkRenderingCore import vtkTextActor
from hero_cad.ui.display_geometry import paths_mesh


class ViewGuides:
    COLORS = {
        'Light Grey': (.72, .76, .80),
        'White': (.95, .95, .95),
        'Orange': (.78, .58, .37),
        'Purple': (.68, .59, .79),
        'Celadon': (.57, .75, .71),
    }
    def __init__(self, viewport):
        self.viewport = viewport
        self.color = 'Light Grey'
        self.scale_visible = False
        self.fade_xray = False
        self.labels = []
        self.label_data = []
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
            mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0, 2 if actor is self.minor_actor else 1)
            actor.VisibilityOff()
            shader = actor.GetShaderProperty()
            uniforms = shader.GetVertexCustomUniforms()
            uniforms.SetUniform2f('gridViewport', (1., 1.))
            uniforms.SetUniformf('gridAlign', 0.)
            uniforms.SetUniformf('gridCenter', .5 if actor is self.minor_actor else 0.)
            shader.AddVertexShaderReplacement(
                '//VTK::PositionVC::Impl', True,
                '//VTK::PositionVC::Impl\nif (gridAlign > .5) {\n'
                ' vec2 pixels = (gl_Position.xy / gl_Position.w * .5 + .5) * gridViewport;\n'
                ' pixels = floor(pixels + (.5 - gridCenter)) + gridCenter;\n'
                ' gl_Position.xy = (pixels / gridViewport * 2. - 1.) * gl_Position.w;\n'
                '}\n', False)
        self.grid_actor.GetProperty().SetLineWidth(2)
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
        for label in self.labels:
            label.VisibilityOff()
        self.label_data = []
        # In face-edit context, opaque foreground lattice lines can otherwise
        # erase coincident source curves on a parallel plane behind the plate.
        context = bool(sketch and sketch.feature)
        color = self.COLORS[self.color]
        opacity = .4 if context else 1.
        if self.fade_xray and v.xray_mode != 'Off':
            opacity *= .6
        pixels = self.spacing * max(v.height(), 1)/(2*camera.GetParallelScale())
        self.effective_opacity = opacity
        # Precompose guide colors once, rather than alpha-blending every crossing.
        # Opaque guide fragments retain ordinary depth testing and cannot accumulate.
        background = v.renderer.GetBackground()
        for actor, rgb, strength in (
                (self.grid_actor, color, opacity),
                (self.minor_actor, tuple(c*.65 for c in color), opacity*min(1., max(.15, pixels/4)))):
            actor.GetProperty().SetColor(*(background[i]*(1-strength)+rgb[i]*strength for i in range(3)))
            actor.GetProperty().SetOpacity(1.)
        visible = bool(frame) and self.grid_visible
        self.grid_actor.SetVisibility(visible)
        self.minor_actor.SetVisibility(visible)
        if not visible:
            return
        # Pixel-align raster positions only for horizontal/vertical face-normal
        # lines. The mesh and all model/snap coordinates stay exact.
        renderer = v.renderer
        renderer.SetWorldPoint(*frame.origin, 1); renderer.WorldToDisplay()
        origin = renderer.GetDisplayPoint()
        renderer.SetWorldPoint(*frame.to_world((1, 0)), 1); renderer.WorldToDisplay()
        along_u = renderer.GetDisplayPoint()
        normal = abs(sum(a*b for a,b in zip(camera.GetDirectionOfProjection(), frame.normal)))
        aligned = (camera.GetParallelProjection() and normal > 1-1e-10
                   and min(abs(along_u[i]-origin[i]) for i in (0,1)) < 1e-6)
        for actor in (self.grid_actor, self.minor_actor):
            uniforms = actor.GetShaderProperty().GetVertexCustomUniforms()
            uniforms.SetUniform2f('gridViewport', tuple(float(x) for x in v.GetRenderWindow().GetSize()))
            uniforms.SetUniformf('gridAlign', float(aligned))
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
        if self.scale_visible:
            self.update_labels(frame, center, half)

    def update_labels(self, frame, center, half):
        """Bounded 2D labels anchored in exact local coordinates, never pickable."""
        v = self.viewport
        width, height = v.GetRenderWindow().GetSize()
        occupied = []
        # Independently spaced labels use the existing major interval and skip
        # overlaps after projection, including on oblique/panned face sketches.
        for axis in (0, 1):
            lo = floor((center[axis]-half)/self.major_spacing)
            hi = ceil((center[axis]+half)/self.major_spacing)
            stride = max(1, ceil((hi-lo)/24))
            for index in range(ceil(lo/stride)*stride, hi+1, stride):
                local = list(center)
                local[axis] = index*self.major_spacing
                # Use local axes if visible; otherwise the nearest major line.
                other = 1-axis
                local[other] = 0 if abs(center[other]) < half*.65 else round(center[other]/self.major_spacing)*self.major_spacing
                v.renderer.SetWorldPoint(*frame.to_world(local), 1)
                v.renderer.WorldToDisplay()
                x, y, z = v.renderer.GetDisplayPoint()
                value = local[axis]
                text = f'{0 if value == 0 else value:.6g}'
                x, y = x+5, y+5
                box = (x, y, x+len(text)*8+4, y+19)
                if not (0 <= z <= 1 and x >= 4 and y >= 4 and box[2] < width-4 and box[3] < height-4):
                    continue
                if any(not (box[2]+8 < a or c+8 < box[0] or box[3]+4 < b or d+4 < box[1]) for a,b,c,d in occupied):
                    continue
                slot = len(self.label_data)
                if slot >= 32:
                    return
                if slot == len(self.labels):
                    label = vtkTextActor()
                    label.PickableOff()
                    label.UseBoundsOff()
                    label.GetTextProperty().SetFontSize(13)
                    label.GetTextProperty().SetFontFamilyToArial()
                    label.GetTextProperty().SetBackgroundColor(.09, .12, .16)
                    label.GetTextProperty().SetBackgroundOpacity(.65)
                    v.renderer.AddViewProp(label)
                    self.labels.append(label)
                label = self.labels[slot]
                label.SetInput(text)
                label.SetDisplayPosition(round(x), round(y))
                label.GetTextProperty().SetColor(*self.COLORS[self.color])
                label.GetTextProperty().SetOpacity(.95 * (.6 if self.fade_xray and v.xray_mode != 'Off' else 1.))
                label.VisibilityOn()
                self.label_data.append((axis, value, tuple(local), box))
                occupied.append(box)

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

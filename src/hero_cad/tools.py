"""UI-independent construction state machines; Shift is sampled only at initiation."""
from dataclasses import dataclass, replace
from math import hypot, atan2, degrees, isfinite
from hero_cad.sketch import Circle, Line, Slot, diagonal_rectangle, edge_rectangle


@dataclass(frozen=True)
class ToolEvent:
    phase: str  # press, move, release, cancel
    point: tuple = (0.0, 0.0)
    shift: bool = False


class ConstructionTool:
    def __init__(self):
        self.cancel()

    def cancel(self):
        self.stage = 'start'
        self.a = self.b = self.cursor = None
        self.preview = ()
        self.preview_entity = None
        self.dimensions = {}
        self.last_point = None

    def dimension_values(self):
        return {}

    def set_dimension(self, name, value):
        if name not in self.dimension_values():
            raise ValueError('Dimension is unavailable at this construction stage')
        if not isfinite(value) or not 1e-6 <= value <= 1e6:
            raise ValueError('Dimension must be finite and between 0.000001 and 1000000 mm')
        self.dimensions[name] = value

    def constrained(self, point):
        return point

    def numeric_phase(self):
        return 'press'

    def finish(self, entity):
        self.cancel()
        return entity


class LineTool(ConstructionTool):
    def dimension_values(self):
        return {'Length': hypot(*(self.last_point[i]-self.a[i] for i in range(2)))} if self.a and self.last_point else {}

    def constrained(self, point):
        return directed_point(self.a, point, self.dimensions.get('Length'))

    @property
    def hint(self):
        return 'LINE | ' + ('Click first point' if self.stage == 'start' else 'Click second point') + ' | Esc: Cancel'

    def handle(self, event):
        if event.phase == 'press':
            if self.stage == 'start':
                self.a = event.point
                self.stage = 'end'
            else:
                return self.finish(Line(*self.a, *event.point))
        elif event.phase == 'move' and self.a is not None:
            self.preview = (self.a, event.point)


class RectangleTool(ConstructionTool):
    def dimension_values(self):
        if self.a is None or self.last_point is None:
            return {}
        if self.stage == 'diagonal':
            return dict(Width=abs(self.last_point[0]-self.a[0]), Depth=abs(self.last_point[1]-self.a[1]))
        if self.stage == 'edge':
            return dict(Width=hypot(*(self.last_point[i]-self.a[i] for i in range(2))))
        if self.stage == 'depth':
            dx, dy = self.b[0]-self.a[0], self.b[1]-self.a[1]
            return dict(Depth=abs(((self.last_point[0]-self.a[0])*(-dy)+(self.last_point[1]-self.a[1])*dx)/hypot(dx, dy)))
        return {}

    def constrained(self, point):
        if self.a is None:
            return point
        if self.stage == 'diagonal':
            return tuple(self.a[i]+(-1 if point[i] < self.a[i] else 1)*self.dimensions.get(n, abs(point[i]-self.a[i]))
                         for i, n in enumerate(('Width', 'Depth')))
        if self.stage == 'edge':
            return directed_point(self.a, point, self.dimensions.get('Width'))
        if self.stage == 'depth' and 'Depth' in self.dimensions:
            dx, dy = self.b[0]-self.a[0], self.b[1]-self.a[1]
            length = hypot(dx, dy)
            nx, ny = -dy/length, dx/length
            sign = -1 if (point[0]-self.a[0])*nx+(point[1]-self.a[1])*ny < 0 else 1
            return self.b[0]+nx*sign*self.dimensions['Depth'], self.b[1]+ny*sign*self.dimensions['Depth']
        return point

    def rectangle(self, point):
        rectangle = (diagonal_rectangle(self.a, point) if self.stage == 'diagonal' else edge_rectangle(self.a, self.b, point))
        return replace(rectangle, width=self.dimensions.get('Width', rectangle.width), height=self.dimensions.get('Depth', rectangle.height))

    def numeric_phase(self):
        return 'release' if self.stage == 'diagonal' else 'press'

    @property
    def hint(self):
        return {'start': 'RECTANGLE | Drag: Corner-to-corner | Shift: Edge-first | Esc: Cancel',
                'diagonal': 'RECTANGLE | Release at opposite corner | Esc: Cancel',
                'edge': 'RECTANGLE: EDGE-FIRST | Select first edge endpoint | Esc: Cancel',
                'depth': 'RECTANGLE: EDGE-FIRST | Specify perpendicular depth | Esc: Cancel'}[self.stage]

    def handle(self, event):
        if event.phase == 'press':
            if self.stage == 'start':
                self.a = event.point
                self.stage = 'edge' if event.shift else 'diagonal'
            elif self.stage == 'edge':
                # Validate the first edge before accepting it, without constructing depth yet.
                Line(*self.a, *event.point)
                self.b = event.point
                self.stage = 'depth'
            elif self.stage == 'depth':
                return self.finish(self.rectangle(event.point))
        elif event.phase == 'release' and self.stage == 'diagonal':
            result = self.rectangle(event.point)
            return self.finish(result)
        elif event.phase == 'move' and self.stage != 'start':
            if self.stage == 'edge':
                self.preview = (self.a, event.point)
            else:
                try:
                    rectangle = self.rectangle(event.point)
                    self.preview = rectangle.points
                except ValueError:
                    self.preview = (self.a, event.point) if self.b is None else (self.a, self.b)


class CircleTool(ConstructionTool):
    def dimension_values(self):
        if self.a is None or self.last_point is None:
            return {}
        name = 'Center distance' if self.stage == 'center' else 'Radius'
        return {name: hypot(self.last_point[0]-self.a[0], self.last_point[1]-self.a[1])}

    def constrained(self, point):
        name = 'Center distance' if self.stage == 'center' else 'Radius'
        return directed_point(self.a, point, self.dimensions.get(name))

    def slot(self, point):
        return Slot(*self.a, self.radius, self.dimensions.get('Center distance', hypot(point[0]-self.a[0], point[1]-self.a[1])),
                    degrees(atan2(point[1]-self.a[1], point[0]-self.a[0])))

    def numeric_phase(self):
        return 'press' if self.stage == 'center' else 'release'

    @property
    def hint(self):
        return {'start': 'CIRCLE | Drag radius | Shift: Slot | Esc: Cancel',
                'radius': 'CIRCLE | Release to finish | Esc: Cancel',
                'slot_radius': 'SLOT | Release to lock radius | Esc: Cancel',
                'center': 'SLOT | Click second end center | Esc: Cancel'}[self.stage]

    def handle(self, event):
        if event.phase == 'press':
            if self.stage == 'start':
                self.a = event.point
                self.stage = 'slot_radius' if event.shift else 'radius'
            elif self.stage == 'center':
                return self.finish(self.slot(event.point))
        elif event.phase == 'release' and self.stage in ('radius', 'slot_radius'):
            radius = self.dimensions.get('Radius', hypot(event.point[0]-self.a[0], event.point[1]-self.a[1]))
            circle = Circle(*self.a, radius)
            if self.stage == 'radius':
                return self.finish(circle)
            self.radius = radius
            self.preview = circle.points
            self.preview_entity = circle
            self.stage = 'center'
        elif event.phase == 'move' and self.stage != 'start':
            try:
                entity = (self.slot(event.point) if self.stage == 'center'
                          else Circle(*self.a, self.dimensions.get('Radius', hypot(event.point[0]-self.a[0], event.point[1]-self.a[1]))))
                self.preview = entity.points
                self.preview_entity = entity
            except ValueError:
                self.preview = ()
                self.preview_entity = None


class ToolController:
    """The viewport forwards events here, regardless of the active tool's stages.

    Future circle/slot tools can implement the same handle/hint/preview contract.
    Navigation is routed separately and never generates construction events.
    """
    def __init__(self):
        self.set_tool('select')

    def set_tool(self, name):
        factory = {'select': None, 'line': LineTool, 'rectangle': RectangleTool, 'circle': CircleTool}
        if name not in factory:
            raise ValueError('Unknown tool')
        self.name = name
        self.tool = factory[name]() if factory[name] else None
        self.error = None

    @property
    def hint(self):
        text = self.tool.hint if self.tool else 'SKETCH | Select an entity to edit | Line / Rectangle to draw | Finish Sketch to return'
        return text if not self.error else f'{text} | {self.error}'

    @property
    def preview(self):
        return self.tool.preview if self.tool else ()

    def handle(self, event):
        self.error = None
        if event.phase == 'cancel':
            self.set_tool('select')
            return
        if self.tool:
            try:
                self.tool.last_point = event.point
                event = ToolEvent(event.phase, self.tool.constrained(event.point), event.shift)
                return self.tool.handle(event)
            except ValueError as error:
                self.error = str(error)


def directed_point(origin, point, length):
    if origin is None or length is None:
        return point
    dx, dy = point[0]-origin[0], point[1]-origin[1]
    norm = hypot(dx, dy)
    return (origin[0]+length*dx/norm, origin[1]+length*dy/norm) if norm else (origin[0]+length, origin[1])

"""UI-independent construction state machines; Shift is sampled only at initiation."""
from dataclasses import dataclass
from star_cad.sketch import Line, diagonal_rectangle, edge_rectangle


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

    def finish(self, entity):
        self.cancel()
        return entity


class LineTool(ConstructionTool):
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
                return self.finish(edge_rectangle(self.a, self.b, event.point))
        elif event.phase == 'release' and self.stage == 'diagonal':
            result = diagonal_rectangle(self.a, event.point)
            return self.finish(result)
        elif event.phase == 'move' and self.stage != 'start':
            if self.stage == 'edge':
                self.preview = (self.a, event.point)
            else:
                try:
                    rectangle = (diagonal_rectangle(self.a, event.point) if self.stage == 'diagonal'
                                 else edge_rectangle(self.a, self.b, event.point))
                    self.preview = rectangle.points
                except ValueError:
                    self.preview = (self.a, event.point) if self.b is None else (self.a, self.b)


class ToolController:
    """The viewport forwards events here, regardless of the active tool's stages.

    Future circle/slot tools can implement the same handle/hint/preview contract.
    Navigation is routed separately and never generates construction events.
    """
    def __init__(self):
        self.set_tool('select')

    def set_tool(self, name):
        factory = {'select': None, 'line': LineTool, 'rectangle': RectangleTool}
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
                return self.tool.handle(event)
            except ValueError as error:
                self.error = str(error)

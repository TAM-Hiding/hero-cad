"""Disposable vector snap symbols and centerline guides in display pixels."""
from math import cos, sin, pi, hypot
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
from vtkmodules.vtkRenderingCore import vtkActor2D, vtkPolyDataMapper2D
from hero_cad.snap_appearance import DEFAULTS


def circle_path(start=0, end=2*pi, radius=1):
    return tuple((radius*cos(start+(end-start)*i/32), radius*sin(start+(end-start)*i/32))
                 for i in range(33))


def symbol_paths(target, midpoint):
    """Normalized glyphs use strokes, including the overlapping C/L mark."""
    if target in ('ENDPOINT', 'MODEL ENDPOINT'):
        return (((-1,-1),(1,-1),(1,1),(-1,1),(-1,-1)),)
    if target in ('MODEL MIDPOINT','SKETCH MIDPOINT'):
        if midpoint == 'Centerline (C/L)':
            return (circle_path(pi/4,7*pi/4,.8), ((.1,1),(.1,-1),(1,-1)))
        return (((0,1),(-1,-1),(1,-1),(0,1)),)
    if target in ('MODEL EDGE','SKETCH EDGE','MODEL CURVE','SKETCH CURVE'):
        return (((0,1),(1,0),(0,-1),(-1,0),(0,1)),)
    cross = (((-1,0),(1,0)), ((0,-1),(0,1)))
    if target in ('CENTER', 'MODEL CENTER'):
        return (circle_path(radius=.7), *cross)
    return cross


def mesh(paths):
    points, lines = vtkPoints(), vtkCellArray()
    points.SetDataTypeToDouble()
    for path in paths:
        lines.InsertNextCell(len(path))
        for x,y in path:
            lines.InsertCellPoint(points.InsertNextPoint(x,y,0))
    result = vtkPolyData()
    result.SetPoints(points)
    result.SetLines(lines)
    return result


def dashed_guide(center, direction, length, scale, style):
    pattern = {'Dashed': (8,5), 'Dash-dot': (8,4,2,4), 'Dotted': (1,4)}[style]
    paths, position, index = [], -length/2, 0
    while position < length/2:
        end = min(length/2, position+pattern[index % len(pattern)]*scale)
        if index % 2 == 0:
            paths.append(tuple((center[0]+t*direction[0],center[1]+t*direction[1]) for t in (position,end)))
        position, index = end, index+1
    return paths


class SnapIndicators:
    def __init__(self, viewport):
        self.viewport = viewport
        self.options = dict(DEFAULTS)
        self.mapper, self.actor = self.layer()
        self.guide_mapper, self.guide_actor = self.layer()
        self._symbol_key = self._guide_key = None

    def layer(self):
        mapper, actor = vtkPolyDataMapper2D(), vtkActor2D()
        mapper.ScalarVisibilityOff()
        actor.SetMapper(mapper)
        actor.PickableOff()
        actor.UseBoundsOff()
        actor.VisibilityOff()
        self.viewport.sketch_renderer.AddViewProp(actor)
        return mapper, actor

    def clear(self):
        self.actor.VisibilityOff()
        self.guide_actor.VisibilityOff()

    def color(self, role, *, guide=False):
        choice = self.options['guide_color' if guide else 'color']
        named = {'Red': (1.,.2,.2), 'Green': (.2,1.,.35), 'Blue': (.35,.65,1.)}
        if choice in named:
            return named[choice]
        fallback = self.viewport.palette_rgb('snap.center',(.35,.65,1.))
        fallback = {'grid': (1.,.85,.25), 'origin': (1.,.35,.9)}.get(role,fallback)
        return self.viewport.palette_rgb('snap.'+role,fallback)

    def recolor(self, result):
        role = {'GRID':'grid', 'ORIGIN':'origin', 'MODEL ENDPOINT':'endpoint',
                'ENDPOINT':'endpoint', 'MODEL MIDPOINT':'midpoint', 'SKETCH MIDPOINT':'midpoint',
                'MODEL EDGE':'edge', 'SKETCH EDGE':'edge', 'MODEL CURVE':'edge', 'SKETCH CURVE':'edge'}.get(result.target,'center')
        self.actor.GetProperty().SetColor(*self.color(role))
        self.guide_actor.GetProperty().SetColor(*self.color('guide',guide=True))

    def show(self, result, frame, references):
        self.clear()
        if result.target == 'FREE':
            return
        v = self.viewport
        def project(local):
            v.renderer.SetWorldPoint(*frame.to_world(local),1)
            v.renderer.WorldToDisplay()
            return v.renderer.GetDisplayPoint()
        projected = project(result.point)
        if not 0 <= projected[2] <= 1:
            return
        center = projected[:2]
        scale = v.GetRenderWindow().GetSize()[1]/max(v.height(),1)
        half = self.options['size']*scale/2
        if result.target == 'GRID':
            half *= .5
        paths = tuple(tuple((center[0]+x*half,center[1]+y*half) for x,y in path)
                      for path in symbol_paths(result.target,self.options['midpoint']))
        if paths != self._symbol_key:
            self.mapper.SetInputData(mesh(paths))
            self._symbol_key = paths
        self.actor.GetProperty().SetLineWidth(self.options['weight']*scale)
        self.actor.VisibilityOn()
        self.recolor(result)
        directions = []
        if self.options['centerline']:
            if result.target in ('MODEL MIDPOINT','SKETCH MIDPOINT') and references is not None:
                line = next((line for line in references.lines if (line.edge_index,line.entity_id,line.segment)
                             == (result.edge_index,result.entity_id,result.segment)),None)
                if line is not None:
                    directions.append((line.a[1]-line.b[1],line.b[0]-line.a[0]))
            elif result.target in ('CENTER','MODEL CENTER'):
                directions = [(1,0),(0,1)]
        guides = []
        for local in directions:
            local_length = hypot(*local)
            if local_length < 1e-12:
                continue
            end = project(tuple(result.point[i]+local[i]/local_length for i in range(2)))
            direction = tuple(end[i]-center[i] for i in range(2))
            length = hypot(*direction)
            if length > 1e-8:
                guides.extend(dashed_guide(center,tuple(x/length for x in direction),
                                           6*self.options['size']*scale,scale,self.options['guide_style']))
        key = tuple(guides)
        if key != self._guide_key:
            self.guide_mapper.SetInputData(mesh(guides))
            self._guide_key = key
        self.guide_actor.GetProperty().SetLineWidth(self.options['weight']*scale)
        self.guide_actor.SetVisibility(bool(guides))

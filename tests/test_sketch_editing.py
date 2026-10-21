from dataclasses import replace
from math import cos, sin, radians, hypot
import pytest
from star_cad.document import Document
from star_cad.features import Feature
from star_cad.sketch import Circle, Line, Rectangle, Slot, SketchParameters
from star_cad.tools import ToolController, ToolEvent


def test_atomic_delete_history_dependencies_and_persistence(tmp_path):
    d = Document()
    a, b = d.add_sketch('XY'), d.add_sketch('XZ')
    circle, line = Circle(1, 2, 3), Line(0, 0, 4, 5)
    d.add_entity(a, circle)
    d.add_entity(b, line)
    before = d.features
    count = len(d._undo)
    d.delete(entities=[(a, circle.id), (b, line.id)])
    assert len(d._undo) == count+1
    assert all(not f.parameters.entities for f in d.sketches)
    d.undo()
    assert d.features == before
    d.redo()
    d.save(tmp_path/'deleted.starcad')
    assert Document.load(d.path).features == d.features
    dependent = replace(d.feature(b), references=('plane:XZ', a))
    d.replace_feature(dependent)
    before, undo = d.features, list(d._undo)
    with pytest.raises(ValueError, match='references'):
        d.delete(features=[a])
    assert d.features == before and d._undo == undo
    with pytest.raises(ValueError, match='base box'):
        d.delete(features=[d.features[0].id])
    with pytest.raises(ValueError, match='Unknown'):
        d.delete(entities=[(a, circle.id)])
    d.delete(features=[a, b])
    assert not d.sketches
    d.undo()
    assert d.features == before


def controller(name, shift=False):
    c = ToolController()
    c.set_tool(name)
    c.handle(ToolEvent('press', (3, 4), shift))
    c.handle(ToolEvent('move', (9, 12)))
    return c


def test_exact_circle_and_slot_dimensions():
    r, distance = 0.0201234567890123, 12.3456789012345
    c = controller('circle')
    c.tool.set_dimension('Radius', r)
    circle = c.handle(ToolEvent('release', (9, 12)))
    assert circle.radius == r and (circle.x, circle.y) == (3, 4)
    c = controller('circle', True)
    c.tool.set_dimension('Radius', r)
    assert c.handle(ToolEvent('release', (9, 12))) is None
    assert c.tool.stage == 'center'
    c.tool.set_dimension('Center distance', distance)
    slot = c.handle(ToolEvent('press', (-3, -4)))
    assert slot.radius == r and slot.distance == distance
    assert slot.angle == pytest.approx(-126.86989764584402)


def test_numeric_line_and_both_rectangle_directions():
    c = controller('line')
    c.tool.set_dimension('Length', 5)
    line = c.handle(ToolEvent('press', (9, 12)))
    assert line.points == ((3, 4), (6, 8))
    c = controller('rectangle')
    width, depth = 7.1234567890123, 6.1234567890123
    c.tool.set_dimension('Width', width)
    c.tool.set_dimension('Depth', depth)
    rectangle = c.handle(ToolEvent('release', (-10, -8)))
    assert rectangle.width == width and rectangle.height == depth
    assert rectangle.points[2] == pytest.approx((3, 4))
    c = controller('rectangle', True)
    c.tool.set_dimension('Width', 5)
    c.handle(ToolEvent('press', (9, 12)))
    assert c.tool.b == (6, 8)
    c.handle(ToolEvent('move', (11, 5)))
    c.tool.set_dimension('Depth', depth)
    rectangle = c.handle(ToolEvent('press', (11, 5)))
    assert rectangle.width == 5 and rectangle.height == depth
    assert rectangle.angle == pytest.approx(53.13010235415598)
    assert rectangle.points[-2] == pytest.approx((3, 4))


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf'), 1e-8, 1000001])
def test_invalid_numeric_dimensions_do_not_change_tool(value):
    c = controller('circle')
    with pytest.raises(ValueError, match='Dimension'):
        c.tool.set_dimension('Radius', value)
    assert not c.tool.dimensions
    assert c.tool.stage == 'radius'

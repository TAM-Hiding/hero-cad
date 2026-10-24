from dataclasses import replace
from math import pi
import json
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from hero_cad.document import Document
from hero_cad.sketch import Circle, Line, Slot
from hero_cad.tools import ToolController, ToolEvent


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
@pytest.mark.parametrize('entity', [Circle(-2, 3, 4), Slot(-2, 3, 4, 12, 37)])
def test_analytic_curve_geometry(plane, entity):
    doc = Document()
    identifier = doc.add_sketch(plane)
    doc.add_entity(identifier, entity)
    shape = doc.sketch_shapes[identifier]
    assert BRepCheck_Analyzer(shape).IsValid()
    properties = GProp_GProps()
    BRepGProp.LinearProperties_s(shape, properties)
    distance = entity.distance if isinstance(entity, Slot) else 0
    assert properties.Mass() == pytest.approx(2*pi*entity.radius+2*distance, abs=1e-8)
    if isinstance(entity, Circle):
        edge = TopoDS.Edge_s(TopExp_Explorer(shape, TopAbs_EDGE).Current())
        wire = BRepBuilderAPI_MakeWire(edge).Wire()
    else:
        wire = TopoDS.Wire_s(TopExp_Explorer(shape, TopAbs_WIRE).Current())
    assert wire.Closed()
    face = BRepBuilderAPI_MakeFace(wire).Face()
    assert BRepCheck_Analyzer(face).IsValid()
    BRepGProp.SurfaceProperties_s(face, properties)
    assert properties.Mass() == pytest.approx(pi*entity.radius**2+2*entity.radius*distance, abs=1e-7)


def event(controller, phase, point=(0, 0), shift=False):
    return controller.handle(ToolEvent(phase, point, shift))


def test_circle_slot_tool_latches_radius_and_shift_and_cancels():
    tools = ToolController()
    tools.set_tool('circle')
    event(tools, 'press', (1, 2))
    event(tools, 'move', (4, 6), True)  # Late Shift must not change tool method.
    assert len(tools.preview) > 16
    circle = event(tools, 'release', (4, 6), True)
    assert isinstance(circle, Circle) and circle.radius == 5
    event(tools, 'press', (1, 2), True)
    assert event(tools, 'release', (4, 6)) is None
    assert tools.tool.stage == 'center'
    event(tools, 'move', (7, 10))
    slot = event(tools, 'press', (7, 10))
    assert isinstance(slot, Slot) and slot.radius == 5 and slot.distance == 10
    assert slot.second_center == pytest.approx((7, 10))
    assert tools.tool.stage == 'start'
    event(tools, 'press', shift=True)
    event(tools, 'release')
    assert tools.error and tools.tool.stage == 'slot_radius'
    event(tools, 'cancel')
    assert tools.name == 'select' and tools.preview == ()
    tools.set_tool('circle')
    event(tools, 'press', shift=True)
    event(tools, 'release', (0, 3))
    assert event(tools, 'press') is None
    assert tools.error and tools.tool.stage == 'center'
    event(tools, 'cancel')
    assert not tools.preview


def test_curve_edit_precision_history_and_legacy_v2(tmp_path):
    doc = Document()
    identifier = doc.add_sketch('YZ')
    line = Line(0, 0, 3, 4)
    doc.add_entity(identifier, line)
    path = tmp_path/'curves.starcad'
    doc.save(path)
    legacy = json.loads(path.read_text())
    legacy['version'] = 2
    path.write_text(json.dumps(legacy))
    doc = Document.load(path)
    assert doc.feature(identifier).parameters.entities == (line,)
    circle = Circle(1.234567891234, -2.987654321987, 3.123456789123)
    slot = Slot(11, 12, 1.234567891234, 17.987654321987, 41.123456789123)
    doc.add_entity(identifier, circle)
    doc.add_entity(identifier, slot)
    edited = replace(slot, angle=-32.012345678912, radius=2.123456789123, distance=20.987654321987)
    doc.update_entity(identifier, edited)
    doc.undo()
    assert doc.feature(identifier).parameters.entities[-1] == slot
    doc.redo()
    doc.save(path)
    assert Document.load(path).features == doc.features
    assert json.loads(path.read_text())['version'] == 3


@pytest.mark.parametrize('entity', [lambda: Circle(0,0,0), lambda: Circle(0,0,float('nan')),
                                    lambda: Slot(0,0,2,0), lambda: Slot(0,0,-2,3),
                                    lambda: Circle(999999,0,3)])
def test_invalid_curves(entity):
    with pytest.raises(ValueError):
        entity()

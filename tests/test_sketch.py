from dataclasses import replace
import json
from math import hypot
import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from star_cad.document import Document
from star_cad.features import FeatureError
from star_cad.sketch import Line, Rectangle, PLANES, diagonal_rectangle, edge_rectangle
from star_cad.tools import ToolController, ToolEvent


@pytest.mark.parametrize('plane', PLANES)
def test_plane_local_world_round_trip_and_regeneration(plane):
    frame = PLANES[plane]
    point = (12.3456789123, -9.8765432123)
    assert frame.to_local(frame.to_world(point)) == pytest.approx(point, abs=1e-12)
    assert sum(n*n for n in frame.normal) == 1
    doc = Document()
    identifier = doc.add_sketch(plane)
    doc.add_entity(identifier, Line(0, 0, *point))
    doc.add_entity(identifier, Rectangle(3, 4, 12.25, 2.75, 31.123))
    assert BRepCheck_Analyzer(doc.sketch_shapes[identifier]).IsValid()
    assert doc.statuses[identifier].valid


def test_order_ids_dependencies_and_failed_edit_are_transactional():
    doc = Document()
    a, b = doc.add_sketch('XY'), doc.add_sketch('XZ')
    first, second, third = doc.features
    assert len({f.id for f in doc.features}) == 3
    doc.replace_feature(replace(third, references=third.references+(a,)))
    assert [f.id for f in doc.features] == [first.id, a, b]
    previous, shape, undo = doc.features, doc.shape, tuple(doc._undo)
    with pytest.raises(FeatureError, match='forward'):
        doc.replace_feature(replace(second, references=second.references+(b,)))
    assert doc.features == previous and doc.shape is shape and tuple(doc._undo) == undo
    assert not doc.last_failure.status.valid and doc.last_failure.feature_id == a
    with pytest.raises(FeatureError, match='Duplicate'):
        doc.set_features(previous+(second,))
    with pytest.raises(FeatureError, match='origin plane'):
        doc.replace_feature(replace(second, references=()))


def test_sketch_edit_undo_precision_and_persistence(tmp_path):
    doc = Document()
    identifier = doc.add_sketch('YZ')
    line = Line(-1.123456789123, 2.987654321987, 22.012345678912, -31.987654321987)
    rectangle = Rectangle(3, 7, 12.3456789, 23.456789, 32.3456789)
    doc.add_entity(identifier, line)
    doc.add_entity(identifier, rectangle)
    before = doc.features
    doc.update_entity(identifier, replace(rectangle, width=25, height=9))
    assert doc.feature(identifier).parameters.entities[1].id == rectangle.id
    doc.undo()
    assert doc.features == before
    doc.redo()
    path = tmp_path/'sketch.starcad'
    doc.save(path)
    assert not doc.dirty
    loaded = Document.load(path)
    assert loaded.features == doc.features
    assert loaded.feature(identifier).parameters.entities[0] == line
    assert BRepCheck_Analyzer(loaded.sketch_shapes[identifier]).IsValid()
    assert not loaded.can_undo
    data = json.loads(path.read_text())
    assert data['version'] == 3
    data['features'][1]['parameters']['frame']['origin'][0] = 123
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='frame'):
        Document.load(path)


def test_legacy_box_file_migrates(tmp_path):
    path = tmp_path/'v1.starcad'
    path.write_text(json.dumps({'format':'star-cad','version':1,'units':'mm',
                               'box':{'width':12.3456789,'height':42,'depth':31}}))
    doc = Document.load(path)
    assert doc.parameters.width == 12.3456789 and not doc.dirty
    identifier = doc.features[0].id
    doc.save(path)
    assert Document.load(path).features[0].id == identifier
    assert json.loads(path.read_text())['version'] == 3


@pytest.mark.parametrize('depth', [8.5, -8.5])
def test_rotated_edge_rectangle_is_perpendicular_and_editable(depth):
    a, b = (3, 4), (6, 8)
    rectangle = edge_rectangle(a, b, (a[0]-0.8*depth, a[1]+0.6*depth))
    assert rectangle.width == pytest.approx(5)
    assert rectangle.height == pytest.approx(abs(depth))
    points = rectangle.points
    u = tuple(points[1][i]-points[0][i] for i in range(2))
    v = tuple(points[3][i]-points[0][i] for i in range(2))
    assert sum(u[i]*v[i] for i in range(2)) == pytest.approx(0, abs=1e-12)
    edited = replace(rectangle, width=11, height=12)
    assert hypot(*(edited.points[1][i]-edited.points[0][i] for i in range(2))) == pytest.approx(11)
    assert edited.id == rectangle.id


def send(controller, phase, point=(0, 0), shift=False):
    return controller.handle(ToolEvent(phase, point, shift))


def test_tools_line_and_diagonal_rectangle_preview_and_cancel():
    tools = ToolController()
    tools.set_tool('line')
    send(tools, 'press', (1, 2), shift=True)
    send(tools, 'move', (5, 9))
    assert tools.preview == ((1, 2), (5, 9))
    result = send(tools, 'press', (5, 9))
    assert type(result) is Line and result.points == ((1, 2), (5, 9))
    assert tools.tool.stage == 'start'
    tools.set_tool('rectangle')
    send(tools, 'press', (8, 9))
    send(tools, 'move', (2, 3))
    assert len(tools.preview) == 5
    rectangle = send(tools, 'release', (2, 3))
    assert (rectangle.x, rectangle.y, rectangle.width, rectangle.height) == (2, 3, 6, 6)
    send(tools, 'press', (0, 0), shift=True)
    send(tools, 'cancel')
    assert tools.name == 'select' and not tools.preview


def test_edge_first_tool_latches_shift_and_rejects_degenerate_geometry():
    tools = ToolController()
    tools.set_tool('rectangle')
    send(tools, 'press', (0, 0), shift=True)
    send(tools, 'release', (0, 0))
    assert tools.tool.stage == 'edge'
    assert send(tools, 'press', (0, 0)) is None
    assert tools.error and tools.tool.stage == 'edge'
    send(tools, 'press', (3, 4))  # Shift no longer held.
    assert tools.tool.stage == 'depth'
    send(tools, 'move', (-5, 9))
    assert len(tools.preview) == 5
    result = send(tools, 'press', (-5, 9))
    assert type(result) is Rectangle and tools.tool.stage == 'start'
    expected = edge_rectangle((0, 0), (3, 4), (-5, 9))
    assert result.points == expected.points


@pytest.mark.parametrize('factory', [lambda: Line(0,0,0,0), lambda: Rectangle(0,0,0,5),
                                      lambda: Rectangle(0,0,5,-1), lambda: Line(float('nan'),0,1,2)])
def test_invalid_entities_rejected(factory):
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize('plane', PLANES)
def test_kernel_sketch_lengths_and_bounds(plane):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    doc = Document()
    identifier = doc.add_sketch(plane)
    doc.add_entity(identifier, Line(0, 0, 3, 4))
    rectangle = Rectangle(1, 2, 12, 7, 37)
    doc.add_entity(identifier, rectangle)
    shape = doc.sketch_shapes[identifier]
    properties = GProp_GProps()
    BRepGProp.LinearProperties_s(shape, properties)
    assert properties.Mass() == pytest.approx(5 + 2*(12+7), abs=1e-9)
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    points = [PLANES[plane].to_world(p) for p in ((0, 0), (3, 4), *rectangle.points)]
    assert box.Get() == pytest.approx(tuple(min(p[i] for p in points) for i in range(3)) +
                                    tuple(max(p[i] for p in points) for i in range(3)), abs=1e-6)


def test_save_size_limit_preserves_previous_file_and_savepoint(tmp_path, monkeypatch):
    import star_cad.document as module
    doc = Document()
    path = tmp_path/'keep.starcad'
    doc.save(path)
    before = path.read_bytes()
    doc.add_sketch('XY')
    monkeypatch.setattr(module, 'serialize', lambda _: {'oversize': 'x'*(4*1024*1024)})
    with pytest.raises(ValueError, match='4 MiB'):
        doc.save(path)
    assert path.read_bytes() == before and doc.dirty

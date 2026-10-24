"""Real kernel regression models for repeated and Boolean face attachments."""
from dataclasses import replace
import json
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE
from hero_cad.attachments import AttachmentError, reference_key
from hero_cad.document import Document
from hero_cad.face_history import evaluated_faces, primitive_lineage
from hero_cad.ui.display_geometry import subshapes
from hero_cad.features import BoxParameters
from hero_cad.geometry import volume
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, Slot, FaceReference
from test_face_attachments import coincident


def center(face):
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.CentreOfMass().Coord()


def screwdriver(*, plane='XY', separate_tool=False, slot=False):
    d = Document()
    source = d.add_sketch(plane)
    circle = Circle(0, 0, 10)
    d.add_entity(source, circle)
    body = d.add_extrusion(source, circle.id, distance=10)
    sid = d.add_face_sketch(FaceReference(body, 'end'))
    rectangle = Slot(-15, 0, 2, 30) if slot else Rectangle(-15, -2, 30, 4)
    d.add_entity(sid, rectangle)
    tool = d.add_extrusion(sid, rectangle.id, distance=-3,
                          operation='new' if separate_tool else 'cut',
                          target_id=None if separate_tool else body)
    result = d.add_boolean('cut', body, (tool,)) if separate_tool else tool
    return d, source, circle, body, sid, rectangle, result


def slot_regions(d, result, source):
    frame = d.feature(source).parameters.frame
    faces = [face for face in subshapes(d.solid_shapes[result], TopAbs_FACE)
             if BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane]
    top = [face for face in faces if abs(sum((center(face)[i]-frame.origin[i])*frame.normal[i] for i in range(3))-10) < 1e-7]
    floor = [face for face in faces
             if abs(sum((center(face)[i]-frame.origin[i])*frame.normal[i] for i in range(3))-7) < 1e-7]
    assert len(top) == 2 and len(floor) == 1
    return (*sorted(top, key=lambda face: frame.to_local(center(face))[1]), floor[0])


@pytest.mark.parametrize('plane', ['XY', 'XZ', 'YZ'])
@pytest.mark.parametrize('separate_tool', [False, True])
@pytest.mark.parametrize('slot', [False, True])
def test_split_cylinder_regions_independent_repeated_sketches_history_and_reload(plane, separate_tool, slot, tmp_path):
    d, source, circle, body, cutter_sketch, rectangle, result = screwdriver(plane=plane, separate_tool=separate_tool, slot=slot)
    faces = slot_regions(d, result, source)
    refs = [d.face_reference(face) for face in faces]
    assert len(set(refs)) == 3 and all(ref.parent_id == result for ref in refs)
    assert all(ref.face == 'evaluated' for ref in refs)
    ids = []
    for face, ref in zip(faces, refs):
        for _ in range(2):
            sid = d.add_face_sketch(ref)
            d.add_entity(sid, Circle(1, 2, .3))
            coincident(d.feature(sid).parameters.frame, face)
            ids.append(sid)
    assert len(set(ids)) == 6
    saved = {sid: d.feature(sid).parameters for sid in ids}
    # Ordinary size/depth edits retain ancestry, distinct split regions and IDs.
    d.update_entity(source, replace(circle, radius=12))
    cutter = d.feature(result if not separate_tool else d.feature(result).parameters.tool_ids[0])
    d.replace_feature(replace(cutter, parameters=replace(cutter.parameters, distance=-4)))
    for sid in ids:
        p = d.feature(sid).parameters
        assert d.statuses[sid].valid and p.entities == saved[sid].entities
        coincident(p.frame, d.face_maps[result][reference_key(p.attachment)])
    assert d.feature(ids[-1]).parameters.frame.origin != saved[ids[-1]].frame.origin
    before = d.features
    d.undo()
    assert d.feature(ids[-1]).parameters.frame == saved[ids[-1]].frame
    d.redo()
    assert d.features == before
    d.save(tmp_path / 'split.starcad')
    payload = json.loads(d.path.read_text())
    assert payload['version'] == 7 and payload['format'] == 'star-cad'
    loaded = Document.load(d.path)
    assert loaded.features == d.features and all(s.valid for s in loaded.statuses.values())
    assert volume(loaded.shape) == pytest.approx(volume(d.shape))
    assert loaded.face_reference(loaded.face_maps[result][reference_key(refs[0])]) == refs[0]


def test_two_successive_plate_holes_attach_to_current_result_and_edit_independently(tmp_path):
    d = Document(BoxParameters(50, 25, 10))
    body = d.features[0].id
    sketches, cuts = [], []
    for x in (10, 35):
        top = next(face for face in d.face_maps[body].values() if abs(center(face)[2]-10) < 1e-7)
        ref = d.face_reference(top)
        assert ref.parent_id == body
        sid = d.add_face_sketch(ref)
        frame = d.feature(sid).parameters.frame
        hole = Circle(*frame.to_local((x, 12, 10)), 2)
        d.add_entity(sid, hole)
        body = d.add_extrusion(sid, hole.id, operation='cut', target_id=body,
                               extent='through_all', direction=-1)
        sketches.append((sid, hole))
        cuts.append(body)
    assert volume(d.solid_shapes[body]) == pytest.approx(50*25*10-2*40*3.141592653589793)
    first, second = (d.feature(sid).parameters for sid, _ in sketches)
    assert first.attachment.parent_id == d.features[0].id
    assert second.attachment.parent_id == cuts[0]
    assert first.attachment != second.attachment
    for sid, hole in sketches:
        d.update_entity(sid, replace(hole, radius=2.5))
        assert d.statuses[body].valid
    before = d.features
    d.undo(); d.redo()
    assert d.features == before
    d.save(tmp_path / 'two-holes.starcad')
    assert Document.load(d.path).features == d.features
    # Old parents stay available to their historical sketches but cannot be
    # mistaken for a new selection on the currently displayed body.
    with pytest.raises(AttachmentError, match='reliable'):
        d.face_reference(d.face_maps[d.features[0].id]['+Z'])


@pytest.mark.parametrize('operation', ['cut', 'join', 'intersect'])
@pytest.mark.parametrize('separate_tool', [False, True])
def test_every_planar_face_of_supported_boolean_models_accepts_sketch(operation, separate_tool, tmp_path):
    d = Document(BoxParameters(10, 10, 10))
    box = d.features[0].id
    sid = d.add_sketch('XY')
    rect = Rectangle(5, -2, 10, 14)
    d.add_entity(sid, rect)
    tool = d.add_extrusion(sid, rect.id, distance=7,
                          operation='new' if separate_tool else operation,
                          target_id=None if separate_tool else box)
    result = d.add_boolean(operation, box, (tool,)) if separate_tool else tool
    faces = subshapes(d.solid_shapes[result], TopAbs_FACE)
    assert len(d.face_maps[result]) == len(faces)
    refs = [d.face_reference(face) for face in faces]
    for ref in refs:
        sid = d.add_face_sketch(ref)
        coincident(d.feature(sid).parameters.frame, d.face_maps[result][reference_key(ref)])
    d.set_box(BoxParameters(11, 11, 11))
    assert all(s.valid for s in d.statuses.values())
    d.save(tmp_path / f'{operation}.starcad')
    assert Document.load(d.path).features == d.features


def test_topology_change_unresolves_without_substitution_blocks_downstream_and_undo_recovers(tmp_path):
    d, source, circle, body, cutter_sketch, rectangle, result = screwdriver()
    ref = d.face_reference(slot_regions(d, result, source)[0])
    sid = d.add_face_sketch(ref)
    c = Circle(0, -5, .5)
    d.add_entity(sid, c)
    downstream = d.add_extrusion(sid, c.id, distance=1)
    old = d.feature(sid).parameters
    # A short pocket no longer divides the top into two regions.
    d.update_entity(cutter_sketch, replace(rectangle, x=-4, width=8))
    assert not d.statuses[sid].valid and 'Unresolved face' in d.statuses[sid].error
    assert d.feature(sid).parameters == old and sid not in d.sketch_shapes
    assert not d.statuses[downstream].valid and downstream not in d.solid_shapes
    d.save(tmp_path / 'lost.starcad')
    loaded = Document.load(d.path)
    assert not loaded.statuses[sid].valid and loaded.feature(sid).parameters == old
    d.undo()
    assert d.statuses[sid].valid and d.statuses[downstream].valid
    d.redo()
    assert not d.statuses[sid].valid


def test_identity_does_not_use_face_order_or_geometric_nearest_match(monkeypatch):
    d, source, circle, body, cutter_sketch, rectangle, result = screwdriver()
    # Rebuild the derived adjacency map with reversed traversal order.
    mapping = d.face_maps[body]
    lineage = primitive_lineage(body, mapping)
    a, b = evaluated_faces(lineage), evaluated_faces(tuple(reversed(lineage)))
    assert set(a) == set(b) and all(a[key].IsSame(b[key]) for key in a)
    import hero_cad.document as module
    monkeypatch.setattr(module, 'evaluated_faces', lambda rows: evaluated_faces(tuple(reversed(rows))))
    other = Document(features=d.features)
    assert set(other.face_maps[result]) == set(d.face_maps[result])
    # Identical source/neighbor signatures must never receive ordinal suffixes.
    face = d.face_maps[body][('start', None, None)]
    other_face = d.face_maps[body][('end', None, None)]
    assert evaluated_faces(((face, frozenset(('same',))), (other_face, frozenset(('same',))))) == {}
    ref = d.face_reference(slot_regions(d, result, source)[0])
    sid = d.add_face_sketch(ref)
    payload = serialize(d.features)
    payload['version'] = 6
    with pytest.raises(ValueError, match='version 7'):
        deserialize(payload)
    with pytest.raises(ValueError, match='identity'):
        FaceReference(result, 'evaluated', segment='face-index-1')


def test_compound_angle_boolean_face_attachment_follows_parent(monkeypatch, tmp_path):
    from test_face_attachments import compound_fixture
    d = compound_fixture(monkeypatch)
    box = d.features[0].id
    sid = d.add_face_sketch(FaceReference(box, '+Z'))
    top_center = center(d.face_maps[box]['+Z'])
    hole = Circle(*d.feature(sid).parameters.frame.to_local(top_center), 2)
    d.add_entity(sid, hole)
    result = d.add_extrusion(sid, hole.id, distance=-5, operation='cut', target_id=box)
    floor = next(face for face in d.face_maps[result].values()
                 if abs(sum((center(face)[i]-top_center[i])*d.feature(sid).parameters.frame.normal[i]
                            for i in range(3))+5) < 1e-7)
    ref = d.face_reference(floor)
    attached = d.add_face_sketch(ref)
    c = Circle(1, 2, .1)
    d.add_entity(attached, c)
    d.set_box(BoxParameters(50, 35, 30))
    assert d.statuses[attached].valid
    p = d.feature(attached).parameters
    assert p.entities == (c,) and all(abs(n) > .1 for n in p.frame.normal)
    coincident(p.frame, d.face_maps[result][reference_key(ref)])
    d.save(tmp_path / 'angled-boolean.starcad')
    assert Document.load(d.path).features == d.features

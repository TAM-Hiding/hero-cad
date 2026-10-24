import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from hero_cad.document import BoxParameters, Document
from hero_cad.geometry import volume


def test_box_regenerates_exact_solid():
    document = Document()
    old_shape = document.shape
    document.set_box(BoxParameters(12.345, 23.456, 34.567))
    assert not document.shape.IsSame(old_shape)
    assert BRepCheck_Analyzer(document.shape).IsValid()
    assert volume(document.shape) == pytest.approx(12.345 * 23.456 * 34.567, rel=1e-12)
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(document.shape, bounds, False, False)
    assert bounds.Get() == pytest.approx((0, 0, 0, 12.345, 23.456, 34.567), abs=1e-7)


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf'), 0.0001, 100001])
def test_reject_invalid_dimensions(value):
    with pytest.raises(ValueError):
        BoxParameters(width=value)


def test_failed_regeneration_keeps_document(monkeypatch):
    import hero_cad.document as module
    document = Document()
    previous = document.parameters, document.shape
    def fail(**kwargs):
        raise ValueError('kernel failure')
    monkeypatch.setattr(module, 'make_box', fail)
    with pytest.raises(ValueError):
        document.set_box(BoxParameters(width=15))
    assert (document.parameters, document.shape) == previous


def test_history_savepoint_and_branch(tmp_path):
    document = Document()
    original = document.parameters
    edited = BoxParameters(width=12.345)
    document.set_box(edited)
    assert document.dirty and document.can_undo
    document.save(tmp_path / 'part.starcad')
    assert not document.dirty
    document.undo()
    assert document.parameters == original and document.dirty and document.can_redo
    document.redo()
    assert document.parameters == edited and not document.dirty
    document.undo()
    document.set_box(BoxParameters(height=15))
    assert not document.can_redo
    document.undo()
    document.set_box(original)  # no-op must preserve the redo branch
    assert document.can_redo


def test_file_round_trip_rebuilds_geometry(tmp_path):
    document = Document()
    document.set_box(BoxParameters(12.3456789, 23.456, 34.567))
    path = tmp_path / 'part.starcad'
    document.save(path)
    loaded = Document.load(path)
    assert loaded.parameters == document.parameters
    assert loaded.path == path and not loaded.dirty
    assert not loaded.can_undo and not loaded.can_redo
    assert BRepCheck_Analyzer(loaded.shape).IsValid()
    assert volume(loaded.shape) == pytest.approx(volume(document.shape), rel=1e-12)


@pytest.mark.parametrize('contents', [
    'null', '{', '{"format":"star-cad","format":"star-cad"}',
    '{"format":"star-cad","version":2,"units":"mm","box":{}}',
    '{"format":"star-cad","version":true,"units":"mm","box":{}}',
    '{"format":"star-cad","version":1,"units":"in","box":{}}',
    '{"format":"star-cad","version":1,"units":"mm","box":{"width":NaN,"depth":2,"height":3}}',
    '{"format":"star-cad","version":1,"units":"mm","box":{"width":true,"depth":2,"height":3}}',
    '{"format":"star-cad","version":1,"units":"mm","box":{"width":"3","depth":2,"height":3}}',
    ' ' * 65537,
])
def test_invalid_files_rejected(tmp_path, contents):
    path = tmp_path / 'bad.starcad'
    path.write_text(contents)
    with pytest.raises(ValueError):
        Document.load(path)


def test_failed_save_preserves_file_path_and_dirty_state(tmp_path, monkeypatch):
    import hero_cad.document as module
    document = Document()
    path = tmp_path / 'part.starcad'
    document.save(path)
    original = path.read_bytes()
    document.set_box(BoxParameters(width=50))
    def fail(*args):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError):
        document.save(path)
    assert path.read_bytes() == original
    assert document.path == path and document.dirty
    assert list(tmp_path.iterdir()) == [path]
    with pytest.raises(OSError):
        document.save(tmp_path / 'another.starcad')
    assert document.path == path and document.dirty


def test_failed_undo_preserves_history(monkeypatch):
    import hero_cad.document as module
    document = Document()
    document.set_box(BoxParameters(width=50))
    shape = document.shape
    def fail(**kwargs):
        raise ValueError('kernel failure')
    monkeypatch.setattr(module, 'make_box', fail)
    with pytest.raises(ValueError):
        document.undo()
    assert document.parameters.width == 50
    assert document.shape is shape and document.can_undo and not document.can_redo


def test_failed_flush_does_not_replace_existing_file(tmp_path, monkeypatch):
    import hero_cad.document as module
    document = Document()
    path = tmp_path / 'part.starcad'
    document.save(path)
    original = path.read_bytes()
    document.set_box(BoxParameters(depth=35))
    def fail(*args):
        raise OSError('simulated flush failure')
    monkeypatch.setattr(module.os, 'fsync', fail)
    with pytest.raises(OSError):
        document.save(path)
    assert path.read_bytes() == original and document.dirty
    assert list(tmp_path.iterdir()) == [path]

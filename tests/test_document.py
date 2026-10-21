import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from star_cad.document import BoxParameters, Document
from star_cad.geometry import volume


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
    import star_cad.document as module
    document = Document()
    previous = document.parameters, document.shape
    def fail(**kwargs):
        raise ValueError('kernel failure')
    monkeypatch.setattr(module, 'make_box', fail)
    with pytest.raises(ValueError):
        document.set_box(BoxParameters(width=15))
    assert (document.parameters, document.shape) == previous

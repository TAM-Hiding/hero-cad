import json
import numpy as np
import pytest
from PySide6.QtCore import QSettings, Qt
from hero_cad.preferences import Preferences
from hero_cad.persistence import serialize
from hero_cad.snap_appearance import DEFAULTS, PREFIX
from test_sketch_ui import window
from test_model_references_ui import attached, move_to
from test_sketch_visibility import capture


def midpoint(w):
    w.viewport.fit()
    w.tool_choice.setCurrentText('Line')
    move_to(w,(20,30))
    assert w.viewport.sketch.snap_result.target == 'MODEL MIDPOINT'
    return w.viewport.sketch


def test_size_color_zoom_highlight_and_acquisition_are_independent(qtbot,monkeypatch):
    w = window(qtbot)
    attached(w)
    v = w.viewport
    w.axes_action.setChecked(False)
    s = midpoint(w)
    before = serialize(w.document.features),tuple(w.document._undo),w.document.shape
    def forbidden(*args,**kwargs):
        raise AssertionError('Appearance/hover must not regenerate geometry')
    monkeypatch.setattr(w.document,'_regenerate',forbidden)
    w.preference_store.set_many({PREFIX+'color':'Green',PREFIX+'size':20,PREFIX+'weight':2.,PREFIX+'highlight':False})
    assert not s.reference_actor.GetVisibility()
    widths = []
    for zoom in (20,40,80):
        v.renderer.GetActiveCamera().SetParallelScale(zoom)
        v.GetRenderWindow().Render()
        move_to(w,(20,30))
        assert s.snap_result.point == (20,30)
        bounds = s.snap_mapper.GetInput().GetBounds()
        widths.append(bounds[1]-bounds[0])
        pixels = capture(v)
        green = (pixels[...,1]>230) & (pixels[...,0]<90) & (pixels[...,2]<130)
        assert np.count_nonzero(green) > 25
    assert widths == pytest.approx([20,20,20])
    assert s.snap_actor.GetProperty().GetLineWidth() == 2.
    w.preference_store.set(PREFIX+'midpoint','Centerline (C/L)')
    assert s.snap_mapper.GetInput().GetNumberOfLines() == 2
    w.preference_store.set(PREFIX+'highlight',True)
    assert s.reference_actor.GetVisibility()
    assert (serialize(w.document.features),tuple(w.document._undo),w.document.shape) == before
    s.set_tool('select')
    assert not s.snap_actor.GetVisibility() and not s.reference_actor.GetVisibility()


def test_midpoint_guide_is_perpendicular_and_clears(qtbot):
    w = window(qtbot)
    attached(w)
    s = midpoint(w)
    w.preference_store.set_many({PREFIX+'centerline':True,PREFIX+'guide_color':'Red'})
    guide = s.indicators.guide_actor
    assert guide.GetVisibility()
    assert guide.GetProperty().GetColor() == (1.,.2,.2)
    points = s.indicators.guide_mapper.GetInput()
    # Acquired top edge runs along U. Its local perpendicular is V, which
    # projects vertically in the normal view. The guide consists of dashes.
    assert points.GetNumberOfLines() > 3
    assert points.GetBounds()[0] == pytest.approx(points.GetBounds()[1])
    w.tool_choice.setCurrentText('Circle')
    assert not guide.GetVisibility()
    w.tool_choice.setCurrentText('Line')
    move_to(w,(20,30))
    assert guide.GetVisibility()
    move_to(w,(18,12))
    assert not guide.GetVisibility()
    move_to(w,(20,30))
    w.finish_sketch()
    assert not guide.GetVisibility()


def test_preferences_and_palette_export_import_preserve_old_files(qtbot,tmp_path):
    w = window(qtbot)
    attached(w)
    s = midpoint(w)
    w.preferences_action.trigger()
    controls = w.preferences_dialog.controls
    controls[PREFIX+'midpoint'].setCurrentText('Centerline (C/L)')
    controls[PREFIX+'size'].setValue(24)
    controls[PREFIX+'weight'].setValue(2.5)
    controls[PREFIX+'color'].setCurrentText('Red')
    w.palette_controller.set_color('snap.midpoint','#00FF00')
    controls[PREFIX+'color'].setCurrentText('Palette')
    assert s.snap_actor.GetProperty().GetColor() == (0.,1.,0.)
    path = tmp_path/'appearance.json'
    w.palette_controller.export_file(path)
    data = json.loads(path.read_text())
    assert data['snap_indicators']['size'] == 24
    w.preference_store.set(PREFIX+'size',12)
    w.palette_controller.import_file(path)
    assert w.preference_store.get(PREFIX+'size') == 24
    fresh = Preferences(QSettings(w.preferences.fileName(),QSettings.IniFormat))
    assert fresh.get(PREFIX+'weight') == 2.5
    del data['snap_indicators']
    path.write_text(json.dumps(data))
    w.preference_store.set(PREFIX+'size',28)
    w.palette_controller.import_file(path)
    assert w.preference_store.get(PREFIX+'size') == 28
    data['snap_indicators'] = {'size':-1}
    path.write_text(json.dumps(data))
    before = dict(w.preference_store.values)
    with pytest.raises(ValueError):
        w.palette_controller.import_file(path)
    assert w.preference_store.values == before

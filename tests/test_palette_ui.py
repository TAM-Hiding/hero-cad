"""Appearance changes must remain outside document/display-geometry transactions."""
from dataclasses import replace
import json
import os
import subprocess
import sys
from time import perf_counter
import pytest
import numpy as np
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QDialog
from hero_cad.palette import COLORS, PREFIX, ENABLED, rgb, decode_palette, encode_palette
from hero_cad.preferences import Preferences
from hero_cad.persistence import serialize
from hero_cad.document import Document
from hero_cad.sketch import Circle
from hero_cad.geometry import volume
from hero_cad.ui.main_window import MainWindow
from hero_cad.ui.palette_controller import contrast
from test_sketch_ui import window, enter, click
from test_sketch_visibility import capture


def model_state(w):
    d, v = w.document, w.viewport
    return (d.features, d.shape, tuple(d._undo), tuple(d._redo), d.path, d.dirty,
            serialize(d.features), v.mapper, v.mapper.GetInput(), v.edge_mapper,
            tuple(v.faces), tuple(v.edges), v.profiles.selections, v.profiles.mapper.GetInput(),
            v.sketch.active_id, v.sketch.controller.tool, v.sketch.mapper.GetInput())


def forbid(*args, **kw):
    raise AssertionError('Appearance must not evaluate geometry or prepare display meshes')


def test_default_editor_live_panels_controls_presets_and_reset(qtbot):
    w = window(qtbot)
    c = w.palette_controller
    original = {widget:widget.styleSheet() for widget in c.base_styles}
    assert not c.overrides() and not w.styleSheet()
    assert w.viewport.actor.GetProperty().GetColor() == (.65,.79,.86)
    w.palette_action.trigger()
    editor = w.palette_editor
    assert editor.isVisible() and not editor.isModal() and editor.windowModality() == Qt.NonModal
    assert set(editor.fields) == set(COLORS)
    # Live edits through the actual hex field (full valid values only).
    field = editor.fields['properties.background']
    editor.tabs.setCurrentIndex(0)
    field.setFocus(); field.selectAll(); qtbot.keyClicks(field, '#253640')
    assert c.colors()['properties.background'] == '#253640'
    assert '#253640' in w.styleSheet()
    c.set_color('tools.background','#223344')
    assert '#223344' in w.tool_island.styleSheet()
    for key in ('controls.normal','controls.active','controls.hover','controls.disabled',
                'controls.text','controls.active_text','controls.input','controls.input_text','controls.input_border'):
        c.set_color(key, '#123456')
    assert ':focus' in w.tool_island.styleSheet() and ':disabled' in w.tool_island.styleSheet()
    assert 'background-color:#123456' in w.operation_panel.styleSheet()
    assert contrast('#FFFFFF','#123456') >= 4.5
    customized = c.colors()
    editor.preset.setCurrentIndex(0)
    assert c.overrides() == {} and all(widget.styleSheet() == text for widget,text in original.items())
    editor.preset.setCurrentIndex(1)
    assert c.colors() == customized
    c.reset(('tools.background',))
    assert 'tools.background' not in c.overrides() and 'properties.background' in c.overrides()
    editor.tabs.setCurrentIndex(1); editor.reset_category()
    assert not any(k.startswith('controls.') for k in c.overrides())
    assert 'properties.background' in c.overrides()
    c.reset()
    assert not c.overrides() and all(widget.styleSheet() == text for widget,text in original.items())


def test_sketch_profile_grid_and_construction_recolor_without_any_geometry_or_selection_change(qtbot, monkeypatch):
    w = window(qtbot); sid = enter(w)
    w.tool_island.set_collapsed(True)
    w.document.add_entity(sid,Circle(10,10,3)); w.refresh()
    v, c = w.viewport, w.palette_controller
    w.profile_action.setChecked(True)
    frame = w.document.feature(sid).parameters.frame
    click(qtbot,v,frame,(10,10))
    assert v.profiles.selection
    state = model_state(w)
    grid = (v.sketch.guides.grid_mapper.GetInput(),v.sketch.guides.minor_mapper.GetInput())
    monkeypatch.setattr(Document,'_regenerate',forbid)
    monkeypatch.setattr(v,'prepare_shape',forbid)
    monkeypatch.setattr(w,'refresh',forbid)
    for key, color in (('sketch.normal','#71D4A2'),('sketch.active','#71D4A2'),
                       ('sketch.profile','#E9C889'),('sketch.selected','#FFE6A1'),
                       ('grid.major','#817161'),('grid.minor','#554433'),('grid.labels','#DDCCBB'),
                       ('sketch.preview','#BBDD77'),('sketch.support','#DDCC99')):
        c.set_color(key,color)
    assert model_state(w) == state
    assert (v.sketch.guides.grid_mapper.GetInput(),v.sketch.guides.minor_mapper.GetInput()) == grid
    assert v.sketch.actor.GetProperty().GetColor() == rgb('#71D4A2')
    assert v.sketch.foreground_actor.GetProperty().GetColor() == rgb('#71D4A2')
    assert v.profiles.actor.GetProperty().GetColor() == rgb('#E9C889')
    assert v.profiles.actor.GetVisibility() and v.profiles.actor.GetProperty().GetOpacity() == .6
    pixels = capture(v)
    assert np.count_nonzero((pixels[...,0] > pixels[...,2]+30) & (pixels[...,1] > pixels[...,2]+20)) > 100


@pytest.mark.parametrize('mode', ['Off','Orange','Celadon'])
def test_viewport_shading_xray_opacity_lighting_and_cached_buffers(qtbot,monkeypatch,mode):
    w = window(qtbot); v,c = w.viewport,w.palette_controller
    v.set_xray_mode(mode)
    before = model_state(w)
    prop = v.actor.GetProperty()
    lighting = (prop.GetLighting(),prop.GetAmbient(),prop.GetDiffuse(),prop.GetSpecular(),prop.GetInterpolation())
    opacity = prop.GetOpacity()
    monkeypatch.setattr(Document,'_regenerate',forbid)
    monkeypatch.setattr(v,'prepare_shape',forbid)
    monkeypatch.setattr(w,'refresh',forbid)
    c.set_color('viewport.model','#A6C9DB')
    c.set_color('viewport.background','#16212B')
    key = {'Off':'viewport.model','Orange':'xray.orange','Celadon':'xray.celadon'}[mode]
    c.set_color(key,'#71C9BD')
    c.set_color('viewport.edges','#283940')
    c.set_color('viewport.contrast_edges','#102030')
    assert prop.GetColor() == rgb('#71C9BD')
    assert v.renderer.GetBackground() == rgb('#16212B')
    assert lighting == (prop.GetLighting(),prop.GetAmbient(),prop.GetDiffuse(),prop.GetSpecular(),prop.GetInterpolation())
    assert prop.GetLighting() and prop.GetOpacity() == opacity
    assert model_state(w) == before
    pixels = capture(v)
    assert np.count_nonzero((pixels[...,1] > pixels[...,0]+20) & (pixels[...,1] > 80)) > 100


def test_roundtrip_atomic_bad_imports_and_default_inheritance(qtbot,tmp_path):
    w = window(qtbot); c = w.palette_controller
    original_styles = dict(c.base_styles)
    path = tmp_path/'palette.json'
    c.export_file(path)
    default_data = json.loads(path.read_text())
    assert default_data['overrides'] == [] and set(default_data['colors']) == set(COLORS)
    c.set_color('tools.background','#213541'); c.set_color('sketch.active','#71D4A2')
    colors = c.colors(); overrides = c.overrides()
    c.export_file(path)
    data = json.loads(path.read_text())
    assert data['format'] == 'hero-ui-palette' and data['version'] == 1
    c.reset(); c.import_file(path)
    assert c.colors() == colors and c.overrides() == overrides
    # Importing original defaults does not flatten native/scoped styles.
    path.write_text(json.dumps(default_data)); c.import_file(path)
    assert not c.overrides() and all(widget.styleSheet() == text for widget,text in original_styles.items())
    c.set_color('viewport.background','#223344')
    accepted = c.colors(), dict(c.store.values), model_state(w)
    mutations = [lambda d:d.update(version=True), lambda d:d.update(version=2),
                 lambda d:d.update(unexpected=True), lambda d:d['colors'].update(unknown='#123456'),
                 lambda d:d['colors'].pop('sketch.normal'),
                 lambda d:d['colors'].update({'sketch.normal':'#12345Z'}),
                 lambda d:d['colors'].update({'sketch.normal':'#11223344'}),
                 lambda d:d.update(overrides=['unknown'])]
    for mutate in mutations:
        invalid = json.loads(json.dumps(data)); mutate(invalid); path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError): c.import_file(path)
        assert (c.colors(),dict(c.store.values),model_state(w)) == accepted
    for text in ('{', '[]', path.read_text().replace('"version": 1','"version": 1, "version": 1'), ' '*65537):
        path.write_text(text)
        with pytest.raises(ValueError): c.import_file(path)
        assert (c.colors(),dict(c.store.values),model_state(w)) == accepted


def test_saved_preferences_fresh_process_and_new_window(qtbot,tmp_path):
    path = tmp_path/'settings.ini'
    w = MainWindow(settings=QSettings(str(path),QSettings.IniFormat)); qtbot.addWidget(w)
    w.show(); qtbot.waitExposed(w)
    w.palette_controller.set_color('sketch.active','#71D4A2')
    w.palette_controller.set_color('properties.background','#242424')
    w.preference_store.set('viewport/v1/sketch_opacity',23)
    w.close()
    script = '''import json,sys
from PySide6.QtCore import QSettings
from hero_cad.preferences import Preferences
p=Preferences(QSettings(sys.argv[1],QSettings.IniFormat))
print(json.dumps(p.values))'''
    fresh = json.loads(subprocess.run([sys.executable,'-c',script,str(path)],check=True,text=True,capture_output=True).stdout)
    assert fresh[PREFIX+'sketch.active'] == '#71D4A2' and fresh[ENABLED] is True
    second = MainWindow(settings=QSettings(str(path),QSettings.IniFormat)); qtbot.addWidget(second)
    assert second.viewport.sketch.foreground_actor.GetProperty().GetColor() == rgb('#71D4A2')
    assert '#242424' in second.styleSheet() and second.viewport.sketch_opacity == .23
    second.palette_controller.reset()
    assert second.preference_store.get('viewport/v1/sketch_opacity') == 23


@pytest.mark.parametrize('bad', ['green','#123','#12345678','#GGGGGG',123,True])
def test_corrupt_stored_color_falls_back_safely(tmp_path,bad):
    settings = QSettings(str(tmp_path/'bad.ini'),QSettings.IniFormat)
    settings.setValue(PREFIX+'sketch.normal',bad)
    assert Preferences(settings).get(PREFIX+'sketch.normal') is None


def test_palette_during_multi_profile_cut_preview_commit_cancel_and_editing(qtbot,monkeypatch):
    from test_multi_profile_ui import selected_window, open_cut
    w,sid,circles,frame = selected_window(qtbot)
    c,v,d = w.palette_controller,w.viewport,w.document
    p = open_cut(w); assert p.preview()
    candidate, baseline, surface = p.candidate,p.baseline,p.preview_surface
    before = model_state(w)
    with monkeypatch.context() as patch:
        patch.setattr(Document,'_regenerate',forbid)
        c.set_color('operation.preview','#82D7CC')
        c.set_color('operation.background','#B87548')
        c.set_color('diagnostics.error','#C94F4F')
        assert p.candidate is candidate and p.baseline is baseline and p.preview_surface is surface
        assert p.actor.GetProperty().GetColor() == rgb('#82D7CC') and p.actor.GetProperty().GetLighting()
        assert model_state(w) == before
        assert p.commit()
    assert d.features[-1].type == 'extrude' and d.statuses[d.features[-1].id].valid
    assert len(d.features[-1].parameters.profiles) == 6
    assert volume(d.shape) < 24000
    accepted = d.features, d.shape, tuple(d._undo)
    w.edit_operation(); assert p.preview()
    c.set_color('operation.preview','#E6D49C')
    p.cancel()
    assert (d.features, d.shape, tuple(d._undo)) == accepted


def test_diagnostics_and_history_recolor_without_rebuilding_items(qtbot):
    w = window(qtbot); c = w.palette_controller
    items = dict(w.browser_items); before = model_state(w)
    for key in ('history.valid','history.unresolved','history.blocked','diagnostics.error','diagnostics.warning','history.selection'):
        c.set_color(key,'#88AACC')
    assert w.browser_items == items and model_state(w) == before
    w.operation_panel.feedback_text('Controlled failure text', role='error')
    assert w.operation_panel.feedback.text() == 'Controlled failure text'
    assert w.operation_panel.feedback.styleSheet()


@pytest.mark.parametrize('operation', ['new', 'join', 'cut'])
def test_custom_palette_keeps_single_profile_material_workflows(qtbot,monkeypatch,operation):
    from test_extrusion_quick_ui import open_quick
    w,p,sid,circle = open_quick(qtbot,face=True)
    p.operation.setCurrentIndex(p.operation.findData(operation))
    p.quick_distance.setText('-3' if operation == 'cut' else '3')
    p.preview_timer.stop()
    assert p.preview()
    candidate = p.candidate
    with monkeypatch.context() as patch:
        patch.setattr(Document,'_regenerate',forbid)
        w.palette_controller.set_color('operation.preview','#D9BB88')
        w.palette_controller.set_color('sketch.active','#71D4A2')
        assert p.candidate is candidate and p.commit()
    feature = w.document.features[-1]
    assert feature.parameters.operation == operation and w.document.statuses[feature.id].valid
    assert w.document.feature(sid).parameters.entities == (circle,)


@pytest.mark.parametrize('accepted',[False,True])
def test_native_color_picker_live_preview_and_cancel_restore(qtbot,monkeypatch,accepted):
    from PySide6.QtWidgets import QColorDialog
    w = window(qtbot); w.open_palette(); c = w.palette_controller
    original = dict(c.store.values)
    def choose(dialog):
        dialog.setCurrentColor(QColor('#71D4A2'))
        assert c.colors()['sketch.normal'] == '#71D4A2'
        return QDialog.Accepted if accepted else QDialog.Rejected
    monkeypatch.setattr(QColorDialog,'exec',choose)
    w.palette_editor.pick_color('sketch.normal')
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not w.palette_editor.findChildren(QColorDialog)
    if accepted:
        assert c.overrides()['sketch.normal'] == '#71D4A2'
    else:
        assert c.store.values == original and not c.overrides()


def test_custom_text_remains_readable_in_editor_menus_and_inputs(qtbot):
    from PySide6.QtWidgets import QLabel
    w = window(qtbot); c = w.palette_controller
    c.set_color('ui.background','#202A31'); c.set_color('ui.text','#FFFFFF')
    w.open_palette(); editor = w.palette_editor
    qtbot.wait(10)
    assert editor.fields['dialogs.background'].text() == '#202A31'
    label = next(label for label in editor.findChildren(QLabel) if label.text().startswith('Live appearance'))
    def hexrole(widget,role): return widget.palette().color(role).name()
    assert contrast(hexrole(label,QPalette.WindowText),hexrole(label,QPalette.Window)) >= 4.5
    field = editor.fields['sketch.normal']
    assert contrast(hexrole(field,QPalette.Text),hexrole(field,QPalette.Base)) >= 4.5
    assert 'QMenu' in w.styleSheet() and 'QComboBox QAbstractItemView' in w.styleSheet()

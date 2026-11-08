"""Existing palette roles, mode inheritance, real text rendering and QAction styling."""
from pathlib import Path
from collections import Counter
import json
import subprocess
import sys
import numpy as np
import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel, QApplication
from hero_cad.palette import COLORS, BASE_COLORS, MODE_COLORS, CONTRAST, PREFIX, rgb, decode_palette
from hero_cad.preferences import Preferences
from hero_cad.document import Document
from hero_cad.sketch import Circle, FaceReference
from hero_cad.ui.main_window import MainWindow
from test_sketch_ui import window, enter, click
from test_opacity_preferences_ui import snapshot, forbidden
from test_sketch_visibility import capture

REFERENCE=Path(__file__).parent/'fixtures/palettes/hero-palette-user-v1.json'


def sketch(qtbot, face=False):
    w=window(qtbot);w.tool_island.set_collapsed(True)
    if face:
        sid=w.document.add_face_sketch(FaceReference(w.document.features[0].id,'+Z'))
        w.refresh();w.viewport.sketch.enter(sid);w.update_actions()
    else:
        sid=enter(w)
    circle=Circle(10,10,4);w.document.add_entity(sid,circle);w.refresh(fit=True)
    frame=w.document.feature(sid).parameters.frame
    click(qtbot,w.viewport,frame,(14,10))
    assert w.viewport.sketch.highlight_actor.GetVisibility()
    return w,sid,circle,frame


def state(w):
    s=w.viewport.sketch
    return snapshot(w),frozenset(s.entity_ids),s.entity_id,s.mapper.GetInput(),s.foreground_mapper.GetInput()


def painted(widget, color):
    image=widget.grab().toImage()
    return sum(image.pixelColor(x,y).name().upper()==color.upper()
               for x in range(image.width()) for y in range(image.height()))


@pytest.mark.parametrize('face',[False,True])
def test_global_inheritance_context_colors_transitions_and_selection(qtbot,monkeypatch,face):
    w,sid,circle,frame=sketch(qtbot,face);c,v=w.palette_controller,w.viewport
    c.set_color('sketch.normal','#773355');c.set_color('sketch.active','#669977');c.set_color('sketch.selected','#AA66DD')
    before=state(w)
    monkeypatch.setattr(Document,'_regenerate',forbidden);monkeypatch.setattr(v,'prepare_shape',forbidden)
    monkeypatch.setattr(w,'refresh',forbidden)
    for mode in ('Off','Orange','Celadon','Off'):
        v.set_xray_mode(mode)
        assert v.sketch.actor.GetProperty().GetColor()==rgb('#773355')
        assert v.sketch.foreground_actor.GetProperty().GetColor()==rgb('#669977')
        assert v.sketch.highlight_actor.GetProperty().GetColor()==rgb('#AA66DD')
        assert state(w)==before
    for mode,normal,active,selected in (('orange','#000000','#000000','#FFFFFF'),
                                       ('celadon','#40D9E6','#40D9E6','#FFA626')):
        for role,value in (('normal',normal),('active',active),('selected',selected)):
            c.set_color(f'sketch.{mode}.{role}',value)
    frames=[]
    for _ in range(2):
        for mode,normal,active,selected in (('Orange','#000000','#000000','#FFFFFF'),
                                           ('Celadon','#40D9E6','#40D9E6','#FFA626'),
                                           ('Off','#773355','#669977','#AA66DD')):
            v.set_xray_mode(mode)
            assert v.sketch.actor.GetProperty().GetColor()==rgb(normal)
            assert v.sketch.foreground_actor.GetProperty().GetColor()==rgb(active)
            assert v.sketch.highlight_actor.GetProperty().GetColor()==rgb(selected)
            assert state(w)==before
            frames.append(capture(v))
    assert np.abs(frames[0]-frames[1]).sum()>10000
    click(qtbot,v,frame,(18,18))
    assert not v.sketch.highlight_actor.GetVisibility()
    click(qtbot,v,frame,(14,10))
    assert v.sketch.highlight_actor.GetVisibility() and state(w)==before
    c.reset(('sketch.orange.normal',))
    c.set_color('sketch.normal','#112244');v.set_xray_mode('Orange')
    assert v.sketch.actor.GetProperty().GetColor()==rgb('#112244')
    assert v.sketch.foreground_actor.GetProperty().GetColor()==rgb('#000000')
    v.set_xray_mode('Celadon')
    assert v.sketch.actor.GetProperty().GetColor()==rgb('#40D9E6')


def test_profile_fill_remains_independent_and_editor_shows_effective_inheritance(qtbot,monkeypatch):
    w,sid,circle,frame=sketch(qtbot);c,v=w.palette_controller,w.viewport
    w.profile_action.setChecked(True);click(qtbot,v,frame,(10,10))
    selected=v.profiles.selections
    c.set_color('sketch.profile','#BBAA77');c.set_color('sketch.normal','#123456')
    w.open_palette();editor=w.palette_editor
    assert len(editor.inheritance)==6 and set(editor.fields)==set(COLORS)
    assert editor.fields['sketch.orange.normal'].text()=='#123456'
    assert not editor.fields['sketch.orange.normal'].isEnabled()
    before=state(w)
    monkeypatch.setattr(Document,'_regenerate',forbidden);monkeypatch.setattr(v,'prepare_shape',forbidden)
    editor.inheritance['sketch.orange.normal'].setCurrentText('Custom')
    assert c.overrides()['sketch.orange.normal']=='#123456'
    c.set_color('sketch.orange.normal','#000000');v.set_xray_mode('Orange')
    assert editor.fields['sketch.orange.normal'].text()=='#000000'
    assert v.profiles.selections==selected and v.profiles.actor.GetProperty().GetColor()==rgb('#BBAA77')
    editor.inheritance['sketch.orange.normal'].setCurrentText('Inherit')
    c.set_color('sketch.normal','#778899')
    assert editor.fields['sketch.orange.normal'].text()=='#778899'
    assert '#778899' in editor.swatches['sketch.orange.normal'].styleSheet()
    assert v.sketch.actor.GetProperty().GetColor()==rgb('#778899') and state(w)==before


def test_text_modes_scopes_and_real_focused_button_rendering(qtbot):
    w=window(qtbot);c=w.palette_controller;c.import_file(REFERENCE);w.open_palette()
    editor=w.palette_editor
    assert c.store.get(CONTRAST)=='Automatic' and editor.text_contrast.currentText()=='Automatic'
    assert w.palette().color(QPalette.WindowText).name()=='#ffffff'
    assert ('#000000','#FFFFFF','#242E34') in c.adjustments
    assert '→' in editor.contrast_info.toolTip()
    editor.text_contrast.setCurrentText('Manual')
    assert w.palette().color(QPalette.WindowText).name()=='#000000'
    assert 'Manual' in editor.contrast_info.text()
    c.set_color('ui.secondary','#CC99AA');c.set_color('ui.heading','#99CCEE')
    assert w.property_info.palette().color(QPalette.WindowText).name()=='#cc99aa'
    assert w.tool_island.context_hint.palette().color(QPalette.WindowText).name()=='#cc99aa'
    heading=w.tool_island.header.findChildren(QLabel)[0]
    assert heading.palette().color(QPalette.WindowText).name()=='#99ccee'
    group=next(label for label in editor.findChildren(QLabel) if label.text()=='Orange X-Ray')
    assert group.palette().color(QPalette.WindowText).name()=='#99ccee'
    c.set_color('controls.text','#12DDAA');c.set_color('controls.input_text','#22CC99')
    c.set_color('operation.text','#AA44CC')
    editor.hide()
    p=w.operation_panel;p.setFloating(True);p.show();p.raise_();p.activateWindow();p.apply_button.setEnabled(True)
    qtbot.waitExposed(p);p.apply_button.setFocus();qtbot.waitUntil(p.apply_button.hasFocus)
    assert p.feedback.palette().color(QPalette.WindowText).name()=='#aa44cc'
    assert p.distance.palette().color(QPalette.Text).name()=='#22cc99'
    # Palette() alone misses pseudo-state painting; inspect actual glyph pixels.
    assert p.apply_button.hasFocus() and painted(p.apply_button,'#12DDAA')>0
    assert ':focus' in p.styleSheet()
    p.hide()
    w.open_preferences();dialog=w.preferences_dialog;dialog.categories.setCurrentRow(2)
    spin=dialog.controls['viewport/v1/sketch_opacity'];spin.setFocus();QApplication.processEvents()
    assert spin.palette().color(QPalette.Text).name()=='#22cc99'
    c.set_contrast('Automatic')
    assert w.palette().color(QPalette.WindowText).name()=='#ffffff'


def test_finish_button_reuses_action_highlight_focus_hover_and_completion(qtbot,monkeypatch):
    w,sid,circle,frame=sketch(qtbot);c=w.palette_controller;b=w.finish_sketch_button
    assert b.defaultAction() is w.finish_sketch_action and b.isEnabled() and b.isVisible()
    assert painted(b,'#E6A04B')>100
    assert ':enabled:hover' in b.styleSheet() and ':enabled:focus' in b.styleSheet()
    before=state(w)
    with monkeypatch.context() as patch:
        patch.setattr(Document,'_regenerate',forbidden);patch.setattr(w.viewport,'prepare_shape',forbidden)
        c.set_color('sketch.finish','#AF7041')
        assert painted(b,'#AF7041')>100 and state(w)==before
    definitions=w.document.features;history=tuple(w.document._undo)
    qtbot.mouseClick(b,Qt.LeftButton)
    assert w.viewport.sketch.active_id is None and not w.sketch_toolbar.isVisible()
    assert not b.isEnabled() and b.defaultAction() is w.finish_sketch_action
    assert w.document.features==definitions and tuple(w.document._undo)==history
    w.viewport.sketch.enter(sid);w.update_actions()
    assert b.isVisible() and b.isEnabled() and painted(b,'#AF7041')>100


def test_v1_user_fixture_preserves_all_explicit_metadata_and_new_defaults(qtbot,tmp_path):
    w=window(qtbot);c=w.palette_controller;original=json.loads(REFERENCE.read_text())
    assert len(original['colors'])==55 and set(original['colors'])==BASE_COLORS
    assert REFERENCE.stat().st_size==2534
    c.set_color('sketch.orange.active','#119977');c.set_contrast('Manual')
    c.import_file(REFERENCE)
    assert c.store.get(CONTRAST)=='Automatic'
    assert set(c.overrides())==set(original['overrides'])
    for key in original['overrides']:assert c.overrides()[key]==original['colors'][key]
    assert all(c.store.get(PREFIX+key) is None for key in MODE_COLORS)
    assert c.colors()['sketch.orange.normal']=='#000000' and c.colors()['sketch.celadon.active']=='#FFFFFF'
    assert c.colors()['sketch.finish']=='#E6A04B'
    c.set_color('sketch.celadon.selected','#FFA626');c.set_contrast('Manual')
    target=tmp_path/'roundtrip.json';c.export_file(target);data=json.loads(target.read_text())
    assert data['version']==1 and data['text_contrast']=='Manual'
    assert set(data['colors'])==set(COLORS)
    expected=c.colors(),c.overrides()
    c.reset();c.import_file(target)
    assert (c.colors(),c.overrides())==expected and c.store.get(CONTRAST)=='Manual'


@pytest.mark.parametrize('mutate',[
    lambda d:d['colors'].pop('sketch.normal'),
    lambda d:d['colors'].update({'sketch.orange.normal':'#12345Z'}),
    lambda d:d['colors'].update({'sketch.unknown.normal':'#FFFFFF'}),
    lambda d:d.update(text_contrast='Boost'),
    lambda d:d.update(overrides=['sketch.orange.normal']),
    lambda d:d.update(version=2),
])
def test_import_rejections_are_atomic(qtbot,tmp_path,mutate):
    w=window(qtbot);c=w.palette_controller;c.set_color('sketch.orange.normal','#114455');c.set_contrast('Manual')
    before=dict(c.store.values),state(w)
    data=json.loads(REFERENCE.read_text());mutate(data)
    path=tmp_path/'bad.json';path.write_text(json.dumps(data))
    with pytest.raises(ValueError):c.import_file(path)
    assert (dict(c.store.values),state(w))==before


def test_restart_preserves_contrast_inheritance_finish_and_opacities(qtbot,tmp_path):
    path=str(tmp_path/'prefs.ini');w=MainWindow(settings=QSettings(path,QSettings.IniFormat));qtbot.addWidget(w)
    c=w.palette_controller;c.set_color('sketch.normal','#119944');c.set_color('sketch.orange.active','#000000')
    c.set_color('sketch.finish','#BB7744');c.set_contrast('Manual')
    w.preference_store.set('viewport/v1/sketch_opacity',10);w.preference_store.set('viewport/v1/xray_opacity',90)
    w.viewport.set_xray_mode('Orange');w.close()
    code='''import json,sys
from PySide6.QtCore import QSettings
from hero_cad.preferences import Preferences
print(json.dumps(Preferences(QSettings(sys.argv[1],QSettings.IniFormat)).values))'''
    saved=json.loads(subprocess.run([sys.executable,'-c',code,path],check=True,text=True,capture_output=True).stdout)
    assert saved[CONTRAST]=='Manual' and saved[PREFIX+'sketch.orange.normal'] is None
    other=MainWindow(settings=QSettings(path,QSettings.IniFormat));qtbot.addWidget(other)
    assert other.viewport.sketch.actor.GetProperty().GetColor()==rgb('#119944')
    assert other.viewport.sketch.foreground_actor.GetProperty().GetColor()==rgb('#000000')
    assert other.palette_controller.colors()['sketch.finish']=='#BB7744'
    assert other.viewport.sketch_opacity==.1 and other.viewport.xray_opacity==.9


def test_context_changes_preserve_operation_preview_candidate(qtbot,monkeypatch):
    from test_multi_profile_ui import selected_window,open_cut
    w,sid,circles,frame=selected_window(qtbot);p=open_cut(w);assert p.preview()
    c=w.palette_controller;candidate,mesh=p.candidate,p.preview_surface;before=state(w)
    monkeypatch.setattr(Document,'_regenerate',forbidden);monkeypatch.setattr(w.viewport,'prepare_shape',forbidden)
    c.set_color('sketch.orange.normal','#000000');c.set_contrast('Manual');c.set_color('sketch.finish','#FFAA55')
    for mode in ('Orange','Celadon','Off'):
        w.viewport.set_xray_mode(mode)
        assert p.candidate is candidate and p.preview_surface is mesh and state(w)==before
    p.cancel()


@pytest.mark.parametrize('mode',['Orange','Celadon'])
def test_sketch_finish_reenter_preserves_context_colors_and_opacity(qtbot,mode):
    w,sid,circle,frame=sketch(qtbot,face=True);c,v=w.palette_controller,w.viewport
    for role,value in (('normal','#334466'),('active','#22BB99'),('selected','#EEDD88')):
        c.set_color(f'sketch.{mode.lower()}.{role}',value)
    w.preference_store.set('viewport/v1/sketch_opacity',10)
    w.preference_store.set('viewport/v1/xray_opacity',90)
    v.set_xray_mode(mode)
    definitions=w.document.features;history=tuple(w.document._undo)
    assert v.sketch.foreground_actor.GetProperty().GetColor()==rgb('#22BB99')
    assert v.actor.GetProperty().GetOpacity()==.1
    w.finish_sketch()
    assert v.sketch.actor.GetProperty().GetColor()==rgb('#334466')
    assert not v.sketch.foreground_actor.GetVisibility() and v.actor.GetProperty().GetOpacity()==.9
    v.sketch.enter(sid);w.update_actions()
    assert v.sketch.foreground_actor.GetVisibility()
    assert v.sketch.foreground_actor.GetProperty().GetColor()==rgb('#22BB99')
    assert v.actor.GetProperty().GetOpacity()==.1 and v.xray_mode==mode
    assert w.document.features==definitions and tuple(w.document._undo)==history


@pytest.mark.parametrize('color',['#000000','#FFFFFF'])
def test_finish_hover_is_distinct_at_rgb_extremes(qtbot,color):
    import re
    from hero_cad.ui.palette_controller import contrast
    w,sid,circle,frame=sketch(qtbot);w.palette_controller.set_color('sketch.finish',color)
    b=w.finish_sketch_button
    hover,text=re.search(r':enabled:hover \{ background: (#[A-Fa-f0-9]{6}); color: (#[A-Fa-f0-9]{6});', b.styleSheet()).groups()
    assert contrast(color,hover)>1.2 and contrast(text,hover)>=4.5
    # Move off first: successive windows may open under the same X11 cursor.
    qtbot.mouseMove(w.viewport,pos=w.viewport.rect().center());qtbot.wait(20)
    qtbot.mouseMove(b,pos=b.rect().center());qtbot.wait(30)
    assert painted(b,hover)>100

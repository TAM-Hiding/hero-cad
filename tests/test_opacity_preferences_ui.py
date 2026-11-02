"""Real numeric-entry/default-button regression and independent opacity policies."""
import json
import subprocess
import sys
import numpy as np
import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QSignalSpy
from hero_cad.document import Document
from hero_cad.preferences import Preferences
from hero_cad.ui.main_window import MainWindow
from hero_cad.persistence import serialize
from hero_cad.sketch import Circle
from test_sketch_ui import window, enter, click
from test_sketch_visibility import capture

SKETCH = 'viewport/v1/sketch_opacity'
GENERAL = 'viewport/v1/xray_opacity'
MODE = 'viewport/v1/xray'


def settings(w):
    w.open_preferences()
    dialog = w.preferences_dialog
    dialog.categories.setCurrentRow(2)
    return dialog


def type_number(qtbot, spin, value, key=Qt.Key_Return):
    spin.setFocus()
    spin.lineEdit().selectAll()
    qtbot.keyClicks(spin, str(value))
    qtbot.keyClick(spin, key)


def snapshot(w):
    d,v = w.document,w.viewport
    return (d.features,d.shape,tuple(d._undo),tuple(d._redo),d.dirty,d.path,serialize(d.features),
            v.mapper,v.mapper.GetInput(),v.edge_mapper,v.edge_mapper.GetInput(),tuple(v.faces),tuple(v.edges),
            v.sketch.active_id,v.sketch.controller.tool,v.profiles.selections,v.profiles.mapper.GetInput())


def forbidden(*a,**kw):
    raise AssertionError('Opacity must not evaluate geometry or prepare solid display')


@pytest.mark.parametrize('mode',['Orange','Celadon'])
@pytest.mark.parametrize('key',[Qt.Key_Return,Qt.Key_Enter])
def test_enter_never_implicitly_restores_viewport_defaults(qtbot,mode,key):
    w=window(qtbot);enter(w);w.viewport.set_xray_mode(mode)
    dialog=settings(w);spy=QSignalSpy(dialog.restore_button.clicked)
    # Model Qt's platform-dependent default assignment if this action opts in.
    # Existing code permits it; the repaired dialog opts out of implicit actions.
    if dialog.restore_button.autoDefault():
        dialog.restore_button.setDefault(True)
    type_number(qtbot,dialog.controls[SKETCH],10,key)
    assert dialog.controls[SKETCH].value()==10
    assert w.preference_store.get(SKETCH)==10 and w.viewport.actor.GetProperty().GetOpacity()==.1
    assert w.viewport.xray_mode==mode and w.preference_store.get(MODE)==mode
    assert spy.count()==0 and dialog.isVisible()
    assert not any(button.isDefault() for button in dialog.findChildren(QPushButton))


@pytest.mark.parametrize('mode',['Orange','Celadon'])
def test_all_sketch_values_visible_transitions_toggle_and_selection_isolation(qtbot,monkeypatch,mode):
    w=window(qtbot);sid=enter(w);w.tool_island.set_collapsed(True)
    w.document.add_entity(sid,Circle(10,10,3));w.refresh()
    w.viewport.set_xray_mode(mode)
    frame=w.document.feature(sid).parameters.frame
    w.profile_action.setChecked(True);click(qtbot,w.viewport,frame,(10,10))
    assert w.viewport.profiles.selection
    dialog=settings(w);v=w.viewport;before=snapshot(w);color=v.actor.GetProperty().GetColor()
    monkeypatch.setattr(Document,'_regenerate',forbidden)
    monkeypatch.setattr(v,'prepare_shape',forbidden)
    monkeypatch.setattr(w,'refresh',forbidden)
    frames={}
    for value in (0,10,35,90,100):
        type_number(qtbot,dialog.controls[SKETCH],value)
        assert dialog.controls[SKETCH].value()==value and w.preference_store.get(SKETCH)==value
        assert v.actor.GetProperty().GetOpacity()==value/100
        assert v.xray_mode==mode and w.xray_choice.currentText()==mode and w.preference_store.get(MODE)==mode
        assert v.actor.GetProperty().GetColor()==color and snapshot(w)==before
        frames[value]=capture(v)
    assert np.abs(frames[90]-frames[10]).sum()>10000
    assert np.abs(frames[100]-frames[0]).sum()>10000
    dialog.controls['viewport/v1/sketch_xray'].setChecked(False)
    assert v.actor.GetProperty().GetOpacity()==1 and not dialog.controls[SKETCH].isEnabled()
    assert w.preference_store.get(SKETCH)==100 and w.preference_store.get(MODE)==mode
    dialog.controls['viewport/v1/sketch_xray'].setChecked(True)
    assert v.actor.GetProperty().GetOpacity()==1 and dialog.controls[SKETCH].isEnabled()
    type_number(qtbot,dialog.controls[SKETCH],10)
    assert v.actor.GetProperty().GetOpacity()==.1 and snapshot(w)==before


@pytest.mark.parametrize('mode',['Orange','Celadon'])
def test_general_values_live_outside_sketch_and_mode_off_is_opaque(qtbot,monkeypatch,mode):
    w=window(qtbot);v=w.viewport;v.set_xray_mode(mode);dialog=settings(w)
    assert dialog.controls[GENERAL].value()==85
    before=snapshot(w);color=v.actor.GetProperty().GetColor()
    monkeypatch.setattr(Document,'_regenerate',forbidden)
    monkeypatch.setattr(v,'prepare_shape',forbidden)
    for value in (0,10,35,90,100):
        type_number(qtbot,dialog.controls[GENERAL],value)
        assert w.preference_store.get(GENERAL)==value and v.actor.GetProperty().GetOpacity()==value/100
        assert w.preference_store.get(SKETCH)==35 and w.preference_store.get(MODE)==mode
        assert color==v.actor.GetProperty().GetColor() and snapshot(w)==before
    v.set_xray_mode('Off')
    type_number(qtbot,dialog.controls[GENERAL],10)
    assert v.actor.GetProperty().GetOpacity()==1 and w.preference_store.get(MODE)=='Off'
    v.set_xray_mode(mode);assert v.actor.GetProperty().GetOpacity()==.1


@pytest.mark.parametrize('mode',['Off','Orange','Celadon'])
def test_enter_finish_preserves_both_opacities_and_general_mode(qtbot,mode):
    w=window(qtbot);store=w.preference_store;v=w.viewport
    store.set(SKETCH,10);store.set(GENERAL,90);v.set_xray_mode(mode)
    sid=enter(w)
    assert v.actor.GetProperty().GetOpacity()==.1 and w.preference_store.get(MODE)==mode
    store.set(GENERAL,35)
    assert v.actor.GetProperty().GetOpacity()==.1
    store.set('viewport/v1/sketch_xray',False)
    assert v.actor.GetProperty().GetOpacity()==1
    store.set('viewport/v1/sketch_xray',True)
    w.finish_sketch()
    assert v.actor.GetProperty().GetOpacity()==(1 if mode=='Off' else .35)
    assert store.get(SKETCH)==10 and store.get(GENERAL)==35 and store.get(MODE)==mode
    w.viewport.sketch.enter(sid)
    assert v.actor.GetProperty().GetOpacity()==.1


def test_opacities_and_rgb_palette_remain_independent(qtbot,monkeypatch):
    w=window(qtbot);enter(w);v=w.viewport;c=w.palette_controller;dialog=settings(w)
    v.set_xray_mode('Orange');before=snapshot(w)
    monkeypatch.setattr(Document,'_regenerate',forbidden)
    monkeypatch.setattr(v,'prepare_shape',forbidden)
    type_number(qtbot,dialog.controls[SKETCH],10)
    type_number(qtbot,dialog.controls[GENERAL],90)
    c.set_color('xray.orange','#CC8833');c.set_color('sketch.active','#71D4A2')
    colors=c.colors()
    for custom in (False,True,False,True):
        c.preset(custom)
        assert v.actor.GetProperty().GetOpacity()==.1
        assert w.preference_store.get(SKETCH)==10 and w.preference_store.get(GENERAL)==90
        assert w.preference_store.get(MODE)=='Orange' and snapshot(w)==before
    assert c.colors()==colors
    type_number(qtbot,dialog.controls[SKETCH],90)
    assert c.colors()==colors and v.actor.GetProperty().GetOpacity()==.9


def test_both_preferences_persist_across_process_and_window_restart(qtbot,tmp_path):
    path=str(tmp_path/'prefs.ini')
    w=MainWindow(settings=QSettings(path,QSettings.IniFormat));qtbot.addWidget(w);w.show();qtbot.waitExposed(w)
    dialog=settings(w)
    type_number(qtbot,dialog.controls[SKETCH],10);type_number(qtbot,dialog.controls[GENERAL],90)
    w.viewport.set_xray_mode('Celadon');w.close()
    code='''import json,sys
from PySide6.QtCore import QSettings
from hero_cad.preferences import Preferences
print(json.dumps(Preferences(QSettings(sys.argv[1],QSettings.IniFormat)).values))'''
    values=json.loads(subprocess.run([sys.executable,'-c',code,path],check=True,text=True,capture_output=True).stdout)
    assert values[SKETCH]==10 and values[GENERAL]==90 and values[MODE]=='Celadon'
    other=MainWindow(settings=QSettings(path,QSettings.IniFormat));qtbot.addWidget(other)
    assert other.viewport.actor.GetProperty().GetOpacity()==.9 and other.viewport.xray_mode=='Celadon'
    dialog=settings(other)
    assert dialog.controls[SKETCH].value()==10 and dialog.controls[GENERAL].value()==90


def test_defaults_reset_only_by_explicit_button_and_invalid_general_pref(qtbot,tmp_path):
    w=window(qtbot);dialog=settings(w)
    type_number(qtbot,dialog.controls[SKETCH],10);type_number(qtbot,dialog.controls[GENERAL],90)
    qtbot.mouseClick(dialog.restore_button,Qt.LeftButton)
    assert dialog.controls[SKETCH].value()==35 and dialog.controls[GENERAL].value()==85
    for invalid in (-1,101,True,3.5,float('nan'),'bad'):
        with pytest.raises(ValueError):w.preference_store.set(GENERAL,invalid)
    saved=QSettings(str(tmp_path/'bad.ini'),QSettings.IniFormat);saved.setValue(GENERAL,'bad')
    assert Preferences(saved).get(GENERAL)==85

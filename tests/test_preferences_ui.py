"""Isolated preference storage and real bidirectional Qt/viewport integration."""
import json
import os
import subprocess
import sys
import pytest
from PySide6.QtCore import QSettings, Qt, QPoint
from PySide6.QtTest import QSignalSpy
from hero_cad.preferences import Preferences, PREFERENCES, CATEGORIES
from hero_cad.ui.main_window import MainWindow
from test_sketch_ui import window, enter, click
from hero_cad.sketch import Circle


def test_defaults_persistence_types_and_fresh_process(tmp_path):
    path=str(tmp_path/'prefs.ini');settings=QSettings(path,QSettings.IniFormat)
    store=Preferences(settings)
    assert {key:store.get(key) for key in PREFERENCES}=={key:spec.default for key,spec in PREFERENCES.items()}
    spy=QSignalSpy(store.changed)
    changes={'grid/v1/grid_visible':False,'grid/v1/color':'Celadon','grid/v1/manual_spacing':.125,
             'viewport/v1/edge_tolerance':9,'tool_island/v1/size':'Expanded'}
    for key,value in changes.items():store.set(key,value);store.set(key,value)
    assert spy.count()==len(changes)
    script='''import json,sys
from PySide6.QtCore import QSettings
from hero_cad.preferences import Preferences
p=Preferences(QSettings(sys.argv[1],QSettings.IniFormat))
print(json.dumps(p.values))'''
    result=subprocess.run([sys.executable,'-c',script,path],check=True,text=True,capture_output=True)
    fresh=json.loads(result.stdout)
    for key,value in changes.items():assert fresh[key]==value and type(fresh[key]) is type(value)
    settings.setValue('unrelated/preserve','yes');store.restore_category('Grid & Snapping')
    assert settings.value('unrelated/preserve')=='yes'
    assert store.get('viewport/v1/edge_tolerance')==9


@pytest.mark.parametrize('key,value',[
    ('viewport/v1/contrast','bad'),('grid/v1/color','Neon'),('grid/v1/grid_visible','maybe'),
    ('viewport/v1/auto_hide_sketches','invalid'),('viewport/v1/edge_tolerance',float('nan')),
    ('viewport/v1/edge_tolerance',3.5),('viewport/v1/edge_tolerance',100),
    ('grid/v1/manual_spacing',float('inf')),('grid/v1/manual_spacing',0),
    ('interface/v1/dimension_opacity',-1),('tool_island/v1/visible','invalid'),
    ('tool_island/v1/size','Giant'),('tool_island/v1/x','NaN')])
def test_bad_saved_values_use_defaults_and_invalid_writes_fail(tmp_path,key,value):
    settings=QSettings(str(tmp_path/'bad.ini'),QSettings.IniFormat);settings.setValue(key,value)
    store=Preferences(settings)
    assert store.get(key)==PREFERENCES[key].default
    with pytest.raises(ValueError):store.set(key,value)


def test_all_dialog_controls_sync_both_ways_and_restore_only_category(qtbot):
    w=window(qtbot);sid=enter(w);w.document.add_entity(sid,Circle(0,0,3));w.refresh()
    state=w.document.features,len(w.document._undo),w.document.shape
    camera=w.viewport.renderer.GetActiveCamera();camera_state=(camera.GetPosition(),camera.GetParallelScale())
    w.preferences_action.trigger();dialog=w.preferences_dialog
    assert dialog.isVisible() and tuple(dialog.categories.item(i).text() for i in range(5))==CATEGORIES
    assert len(dialog.controls)==sum(spec.exposed for spec in PREFERENCES.values())
    controls=dialog.controls
    controls['grid/v1/grid_visible'].setChecked(False)
    assert not w.grid_action.isChecked() and not w.viewport.sketch.guides.grid_actor.GetVisibility()
    w.grid_action.setChecked(True);assert controls['grid/v1/grid_visible'].isChecked()
    controls['grid/v1/color'].setCurrentText('Purple');assert w.grid_color.currentText()=='Purple'
    w.grid_color.setCurrentText('Orange');assert controls['grid/v1/color'].currentText()=='Orange'
    for key,action,option in (('snap_grid',w.snap_grid_action,'snap_grid'),('snap_origin',w.snap_origin_action,'snap_origin'),('snap_center',w.snap_center_action,'snap_center')):
        controls['grid/v1/'+key].setChecked(False)
        assert not action.isChecked() and not getattr(w.viewport.sketch.guides,option)
        action.setChecked(True);assert controls['grid/v1/'+key].isChecked()
    controls['grid/v1/automatic'].setChecked(False)
    assert controls['grid/v1/manual_spacing'].isEnabled() and w.manual_grid_spacing.isEnabled()
    controls['grid/v1/manual_spacing'].setValue(.125);assert w.viewport.sketch.guides.spacing==.125
    controls['viewport/v1/xray'].setCurrentText('Orange')
    assert w.viewport.xray_mode=='Orange' and w.xray_choice.currentText()=='Orange'
    w.xray_actions['Celadon'].trigger();assert controls['viewport/v1/xray'].currentText()=='Celadon'
    controls['viewport/v1/contrast'].setCurrentText('Off');assert w.contrast_actions['Off'].isChecked() and not w.viewport.high_contrast()
    w.contrast_actions['Always'].trigger();assert controls['viewport/v1/contrast'].currentText()=='Always'
    controls['viewport/v1/edge_tolerance'].setValue(10);assert w.pick_radius.value()==10 and w.viewport.edge_tolerance_px==10
    controls['viewport/v1/display_mode'].setCurrentText('CAD Wireframe');assert w.viewport.display_mode=='CAD Wireframe'
    w.display_actions['Shaded'].trigger();assert controls['viewport/v1/display_mode'].currentText()=='Shaded'
    controls['viewport/v1/auto_hide_sketches'].setChecked(False);assert not w.auto_hide_sketches.isChecked()
    w.auto_hide_sketches.setChecked(True);assert controls['viewport/v1/auto_hide_sketches'].isChecked()
    controls['interface/v1/dimension_opacity'].setValue(28);assert w.dimension_opacity.value()==28
    controls['tool_island/v1/visible'].setChecked(False);assert not w.tool_island.requested_visible and not w.island_action.isChecked()
    w.island_action.setChecked(True);assert controls['tool_island/v1/visible'].isChecked()
    controls['tool_island/v1/size'].setCurrentText('Compact');assert w.tool_island.preset=='Compact'
    w.tool_island.set_preset('Expanded');assert controls['tool_island/v1/size'].currentText()=='Expanded'
    w.tool_island.set_collapsed(True);assert controls['tool_island/v1/collapsed'].isChecked()
    dialog.categories.setCurrentRow(1);qtbot.mouseClick(dialog.restore_button,Qt.LeftButton)
    for key,spec in PREFERENCES.items():
        if spec.category=='Grid & Snapping':assert w.preference_store.get(key)==spec.default
    assert w.viewport.xray_mode=='Celadon' and w.tool_island.preset=='Expanded'
    assert (w.document.features,len(w.document._undo),w.document.shape)==state
    assert (camera.GetPosition(),camera.GetParallelScale())==camera_state
    dialog.close();w.grid_color.setCurrentText('White');w.open_preferences()
    assert w.preferences_dialog is dialog and controls['grid/v1/color'].currentText()=='White'


def test_actual_window_restart_preserves_new_and_legacy_preferences(qtbot,tmp_path):
    path=str(tmp_path/'old.ini');settings=QSettings(path,QSettings.IniFormat)
    # Existing keys migrate in place; there is no replacement config file.
    for key,value in {'grid/v1/color':'Purple','grid/v1/scale_visible':True,
                      'grid/v1/fade_xray':True,'viewport/v1/contrast':'Always',
                      'tool_island/v1/size':'Compact'}.items():settings.setValue(key,value)
    w=MainWindow(settings=settings);qtbot.addWidget(w);w.show();qtbot.waitExposed(w);qtbot.waitUntil(lambda:w.tool_island._ready)
    assert w.grid_color.currentText()=='Purple' and w.grid_scale_action.isChecked() and w.grid_fade_action.isChecked()
    assert w.viewport.contrast_mode=='Always' and w.tool_island.preset=='Compact'
    w.pick_radius.setValue(8);w.xray_choice.setCurrentText('Orange');w.grid_action.setChecked(False)
    w.snap_center_action.setChecked(False);w.dimension_opacity.setValue(44)
    w.tool_island.set_collapsed(True);w.tool_island.place(QPoint(25,35));w.tool_island.save_layout();w.close()
    other=MainWindow(settings=QSettings(path,QSettings.IniFormat));qtbot.addWidget(other);other.show();qtbot.waitExposed(other);qtbot.waitUntil(lambda:other.tool_island._ready)
    assert other.pick_radius.value()==8 and other.viewport.edge_tolerance_px==8
    assert other.viewport.xray_mode=='Orange' and not other.grid_action.isChecked()
    assert not other.snap_center_action.isChecked() and other.dimension_opacity.value()==44
    assert other.tool_island.collapsed and other.tool_island.pos()==QPoint(25,35)
    assert other.viewport.contrast_mode=='Always' and other.grid_color.currentText()=='Purple'


def test_interface_restore_keeps_other_categories_and_document(qtbot):
    w=window(qtbot);qtbot.waitUntil(lambda:w.tool_island._ready)
    w.open_preferences();dialog=w.preferences_dialog
    w.pick_radius.setValue(9);w.tool_island.set_preset('Expanded');w.tool_island.set_collapsed(True)
    w.tool_island.place(QPoint(20,45));w.tool_island.save_layout();w.island_action.setChecked(False)
    state=w.document.features,len(w.document._undo),w.document.dirty
    dialog.categories.setCurrentRow(4);dialog.restore_category()
    assert w.tool_island.preset=='Medium' and not w.tool_island.collapsed and w.tool_island.requested_visible
    assert w.island_action.isChecked() and w.tool_island.y()==16
    assert w.pick_radius.value()==9 and (w.document.features,len(w.document._undo),w.document.dirty)==state

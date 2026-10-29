"""Keyboard-first UI over the existing candidate/commit extrusion pipeline."""
from math import pi
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.sketch import Circle,FaceReference
from test_sketch_ui import window,enter,click


def open_quick(qtbot,face=False,hide_body=False):
    w=window(qtbot);w.tool_island.set_collapsed(True)
    if face:
        sid=w.document.add_face_sketch(FaceReference(w.document.features[0].id,'+Z'))
        w.refresh();w.browser.setCurrentItem(w.browser_items[('sketch',sid)]);w.edit_sketch()
    else:
        sid=enter(w,'XY')
    if hide_body:w.show_base_box.setChecked(False)
    c=Circle(10,10,2);w.document.add_entity(sid,c);w.refresh()
    frame=w.document.feature(sid).parameters.frame
    w.profile_action.setChecked(True);click(qtbot,w.viewport,frame,(10,10))
    assert w.viewport.profiles.selection
    assert w.commands.execute('model.extrude')
    p=w.operation_panel
    qtbot.waitUntil(lambda:QApplication.focusWidget() is p.quick_distance)
    assert p.isFloating() and p.isVisible() and p.quick_mode
    assert p.quick_distance.selectedText()=='10'
    return w,p,sid,c


@pytest.mark.parametrize('text',['4','-3.25','0.0123456789123'])
def test_immediate_typing_enter_commit_history_properties_and_reload(qtbot,text,tmp_path):
    w,p,sid,c=open_quick(qtbot)
    before=w.document.features;count=len(w.document._undo)
    qtbot.keyClicks(QApplication.focusWidget(),text)
    assert p.quick_distance.text()==text
    qtbot.keyClick(QApplication.focusWidget(),Qt.Key_Return)
    assert not p.isVisible() and not p.active and p.candidate is None
    f=w.document.features[-1]
    assert f.type=='extrude' and f.parameters.distance==float(text)
    assert len(w.document.features)==len(before)+1 and len(w.document._undo)==count+1
    assert volume(w.document.solid_shapes[f.id])==pytest.approx(4*pi*abs(float(text)))
    assert w.viewport.sketch.active_id is None and not w.profile_action.isChecked()
    assert not w.extrude_action.isEnabled()
    saved=w.document.features;w.undo();assert w.document.features==before
    w.redo();assert w.document.features==saved
    w.document.save(tmp_path/'quick.starcad')
    assert Document.load(w.document.path).features==saved
    w.browser.setCurrentItem(w.browser_items[('extrude',f.id)])
    w.entity_fields['distance'].setValue(2.5);w.entity_apply.click()
    assert w.document.feature(f.id).parameters.distance==2.5
    w.edit_operation()
    assert not p.quick_mode and p.isFloating()
    p.distance.setValue(3.5);assert p.preview() and p.commit()
    assert w.document.feature(f.id).parameters.distance==3.5


@pytest.mark.parametrize('text',['','-','.','0','nan','inf','1e','1e999','100001','abc'])
def test_invalid_input_stays_open_and_never_substitutes_old_value(qtbot,monkeypatch,text):
    w,p,sid,c=open_quick(qtbot)
    import hero_cad.ui.operation_panel as module
    calls=[];real=module.Document
    def counted(*a,**kw):calls.append(1);return real(*a,**kw)
    monkeypatch.setattr(module,'Document',counted)
    before=w.document.features;count=len(w.document._undo)
    p.quick_distance.setText(text)
    qtbot.keyClick(p.quick_distance,Qt.Key_Return)
    qtbot.wait(230)
    assert p.active and p.isVisible() and QApplication.focusWidget() is p.quick_distance
    assert p.quick_distance.text()==text
    assert w.document.features==before and len(w.document._undo)==count
    assert calls==[] and not p.actor.GetVisibility() and p.candidate is None
    assert p.feedback.text()


def test_debounced_preview_escape_cancellation_and_shared_command_state(qtbot,monkeypatch):
    w,p,sid,c=open_quick(qtbot)
    before=w.document.features;count=len(w.document._undo)
    qtbot.waitUntil(lambda:p.candidate is not None,timeout=4000)
    assert p.actor.GetVisibility()
    import hero_cad.ui.operation_panel as module
    calls=[];real=module.Document
    def counted(*a,**kw):calls.append(1);return real(*a,**kw)
    monkeypatch.setattr(module,'Document',counted)
    for text in ('2','2.','2.125'):p.quick_distance.setText(text)
    qtbot.waitUntil(lambda:p.candidate is not None,timeout=4000)
    assert calls==[1] and p.candidate.features[-1].parameters.distance==2.125
    assert w.document.features==before and len(w.document._undo)==count
    qtbot.keyClick(p.quick_distance,Qt.Key_Escape)
    assert not p.active and not p.isVisible() and not p.actor.GetVisibility()
    assert not w.viewport.profiles.active and not w.profile_action.isChecked()
    assert not w.extrude_action.isEnabled() and not p.preview_timer.isActive()
    qtbot.wait(230)
    assert w.document.features==before and len(w.document._undo)==count
    assert not p.actor.GetVisibility()


@pytest.mark.parametrize('operation,distance',[('new','-2.5'),('join','5'),('cut','-5'),('intersect','-5')])
def test_face_profile_all_operations_use_existing_target_and_preview(qtbot,operation,distance):
    w,p,sid,c=open_quick(qtbot,face=True)
    target=p.target.currentData();before=w.document.features
    p.operation.setCurrentIndex(p.operation.findData(operation))
    assert p.target.currentData()==target
    p.quick_distance.setText(distance)
    qtbot.waitUntil(lambda:p.candidate is not None,timeout=4000)
    assert p.actor.GetVisibility() and w.document.features==before
    qtbot.keyClick(p.quick_distance,Qt.Key_Return)
    f=w.document.features[-1]
    assert f.parameters.operation==operation and f.parameters.distance==float(distance)
    assert f.parameters.target_id==(None if operation=='new' else target)
    assert w.document.statuses[f.id].valid


def test_missing_target_is_explained_without_history_or_silent_target_change(qtbot):
    w,p,sid,c=open_quick(qtbot,hide_body=True)
    assert p.target.count()==0
    before=w.document.features
    p.operation.setCurrentIndex(p.operation.findData('cut'))
    p.quick_distance.setText('-5')
    qtbot.keyClick(p.quick_distance,Qt.Key_Return)
    assert p.active and w.document.features==before
    assert 'target body' in p.feedback.text()
    assert QApplication.focusWidget() is p.quick_distance


def test_popup_position_clamped_to_available_screen_and_advanced_extent(qtbot):
    app=QApplication.instance();area=app.primaryScreen().availableGeometry()
    QCursor.setPos(area.right()-2,area.bottom()-2)
    w,p,sid,c=open_quick(qtbot,face=True)
    assert area.contains(p.frameGeometry())
    assert p.width()<=400 and p.height()<380
    target=p.target.currentData()
    for operation in ('cut','join','intersect','new'):
        p.operation.setCurrentIndex(p.operation.findData(operation))
        assert p.target.currentData()==target
    p.operation.setCurrentIndex(p.operation.findData('cut'))
    p.advanced.setChecked(True)
    p.extent.setCurrentIndex(p.extent.findData('through_all'))
    p.direction.setCurrentIndex(p.direction.findData(-1))
    assert not p.quick_distance.isEnabled()
    assert area.contains(p.frameGeometry())
    assert p.apply_input()
    assert w.document.features[-1].parameters.extent=='through_all'

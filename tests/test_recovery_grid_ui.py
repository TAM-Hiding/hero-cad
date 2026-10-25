import pytest
from PySide6.QtCore import Qt, QSettings
from hero_cad.ui.main_window import MainWindow
from hero_cad.features import BoxParameters
from hero_cad.sketch import Circle, FaceReference
from hero_cad.geometry import volume
from test_sketch_ui import window, enter, pixel, click, hover
from test_boolean_ui import choose


def assert_normal(w):
    assert not w.profile_action.isChecked()
    assert not w.viewport.profiles.active
    assert not w.viewport.profiles.selection
    assert not w.viewport.profiles.actor.GetVisibility()
    assert not w.operation_panel.active
    assert not w.operation_panel.actor.GetVisibility()
    assert not w.viewport.sketch.preview_actor.GetVisibility()
    assert w.commands.commands['profile.select'].action is w.profile_action


def test_new_body_undo_face_pick_cut_and_repeated_history(qtbot):
    w = window(qtbot); d = w.document; v = w.viewport
    d.set_box(BoxParameters(20,20,10)); box = d.features[0].id
    sid = d.add_face_sketch(FaceReference(box,'+Z'))
    c = Circle(10,10,2); d.add_entity(sid,c); w.refresh(fit=True)
    p = w.operation_panel
    p.open(source=(sid,c.id,())); p.distance.setValue(-5)
    assert p.preview() and p.commit()
    new = d.features[-1].id
    # Clearing the profile highlight alone used to leave this click router active.
    w.profile_action.setChecked(True)
    cam = v.renderer.GetActiveCamera()
    position, focal, scale = cam.GetPosition(), cam.GetFocalPoint(), cam.GetParallelScale()
    w.undo(); assert new not in d.active_body_ids
    assert_normal(w)
    assert cam.GetPosition() == pytest.approx(position)
    assert cam.GetFocalPoint() == pytest.approx(focal)
    assert cam.GetParallelScale() == pytest.approx(scale)
    for _ in range(3):
        w.redo(); assert new in d.active_body_ids
        w.profile_action.setChecked(True)
        w.undo(); assert_normal(w)
        v.orient('Top')
        qtbot.mouseClick(v, Qt.LeftButton, pos=pixel(v,(3,3,10)))
        assert v.selection and d.face_reference(v.selection.shape).parent_id == box
        assert w.new_sketch_action.isEnabled()
    p.open(source=(sid,c.id,())); choose(p.operation,'cut'); choose(p.target,box)
    p.distance.setValue(-5)
    assert p.preview() and p.commit()
    assert volume(d.solid_shapes[d.features[-1].id]) == pytest.approx(4000-20*3.141592653589793)
    v.orient('Top')
    qtbot.mouseClick(v,Qt.LeftButton,pos=pixel(v,(3,3,10)))
    assert v.selection and w.new_sketch_action.isEnabled()
    w.new_sketch_action.trigger(); assert v.sketch.active_id
    w.commands.execute('tool.line')
    frame = v.sketch.feature.parameters.frame
    click(qtbot,v,frame,(1,1)); hover(v,pixel(v,frame.to_world((4,4))))
    before = d.features
    qtbot.keyClick(v,Qt.Key_Escape)
    assert d.features == before and v.sketch.controller.name == 'select'
    assert_normal(w)


@pytest.mark.parametrize('operation',['new','cut','join'])
def test_preview_cancel_restores_routing_and_commands(qtbot,operation):
    w=window(qtbot);d=w.document;v=w.viewport
    box=d.features[0].id
    sid=d.add_face_sketch(FaceReference(box,'+Z'))
    c=Circle(10,10,2);d.add_entity(sid,c);w.refresh(fit=True)
    before, count=d.features,len(d._undo)
    w.profile_action.setChecked(True)
    p=w.operation_panel;p.open(source=(sid,c.id,()))
    choose(p.operation,operation); choose(p.target,box)
    p.distance.setValue(5 if operation=='join' else -5)
    assert p.preview()
    p.cancel()
    assert_normal(w)
    assert d.features==before and len(d._undo)==count
    w.profile_action.setChecked(True)
    qtbot.keyClick(v,Qt.Key_Escape)
    assert_normal(w)
    assert w.profile_action.isEnabled() and v.mapper.GetInput().GetNumberOfCells()>0


@pytest.mark.parametrize('plane',['XY','XZ','YZ'])
def test_grid_appearance_labels_and_snapping_unchanged(qtbot,plane):
    w=window(qtbot);sid=enter(w,plane);v=w.viewport;g=v.sketch.guides
    w.auto_grid_action.setChecked(False);w.manual_grid_spacing.setValue(1)
    frame=w.document.feature(sid).parameters.frame
    camera=v.renderer.GetActiveCamera();camera.SetParallelScale(25)
    before=w.document.features
    w.grid_scale_action.setChecked(True)
    from hero_cad.ui.snapping import snap_point
    def snap():
        def project(local):
            v.renderer.SetWorldPoint(*frame.to_world(local),1)
            v.renderer.WorldToDisplay()
            return v.renderer.GetDisplayPoint()[:2]
        return snap_point((1.02,2.01),project((1.02,2.01)),project,g.spacing,
                          grid=True,origin=True,centers=())
    expected=snap()
    for name,color in g.COLORS.items():
        w.grid_color.setCurrentText(name)
        assert g.grid_actor.GetProperty().GetColor()==pytest.approx(tuple(.6*b+.4*c for b,c in zip(v.renderer.GetBackground(),color)))
        assert max(g.minor_actor.GetProperty().GetColor()) < max(color)
        assert g.major_spacing==10 and g.spacing==1 and snap()==expected
        assert g.label_data
        for axis,value,local,box in g.label_data:
            assert local[axis]==value and value/10==pytest.approx(round(value/10))
            assert frame.to_local(frame.to_world(local))==pytest.approx(local)
        for i,a in enumerate(g.label_data):
            for b in g.label_data[i+1:]:
                x,y,r,t=a[3];xx,yy,rr,tt=b[3]
                assert r<xx or rr<x or t<yy or tt<y
    normal=g.effective_opacity
    labels=[(a,b,c) for a,b,c,_ in g.label_data]
    w.xray_choice.setCurrentText('Orange')
    assert g.effective_opacity==normal
    w.grid_fade_action.setChecked(True)
    assert g.effective_opacity==pytest.approx(normal*.6)
    assert [(a,b,c) for a,b,c,_ in g.label_data]==labels
    w.xray_choice.setCurrentText('Off')
    assert g.effective_opacity==normal
    w.grid_action.setChecked(False)
    assert not any(label.GetVisibility() for label in g.labels)
    w.grid_action.setChecked(True);w.grid_scale_action.setChecked(False)
    assert not g.label_data
    w.auto_grid_action.setChecked(True)
    w.grid_scale_action.setChecked(True)
    camera.SetParallelScale(1);fine=g.spacing
    for axis,value,local,box in g.label_data:
        assert value/g.major_spacing==pytest.approx(round(value/g.major_spacing))
    camera.SetParallelScale(1000);assert g.spacing>fine
    assert len(g.label_data)<=32
    for axis,value,local,box in g.label_data:
        assert value/g.major_spacing==pytest.approx(round(value/g.major_spacing))
    assert w.document.features==before


def test_grid_preferences_persist_without_document_changes(qtbot,tmp_path):
    path=str(tmp_path/'saved.ini')
    w=MainWindow(settings=QSettings(path,QSettings.IniFormat));qtbot.addWidget(w)
    w.grid_color.setCurrentText('Purple')
    w.grid_scale_action.setChecked(True);w.grid_fade_action.setChecked(True)
    settings=QSettings(path,QSettings.IniFormat)
    assert settings.value('grid/v1/color')=='Purple'
    other=MainWindow(settings=settings);qtbot.addWidget(other)
    assert other.grid_color.currentText()=='Purple'
    assert other.grid_scale_action.isChecked() and other.grid_fade_action.isChecked()


def test_face_sketch_labels_render_and_resize(qtbot):
    import numpy as np
    from test_sketch_visibility import capture
    w=window(qtbot);d=w.document;v=w.viewport
    sid=d.add_face_sketch(FaceReference(d.features[0].id,'+X'))
    w.refresh()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)])
    w.edit_sketch()
    v.renderer.GetActiveCamera().SetParallelScale(30)
    plain=capture(v)
    w.grid_scale_action.setChecked(True)
    labelled=capture(v)
    assert np.count_nonzero(np.max(abs(labelled-plain),axis=2)>5)>50
    g=v.sketch.guides
    assert g.label_data and len(g.labels)<=32
    v.setFixedSize(480,360)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert g.label_data
    for *_,box in g.label_data:
        assert 0<=box[0]<box[2]<480 and 0<=box[1]<box[3]<360

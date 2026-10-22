import numpy as np
import pytest
from PySide6.QtCore import Qt
from star_cad.features import BoxParameters
from star_cad.sketch import Circle,FaceReference
from star_cad.geometry import volume
from test_sketch_ui import window,pixel
from test_booleans import cylinder


def choose(combo,data):
    combo.setCurrentIndex(combo.findData(data))


def test_combine_context_explicit_target_preview_cancel_apply(qtbot):
    w=window(qtbot)
    w.document.set_box(BoxParameters(10,10,10))
    _,_,eid=cylinder(w.document)
    w.refresh(fit=True)
    box=w.document.features[0].id
    w.browser.setCurrentItem(w.browser_items[('box',box)])
    w.browser_items[('extrude',eid)].setSelected(True)
    menu=w.context_menu(('box',box))
    assert 'Combine…' in [a.text() for a in menu.actions()]
    w.combine_selected()
    panel=w.operation_panel
    assert panel.active
    choose(panel.operation,'cut')
    choose(panel.target,box)
    before=w.document.features
    assert panel.preview()
    assert panel.actor.GetVisibility() and not w.viewport.mapper.GetInput().GetNumberOfCells()
    assert w.document.features==before
    panel.cancel()
    assert not panel.actor.GetVisibility() and w.document.features==before
    assert w.viewport.mapper.GetInput().GetNumberOfCells()>0
    w.combine_selected()
    choose(panel.operation,'cut');choose(panel.target,box)
    assert panel.preview() and panel.commit()
    result=w.document.features[-1]
    assert result.type=='boolean' and w.document.active_body_ids=={result.id}
    assert 'historical' in w.browser_items[('extrude',eid)].text(0)
    assert 'Target:' in w.property_info.text()
    w.undo(); assert w.document.features==before
    w.redo(); assert result.id in w.document.active_body_ids


def test_cut_through_panel_mode_switch_and_edit(qtbot,tmp_path):
    w=window(qtbot)
    d=w.document
    d.set_box(BoxParameters(20,20,10));box=d.features[0].id
    sid=d.add_face_sketch(FaceReference(box,'+Z'))
    circle=Circle(10,10,2);d.add_entity(sid,circle)
    w.refresh()
    w.operation_panel.open(source=(sid,circle.id,()))
    p=w.operation_panel
    choose(p.operation,'cut');choose(p.target,box)
    p.distance.setValue(-5)
    assert p.preview() and p.commit()
    eid=d.features[-1].id
    assert volume(d.solid_shapes[eid])==pytest.approx(4000-20*np.pi)
    w.edit_operation()
    choose(p.extent,'through_all');choose(p.direction,-1)
    assert p.preview() and p.commit()
    d.set_box(BoxParameters(20,20,25));w.refresh()
    assert volume(d.solid_shapes[eid])==pytest.approx(10000-100*np.pi)
    d.save(tmp_path/'through.starcad')


@pytest.mark.parametrize('mode',['Shaded with CAD Edges','Shaded','CAD Wireframe','Mesh Debug'])
def test_display_modes_keys_picking_and_regeneration(qtbot,mode):
    w=window(qtbot);v=w.viewport
    v.orient('Front')
    w.display_actions[mode].trigger()
    before=w.document.features
    if mode=='CAD Wireframe':
        assert not v.actor.GetVisibility() and v.edge_actor.GetVisibility()
    elif mode=='Mesh Debug':
        assert v.actor.GetProperty().GetRepresentation()==1 and not v.edge_actor.GetVisibility()
    else:
        assert v.actor.GetProperty().GetRepresentation()==2
        assert bool(v.edge_actor.GetVisibility())==(mode=='Shaded with CAD Edges')
    for key in (Qt.Key_W,Qt.Key_S,Qt.Key_P):
        qtbot.keyClick(v,key)
        assert v.display_mode==mode
        assert v.actor.GetProperty().GetRepresentation()==(1 if mode=='Mesh Debug' else 2)
    point=pixel(v,(20,0,10))
    qtbot.mouseClick(v,Qt.LeftButton,pos=point)
    assert v.selection and v.selection.kind=='face'
    assert v.face_pick_at(*v.renderer.GetDisplayPoint()[:2]) is not None
    v.set_selection_mode('edge')
    edgepoint=pixel(v,(0,0,10))
    qtbot.mouseClick(v,Qt.LeftButton,pos=edgepoint)
    assert v.selection and v.selection.kind=='edge'
    assert w.document.features==before
    w.document.set_box(BoxParameters(41,30,20));w.refresh()
    assert v.display_mode==mode and v.actor.GetProperty().GetRepresentation()==(1 if mode=='Mesh Debug' else 2)


def test_operation_preview_and_modes_nonblank_render(qtbot):
    from test_sketch_visibility import capture
    w=window(qtbot)
    v=w.viewport
    images={}
    for mode in w.display_actions:
        w.display_actions[mode].trigger()
        images[mode]=capture(v)
        background=np.array(v.renderer.GetBackground())*255
        assert np.count_nonzero(np.max(abs(images[mode]-background),axis=2)>10)>100
    assert np.count_nonzero(np.max(abs(images['CAD Wireframe']-images['Mesh Debug']),axis=2)>10)>100
    w.document.set_box(BoxParameters(10,10,10));box=w.document.features[0].id
    _,_,eid=cylinder(w.document)
    w.refresh(fit=True)
    w.operation_panel.open(bodies=(box,eid))
    assert w.operation_panel.preview()
    preview=capture(v)
    orange=(preview[:,:,0]>preview[:,:,2]+25)&(preview[:,:,0]>100)
    assert np.count_nonzero(orange)>100
    w.operation_panel.cancel()

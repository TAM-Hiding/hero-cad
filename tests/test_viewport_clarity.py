"""PR26: presentation metadata, real commit paths, grid raster and CAD-edge depth."""
from dataclasses import replace
from math import log10
import json
import numpy as np
import pytest
from PySide6.QtCore import Qt, QPoint, QSettings
from hero_cad.document import Document
from hero_cad.persistence import serialize, deserialize
from hero_cad.sketch import Circle, Rectangle, Slot, FaceReference
from hero_cad.geometry import volume
from test_sketch_ui import window, enter, click, pixel
from test_sketch_visibility import capture
from test_extrusion_quick_ui import open_quick


def test_visibility_metadata_is_not_evaluation_and_roundtrips(tmp_path):
    d=Document();sid=d.add_sketch('XY');c=Circle(0,0,5);d.add_entity(sid,c)
    ext=d.add_extrusion(sid,c.id,(),8)
    bodies=d.solid_shapes;faces=d.face_maps;mass=volume(d.shape);old=d.features
    d.set_sketch_visibility(sid,False)
    assert d.solid_shapes is bodies and d.face_maps is faces
    assert volume(d.shape)==mass and d.statuses[ext].valid
    assert not d.feature(sid).sketch_visible and d.feature(sid).parameters==old[1].parameters
    payload=serialize(d.features);assert payload['version']==11
    assert deserialize(payload)==d.features
    d.save(tmp_path/'hidden.starcad');loaded=Document.load(d.path)
    assert loaded.features==d.features and volume(loaded.shape)==pytest.approx(mass)
    d.undo();assert d.features==old
    d.redo();assert not d.feature(sid).sketch_visible and d.statuses[ext].valid
    # Legacy documents have no display metadata and remain visible.
    assert all(f.sketch_visible for f in deserialize(serialize(old)))
    for value in (None,0,'false'):
        bad=json.loads(json.dumps(payload));bad['features'][1]['sketch_visible']=value
        with pytest.raises(ValueError):deserialize(bad)
    bad=json.loads(json.dumps(payload));bad['version']=10
    with pytest.raises(ValueError):deserialize(bad)


@pytest.mark.parametrize('operation,depth',[('new',3),('join',-3),('cut',3),('intersect',3)])
@pytest.mark.parametrize('auto_hide',[False,True])
def test_success_only_auto_hide_one_transaction(qtbot,operation,depth,auto_hide):
    w,p,sid,c=open_quick(qtbot)
    w.auto_hide_sketches.setChecked(auto_hide)
    box=w.document.features[0].id
    p.operation.setCurrentIndex(p.operation.findData(operation))
    if operation!='new':p.target.setCurrentIndex(p.target.findData(box))
    before=w.document.features;count=len(w.document._undo)
    p.quick_distance.setText(str(depth))
    # Preview never changes the visibility flag.
    assert p.preview() and w.document.features==before
    assert p.commit()
    assert w.document.feature(sid).sketch_visible is not auto_hide
    assert len(w.document._undo)==count+1 and w.document.statuses[w.document.features[-1].id].valid
    assert all(row[0]!=sid for row in w.viewport.sketch.mapping) is auto_hide
    after=w.document.features;w.undo();assert w.document.features==before
    w.redo();assert w.document.features==after


def test_cancel_invalid_and_failed_preview_leave_visibility(qtbot):
    w,p,sid,c=open_quick(qtbot);before=w.document.features
    p.quick_distance.setText('nan');assert not p.apply_input()
    assert w.document.features==before
    p.operation.setCurrentIndex(p.operation.findData('cut'));p.quick_distance.setText('-4')
    assert not p.preview()  # Negative Cut only touches the bottom plane and removes no volume.
    assert w.document.features==before and w.document.feature(sid).sketch_visible
    p.cancel();assert w.document.features==before


def toggle(qtbot,w,sid):
    item=w.browser_items[('sketch',sid)]
    w.browser.scrollToItem(item)
    rect=w.browser.visualItemRect(item)
    x=w.browser.columnViewportPosition(1)+w.browser.columnWidth(1)//2
    qtbot.mouseClick(w.browser.viewport(),Qt.LeftButton,pos=QPoint(x,rect.center().y()))


def test_browser_visibility_preserves_selection_and_edit_override(qtbot,tmp_path):
    w=window(qtbot);sid=enter(w,'XY');c=Circle(0,0,3);w.document.add_entity(sid,c);w.refresh();w.finish_sketch()
    other=w.document.add_sketch('YZ');w.document.add_entity(other,Circle(0,0,2));w.refresh()
    selected=w.browser_items[('sketch',other)];w.browser.setCurrentItem(selected)
    before=w.browser_key;selection=w.selected_keys();shape=w.document.shape
    toggle(qtbot,w,sid)
    assert w.browser_key==before and w.selected_keys()==selection
    assert w.document.shape is shape and not w.document.feature(sid).sketch_visible
    assert not any(row[0]==sid for row in w.viewport.sketch.mapping)
    assert any(row[0]==other for row in w.viewport.sketch.mapping)
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)]);w.edit_sketch()
    assert any(row[0]==sid for row in w.viewport.sketch.mapping)
    assert not w.document.feature(sid).sketch_visible
    click(qtbot,w.viewport,w.document.feature(sid).parameters.frame,(3,0))
    assert w.viewport.sketch.entity_id==c.id
    w.finish_sketch();assert not any(row[0]==sid for row in w.viewport.sketch.mapping)
    w.edit_sketch();toggle(qtbot,w,sid);w.finish_sketch()
    assert w.document.feature(sid).sketch_visible and any(row[0]==sid for row in w.viewport.sketch.mapping)
    w.document.save(tmp_path/'shown.starcad');assert Document.load(w.document.path).feature(sid).sketch_visible


@pytest.mark.parametrize('plane',['XY','XZ','YZ'])
def test_grid_raster_width_uniformity_and_exact_spacing(qtbot,plane):
    w=window(qtbot);sid=enter(w,plane);v=w.viewport;g=v.sketch.guides
    w.show_base_box.setChecked(False);w.axes_action.setChecked(False);w.tool_island.hide()
    v.sketch.origin_actor.VisibilityOff();w.auto_grid_action.setChecked(False)
    w.manual_grid_spacing.setValue(1);frame=w.document.feature(sid).parameters.frame
    camera=v.renderer.GetActiveCamera();camera.SetFocalPoint(*frame.origin)
    camera.SetPosition(*(frame.origin[i]+100*frame.normal[i] for i in range(3)))
    for size in ((714,677),(883,521)):
        v.setFixedSize(*size)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        for scale in (19.37,22.123,35.71):
            camera.SetParallelScale(scale);g.update();v.clamp_zoom();pixels=capture(v)
            h,width,_=pixels.shape;ppm=h/(2*scale)
            # Sample separate vertical minor lines away from every intersection.
            strengths=[];widths=[]
            for index in range(-8,9):
                if index==0:continue
                v.renderer.SetWorldPoint(*frame.to_world((index,.43)),1);v.renderer.WorldToDisplay()
                x,y,_=v.renderer.GetDisplayPoint();x,y=round(x),round(y)
                row=pixels[y,x-3:x+4].mean(axis=1)
                strengths.append(row.max());widths.append(np.count_nonzero(row>45))
            assert np.ptp(strengths)<=2, (size,scale,strengths)
            assert set(widths)=={1}, widths
            # Major zero line is two physical pixels, without an intersection bump.
            v.renderer.SetWorldPoint(*frame.to_world((0,.43)),1);v.renderer.WorldToDisplay()
            x,y,_=v.renderer.GetDisplayPoint();x,y=round(x),round(y)
            assert np.count_nonzero(pixels[y,x-3:x+4].mean(axis=1)>70)==2
            assert g.grid_actor.GetProperty().GetOpacity()==g.minor_actor.GetProperty().GetOpacity()==1
            assert g.grid_actor.GetProperty().GetLineWidth()==2 and g.minor_actor.GetProperty().GetLineWidth()==1
            # The source lattice is still at exact model coordinates.
            for mapper in (g.grid_mapper,g.minor_mapper):
                mesh=mapper.GetInput()
                for i in range(mesh.GetNumberOfCells()):
                    cell=mesh.GetCell(i);a,b=(frame.to_local(mesh.GetPoint(cell.GetPointId(j))) for j in (0,1))
                    value=a[0] if abs(a[0]-b[0])<1e-8 else a[1]
                    assert value==pytest.approx(round(value))
    # Oblique and tilted views still render a nonblank lattice with bounded density.
    for angle in (.25,32,57):
        camera.Azimuth(angle);camera.Elevation(angle/2);g.update()
        image=capture(v);assert np.count_nonzero(np.max(image,axis=2)>65)>500


def test_automatic_intervals_labels_and_preferences(qtbot,tmp_path):
    w=window(qtbot);sid=enter(w,'XY');g=w.viewport.sketch.guides;c=w.viewport.renderer.GetActiveCamera()
    w.grid_scale_action.setChecked(True)
    for scale in (.001,.018,.4,3,11,37,130,1000):
        c.SetParallelScale(scale);g.update();power=10**np.floor(log10(g.major_spacing))
        assert g.major_spacing/power==pytest.approx(round(g.major_spacing/power))
        assert round(g.major_spacing/power) in (1,2,5)
        assert g.major_spacing==pytest.approx(10*g.spacing)
        for label in g.labels:
            if label.GetVisibility():
                text=label.GetInput();assert ':' not in text and 'mm' not in text
                assert np.isfinite(float(text))
    assert any(value<0 for _,value,_,_ in g.label_data)
    w.contrast_actions['Always'].trigger();w.auto_hide_sketches.setChecked(False)
    from hero_cad.ui.main_window import MainWindow
    other=MainWindow(settings=QSettings(w.preferences.fileName(),QSettings.IniFormat));qtbot.addWidget(other)
    assert other.viewport.contrast_mode=='Always' and not other.auto_hide_sketches.isChecked()


@pytest.mark.parametrize('xray',['Off','Celadon','Orange'])
def test_contrast_auto_views_preserves_depth_sketch_and_selection(qtbot,xray):
    w=window(qtbot);d=w.document;v=w.viewport
    sid=d.add_sketch('XY');outer=Rectangle(-15,-12,30,24);hole=Circle(-7,0,2);slot=Slot(2,0,1.5,6)
    for entity in (outer,hole,slot):d.add_entity(sid,entity)
    eid=d.add_extrusion(sid,outer.id,(hole.id,slot.id),8)
    d.set_sketch_visibility(sid,False)
    # A blind Boolean pocket supplies additional actual solid boundaries.
    pocket=d.add_face_sketch(FaceReference(eid,'end'));rect=Rectangle(-3,6,6,3);d.add_entity(pocket,rect)
    d.add_extrusion(pocket,rect.id,(),-3,operation='cut',target_id=eid);d.set_sketch_visibility(pocket,False)
    w.refresh();w.xray_choice.setCurrentText(xray);w.axes_action.setChecked(False)
    for normal,up in (((0,0,1),(0,1,0)),((0,-1,0),(0,0,1)),((1,0,0),(0,0,1))):
        camera=v.renderer.GetActiveCamera();camera.SetFocalPoint(0,0,4);camera.SetPosition(*(40*n+o for n,o in zip(normal,(0,0,4))));camera.SetViewUp(*up);camera.SetParallelScale(23)
        w.contrast_actions['Auto'].trigger();assert v.high_contrast()
        v.clamp_zoom()
        high=capture(v);assert np.ptp(high)>100
        selection_color=v.highlight_actor.GetProperty().GetColor()
        w.contrast_actions['Off'].trigger();assert not v.high_contrast()
        low=capture(v)
        assert np.count_nonzero(np.max(abs(high-low),axis=2)>3)>50
        assert v.highlight_actor.GetProperty().GetColor()==selection_color
        assert v.edge_actor.GetProperty().GetLineWidth()==1
        assert v.actor.GetProperty().GetOpacity()==(1 if xray=='Off' else .85)
    camera.SetPosition(40,-40,40);camera.SetViewUp(0,0,1)
    w.contrast_actions['Auto'].trigger();assert not v.high_contrast()
    w.contrast_actions['Always'].trigger();assert v.high_contrast()
    w.browser.setCurrentItem(w.browser_items[('sketch',sid)]);w.edit_sketch()
    w.contrast_actions['Auto'].trigger();assert v.high_contrast()
    assert v.sketch.foreground_actor.GetProperty().GetColor()==pytest.approx((.4,.85,.95))


def test_high_contrast_does_not_reveal_edges_behind_opaque_body(qtbot):
    w=window(qtbot);d=w.document;v=w.viewport
    sid=d.add_sketch('XY');circle=Circle(20,15,5);d.add_entity(sid,circle)
    d.add_extrusion(sid,circle.id,(),4);d.set_sketch_visibility(sid,False);w.refresh()
    w.show_base_box.setChecked(True);w.axes_action.setChecked(False);w.tool_island.hide()
    c=v.renderer.GetActiveCamera();c.SetPosition(20,15,100);c.SetFocalPoint(20,15,10);c.SetViewUp(0,1,0);c.SetParallelScale(25)
    w.contrast_actions['Always'].trigger();v.clamp_zoom()
    edges=capture(v);v.edge_actor.VisibilityOff();without=capture(v)
    # Cylinder is entirely behind the opaque box; no internal edge may leak.
    x,y=pixel(v,(20,15,20)).toTuple();h=edges.shape[0];y=h-1-y
    assert np.max(abs(edges[y-45:y+45,x-45:x+45]-without[y-45:y+45,x-45:x+45]))<=1
    assert np.count_nonzero(np.max(abs(edges-without),axis=2)>3)>50  # Real outer edges remain.


def test_original_translucent_grid_accumulated_at_crossings(qtbot,monkeypatch):
    w=window(qtbot);sid=enter(w,'XY');v=w.viewport;g=v.sketch.guides
    w.show_base_box.setChecked(False);w.axes_action.setChecked(False);w.tool_island.hide();v.sketch.origin_actor.VisibilityOff()
    w.auto_grid_action.setChecked(False);w.manual_grid_spacing.setValue(1)
    frame=w.document.feature(sid).parameters.frame;c=v.renderer.GetActiveCamera()
    c.SetFocalPoint(0,0,0);c.SetPosition(0,0,100);c.SetViewUp(0,1,0);c.SetParallelScale(19.37);v.clamp_zoom();g.update()
    corrected=capture(v)
    monkeypatch.setattr(g,'update',lambda:None)
    for actor,rgb in ((g.grid_actor,g.COLORS[g.color]),(g.minor_actor,tuple(.65*c for c in g.COLORS[g.color]))):
        actor.GetProperty().SetColor(*rgb);actor.GetProperty().SetOpacity(.4);actor.GetProperty().SetLineWidth(1)
        actor.GetShaderProperty().GetVertexCustomUniforms().SetUniformf('gridAlign',0.)
    original=capture(v)
    def strength(image,local):
        v.renderer.SetWorldPoint(*frame.to_world(local),1);v.renderer.WorldToDisplay()
        x,y,_=v.renderer.GetDisplayPoint();x,y=round(x),round(y)
        return image[y-2:y+3,x-2:x+3].mean(axis=2).max()
    assert strength(original,(3,4))>strength(original,(3,4.43))+10
    assert abs(strength(corrected,(3,4))-strength(corrected,(3,4.43)))<=2


def test_auto_contrast_uses_actual_compound_face_normal(qtbot):
    from test_face_view import angled_window
    w,shape,world,normal=angled_window(qtbot);v=w.viewport;c=v.renderer.GetActiveCamera()
    assert not v.high_contrast()
    focus=world((20,15,20));c.SetFocalPoint(*focus)
    c.SetPosition(*(focus[i]+100*normal[i] for i in range(3)))
    assert v.high_contrast() and not any(abs(x)>.99 for x in normal)
    v.clamp_zoom();assert np.ptp(capture(v))>100
    c.Azimuth(12);assert not v.high_contrast()

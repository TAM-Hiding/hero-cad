"""Focused reproduction of unwanted native stereo and circle entry semantics."""
from dataclasses import replace
from math import pi
import pytest
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Plane
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.geometry import volume
from hero_cad.booleans import bounds
from hero_cad.face_history import subshapes
from hero_cad.sketch import Circle, FaceReference, Slot
from test_sketch_ui import window, enter, pixel, hover


def capture(v):
    v.GetRenderWindow().Render()
    snapshot = vtkWindowToImageFilter()
    snapshot.SetInput(v.GetRenderWindow())
    snapshot.ReadFrontBufferOff()
    snapshot.Update()
    return vtk_to_numpy(snapshot.GetOutput().GetPointData().GetScalars()).copy()


def actors(v):
    return tuple(tuple(renderer.GetActors().GetItemAsObject(i).GetAddressAsString('')
                       for i in range(renderer.GetActors().GetNumberOfItems()))
                 for renderer in (v.renderer, v.sketch_renderer))


def test_unclaimed_three_never_enables_native_stereo_or_changes_framebuffer(qtbot):
    w = window(qtbot)
    w.show_base_box.setChecked(True)
    v, doc = w.viewport, w.document
    v.orient('Isometric')
    v.setFocus()
    before, inventory = capture(v), actors(v)
    state = doc.features, doc.shape, doc._undo[:], doc._redo[:]
    qtbot.keyClick(v, Qt.Key_3)
    after = capture(v)
    assert not v.GetRenderWindow().GetStereoRender()
    assert np.array_equal(before, after)
    # Shaded stock-box faces can be dim in isometric view. Require the actual
    # blue/green solid palette, excluding the dark background and RGB axes.
    rgb = after.astype(int)
    assert np.count_nonzero((rgb[:, 0] > 65) & (rgb[:, 1] > rgb[:, 0]+5)
                            & (rgb[:, 2] > rgb[:, 0]+10)) > 500
    assert actors(v) == inventory
    assert (doc.features, doc.shape, doc._undo, doc._redo) == state


def assembly():
    doc = Document(BoxParameters(60, 40, 5))
    plate = doc.features[0].id
    posts = []
    for x in (15, 35):
        sid = doc.add_face_sketch(FaceReference(plate, '+Z'))
        circle = Circle(x, 15, 3)
        doc.add_entity(sid, circle)
        posts.append(doc.add_extrusion(sid, circle.id, distance=10))
    sid = doc.add_face_sketch(FaceReference(posts[0], 'end'))
    slot = Slot(15, 15, 4, 20, 0)
    doc.add_entity(sid, slot)
    handle = doc.add_extrusion(sid, slot.id, distance=4, operation='join', target_id=posts[0])
    top = next(TopoDS.Face_s(f) for f in subshapes(doc.solid_shapes[handle], TopAbs_FACE)
               if BRepAdaptor_Surface(TopoDS.Face_s(f)).GetType() == GeomAbs_Plane
               and abs(bounds(f)[4]-19) < 1e-7 and abs(bounds(f)[5]-19) < 1e-7)
    sid = doc.add_face_sketch(doc.face_reference(top))
    rod = Circle(25, 15, 2)
    doc.add_entity(sid, rod)
    assert len(doc.active_body_ids) == 3
    return doc, handle, sid, rod


def normal(v, inventory, xray):
    assert not v.GetRenderWindow().GetStereoRender()
    assert v.renderer.GetBackground() == pytest.approx((.09, .12, .16))
    assert v.actor.GetProperty().GetColor() == pytest.approx((1., .65, .15) if xray == 'Orange' else (.65, .79, .86))
    assert v.GetRenderWindow().GetNumberOfLayers() == 2
    assert v.renderer.GetLayer() == 0 and v.sketch_renderer.GetLayer() == 1
    assert actors(v) == inventory
    assert not v.sketch.preview_actor.GetVisibility() and not v.support_actor.GetVisibility()
    assert np.count_nonzero(capture(v)[:, 1] > 80) > 500


@pytest.mark.parametrize('xray', ['Off', 'Orange'])
@pytest.mark.parametrize('case', ['cancel_valid', 'cancel_invalid', 'fail_then_new', 'fail_then_delete', 'join'])
def test_multibody_join_preview_recovery_and_continued_modeling(qtbot, xray, case):
    w = window(qtbot)
    doc, handle, sid, rod = assembly()
    w.document = doc
    w.refresh(fit=True)
    v = w.viewport
    v.set_xray_mode(xray)
    # Enter/exit the supporting-face sketch before the operation, as in modeling.
    v.sketch.enter(sid)
    assert v.support_actor.GetVisibility()
    v.sketch.finish()
    inventory = actors(v)
    v.select_face(v.faces[0])
    original, shape, stacks = doc.features, doc.shape, (doc._undo[:], doc._redo[:])
    panel = w.operation_panel
    panel.open(source=(sid, rod.id, ()), quick=True)
    assert panel.operation.currentData() == 'join'
    if case in ('cancel_invalid', 'fail_then_new', 'fail_then_delete'):
        # A face-attached sketch may place material outside its support face.
        panel.cancel()
        doc.update_entity(sid, replace(rod, x=90))
        w.refresh(fit=True)
        original, shape, stacks = doc.features, doc.shape, (doc._undo[:], doc._redo[:])
        panel.open(source=(sid, rod.id, ()), quick=True)
    panel.quick_distance.setText('6')
    if case in ('cancel_valid', 'join'):
        assert panel.preview()
        assert doc.features is original and doc.shape is shape
        assert panel.actor.GetVisibility()
        if case == 'join':
            assert panel.commit()
            assert len(doc.active_body_ids) == 3
            assert BRepCheck_Analyzer(doc.shape).IsValid()
        else:
            panel.cancel()
            assert doc.features is original and doc.shape is shape
            assert (doc._undo, doc._redo) == stacks
    else:
        assert not panel.preview()
        assert panel.candidate is None and not panel.actor.GetVisibility()
        assert doc.features is original and doc.shape is shape
        assert (doc._undo, doc._redo) == stacks
        panel.cancel()
        if case == 'fail_then_new':
            doc.update_entity(sid, replace(rod, x=90, radius=1.5))
            w.refresh()
            panel.open(source=(sid, rod.id, ()), quick=True)
            panel.operation.setCurrentIndex(panel.operation.findData('new'))
            panel.quick_distance.setText('6')
            assert panel.apply_input()
            assert len(doc.active_body_ids) == 4
        elif case == 'fail_then_delete':
            doc.delete(features=(sid,))
            w.refresh()
            assert len(doc.active_body_ids) == 3
    normal(v, inventory, xray)
    assert not panel.actor.GetVisibility() and panel.candidate is None
    # Real picking maps remain native faces of the committed current bodies.
    for face in v.faces:
        assert any(any(face.IsSame(f) for f in subshapes(doc.solid_shapes[i], TopAbs_FACE))
                   for i in doc.active_body_ids)
    camera = v.renderer.GetActiveCamera()
    surface, wire = v.mapper.GetInput(), v.edge_mapper.GetInput()
    for _ in range(3):
        camera.Azimuth(2)
        p, f = camera.GetPosition(), camera.GetFocalPoint()
        camera.SetPosition(p[0]+.1, *p[1:])
        camera.SetFocalPoint(f[0]+.1, *f[1:])
        v.clamp_zoom()
        v.GetRenderWindow().Render()
    assert v.mapper.GetInput() is surface and v.edge_mapper.GetInput() is wire
    assert actors(v) == inventory


@pytest.mark.parametrize('mode', ['Radius', 'Diameter'])
@pytest.mark.parametrize('value', [1., 2.5, 4.99999, 9.99998, 10.])
def test_circle_radius_diameter_preview_kernel_properties_and_reopen(qtbot, tmp_path, mode, value):
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.activateWindow()
    QApplication.processEvents()
    v.sketch.set_tool('circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((8, 6))))
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    field = v.dimensions.input
    if mode == 'Diameter':
        qtbot.keyClick(field, Qt.Key_Tab)
    assert v.dimensions.names[v.dimensions.index] == mode
    qtbot.keyClicks(field, str(value))
    radius = value/2 if mode == 'Diameter' else value
    assert v.sketch.controller.tool.preview_entity.radius == radius
    assert not w.document.feature(sid).parameters.entities
    assert not v.GetRenderWindow().GetStereoRender()
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((8, 6))))
    qtbot.keyClick(field, Qt.Key_Return)
    circle = w.document.feature(sid).parameters.entities[-1]
    assert circle.radius == radius
    assert w.entity_context == (sid, circle.id)
    assert w.entity_fields['radius'].value() == pytest.approx(radius, abs=1e-9)
    edge = TopoDS.Edge_s(subshapes(w.document.sketch_shapes[sid], TopAbs_EDGE)[0])
    assert BRepAdaptor_Curve(edge).GetType() == GeomAbs_Circle
    assert BRepAdaptor_Curve(edge).Circle().Radius() == radius
    eid = w.document.add_extrusion(sid, circle.id, distance=3)
    assert volume(w.document.solid_shapes[eid]) == pytest.approx(pi*radius**2*3)
    b = bounds(w.document.solid_shapes[eid])
    assert b[1]-b[0] == pytest.approx(2*radius) and b[3]-b[2] == pytest.approx(2*radius)
    w.document.save(tmp_path/'circle.starcad')
    loaded = Document.load(w.document.path)
    assert loaded.features == w.document.features
    assert loaded.feature(sid).parameters.entities[-1].radius == radius


def test_numeric_three_is_still_a_radius_during_construction(qtbot):
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    v.sketch.set_tool('circle')
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((8, 6))))
    qtbot.keyClicks(v, '3')
    assert v.dimensions.editing and v.sketch.controller.tool.preview_entity.radius == 3
    assert not v.GetRenderWindow().GetStereoRender()
    qtbot.keyClick(v.dimensions.input, Qt.Key_Return)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((8, 6))))
    assert w.document.feature(sid).parameters.entities[-1].radius == 3


@pytest.mark.parametrize('entry', ['type', 'tab', 'click'])
def test_near_fit_radius_entry_paths_and_mode_reset(qtbot, entry):
    w = window(qtbot)
    sid = enter(w)
    v = w.viewport
    frame = w.document.feature(sid).parameters.frame
    w.activateWindow()
    QApplication.processEvents()
    v.sketch.set_tool('circle')
    # First create by Diameter, then use the same tool for a Radius entry.
    qtbot.mousePress(v, Qt.LeftButton, pos=pixel(v, frame.to_world((0, 0))))
    hover(v, pixel(v, frame.to_world((8, 6))))
    qtbot.keyClick(v, Qt.Key_Tab)
    qtbot.keyClick(v.dimensions.input, Qt.Key_Tab)
    qtbot.keyClicks(v.dimensions.input, '9.99998')
    qtbot.keyClick(v.dimensions.input, Qt.Key_Return)
    qtbot.mouseRelease(v, Qt.LeftButton, pos=pixel(v, frame.to_world((8, 6))))
    assert w.document.feature(sid).parameters.entities[-1].radius == 4.99999
    a, b = pixel(v, frame.to_world((20, 0))), pixel(v, frame.to_world((28, 6)))
    if entry == 'click':
        # A click/release at the center leaves the zero-radius attempt pending;
        # the visible editor can then be reached without holding a mouse button.
        qtbot.mouseClick(v, Qt.LeftButton, pos=a)
    else:
        qtbot.mousePress(v, Qt.LeftButton, pos=a)
    hover(v, b)
    assert v.dimensions.names[v.dimensions.index] == 'Radius'
    if entry == 'type':
        qtbot.keyClicks(v, '4')
        qtbot.keyClicks(v.dimensions.input, '.99999')
    else:
        if entry == 'tab':
            qtbot.keyClick(v, Qt.Key_Tab)
        else:
            qtbot.mouseClick(v.dimensions.input, Qt.LeftButton)
        assert 'Radius' in v.dimensions.input.placeholderText()
        qtbot.keyClicks(v.dimensions.input, '4.99999')
    assert v.sketch.controller.tool.preview_entity.radius == 4.99999
    assert not v.GetRenderWindow().GetStereoRender()
    qtbot.keyClick(v.dimensions.input, Qt.Key_Return)
    if entry != 'click':
        qtbot.mouseRelease(v, Qt.LeftButton, pos=b)
    assert len(w.document.feature(sid).parameters.entities) == 2
    assert all(c.radius == 4.99999 for c in w.document.feature(sid).parameters.entities)


@pytest.mark.parametrize('stage', ['input', 'conversion'])
def test_interrupted_multibody_preview_restores_and_next_operation_succeeds(qtbot, monkeypatch, stage):
    import hero_cad.ui.operation_panel as module
    w = window(qtbot)
    doc, _, sid, rod = assembly()
    w.document = doc
    w.refresh(fit=True)
    v, panel = w.viewport, w.operation_panel
    v.select_face(v.faces[0])
    inventory = actors(v)
    before, stacks = doc.features, (doc._undo[:], doc._redo[:])
    panel.open(source=(sid, rod.id, ()), quick=True)
    panel.quick_distance.setText('6')
    assert panel.preview()
    with monkeypatch.context() as patch:
        if stage == 'conversion':
            def interrupted(*args):
                raise ValueError('injected interrupted preview mesh preparation')
            patch.setattr(module, 'tessellate', interrupted)
        else:
            panel.quick_distance.setText('nan')
        assert not panel.preview()
    assert doc.features is before and (doc._undo, doc._redo) == stacks
    assert panel.candidate is None and panel.preview_surface is None and not panel.actor.GetVisibility()
    assert v.selection is not None and any(v.selection.shape.IsSame(face) for face in v.faces)
    panel.cancel()
    normal(v, inventory, 'Off')
    panel.open(source=(sid, rod.id, ()), quick=True)
    panel.operation.setCurrentIndex(panel.operation.findData('new'))
    panel.quick_distance.setText('6')
    assert panel.apply_input()
    assert len(doc.active_body_ids) == 4
    normal(v, inventory, 'Off')

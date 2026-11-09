from dataclasses import replace
from math import pi

import pytest
from PySide6.QtCore import Qt

from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.ui import profile_view
from test_intersection_profiles import lens_area, model
from test_sketch_ui import click, hover, pixel, window


@pytest.mark.parametrize('operation', ['cut', 'join'])
def test_cell_hover_selection_preview_and_commit(qtbot, monkeypatch, operation, tmp_path):
    w = window(qtbot)
    d, sid, a, b = model()
    w.document = d
    w.refresh(fit=True)
    v = w.viewport
    v.orient('Top')
    v.set_display_mode('CAD Wireframe')
    w.xray_choice.setCurrentText('Orange')
    w.palette_controller.set_color('sketch.profile', '#19DDAA')
    w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
    w.profile_action.setChecked(True)
    frame = d.feature(sid).parameters.frame
    calls = []
    evaluate = profile_view.regions

    def counted(parameters):
        calls.append(parameters)
        return evaluate(parameters)

    monkeypatch.setattr(profile_view, 'regions', counted)
    hover(v, pixel(v, frame.to_world((13, 10))))
    assert v.profiles.hovered and v.profiles.hover_actor.GetVisibility()
    assert v.profiles.hover_mapper.GetInput().GetNumberOfPolys() > 0
    assert v.profiles.hover_actor.GetProperty().GetColor() == v.profiles.actor.GetProperty().GetColor()
    assert v.profiles.hover_actor.GetProperty().GetOpacity() < v.profiles.actor.GetProperty().GetOpacity()
    hover(v, pixel(v, frame.to_world((14, 10))))
    assert len(calls) == 1
    click(qtbot, v, frame, (13, 10))
    lens = v.profiles.selection[1]
    assert lens.region_sources and not v.profiles.hover_actor.GetVisibility()
    assert v.profiles.mapper.GetInput().GetBounds()[:2] == pytest.approx((11, 15), abs=.05)
    click(qtbot, v, frame, (7, 10), Qt.ShiftModifier)
    assert len(v.profiles.selections) == 2
    assert len(calls) == 1
    w.extrude_action.trigger()
    panel = w.operation_panel
    panel.operation.setCurrentIndex(panel.operation.findData(operation))
    panel.target.setCurrentIndex(panel.target.findData(d.features[0].id))
    panel.distance.setValue(4 if operation == 'cut' else -4)
    assert panel.preview() and panel.actor.GetVisibility()
    assert panel.commit()
    extrusion = d.features[-1].id
    expected = 24000 + (-1 if operation == 'cut' else 1)*100*pi
    assert volume(d.solid_shapes[extrusion]) == pytest.approx(expected)
    assert len(d.feature(extrusion).parameters.profiles) == 2

    path = tmp_path/'intersection.hcad'
    d.save(path)
    w.document = Document.load(path)
    w.refresh(fit=True)
    w.document.update_entity(sid, replace(b, radius=5.25))
    w.refresh(fit=True)
    w.browser.setCurrentItem(w.browser_items[('sketch', sid)])
    if not w.profile_action.isChecked():
        w.profile_action.setChecked(True)
    click(qtbot, v, frame, (13, 10))
    assert v.profiles.selection[1].reference == lens.reference
    assert w.document.statuses[extrusion].valid

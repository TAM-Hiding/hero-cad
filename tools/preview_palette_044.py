"""Reproducible editor screenshots and bounded live-recolor measurements.

Run under Xvfb/software OpenGL: .venv/bin/python tools/preview_palette_044.py
Outputs are repository review assets; timings have no CI thresholds.
"""
import json
import os
from pathlib import Path
import platform
from statistics import median
import tempfile
from time import perf_counter
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from hero_cad.ui.main_window import MainWindow
from hero_cad.document import Document
from hero_cad.sketch import Circle, FaceReference
from hero_cad.persistence import serialize
from hero_cad.palette import PREFIX, ENABLED


def main():
    app = QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        w = MainWindow(settings=QSettings(temporary+'/prefs.ini',QSettings.IniFormat))
        w.resize(1400,900); w.show(); app.processEvents()
        sid = w.document.add_face_sketch(FaceReference(w.document.features[0].id,'+Z'))
        for x in (8,20,32): w.document.add_entity(sid,Circle(x,12,3))
        w.refresh(fit=True)
        w.viewport.sketch.enter(sid)
        w.profile_action.setChecked(True)
        v,c = w.viewport,w.palette_controller
        frame = w.document.feature(sid).parameters.frame
        for x in (8,20,32):
            v.renderer.SetWorldPoint(*frame.to_world((x,12)),1); v.renderer.WorldToDisplay()
            v.profiles.pick(*v.renderer.GetDisplayPoint()[:2],additive=True)
        colors = {'ui.background':'#252D33','browser.background':'#1E272E','properties.background':'#242C33',
                  'tools.background':'#253640','ui.text':'#E5EBE9','ui.secondary':'#B1C3C0','ui.heading':'#E4C694',
                  'controls.normal':'#35434B','controls.text':'#E8EFEC','controls.active':'#967246',
                  'controls.active_text':'#FFF0CB','controls.hover':'#4E6269','controls.disabled':'#29353C',
                  'controls.input':'#1B252D','controls.input_text':'#D7E5DE','controls.input_border':'#586E75',
                  'controls.selection':'#6F573B','controls.selection_text':'#FFF0CB','history.selection':'#6F573B',
                  'sketch.normal':'#71D4A2','sketch.active':'#71D4A2','sketch.profile':'#E7C88F',
                  'viewport.model':'#A6C9DB','xray.orange':'#CE8D36','xray.orange_highlight':'#FFE7AD',
                  'viewport.background':'#17202B','operation.preview':'#E7C88F','grid.major':'#728E86',
                  'grid.minor':'#4C645D','grid.labels':'#AEC5BA'}
        c.store.set_many({**{PREFIX+k:v for k,v in colors.items()},ENABLED:True})
        # All changes below must leave definition/history and disposable mesh identities alone.
        state = (w.document.features,w.document.shape,tuple(w.document._undo),serialize(w.document.features),
                 v.mapper,v.mapper.GetInput(),v.edge_mapper,v.profiles.selections,v.profiles.mapper.GetInput())
        original = Document._regenerate
        counts = {'geometry_evaluations':0,'solid_display_preparations':0}
        def forbidden(*a,**kw):
            counts['geometry_evaluations'] += 1
            raise AssertionError('Palette attempted geometry evaluation')
        Document._regenerate = forbidden
        prepare = v.prepare_shape
        def no_prepare(*a,**kw):
            counts['solid_display_preparations'] += 1
            raise AssertionError('Palette attempted solid display preparation')
        v.prepare_shape = no_prepare
        measurements = {}
        try:
            for key in ('viewport.background','sketch.active','properties.background'):
                values = []
                previous = c.colors()[key]
                for i in range(10):
                    start = perf_counter(); c.set_color(key, '#294138' if i%2 else '#172D35')
                    values.append((perf_counter()-start)*1000)
                c.set_color(key,previous)
                measurements[key] = {'median_ms':median(values),'samples_ms':values}
        finally:
            Document._regenerate = original
            v.prepare_shape = prepare
        assert state == (w.document.features,w.document.shape,tuple(w.document._undo),serialize(w.document.features),
                         v.mapper,v.mapper.GetInput(),v.edge_mapper,v.profiles.selections,v.profiles.mapper.GetInput())
        assets = Path('docs/images'); assets.mkdir(parents=True,exist_ok=True)
        app.processEvents(); v.GetRenderWindow().Render()
        assert w.screen().grabWindow(w.winId()).save(str(assets/'palette-044-modeling.png'))
        w.open_palette(); app.processEvents()
        w.palette_editor.resize(760,700); app.processEvents()
        assert w.palette_editor.grab().save(str(assets/'palette-044-editor.png'))
        report = {'python':platform.python_version(),'platform':platform.platform(),
                  'qt_platform':os.environ.get('QT_QPA_PLATFORM'),'software_gl':os.environ.get('LIBGL_ALWAYS_SOFTWARE'),
                  'feature_count':len(w.document.features),'sketch_entity_count':3,'samples_per_color':10,
                  'timings':measurements,**counts,'definitions_history_serialization_meshes_selection_unchanged':True}
        output = Path('docs/benchmarks/palette-044.json'); output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        w.hide()


if __name__ == '__main__': main()

"""Actual Normal/Orange/Celadon screenshots and appearance-only timing evidence.

Run from repository root under Xvfb: .venv/bin/python tools/preview_sketch_045.py
Uses the user's complete v1 reference in isolated temporary settings. No defaults
are changed; example overrides are configured only inside this harness window.
"""
from pathlib import Path
from statistics import median
from time import perf_counter
import json
import os
import platform
import tempfile
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from hero_cad.document import Document
from hero_cad.persistence import serialize
from hero_cad.sketch import Circle,FaceReference
from hero_cad.ui.main_window import MainWindow


def main():
    app=QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        w=MainWindow(settings=QSettings(temporary+'/prefs.ini',QSettings.IniFormat))
        w.resize(1500,950);w.show();app.processEvents()
        d,v,c=w.document,w.viewport,w.palette_controller
        sid=d.add_face_sketch(FaceReference(d.features[0].id,'+Z'))
        circles=[Circle(x,12,3) for x in (8,20,32)]
        for circle in circles:d.add_entity(sid,circle)
        reference=d.add_face_sketch(FaceReference(d.features[0].id,'+Z'))
        d.add_entity(reference,Circle(20,23,2))
        w.refresh(fit=True);v.sketch.enter(sid);w.update_actions()
        c.import_file('tests/fixtures/palettes/hero-palette-user-v1.json')
        for mode,line,selected in (('orange','#000000','#FFFFFF'),('celadon','#40D9E6','#FFA626')):
            for role,color in (('normal',line),('active',line),('selected',selected)):
                c.set_color(f'sketch.{mode}.{role}',color)
        w.grid_action.setChecked(False)
        w.preference_store.set('viewport/v1/sketch_face',False)
        w.tool_island.set_collapsed(True)
        frame=d.feature(sid).parameters.frame
        def display(local):
            v.renderer.SetWorldPoint(*frame.to_world(local),1);v.renderer.WorldToDisplay()
            return v.renderer.GetDisplayPoint()[:2]
        v.sketch.pick(*display((11,12)))
        v.profiles.pick(*display((20,12)))
        before=(d.features,d.shape,tuple(d._undo),tuple(d._redo),serialize(d.features),d.dirty,
                v.mapper,v.mapper.GetInput(),v.edge_mapper,v.sketch.mapper.GetInput(),
                v.profiles.selections,v.profiles.mapper.GetInput(),frozenset(v.sketch.entity_ids))
        counts={'geometry_evaluations':0,'solid_display_preparations':0}
        original=Document._regenerate;prepare=v.prepare_shape
        def no_geometry(*a,**kw):counts['geometry_evaluations']+=1;raise AssertionError('Unexpected geometry evaluation')
        def no_display(*a,**kw):counts['solid_display_preparations']+=1;raise AssertionError('Unexpected solid display preparation')
        Document._regenerate=no_geometry;v.prepare_shape=no_display
        assets=Path('docs/images');assets.mkdir(parents=True,exist_ok=True)
        timings={}
        try:
            for mode,name in (('Off','normal'),('Orange','orange'),('Celadon','celadon')):
                v.set_xray_mode(mode);app.processEvents();v.GetRenderWindow().Render()
                assert w.screen().grabWindow(w.winId()).save(str(assets/f'sketch-045-{name}.png'))
            w.open_palette();editor=w.palette_editor;editor.resize(920,850);editor.tabs.setCurrentIndex(2)
            app.processEvents()
            assert editor.grab().save(str(assets/'sketch-045-editor.png'))
            values=[]
            for mode in ('Off','Orange','Celadon')*4:
                start=perf_counter();v.set_xray_mode(mode);app.processEvents()
                values.append((perf_counter()-start)*1000)
            timings['mode_switch_editor_open']={'median_ms':median(values),'samples_ms':values}
            values=[]
            for i in range(10):
                start=perf_counter();c.set_color('sketch.celadon.active','#40D9E6' if i%2 else '#36B8C5');app.processEvents()
                values.append((perf_counter()-start)*1000)
            timings['context_color_editor_open']={'median_ms':median(values),'samples_ms':values}
            assert before==(d.features,d.shape,tuple(d._undo),tuple(d._redo),serialize(d.features),d.dirty,
                v.mapper,v.mapper.GetInput(),v.edge_mapper,v.sketch.mapper.GetInput(),
                v.profiles.selections,v.profiles.mapper.GetInput(),frozenset(v.sketch.entity_ids))
            assert counts=={'geometry_evaluations':0,'solid_display_preparations':0}
        finally:
            Document._regenerate=original;v.prepare_shape=prepare
        report={'python':platform.python_version(),'platform':platform.platform(),
                'qt_platform':os.environ.get('QT_QPA_PLATFORM'),'software_gl':os.environ.get('LIBGL_ALWAYS_SOFTWARE'),
                'feature_count':len(d.features),'entity_count':4,'palette_editor_open_during_timings':True,
                **counts,'definitions_history_serialization_meshes_selections_unchanged':True,'timings':timings}
        output=Path('docs/benchmarks/sketch-045.json');output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
        editor.hide();w.hide()


if __name__=='__main__':main()

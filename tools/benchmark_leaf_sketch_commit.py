"""PR34 CPU stage medians; run with PYTHONPATH=.:src, Qt offscreen.

Set PYTHONPATH=/path/to/baseline/src:. to measure an unchanged baseline using
this same script. Render is disabled: these are CPU measurements, not GPU FPS.
"""
import argparse
from collections import defaultdict
from statistics import median
from time import perf_counter
from PySide6.QtWidgets import QApplication
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from hero_cad.document import Document
from hero_cad.features import Feature
from hero_cad.sketch import Circle, Line, SketchParameters
from hero_cad.ui.main_window import MainWindow
from tools.profile_sketch_commit import fixture


def build(existing, count, boolean=False):
    if boolean:
        doc = Document()
        target = doc.features[0].id
        for i in range(8):
            sid = doc.add_sketch('XY')
            c = Circle(5 + (i % 4)*9, 7 + (i//4)*15, 2)
            doc.add_entity(sid, c)
            target = doc.add_extrusion(sid, c.id, distance=20, operation='cut', target_id=target)
        sid = doc.add_sketch('XY')
        for i in range(count):
            doc.add_entity(sid, Line(i*2, 50, i*2+1, 51))
        return doc, sid
    doc, sid = fixture((existing-1)//2, count)
    if existing % 2 == 0:
        extra = Feature('sketch', SketchParameters('XZ'), ('plane:XZ',))
        doc = Document(features=(*doc.features[:-1], extra, doc.features[-1]))
    assert len(doc.features)-1 == existing
    return doc, sid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=5)
    args = parser.parse_args()
    original = QVTKRenderWindowInteractor.__init__
    def no_gpu(self, *a, **kw):
        original(self, *a, **kw)
        self.GetRenderWindow().Render = lambda: None
    QVTKRenderWindowInteractor.__init__ = no_gpu
    app = QApplication([])
    w = MainWindow()
    print('case,entities,insertion_ms,regeneration_ms,sketch_build_ms,solid_display_ms,ui_sync_ms,total_ms', flush=True)
    for existing, count, boolean in [(1,10,False),(25,10,False),(75,10,False),
                                     (100,10,False),(75,50,False),(17,10,True)]:
        samples = defaultdict(list)
        for _ in range(args.samples):
            w.document, sid = build(existing, count, boolean)
            w.refresh()
            w.viewport.sketch.enter(sid)
            times = defaultdict(float)
            def wrap(owner, name, label):
                original = getattr(owner, name)
                def timed(*a, **kw):
                    start = perf_counter()
                    try:
                        return original(*a, **kw)
                    finally:
                        times[label] += (perf_counter()-start)*1000
                setattr(owner, name, timed)
                return original
            import hero_cad.document as module
            wrap(w.document, 'add_entity', 'document')
            wrap(w.document, '_regenerate', 'regeneration')
            wrap(w, 'display_solids', 'display')
            original_sketch = wrap(module, 'make_sketch', 'sketch')
            start = perf_counter()
            w.entity_created(Line(0, 60, 1, 61))
            total = (perf_counter()-start)*1000
            module.make_sketch = original_sketch
            # Restore the bound window method (avoid nested instrumentation).
            del w.display_solids
            regen_exclusive = times['regeneration']-times['sketch'] if times['regeneration'] else 0
            insertion = times['document']-times['regeneration']-(times['sketch'] if not times['regeneration'] else 0)
            values = (insertion, regen_exclusive, times['sketch'], times['display'],
                      total-times['document']-times['display'], total)
            assert len(w.document.feature(sid).parameters.entities) == count+1
            for key, value in zip(range(6), values):
                samples[key].append(value)
        print(','.join([str(existing)+('-cuts' if boolean else ''),str(count)] +
                       [f'{median(samples[k]):.3f}' for k in range(6)]), flush=True)
    w.viewport.Finalize()


if __name__ == '__main__':
    main()

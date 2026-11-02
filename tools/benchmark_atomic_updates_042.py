"""Compare real Properties edits using baseline/current src first in PYTHONPATH.

LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb PYTHONPATH=.:src xvfb-run -a \
 .venv/bin/python tools/benchmark_atomic_updates_042.py --output /tmp/atomic.json
No CI timing thresholds. Measurements include actual software-rendered refresh.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
from statistics import median
import sys
from time import perf_counter
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from hero_cad.document import Document
from hero_cad.ui.main_window import MainWindow
import hero_cad.ui.viewport as viewport
from tools.benchmark_audit_041 import model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--features', nargs='+', type=int, default=[5, 20, 50])
    parser.add_argument('--samples', type=int, default=3)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive')
    app = QApplication([])
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        w = MainWindow(settings=QSettings(str(Path(temp)/'preferences.ini'), QSettings.IniFormat))
        w.show()
        app.processEvents()
        result = {'environment': {'python': sys.version, 'platform': platform.platform(),
                  'qt_platform': os.environ.get('QT_QPA_PLATFORM'),
                  'software_gl': os.environ.get('LIBGL_ALWAYS_SOFTWARE'),
                  'samples': args.samples, 'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, 'cases': []}
        import OCP, PySide6, vtk
        result['environment'].update(ocp=OCP.__version__, qt=PySide6.__version__, vtk=vtk.vtkVersion.GetVTKVersion(),
                                     logical_cpus=os.cpu_count(), cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), 'unknown'))
        import hero_cad.document as document_module
        root = Path(document_module.__file__).parent
        result['environment']['source_sha256'] = {p: hashlib.sha256((root/p).read_bytes()).hexdigest()
                                                  for p in ('document.py', 'features.py', 'ui/main_window.py', 'ui/viewport.py', 'ui/sketch_view.py', 'ui/support_face.py', 'ui/operation_panel.py')}
        try:
            for count in args.features:
                w.document = model(count)
                w.refresh(fit=True)
                cut = next(f for f in reversed(w.document.features) if f.type == 'extrude' and f.parameters.operation == 'cut')
                w.entity_context, w.browser_key = ('extrude', cut.id), ('extrude', cut.id)
                w.show_properties()
                measurements, calls = defaultdict(list), defaultdict(list)
                history = {name: {'measurements': defaultdict(list), 'calls': defaultdict(list)} for name in ('undo', 'redo')}
                def measure(action):
                    timings, counts, originals = defaultdict(float), defaultdict(int), []
                    def wrap(owner, name, label):
                        native = getattr(owner, name)
                        def measured(*a, **kw):
                            start = perf_counter()
                            try:
                                return native(*a, **kw)
                            finally:
                                timings[label] += (perf_counter()-start)*1000
                                counts[label] += 1
                        originals.append((owner, name, native))
                        setattr(owner, name, measured)
                    wrap(Document, '_regenerate', 'regeneration')
                    wrap(viewport, 'tessellate', 'tessellation_conversion')
                    wrap(viewport, 'edge_mesh', 'edge_mesh')
                    if hasattr(Document, 'adopt_candidate'):
                        wrap(Document, 'adopt_candidate', 'candidate_publication')
                    start = perf_counter()
                    try:
                        action()
                        total = (perf_counter()-start)*1000
                    finally:
                        for owner, name, native in originals:
                            setattr(owner, name, native)
                    timings['total'] = total
                    timings['display_mesh_preparation'] = timings['tessellation_conversion']+timings['edge_mesh']
                    return timings, counts
                def record(data, measurements, calls):
                    timings, counts = data
                    for key in ('total','regeneration','tessellation_conversion','edge_mesh','display_mesh_preparation','candidate_publication'):
                        measurements[key].append(timings[key])
                        calls[key].append(counts[key])
                for i in range(args.samples):
                    value = 5.5 if i % 2 == 0 else 6.
                    w.entity_fields['distance'].setValue(value)
                    def apply():
                        assert w.apply_dimensions()
                    record(measure(apply), measurements, calls)
                    assert w.document.feature(cut.id).parameters.distance == value
                    for name in ('undo', 'redo'):
                        record(measure(getattr(w, name)), history[name]['measurements'], history[name]['calls'])
                    assert w.document.feature(cut.id).parameters.distance == value
                row = {'features': count, 'median_ms': {k: median(v) for k,v in measurements.items()},
                       'calls_per_edit': dict(calls),
                       'history': {name: {'median_ms': {k: median(v) for k,v in data['measurements'].items()},
                                          'calls': dict(data['calls'])} for name,data in history.items()},
                       'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                       'viewport_size': list(w.viewport.GetRenderWindow().GetSize())}
                from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
                from vtkmodules.util.numpy_support import vtk_to_numpy
                import numpy as np
                capture = vtkWindowToImageFilter()
                capture.SetInput(w.viewport.GetRenderWindow())
                capture.ReadFrontBufferOff()
                capture.Update()
                pixels = vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars())
                row['body_pixels'] = int(np.count_nonzero(np.all(pixels[:, :3] > 110, axis=1)))
                row['framebuffer_nonblank'] = row['body_pixels'] > 500
                if not row['framebuffer_nonblank']:
                    raise RuntimeError('Blank model framebuffer; rendered benchmark is invalid')
                result['cases'].append(row)
                args.output.write_text(json.dumps(result, indent=2)+'\n')
                print(json.dumps(row), flush=True)
        finally:
            w.viewport.Finalize()
            w.hide()


if __name__ == '__main__':
    main()

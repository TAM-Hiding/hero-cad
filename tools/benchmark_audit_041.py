"""Deterministic connected mechanical parts; no CI timing thresholds.

PYTHONPATH=.:src .venv/bin/python tools/benchmark_audit_041.py --output result.json
Add --viewport under Xvfb/a desktop to include real rendered navigation/picking.
"""
import argparse
from contextlib import contextmanager
import json
import hashlib
import os
import platform
from pathlib import Path
import resource
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter
from uuid import UUID, uuid5

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.TopoDS import TopoDS
from OCP.TopAbs import TopAbs_EDGE
from hero_cad.document import Document
from hero_cad.features import BoxParameters, ExtrudeParameters, Feature
from hero_cad.face_history import subshapes
from hero_cad.sketch import Circle, FaceReference, SketchParameters, Slot
from hero_cad.ui.display_geometry import tessellate, edge_mesh

NAMESPACE = UUID('c99b43a6-5041-4f39-9e19-0a0000000041')


def stable_id(label):
    return str(uuid5(NAMESPACE, label))


def upper_edges(doc, target, z):
    return tuple(e for e in subshapes(doc.solid_shapes[target], TopAbs_EDGE)
                 if all(abs(BRepAdaptor_Curve(TopoDS.Edge_s(e)).Value(t).Z()-z) < 1e-8
                        for t in (BRepAdaptor_Curve(TopoDS.Edge_s(e)).FirstParameter(),
                                  BRepAdaptor_Curve(TopoDS.Edge_s(e)).LastParameter())))


def slot_fin(radius=1., height=10.):
    """40×30×5 base; face-attached 12 mm center-distance slot, joined upward."""
    box = Feature('box', BoxParameters(40, 30, 5), id=stable_id('boundary-box'))
    doc = Document(features=(box,))
    sid = doc.add_face_sketch(FaceReference(box.id, '+Z'))
    slot = Slot(10, 10, radius, 12, 0, id=stable_id('boundary-slot'))
    doc.add_entity(sid, slot)
    target = doc.add_extrusion(sid, slot.id, distance=height, operation='join', target_id=box.id)
    _, refs = doc.edge_references(upper_edges(doc, target, 5+height))
    return doc, target, sid, slot, refs


def model(count):
    """One plate, joined rounded fin, grid of through holes, optional fin chamfer.

    A=5: one hole; B=20: eight; C=50: 23; D=100: 48. UUIDs,
    feature order and geometry are deterministic, including the final chamfer.
    Construction is one ordered evaluation plus the final reference-based bevel;
    it is not a simulation of repeated UI authoring transactions.
    """
    if count not in (5, 20, 50, 100):
        raise ValueError('Choose 5, 20, 50 or 100 features')
    box = Feature('box', BoxParameters(80, 70, 5), id=stable_id('plate'))
    slot = Slot(10, 62, 3, 45, 0, id=stable_id('fin-entity'))
    sketch = Feature('sketch', SketchParameters('FACE', entities=(slot,),
                     attachment=FaceReference(box.id, '+Z'),
                     attached_frame=SketchParameters('XY').frame), (box.id,), stable_id('fin-sketch'))
    fin = Feature('extrude', ExtrudeParameters(sketch.id, slot.id, distance=12,
                  operation='join', target_id=box.id), (sketch.id, box.id), stable_id('fin'))
    features, target = [box, sketch, fin], fin.id
    for i in range((count-3)//2):
        hole = Circle(5+(i % 8)*10, 5+(i//8)*8, 2, id=stable_id(f'hole-{i}'))
        source = Feature('sketch', SketchParameters('XY', entities=(hole,)),
                         ('plane:XY',), stable_id(f'sketch-{i}'))
        cut = Feature('extrude', ExtrudeParameters(source.id, hole.id, distance=5,
                      operation='cut', target_id=target), (source.id, target), stable_id(f'cut-{i}'))
        features.extend((source, cut))
        target = cut.id
    doc = Document(features=features)
    if len(features) < count:
        from hero_cad.features import ChamferParameters
        _, refs = doc.edge_references(upper_edges(doc, target, 17))
        bevel = Feature('chamfer', ChamferParameters(target, refs, .5), (target,), stable_id('bevel'))
        doc.set_features((*doc.features, bevel))
    assert len(doc.features) == count and all(s.valid for s in doc.statuses.values())
    return doc


def timed(call):
    start = perf_counter()
    value = call()
    return value, (perf_counter()-start)*1000


def feature_times(features):
    """Separate, instrumented evaluation. Line tracing adds overhead; not baseline."""
    code = Document._regenerate.__code__
    import inspect
    lines, start_line = inspect.getsourcelines(Document._regenerate)
    loop_line = start_line + next(i for i, line in enumerate(lines) if line.strip() == 'for feature in features:')
    rows, current, started, pending = [], None, None, False
    def trace(frame, event, arg):
        nonlocal current, started, pending
        if frame.f_code is not code:
            return None
        if (event == 'line' and frame.f_lineno == loop_line) or event == 'return':
            now = perf_counter()
            if current is not None:
                rows.append({'id': current.id, 'type': current.type, 'ms': (now-started)*1000})
            current, started, pending = None, now, event != 'return'
        elif event == 'line' and pending and 'feature' in frame.f_locals and frame.f_lineno > loop_line:
            current = frame.f_locals['feature']
            pending = False
        return trace
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        Document(features=features)
    finally:
        sys.settrace(previous)
    # The final exhausted-loop event still has the previous iteration's local.
    return rows[:len(features)]


@contextmanager
def counters():
    """Structural verification: viewport actions must not regenerate or remesh."""
    import hero_cad.ui.viewport as module
    originals, counts = {}, {'regeneration': 0, 'tessellation': 0, 'edge_mesh': 0}
    for owner, name, key in ((Document, '_regenerate', 'regeneration'),
                              (module, 'tessellate', 'tessellation'), (module, 'edge_mesh', 'edge_mesh')):
        original = getattr(owner, name)
        def wrap(*args, _original=original, _key=key, **kw):
            counts[_key] += 1
            return _original(*args, **kw)
        originals[owner, name] = original
        setattr(owner, name, wrap)
    try:
        yield counts
    finally:
        for (owner, name), value in originals.items():
            setattr(owner, name, value)


def viewport_metrics(doc, samples):
    from hero_cad.ui.viewport import Viewport
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from PySide6.QtWidgets import QApplication
    import numpy as np
    app = QApplication.instance() or QApplication([])
    view = Viewport()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    try:
        _, update = timed(lambda: view.set_shape(doc.shape, fit=True))
        camera = view.renderer.GetActiveCamera()
        navigation, selection, edge_selection = [], [], []
        with counters() as calls:
            for _ in range(samples):
                def navigate():
                    camera.Azimuth(3)
                    view.clamp_zoom()
                    view.GetRenderWindow().Render()
                navigation.append(timed(navigate)[1])
                selection.append(timed(lambda: view.pick_at(400, 300))[1])
                edge_selection.append(timed(lambda: view.edge_pick_at(400, 300))[1])
            view.set_xray_mode('Orange')
            view.set_display_mode('CAD Wireframe')
            view.set_display_mode('Shaded with CAD Edges')
        capture = vtkWindowToImageFilter()
        capture.SetInput(view.GetRenderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        pixels = vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars())
        nonblank = bool(np.any(pixels.max(axis=0)-pixels.min(axis=0) > 20))
        if not nonblank:
            raise RuntimeError('Blank framebuffer: rendered timings are not valid')
        return {'update_ms': update, 'orbit_render_ms': median(navigation),
                'face_selection_render_ms': median(selection), 'edge_pick_ms': median(edge_selection),
                'viewport_only_calls': calls, 'framebuffer_nonblank': nonblank,
                'size': list(view.GetRenderWindow().GetSize()),
                'render_capabilities': view.GetRenderWindow().ReportCapabilities()}
    finally:
        view.Finalize()
        view.close()


def run(count, samples, viewport):
    doc, construction = timed(lambda: model(count))
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)/'benchmark.starcad'
        doc.save(path)
        load, regen, mesh, native_mesh, conversion, wire = [], [], [], [], [], []
        for _ in range(samples):
            load.append(timed(lambda: Document.load(path))[1])
            fresh, ms = timed(lambda: Document(features=doc.features))
            regen.append(ms)
            # Every sample has fresh native geometry: no accidental warm mesh reuse.
            import hero_cad.ui.display_geometry as display
            original_mesher = display.BRepMesh_IncrementalMesh
            native_ms = 0.
            def measured_mesher(*args, **kwargs):
                nonlocal native_ms
                value, elapsed = timed(lambda: original_mesher(*args, **kwargs))
                native_ms += elapsed
                return value
            display.BRepMesh_IncrementalMesh = measured_mesher
            try:
                surface, ms = timed(lambda: tessellate(fresh.shape))
            finally:
                display.BRepMesh_IncrementalMesh = original_mesher
            mesh.append(ms)
            native_mesh.append(native_ms)
            conversion.append(ms-native_ms)
            edges, ms = timed(lambda: edge_mesh(fresh.shape))
            wire.append(ms)
    result = {'features': count, 'construction_ms': construction, 'load_ms': median(load),
              'regeneration_ms': median(regen), 'tessellation_conversion_ms': median(mesh),
              'native_mesher_ms': median(native_mesh), 'vtk_conversion_normals_ms': median(conversion),
              'edge_mesh_ms': median(wire), 'triangles': surface.GetNumberOfCells(),
              'edge_points': edges.GetNumberOfPoints(), 'feature_execution_instrumented': feature_times(doc.features),
              'process_peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
    if viewport:
        result['viewport'] = viewport_metrics(doc, max(samples, 5))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', nargs='+', type=int, default=[5, 20, 50, 100])
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--viewport', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive')
    import OCP, vtk, PySide6, numpy
    import hero_cad.document as document_module
    result = {'environment': {'platform': platform.platform(), 'python': sys.version,
              'ocp': OCP.__version__, 'vtk': vtk.vtkVersion.GetVTKVersion(), 'qt': PySide6.__version__,
              'numpy': numpy.__version__,
              'cpu': next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                           if line.startswith('model name')), platform.processor()), 'logical_cpus': os.cpu_count(),
              'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'qt_platform': os.environ.get('QT_QPA_PLATFORM'),
              'software_gl': os.environ.get('LIBGL_ALWAYS_SOFTWARE'),
              'surface_deflection_mm': .02, 'angular_deflection_rad': .08,
              'samples': args.samples}, 'cases': []}
    source_root = Path(document_module.__file__).parent
    result['environment']['source_sha256'] = {
        name: hashlib.sha256((source_root/name).read_bytes()).hexdigest()
        for name in ('document.py', 'chamfers.py', 'features.py', 'ui/display_geometry.py')}
    result['environment']['harness_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for count in args.features:
        row = run(count, args.samples, args.viewport)
        result['cases'].append(row)
        args.output.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k: v for k, v in row.items() if k not in ('feature_execution_instrumented', 'viewport')}), flush=True)


if __name__ == '__main__':
    main()

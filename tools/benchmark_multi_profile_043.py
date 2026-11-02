"""Six individual pockets versus one multi-profile Cut; no timing thresholds.

PYTHONPATH=src .venv/bin/python tools/benchmark_multi_profile_043.py --output report.json
Display preparation uses the real detached solid mesh, edge and picking-map path;
no render window is needed. Operation time includes feature evaluation/history.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import UUID, uuid5
from types import SimpleNamespace
import OCP
import PySide6
import vtk
from OCP.BRepCheck import BRepCheck_Analyzer
from hero_cad.document import Document
from hero_cad.features import Feature, BoxParameters, ProfileReference
from hero_cad.geometry import volume
from hero_cad.sketch import Circle, SketchParameters
from hero_cad.ui.viewport import Viewport


NS = UUID('c99b43a6-5041-4f39-9e19-0a0000000043')
def identifier(label): return str(uuid5(NS, label))


def model():
    circles = tuple(Circle(x, y, 2, id=identifier(f'circle-{x}-{y}'))
                    for y in (8, 20) for x in (6, 18, 30))
    box = Feature('box', BoxParameters(), id=identifier('box'))
    sketch = Feature('sketch', SketchParameters('XY', circles), ('plane:XY',), id=identifier('sketch'))
    return Document(features=(box, sketch)), sketch.id, box.id, circles


def timed(action):
    start = perf_counter()
    value = action()
    return (perf_counter()-start)*1000, value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1: parser.error('samples must be positive')
    result = {'environment': {'python': platform.python_version(), 'platform': platform.platform(),
              'ocp': OCP.__version__, 'qt': PySide6.__version__, 'vtk': vtk.vtkVersion.GetVTKVersion(),
              'samples': args.samples, 'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              'cases': {}}
    for multiple in (False, True):
        rows = []
        for _ in range(args.samples):
            d, sid, target, circles = model()
            def operate():
                current = target
                if multiple:
                    return d.add_multi_extrusion(sid, tuple(ProfileReference(c.id) for c in circles),
                                                 3, operation='cut', target_id=current)
                for c in circles:
                    current = d.add_extrusion(sid, c.id, distance=3, operation='cut', target_id=current)
                return current
            operation, eid = timed(operate)
            regeneration, regenerated = timed(lambda: Document(features=d.features))
            display, prepared = timed(lambda: Viewport.prepare_shape(SimpleNamespace(model_span=1), d.shape))
            assert prepared.mapper.GetInput().GetNumberOfCells() > 0
            assert BRepCheck_Analyzer(regenerated.shape).IsValid()
            assert abs(volume(regenerated.shape)-volume(d.shape)) < 1e-7
            rows.append({'operation_ms':operation, 'regeneration_ms':regeneration, 'display_preparation_ms':display})
        result['cases']['multi_profile' if multiple else 'individual'] = {
            'median_ms': {k:median(row[k] for row in rows) for k in rows[0]}, 'samples_ms':rows,
            'total_feature_count':len(d.features), 'extrusion_feature_count':sum(f.type == 'extrude' for f in d.features),
            'valid':BRepCheck_Analyzer(d.shape).IsValid(), 'volume_mm3':volume(d.shape)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()

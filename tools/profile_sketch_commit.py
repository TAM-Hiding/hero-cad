"""Run with .venv/bin/python tools/profile_sketch_commit.py; no CI timing limits."""
import cProfile
import pstats
from statistics import median
from time import perf_counter
from hero_cad.document import Document
from hero_cad.features import Feature, BoxParameters, ExtrudeParameters
from hero_cad.sketch import SketchParameters, Circle, Line


def fixture(pairs, count):
    features = [Feature('box', BoxParameters())]
    for i in range(pairs):
        circle = Circle(i * 6, 0, 2)
        sketch = Feature('sketch', SketchParameters('XY', entities=(circle,)), ('plane:XY',))
        features.extend((sketch, Feature('extrude', ExtrudeParameters(sketch.id, circle.id), (sketch.id,))))
    lines = tuple(Line(i * 2, 50, i * 2 + 1, 51) for i in range(count))
    active = Feature('sketch', SketchParameters('XY', entities=lines), ('plane:XY',))
    return Document(features=(*features, active)), active.id


def main():
    print('existing_features,active_entities,median_document_commit_ms')
    for pairs, count in [(0, n) for n in (10, 50, 100, 250)] + [(12, 10), (37, 10)]:
        samples = []
        for _ in range(5):
            doc, sid = fixture(pairs, count)
            start = perf_counter()
            doc.add_entity(sid, Line(0, 60, 1, 61))
            samples.append((perf_counter() - start) * 1000)
            assert doc.can_undo and all(s.valid for s in doc.statuses.values())
        print(f'{1+2*pairs},{count},{median(samples):.3f}', flush=True)
    doc, sid = fixture(37, 10)
    profiler = cProfile.Profile()
    profiler.runcall(doc.add_entity, sid, Line(0, 60, 1, 61))
    pstats.Stats(profiler).strip_dirs().sort_stats('cumulative').print_stats(20)


if __name__ == '__main__':
    main()

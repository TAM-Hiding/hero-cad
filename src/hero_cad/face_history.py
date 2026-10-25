"""Conservative Boolean face identity from OCCT ancestry and CAD adjacency.

No face order, triangulation, nearest-plane or centroid fallback participates.
Ambiguous neighborhoods are deliberately not published as attachment targets.
"""
from collections import Counter
from hashlib import sha256
import json
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


def subshapes(shape, kind):
    explorer, result = TopExp_Explorer(shape, kind), []
    while explorer.More():
        item = explorer.Current()
        if not any(item.IsSame(old) for old in result):
            result.append(item)
        explorer.Next()
    return result


def primitive_lineage(identifier, mapping):
    return tuple((face, frozenset((json.dumps([identifier, key], separators=(',', ':')),)))
                 for key, face in mapping.items())


def propagate(builder, result, sources):
    """Normalize history descendants to faces in the actual oriented result."""
    descendants = []
    for face, tokens in sources:
        unchanged = [] if builder.IsDeleted(face) else [face]
        descendants.append((tuple([*unchanged, *builder.Modified(face), *builder.Generated(face)]), tokens))
    return tuple((TopoDS.Face_s(face), frozenset(token for candidates, tokens in descendants
                                               if any(face.IsSame(candidate) for candidate in candidates)
                                               for token in tokens))
                 for face in subshapes(result, TopAbs_FACE))


def evaluated_candidates(lineage):
    """Publish only unique planar ancestry + edge-neighbor signatures.

    Split counts prevent a disappearing ambiguous sibling from turning a
    formerly ambiguous identity into a match. Unnamed neighbors also reject
    attachment. Curved neighbors contribute identity but cannot host sketches.
    """
    counts = Counter(tokens for _, tokens in lineage)
    edges = [subshapes(face, TopAbs_EDGE) for face, _ in lineage]
    candidates = []
    for i, (face, tokens) in enumerate(lineage):
        if not tokens or BRepAdaptor_Surface(face).GetType() != GeomAbs_Plane:
            continue
        neighbors = [other for j, (_, other) in enumerate(lineage) if i != j and
                     any(a.IsSame(b) for a in edges[i] for b in edges[j])]
        if any(not other for other in neighbors):
            continue
        signature = [sorted(tokens), counts[tokens],
                     sorted([sorted(other), counts[other]] for other in neighbors)]
        key = sha256(json.dumps(signature, separators=(',', ':')).encode()).hexdigest()
        candidates.append((key, face))
    return tuple(candidates)


def evaluated_faces(lineage):
    candidates = evaluated_candidates(lineage)
    unique = Counter(key for key, _ in candidates)
    return {('evaluated', None, key): face for key, face in candidates if unique[key] == 1}

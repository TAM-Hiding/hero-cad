"""Read-only manufacturing export of evaluated millimeter B-reps."""
import math
import os
import struct
import tempfile
from collections import Counter
from pathlib import Path
from threading import Lock

from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_ManifoldSolidBrep, STEPControl_Reader, STEPControl_Writer
from OCP.StlAPI import StlAPI_Writer
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from hero_cad.geometry import compound, volume


EXTENSIONS = {'stl': ('.stl',), 'step': ('.step', '.stp')}
# Absolute chordal deflection in mm and angular deflection in radians.
STL_QUALITY = {'Coarse': (0.25, 0.5), 'Standard': (0.08, 0.25), 'Fine': (0.02, 0.12)}
_SOLID_FEATURES = {'box', 'extrude', 'boolean', 'chamfer'}
_STEP_LOCK = Lock()
_STL_FACET = struct.Struct('<12fH')


def _subshapes(shape, shape_type):
    explorer = TopExp_Explorer(shape, shape_type)
    while explorer.More():
        yield explorer.Current()
        explorer.Next()


def _valid_solid(shape):
    return (not shape.IsNull() and shape.ShapeType() == TopAbs_SOLID
            and BRepCheck_Analyzer(shape).IsValid() and 0 < volume(shape) < math.inf)


def _export_bodies(document, body_ids):
    active = document.active_body_ids
    requested = active if body_ids is None else frozenset(body_ids)
    if requested - active:
        raise ValueError('Select only current solid bodies and resolve failed features before exporting.')
    for feature in document.features:
        status = document.statuses[feature.id]
        if feature.type in _SOLID_FEATURES and not status.valid:
            if body_ids is None or requested.intersection(feature.references):
                raise ValueError(f'Resolve the failed {feature.type} before exporting. {status.error}')
    if not requested:
        raise ValueError('There are no current solid bodies in this export scope.')
    shapes = []
    for feature in document.features:
        if feature.id in requested:
            shape = document.solid_shapes[feature.id]
            if not _valid_solid(shape):
                raise ValueError(f'Repair the invalid {feature.type} body ({feature.id[:8]}) before exporting.')
            shapes.append(shape)
    return shapes


def export_document(document, destination, format_name, *, body_ids=None, quality='Standard'):
    """Export all current bodies, or exactly the supplied current feature IDs."""
    extensions = EXTENSIONS[format_name]
    path = Path(destination).expanduser().absolute()
    if not path.suffix:
        path = path.with_suffix(extensions[0])
    if path.suffix.lower() not in extensions:
        raise ValueError(f'Use a {" or ".join(extensions)} file extension.')
    # Match native Save's replacement semantics. An export must never write
    # through an alias or replace one with a manufacturing file.
    if path.is_symlink():
        raise ValueError('Choose a regular destination file instead of a symbolic link.')
    if path.exists() and not path.is_file():
        raise ValueError('Choose a regular destination file.')
    shapes = _export_bodies(document, body_ids)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.hero-export-', delete=False) as stream:
            temporary = Path(stream.name)
        if format_name == 'stl':
            _write_stl(shapes, temporary, *STL_QUALITY[quality])
        else:
            _write_step(shapes, temporary)
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def _write_stl(shapes, path, linear, angular):
    meshes, facet_counts = [], []
    for shape in shapes:
        # OCCT meshing attaches triangulations/edge polygons to topology.
        # Copy geometry and omit all existing viewport tessellation.
        mesh = BRepBuilderAPI_Copy(shape, True, False).Shape()
        mesher = BRepMesh_IncrementalMesh(mesh, linear, False, angular, False)
        if not mesher.IsDone():
            raise ValueError('OCCT could not tessellate a body. Try STEP or repair the body.')
        count = 0
        for face in _subshapes(mesh, TopAbs_FACE):
            triangles = BRep_Tool.Triangulation_s(TopoDS.Face_s(face), TopLoc_Location())
            if triangles is None or not triangles.NbTriangles():
                raise ValueError('Tessellation is missing a face. Try STEP or repair the body.')
            count += triangles.NbTriangles()
        meshes.append(mesh)
        facet_counts.append(count)
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(compound(meshes), str(path)):
        raise ValueError('OCCT could not write the STL file.')
    _validate_stl(path, facet_counts)


def _validate_stl(path, facet_counts):
    # The native writer visits all faces of each compound child consecutively.
    # Check each body separately since coincident edges between different
    # bodies are permitted and Export All does not fuse or repair them.
    count = sum(facet_counts)
    error = 'STL tessellation lost precision or produced an open or inverted mesh. Try STEP or a finer STL quality.'
    with path.open('rb') as stream:
        stream.seek(80)
        if (not count or stream.read(4) != struct.pack('<I', count)
                or path.stat().st_size != 84 + _STL_FACET.size * count):
            raise ValueError('OCCT wrote an incomplete binary STL file.')
        for facets in facet_counts:
            edges = Counter()
            signed_volume = 0.0
            origin = None
            for _ in range(facets):
                nx, ny, nz, ax, ay, az, bx, by, bz, cx, cy, cz, _ = _STL_FACET.unpack(stream.read(_STL_FACET.size))
                if not all(map(math.isfinite, (nx, ny, nz, ax, ay, az, bx, by, bz, cx, cy, cz))):
                    raise ValueError(error)
                if origin is None:
                    origin = (ax, ay, az)
                ux, uy, uz = bx - ax, by - ay, bz - az
                vx, vy, vz = cx - ax, cy - ay, cz - az
                x, y, z = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                if x * nx + y * ny + z * nz <= 0:
                    raise ValueError(error)
                ox, oy, oz = origin
                signed_volume += (ax - ox) * x + (ay - oy) * y + (az - oz) * z
                a, b, c = (ax, ay, az), (bx, by, bz), (cx, cy, cz)
                edges.update(((a, b), (b, c), (c, a)))
            if signed_volume <= 0 or any(n != 1 or edges[b, a] != 1 for (a, b), n in edges.items()):
                raise ValueError(error)


def _write_step(shapes, path):
    # The pinned OCP bindings expose STEP unit configuration through OCCT's
    # process-wide Interface_Static settings. Scope those changes to this write.
    with _STEP_LOCK:
        writer = STEPControl_Writer()
        settings = ('write.step.unit', 'xstep.cascade.unit')
        previous = [Interface_Static.CVal_s(key) for key in settings]
        try:
            for key in settings:
                if not Interface_Static.SetCVal_s(key, 'MM'):
                    raise ValueError('OCCT could not configure millimeter STEP units.')
            writer.Model().SetLocalLengthUnit(1.0)
            for shape in shapes:
                copy = BRepBuilderAPI_Copy(shape, True, False).Shape()
                if writer.Transfer(copy, STEPControl_ManifoldSolidBrep) != IFSelect_RetDone:
                    raise ValueError('OCCT could not translate a body to STEP B-rep.')
            if writer.Write(str(path)) != IFSelect_RetDone:
                raise ValueError('OCCT could not write the STEP file.')
            _validate_step(path, len(shapes))
        finally:
            for key, value in zip(settings, previous):
                Interface_Static.SetCVal_s(key, value)


def _validate_step(path, expected_count):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError('OCCT could not reopen the written STEP file.')
    lengths, angles, solid_angles = (TColStd_SequenceOfAsciiString() for _ in range(3))
    reader.FileUnits(lengths, angles, solid_angles)
    if lengths.IsEmpty() or any(lengths.Value(i).ToCString() != 'millimetre'
                                for i in range(1, lengths.Length() + 1)):
        raise ValueError('The written STEP file does not specify millimeter units.')
    reader.SetSystemLengthUnit(1.0)
    if reader.TransferRoots() != expected_count:
        raise ValueError('OCCT could not recover all bodies from the written STEP file.')
    solids = list(_subshapes(reader.OneShape(), TopAbs_SOLID))
    if len(solids) != expected_count or not all(map(_valid_solid, solids)):
        raise ValueError('The written STEP file does not contain the expected valid solids.')

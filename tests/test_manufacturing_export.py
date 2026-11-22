from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkFiltersCore import vtkPolyDataConnectivityFilter
from vtkmodules.vtkIOGeometry import vtkSTLReader

import hero_cad.manufacturing_export as manufacturing
from hero_cad.booleans import bounds
from hero_cad.document import BoxParameters, Document
from hero_cad.face_history import subshapes
from hero_cad.geometry import volume
from hero_cad.manufacturing_export import export_document
from hero_cad.sketch import Circle, Rectangle, Slot
from hero_cad.profiles import regions
from test_intersection_profiles import lens_area, model as intersection_model, picked


MOUNT = Path(__file__).parent / 'fixtures' / 'manufacturing-mount.hcad'


def add_extrusion(document, entity, *, distance=8, offset=None, **kwargs):
    if offset is None:
        sketch_id = document.add_sketch('XY')
    else:
        plane = document.add_offset_plane('plane:XY', offset)
        sketch_id = document.add_plane_sketch(plane)
    document.add_entity(sketch_id, entity)
    return document.add_extrusion(sketch_id, entity.id, distance=distance, **kwargs), sketch_id


def model(case):
    doc = Document()
    box = doc.features[0].id
    if case == 'box':
        return doc, (box,)
    if case == 'mount':
        doc = Document.load(MOUNT)
        return doc, tuple(doc.active_body_ids)
    if case == 'hollow':
        sketch_id = doc.add_sketch('XY')
        outer, inner = Circle(15, 15, 9), Circle(15, 15, 5)
        for entity in (outer, inner):
            doc.add_entity(sketch_id, entity)
        return doc, (doc.add_extrusion(sketch_id, outer.id, (inner.id,), 8),)
    if case in {'rectangle', 'circle', 'slot', 'disconnected', 'coincident'}:
        entity = {
            'rectangle': Rectangle(-55, -17, 19, 11, 21),
            'circle': Circle(-55, -17, 6),
            'slot': Slot(-55, -17, 4, 13, 36),
            'disconnected': Circle(-55, -17, 6),
            'coincident': Rectangle(0, 0, 40, 30),
        }[case]
        body, _ = add_extrusion(doc, entity, distance=20 if case == 'coincident' else 8)
        return doc, (box, body) if case in {'disconnected', 'coincident'} else (body,)
    if case in {'cavity', 'hole', 'chamfer'}:
        body, _ = add_extrusion(doc, Circle(15, 15, 5), operation='cut', target_id=box,
                                distance=8 if case == 'cavity' else 20,
                                offset=5 if case == 'cavity' else None)
        if case == 'chamfer':
            rim = next(edge for edge in subshapes(doc.solid_shapes[body], TopAbs_EDGE)
                       if (curve := BRepAdaptor_Curve(TopoDS.Edge_s(edge))).GetType() == GeomAbs_Circle
                       and curve.Circle().Location().Z() == 20)
            target, reference = doc.edge_reference(rim)
            body = doc.add_chamfer(target, reference, 1.0)
        return doc, (body,)
    tool, _ = add_extrusion(doc, Rectangle(28, 10, 20, 10))
    return doc, (doc.add_boolean(case, box, [tool]),)


def read_step(path):
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    units = [TColStd_SequenceOfAsciiString() for _ in range(3)]
    reader.FileUnits(*units)
    assert [units[0].Value(i).ToCString() for i in range(1, units[0].Length() + 1)] == ['millimetre']
    reader.SetSystemLengthUnit(1.0)
    assert reader.TransferRoots() > 0
    return subshapes(reader.OneShape(), TopAbs_SOLID)


def read_stl(path):
    reader = vtkSTLReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    assert mesh.GetNumberOfPolys() > 0
    assert path.stat().st_size == 84 + 50 * mesh.GetNumberOfPolys()
    points = vtk_to_numpy(mesh.GetPoints().GetData()).astype(float)
    triangles = vtk_to_numpy(mesh.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    assert np.isfinite(points).all()
    a, b, c = points[triangles].transpose(1, 0, 2)
    normals = np.cross(b - a, c - a)
    assert (np.linalg.norm(normals, axis=1) > 0).all()
    directed = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges, counts = np.unique(directed, axis=0, return_counts=True)
    assert (counts == 1).all()
    assert np.array_equal(edges, np.unique(directed[:, ::-1], axis=0))
    connectivity = vtkPolyDataConnectivityFilter()
    connectivity.SetInputData(mesh)
    connectivity.SetExtractionModeToAllRegions()
    connectivity.Update()
    return mesh.GetBounds(), np.einsum('ij,ij->', a - points[0], normals) / 6, connectivity.GetNumberOfExtractedRegions()


def surface_types(shape):
    return {BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType()
            for face in subshapes(shape, TopAbs_FACE)}


@pytest.mark.parametrize('case', ['box', 'rectangle', 'circle', 'slot', 'hollow', 'hole', 'cavity', 'chamfer',
                                  'join', 'cut', 'intersect', 'disconnected', 'mount'])
@pytest.mark.parametrize('format_name', ['stl', 'step'])
def test_manufacturing_roundtrip(case, format_name, tmp_path):
    doc, ids = model(case)
    originals = [doc.solid_shapes[identifier] for identifier in ids]
    scope = {'body_ids': ids} if case in {'rectangle', 'circle', 'slot', 'hollow'} else {}
    path = export_document(doc, tmp_path/'result', format_name, **scope)
    if format_name == 'stl':
        dimensions, mesh_volume, components = read_stl(path)
        assert components == (2 if case in {'cavity', 'disconnected'} else 1)
        target_bounds = tuple(fn(bounds(shape)[i] for shape in originals)
                              for i, fn in enumerate((min, max) * 3))
        assert dimensions == pytest.approx(target_bounds, abs=0.08)
        # Standard is chordal, so the volume estimate is approximate on curves.
        assert mesh_volume == pytest.approx(sum(map(volume, originals)), rel=0.005)
    else:
        recovered = sorted(read_step(path), key=volume)
        assert len(recovered) == len(originals)
        for solid, original in zip(recovered, sorted(originals, key=volume)):
            assert BRepCheck_Analyzer(solid).IsValid()
            assert bounds(solid) == pytest.approx(bounds(original), abs=1e-7)
            assert volume(solid) == pytest.approx(volume(original), rel=1e-9)
            assert len(subshapes(solid, TopAbs_SHELL)) == (2 if case == 'cavity' else 1)
            assert surface_types(solid) == surface_types(original)
            assert GeomAbs_Plane in surface_types(solid)
        if case in {'circle', 'slot', 'hollow', 'hole', 'cavity', 'chamfer', 'mount'}:
            assert GeomAbs_Cylinder in surface_types(recovered[0])
            assert any(BRepAdaptor_Curve(TopoDS.Edge_s(edge)).GetType() == GeomAbs_Circle
                       for edge in subshapes(recovered[0], TopAbs_EDGE))
        if case == 'chamfer':
            assert GeomAbs_Cone in surface_types(recovered[0])


def test_coincident_bodies_are_not_fused(tmp_path):
    doc, _ = model('coincident')
    stl = export_document(doc, tmp_path/'multiple', 'stl')
    step = export_document(doc, tmp_path/'multiple.stp', 'step')
    assert (stl.stat().st_size - 84) // 50 == 24
    assert len(read_step(step)) == 2


def test_export_respects_presets_and_ignores_display_mesh(tmp_path):
    doc, ids = model('circle')
    shape = doc.solid_shapes[ids[0]]
    BRepMesh_IncrementalMesh(shape, 0.003, False, 0.04, False)

    def mesh_sizes():
        return [BRep_Tool.Triangulation_s(TopoDS.Face_s(face), TopLoc_Location()).NbTriangles()
                for face in subshapes(shape, TopAbs_FACE)]

    original_mesh = mesh_sizes()
    sizes = [export_document(doc, tmp_path/quality, 'stl', body_ids=ids, quality=quality).stat().st_size
             for quality in ('Coarse', 'Standard', 'Fine')]
    assert sizes[0] < sizes[1] < sizes[2]
    assert mesh_sizes() == original_mesh


def test_step_units_are_explicit_and_restore_occt_settings(tmp_path):
    STEPControl_Writer()  # Initialize the process-global translation settings.
    unit_key = 'write.step.unit'
    model_key = 'xstep.cascade.unit'
    previous = [Interface_Static.CVal_s(key) for key in (unit_key, model_key)]
    try:
        assert Interface_Static.SetCVal_s(unit_key, 'INCH')
        assert Interface_Static.SetCVal_s(model_key, 'INCH')
        path = export_document(Document(), tmp_path/'part', 'step')
        assert Interface_Static.CVal_s(unit_key) == 'INCH'
        assert Interface_Static.CVal_s(model_key) == 'INCH'
        assert bounds(read_step(path)[0]) == pytest.approx((0, 40, 0, 30, 0, 20))
    finally:
        for key, value in zip((unit_key, model_key), previous):
            Interface_Static.SetCVal_s(key, value)


def test_export_does_not_touch_saved_document_or_history(tmp_path):
    doc = Document.load(MOUNT)
    native = tmp_path/'part.hcad'
    doc.set_box(BoxParameters(42, 30, 5))
    doc.set_box(BoxParameters(45, 30, 5))
    doc.undo()
    doc.save(native)
    loaded = Document.load(native)
    before = doc.features, tuple(doc._undo), tuple(doc._redo), native.read_bytes(), doc.path
    for candidate in (doc, loaded):
        stl = export_document(candidate, tmp_path/'part', 'stl')
        step = export_document(candidate, tmp_path/'part', 'step')
        assert read_stl(stl)[0] == pytest.approx((0, 42, 0, 30, 0, 10))
        assert bounds(read_step(step)[0]) == pytest.approx((0, 42, 0, 30, 0, 10))
        assert not candidate.dirty
    assert (doc.features, tuple(doc._undo), tuple(doc._redo), native.read_bytes(), doc.path) == before


def test_unresolved_history_and_consumed_ids_are_rejected(tmp_path):
    doc = Document()
    box = doc.features[0].id
    entity = Circle(15, 15, 4)
    result, sketch_id = add_extrusion(doc, entity, operation='cut', target_id=box, distance=20)
    with pytest.raises(ValueError, match='current solid bodies'):
        export_document(doc, tmp_path/'consumed', 'step', body_ids=[box])
    doc.update_entity(sketch_id, replace(entity, x=75))
    assert not doc.statuses[result].valid and doc.active_body_ids == {box}
    unrelated, _ = add_extrusion(doc, Circle(-20, -20, 3))
    for scope in ({}, {'body_ids': [box]}):
        with pytest.raises(ValueError, match='Resolve the failed extrude'):
            export_document(doc, tmp_path/'unresolved', 'stl', **scope)
    assert export_document(doc, tmp_path/'unrelated', 'stl', body_ids=[unrelated]).is_file()


@pytest.mark.parametrize('format_name', ['stl', 'step'])
def test_rejects_empty_scope_and_invalid_geometry(tmp_path, format_name):
    doc = Document()
    with pytest.raises(ValueError, match='no current solid bodies'):
        export_document(doc, tmp_path/'empty', format_name, body_ids=())
    box = doc.features[0].id
    doc.solid_shapes[box] = subshapes(doc.solid_shapes[box], TopAbs_FACE)[0]
    with pytest.raises(ValueError, match='invalid box body'):
        export_document(doc, tmp_path/'face', format_name)
    assert not list(tmp_path.iterdir())


def test_stl_float_precision_loss_is_rejected(tmp_path):
    doc = Document()
    body, _ = add_extrusion(doc, Rectangle(99999, 99999, 0.001, 0.001))
    destination = tmp_path/'precision.stl'
    destination.write_bytes(b'previous')
    with pytest.raises(ValueError, match='precision'):
        export_document(doc, destination, 'stl', body_ids=[body])
    assert destination.read_bytes() == b'previous'
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize('format_name', ['stl', 'step'])
def test_bad_destination_and_write_failure_preserve_files(tmp_path, monkeypatch, format_name):
    doc = Document()
    with pytest.raises(FileNotFoundError):
        export_document(doc, tmp_path/'missing'/'part', format_name)
    with pytest.raises(ValueError, match='extension'):
        export_document(doc, tmp_path/'part.hcad', format_name)

    destination = tmp_path/f'part.{format_name}'
    destination.write_bytes(b'old geometry')
    link = tmp_path/f'link.{format_name}'
    link.symlink_to(destination)
    with pytest.raises(ValueError, match='symbolic link'):
        export_document(doc, link, format_name)
    with monkeypatch.context() as patch:
        def refuse_replace(*args):
            raise PermissionError('Permission denied')

        patch.setattr(manufacturing.os, 'replace', refuse_replace)
        with pytest.raises(PermissionError, match='Permission denied'):
            export_document(doc, destination, format_name)

    def interrupted_write(shapes, path, *args):
        path.write_bytes(b'partial geometry')
        raise OSError('write interrupted')

    monkeypatch.setattr(manufacturing, f'_write_{format_name}', interrupted_write)
    with pytest.raises(OSError, match='write interrupted'):
        export_document(doc, destination, format_name)
    assert destination.read_bytes() == b'old geometry'
    assert set(tmp_path.iterdir()) == {destination, link}


@pytest.mark.parametrize('format_name', ['stl', 'step'])
@pytest.mark.parametrize('operation', ['lens', 'cut'])
def test_intersection_cells_export_modeled_solid_after_native_reopen(tmp_path, format_name, operation):
    doc, sketch_id, first, second = intersection_model()
    available = regions(doc.feature(sketch_id).parameters)
    lens = picked(available, 13, 10)
    if operation == 'lens':
        result = doc.add_extrusion(sketch_id, lens.outer_id, distance=4)
        expected_bounds = (11, 15, 6, 14, 0, 4)
        expected_volume = 4 * lens_area(5, 6)
        # The original base box is still current but outside this export scope.
        scope = {'body_ids': (result,)}
    else:
        outer_cell = picked(available, 7, 10)
        box = doc.features[0].id
        result = doc.add_multi_extrusion(sketch_id, (outer_cell.reference, lens.reference),
                                         20, operation='cut', target_id=box)
        expected_bounds = (0, 40, 0, 30, 0, 20)
        expected_volume = 40 * 30 * 20 - 20 * 25 * np.pi
        assert doc.active_body_ids == {result}
        scope = {}

    native = tmp_path/'intersecting.hcad'
    doc.save(native)
    loaded = Document.load(native)
    assert loaded.feature(sketch_id).parameters.entities == (first, second)
    assert loaded.feature(result) == doc.feature(result)
    assert all(ref.region_sources for ref in loaded.feature(result).parameters.profiles)
    native_bytes = native.read_bytes()
    features, shape = loaded.features, loaded.shape
    history = tuple(loaded._undo), tuple(loaded._redo)
    path = export_document(loaded, tmp_path/'modeled', format_name, **scope)
    if format_name == 'stl':
        exported_bounds, exported_volume, components = read_stl(path)
        assert components == 1
        assert exported_bounds == pytest.approx(expected_bounds, abs=0.08)
        assert exported_volume == pytest.approx(expected_volume, rel=0.005)
    else:
        solid, = read_step(path)
        assert BRepCheck_Analyzer(solid).IsValid()
        assert GeomAbs_Cylinder in surface_types(solid)
        assert bounds(solid) == pytest.approx(expected_bounds, abs=1e-7)
        assert volume(solid) == pytest.approx(expected_volume, rel=1e-9)
    assert loaded.path == native and not loaded.dirty
    assert loaded.features == features and loaded.shape.IsSame(shape)
    assert (tuple(loaded._undo), tuple(loaded._redo)) == history
    assert native.read_bytes() == native_bytes

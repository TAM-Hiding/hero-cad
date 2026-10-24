from math import sqrt
import pytest
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Trsf, gp_Vec
from hero_cad.document import Document
from hero_cad.geometry import volume
from hero_cad.ui.display_geometry import tessellate, edge_mesh, subshapes, selected_mesh


@pytest.mark.parametrize('radius', [.02, 2, 50])
def test_refined_curves_exact_surface_normals_and_unchanged_kernel(radius):
    shape = BRepPrimAPI_MakeCylinder(radius, 5).Shape()
    old_volume = volume(shape)
    faces = subshapes(shape, TopAbs_FACE)
    BRepMesh_IncrementalMesh(shape, .1, False, .2, True)
    coarse_count = sum(BRep_Tool.Triangulation_s(face, TopLoc_Location()).NbTriangles() for face in faces)
    mesh = tessellate(shape)
    assert mesh.GetNumberOfCells() > coarse_count*1.5
    assert volume(shape) == old_volume
    normals = mesh.GetPointData().GetNormals()
    assert normals and normals.GetNumberOfTuples() == mesh.GetNumberOfPoints()
    checked = 0
    for i in range(mesh.GetNumberOfPoints()):
        x, y, z = mesh.GetPoint(i)
        nx, ny, nz = normals.GetTuple(i)
        assert sqrt(nx*nx+ny*ny+nz*nz) == pytest.approx(1)
        if abs(nz) < .5:
            assert (nx, ny, nz) == pytest.approx((x/radius, y/radius, 0), abs=1e-9)
            checked += 1
    assert checked > 100
    ids = mesh.GetCellData().GetArray('face_id')
    assert {ids.GetValue(i) for i in range(mesh.GetNumberOfCells())} == set(range(len(faces)))
    assert all(selected_mesh(mesh, 'face_id', i).GetNumberOfCells() > 0 for i in range(len(faces)))
    wire = edge_mesh(shape)
    assert wire.GetNumberOfCells() == 3
    assert max(wire.GetCell(i).GetNumberOfPoints() for i in range(3)) > 70


def test_point_normals_do_not_round_sharp_box_edges():
    mesh = tessellate(Document().shape)
    normals = mesh.GetPointData().GetNormals()
    corner = [normals.GetTuple(i) for i in range(mesh.GetNumberOfPoints()) if mesh.GetPoint(i) == (0., 0., 0.)]
    assert set(corner) == {(-1., 0., 0.), (0., -1., 0.), (0., 0., -1.)}
    assert mesh.GetNumberOfCells() == 12


def test_normals_respect_face_locations():
    shape = BRepPrimAPI_MakeCylinder(2, 5).Shape()
    t = gp_Trsf(); t.SetTranslation(gp_Vec(10, 20, 30))
    mesh = tessellate(shape.Moved(TopLoc_Location(t)))
    for i in range(mesh.GetNumberOfPoints()):
        nx, ny, nz = mesh.GetPointData().GetNormals().GetTuple(i)
        if abs(nz) < .5:
            x, y, z = mesh.GetPoint(i)
            assert (nx, ny) == pytest.approx(((x-10)/2, (y-20)/2), abs=1e-9)

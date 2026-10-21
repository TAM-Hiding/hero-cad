"""Disposable display data with a cell-to-OCCT-subshape mapping."""
from dataclasses import dataclass
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from vtkmodules.vtkCommonCore import vtkIntArray, vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData


def subshapes(shape, kind):
    mapping = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, mapping)
    cast = TopoDS.Face_s if kind == TopAbs_FACE else TopoDS.Edge_s
    return [cast(mapping.FindKey(i)) for i in range(1, mapping.Extent() + 1)]


def tessellate(shape):
    """Triangles carry zero-based face indices into subshapes(shape, FACE)."""
    BRepMesh_IncrementalMesh(shape, 0.1, False, 0.2, True)
    points, cells, face_ids = vtkPoints(), vtkCellArray(), vtkIntArray()
    points.SetDataTypeToDouble()
    face_ids.SetName('face_id')
    for face_id, subshape in enumerate(subshapes(shape, TopAbs_FACE)):
        face = TopoDS.Face_s(subshape)
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is None:
            raise ValueError('OCCT did not generate a display mesh')
        offset = points.GetNumberOfPoints()
        for index in range(1, mesh.NbNodes() + 1):
            p = mesh.Node(index).Transformed(location.Transformation())
            points.InsertNextPoint(p.X(), p.Y(), p.Z())
        for index in range(1, mesh.NbTriangles() + 1):
            a, b, c = mesh.Triangle(index).Get()
            if face.Orientation() == TopAbs_REVERSED:
                b, c = c, b
            cells.InsertNextCell(3)
            for node in (a, b, c):
                cells.InsertCellPoint(offset + node - 1)
            face_ids.InsertNextValue(face_id)
    result = vtkPolyData()
    result.SetPoints(points)
    result.SetPolys(cells)
    result.GetCellData().AddArray(face_ids)
    return result


def edge_mesh(shape):
    """One polyline per nondegenerate topological edge; no triangle diagonals."""
    points, cells, ids = vtkPoints(), vtkCellArray(), vtkIntArray()
    points.SetDataTypeToDouble()
    ids.SetName('edge_id')
    for index, subshape in enumerate(subshapes(shape, TopAbs_EDGE)):
        edge = TopoDS.Edge_s(subshape)
        if BRep_Tool.Degenerated_s(edge):
            continue
        curve = BRepAdaptor_Curve(edge)
        samples = GCPnts_QuasiUniformDeflection(curve, 0.1)
        if not samples.IsDone() or samples.NbPoints() < 2:
            raise ValueError('OCCT could not sample an edge')
        cells.InsertNextCell(samples.NbPoints())
        for i in range(1, samples.NbPoints() + 1):
            p = samples.Value(i)
            cells.InsertCellPoint(points.InsertNextPoint(p.X(), p.Y(), p.Z()))
        ids.InsertNextValue(index)
    result = vtkPolyData()
    result.SetPoints(points)
    result.SetLines(cells)
    result.GetCellData().AddArray(ids)
    return result


def selected_mesh(mesh, name, index):
    cells = vtkCellArray()
    ids = mesh.GetCellData().GetArray(name)
    for i in range(mesh.GetNumberOfCells()):
        if ids.GetValue(i) == index:
            cells.InsertNextCell(mesh.GetCell(i).GetPointIds())
    result = vtkPolyData()
    result.SetPoints(mesh.GetPoints())
    if name == 'face_id':
        result.SetPolys(cells)
    else:
        result.SetLines(cells)
    return result


@dataclass(frozen=True)
class Selection:
    """Valid only for the current displayed solid; never a persistent reference."""
    kind: str
    index: int
    shape: object

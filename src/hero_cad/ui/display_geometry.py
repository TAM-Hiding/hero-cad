"""Disposable display data with a cell-to-OCCT-subshape mapping."""
from dataclasses import dataclass
from math import cos
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.GeomAbs import GeomAbs_Circle
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from vtkmodules.vtkCommonCore import vtkDoubleArray, vtkIntArray, vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

SURFACE_DEFLECTION = .02  # millimetres, display only
ANGULAR_DEFLECTION = .08  # radians


def subshapes(shape, kind):
    mapping = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, mapping)
    cast = TopoDS.Face_s if kind == TopAbs_FACE else TopoDS.Edge_s
    return [cast(mapping.FindKey(i)) for i in range(1, mapping.Extent() + 1)]


def tessellate(shape):
    """Triangles carry zero-based face indices into subshapes(shape, FACE)."""
    BRepMesh_IncrementalMesh(shape, SURFACE_DEFLECTION, False, ANGULAR_DEFLECTION, True)
    points, cells, face_ids = vtkPoints(), vtkCellArray(), vtkIntArray()
    normals = vtkDoubleArray()
    normals.SetName('Normals')
    normals.SetNumberOfComponents(3)
    complete_normals = True
    points.SetDataTypeToDouble()
    face_ids.SetName('face_id')
    for face_id, subshape in enumerate(subshapes(shape, TopAbs_FACE)):
        face = TopoDS.Face_s(subshape)
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is None:
            raise ValueError('OCCT did not generate a display mesh')
        offset = points.GetNumberOfPoints()
        surface = BRepAdaptor_Surface(face)
        for index in range(1, mesh.NbNodes() + 1):
            p = mesh.Node(index).Transformed(location.Transformation())
            points.InsertNextPoint(p.X(), p.Y(), p.Z())
            if mesh.HasUVNodes():
                uv = mesh.UVNode(index)
                props = BRepLProp_SLProps(surface, uv.X(), uv.Y(), 1, 1e-9)
                if props.IsNormalDefined():
                    direction = props.Normal()
                    sign = -1 if face.Orientation() == TopAbs_REVERSED else 1
                    normals.InsertNextTuple(tuple(sign*x for x in direction.Coord()))
                    continue
            # Exotic singular surfaces retain the prior mapper fallback rather
            # than supplying invalid normals. Existing analytic faces have UVs.
            complete_normals = False
            normals.InsertNextTuple((0., 0., 0.))
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
    if complete_normals:
        # Points are deliberately separate between CAD faces: smooth each
        # analytic surface, never interpolate normals across mechanical corners.
        result.GetPointData().SetNormals(normals)
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
        deflection = SURFACE_DEFLECTION
        if curve.GetType() == GeomAbs_Circle:
            deflection = min(deflection, curve.Circle().Radius()*(1-cos(ANGULAR_DEFLECTION/2)))
        samples = GCPnts_QuasiUniformDeflection(curve, deflection)
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


def paths_mesh(paths):
    points, cells = vtkPoints(), vtkCellArray()
    points.SetDataTypeToDouble()
    for path in paths:
        if len(path) < 2:
            continue
        cells.InsertNextCell(len(path))
        for point in path:
            cells.InsertCellPoint(points.InsertNextPoint(*point))
    result = vtkPolyData()
    result.SetPoints(points)
    result.SetLines(cells)
    return result

"""Display OCCT tessellation; never use the display mesh for CAD operations."""
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401 registers rendering backend
import vtkmodules.vtkInteractionStyle  # noqa: F401
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer
from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS


def tessellate(shape):
    BRepMesh_IncrementalMesh(shape, 0.1, False, 0.2, True)
    points, cells = vtkPoints(), vtkCellArray()
    points.SetDataTypeToDouble()
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        face = TopoDS.Face_s(faces.Current())
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is None:
            raise ValueError("OCCT did not generate a display mesh")
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
        faces.Next()
    result = vtkPolyData()
    result.SetPoints(points)
    result.SetPolys(cells)
    return result


class Viewport(QVTKRenderWindowInteractor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.09, 0.12, 0.16)
        self.GetRenderWindow().AddRenderer(self.renderer)
        self.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor()
        self.actor.SetMapper(self.mapper)
        self.actor.GetProperty().SetColor(0.65, 0.79, 0.86)
        self.actor.GetProperty().EdgeVisibilityOn()
        self.actor.GetProperty().SetEdgeColor(0.13, 0.20, 0.25)
        self.renderer.AddActor(self.actor)
        camera = self.renderer.GetActiveCamera()
        camera.SetPosition(1, -1, 1)
        camera.SetViewUp(0, 0, 1)
        camera.ParallelProjectionOn()
        self.Initialize()

    def set_shape(self, shape, fit=False):
        self.mapper.SetInputData(tessellate(shape))
        if fit:
            self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.GetRenderWindow().Render()

    def fit(self):
        self.renderer.ResetCamera()
        self.GetRenderWindow().Render()

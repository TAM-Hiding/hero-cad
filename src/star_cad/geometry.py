"""OCCT operations. No UI or rendering dependencies belong here."""
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def make_box(width: float, depth: float, height: float):
    builder = BRepPrimAPI_MakeBox(width, depth, height)
    shape = builder.Shape()
    if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError("OCCT could not construct a valid box")
    return shape


def volume(shape) -> float:
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    return properties.Mass()


def make_sketch(parameters):
    """Regenerate analytic OCCT wires/edges from local sketch parameters."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Pnt
    from star_cad.sketch import Line
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for entity in parameters.entities:
        points = [gp_Pnt(*parameters.frame.to_world(p)) for p in entity.points]
        if type(entity) is Line:
            shape = BRepBuilderAPI_MakeEdge(points[0], points[1]).Edge()
        else:
            polygon = BRepBuilderAPI_MakePolygon()
            for point in points[:-1]:
                polygon.Add(point)
            polygon.Close()
            shape = polygon.Wire()
        builder.Add(compound, shape)
    if not BRepCheck_Analyzer(compound).IsValid():
        raise ValueError('OCCT could not regenerate valid sketch geometry')
    return compound

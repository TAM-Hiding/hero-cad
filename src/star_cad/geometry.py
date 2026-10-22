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


def compound(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    builder, result = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def make_sketch(parameters):
    """Regenerate analytic OCCT wires/edges from local sketch parameters."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
    from math import cos, sin, radians
    from star_cad.sketch import Circle, Line, Slot
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for entity in parameters.entities:
        def point(local):
            return gp_Pnt(*parameters.frame.to_world(local))
        if type(entity) is Circle:
            frame = parameters.frame
            circle = gp_Circ(gp_Ax2(point((entity.x, entity.y)), gp_Dir(*frame.normal), gp_Dir(*frame.u)), entity.radius)
            shape = BRepBuilderAPI_MakeEdge(circle).Edge()
        elif type(entity) is Slot:
            a, b = (entity.x, entity.y), entity.second_center
            c, s, r = cos(radians(entity.angle)), sin(radians(entity.angle)), entity.radius
            def offset(center, u, v):
                return point((center[0]+r*(u*c-v*s), center[1]+r*(u*s+v*c)))
            bottom_a, bottom_b = offset(a, 0, -1), offset(b, 0, -1)
            top_a, top_b = offset(a, 0, 1), offset(b, 0, 1)
            wire = BRepBuilderAPI_MakeWire()
            for edge in (BRepBuilderAPI_MakeEdge(bottom_a, bottom_b).Edge(),
                         BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(bottom_b, offset(b, 1, 0), top_b).Value()).Edge(),
                         BRepBuilderAPI_MakeEdge(top_b, top_a).Edge(),
                         BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(top_a, offset(a, -1, 0), bottom_a).Value()).Edge()):
                wire.Add(edge)
            shape = wire.Wire()
        elif type(entity) is Line:
            points = [point(p) for p in entity.points]
            shape = BRepBuilderAPI_MakeEdge(points[0], points[1]).Edge()
        else:
            polygon = BRepBuilderAPI_MakePolygon()
            for local in entity.points[:-1]:
                polygon.Add(point(local))
            polygon.Close()
            shape = polygon.Wire()
        builder.Add(compound, shape)
    if not BRepCheck_Analyzer(compound).IsValid():
        raise ValueError('OCCT could not regenerate valid sketch geometry')
    return compound

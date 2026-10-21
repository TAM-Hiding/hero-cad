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

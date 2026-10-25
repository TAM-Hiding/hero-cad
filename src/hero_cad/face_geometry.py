"""Conservative current-face verification, not a topological naming system.

Exact ordered-feature regeneration is authoritative. This bounded descriptor
checks planar faces bounded by the line/circle curves used by current tools.
It cannot infer ancestry or recover changed geometry.
"""
from hashlib import sha256
import json
from math import pi
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
from OCP.TopoDS import TopoDS
from hero_cad.attachments import AttachmentError, planar_frame
from hero_cad.face_history import subshapes


def q(value):
    result = round(float(value),9)
    return 0.0 if result == 0 else result


def coords(point):
    return tuple(q(x) for x in point.Coord())


def edge_descriptor(raw):
    edge = TopoDS.Edge_s(raw)
    curve = BRepAdaptor_Curve(edge)
    kind = curve.GetType()
    if kind not in (GeomAbs_Line,GeomAbs_Circle):
        raise AttachmentError('Unsupported planar boundary: current references require line/circle edges')
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge,props)
    length = props.Mass()
    ends = sorted((coords(curve.Value(curve.FirstParameter())),coords(curve.Value(curve.LastParameter()))))
    if kind == GeomAbs_Line:
        return ['line',q(length),ends]
    circle = curve.Circle()
    axis = list(circle.Axis().Direction().Coord())
    if next((x for x in axis if abs(x)>1e-12),1)<0:
        axis = [-x for x in axis]
    full = abs(length-2*pi*circle.Radius())<1e-9
    return ['circle',coords(circle.Location()),q(circle.Radius()),[q(x) for x in axis],q(length),[] if full else [ends,coords(curve.Value((curve.FirstParameter()+curve.LastParameter())/2))]]


def face_digest(face):
    frame = planar_frame(face)
    # Canonical plane offset avoids dependence on OCCT's arbitrary in-plane
    # surface origin. Preserve the oriented normal to distinguish face sides.
    normal = tuple(q(x) for x in frame.normal)
    offset = q(sum(x*y for x,y in zip(frame.origin,frame.normal)))
    wires = []
    for wire in subshapes(face,TopAbs_WIRE):
        edges = [edge_descriptor(edge) for edge in subshapes(wire,TopAbs_EDGE)]
        wires.append(sorted(edges,key=lambda e:json.dumps(e,separators=(',',':'))))
    wires.sort(key=lambda w:json.dumps(w,separators=(',',':')))
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face,props)
    descriptor = ['current-planar-face/v1',normal,offset,q(props.Mass()),coords(props.CentreOfMass()),wires]
    return sha256(json.dumps(descriptor,separators=(',',':')).encode()).hexdigest()

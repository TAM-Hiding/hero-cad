"""Conservative analytic OCCT operations: one connected solid, explicit inputs."""
from itertools import product
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from hero_cad.geometry import volume


class OperationError(ValueError):
    pass


def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    b = box.Get()
    return b[0],b[3],b[1],b[4],b[2],b[5]


def run(operator, a, b):
    builder = operator()
    from OCP.TopTools import TopTools_ListOfShape
    arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    arguments.Append(a)
    tools.Append(b)
    builder.SetArguments(arguments)
    builder.SetTools(tools)
    builder.SetNonDestructive(True)
    builder.SetRunParallel(False)
    builder.Build()
    if not builder.IsDone() or builder.Shape().IsNull():
        raise OperationError('OCCT Boolean operation failed')
    return builder.Shape()


def one_solid(shape):
    ex, solids = TopExp_Explorer(shape, TopAbs_SOLID), []
    while ex.More():
        solids.append(TopoDS.Solid_s(ex.Current()))
        ex.Next()
    if len(solids) != 1 or not BRepCheck_Analyzer(shape).IsValid() or volume(shape) <= 1e-15:
        raise OperationError('Operation must produce one valid connected positive-volume solid')
    return solids[0]


def combine(operation, target, tools):
    result, pending = target,list(tools)
    while pending:
        chosen = None
        for i,tool in enumerate(pending):
            overlap = run(BRepAlgoAPI_Common,result,tool)
            if volume(overlap) > max(1e-15,min(volume(result),volume(tool))*1e-10):
                chosen = i
                break
            if operation != 'join':
                break
        if chosen is None:
            raise OperationError('Bodies do not overlap in volume; disconnected, touching-only or ineffective operations are rejected')
        tool = pending.pop(chosen)
        result = run({'join': BRepAlgoAPI_Fuse, 'cut': BRepAlgoAPI_Cut,
                      'intersect': BRepAlgoAPI_Common}[operation],result,tool)
        result = one_solid(result)
    return result


def through_distance(frame, target, direction):
    b = bounds(target)
    axis = tuple(direction*n for n in frame.normal)
    depths = [sum((p[i]-frame.origin[i])*axis[i] for i in range(3))
              for p in product(*[(b[2*i],b[2*i+1]) for i in range(3)])]
    if max(depths) <= 1e-7:
        raise OperationError('Through All direction does not enter the target; reverse Direction')
    return direction*(max(depths)+max(max(depths)-min(depths),1)*1e-5)

"""Investigation-only raw OCCT boundary probe; never changes an application doc.

PYTHONPATH=.:src .venv/bin/python tools/probe_chamfer_041.py --output probe.json
--mesh-invalid deliberately meshes rejected shapes to locate a failure stage.
--alternative investigates ONE explicitly defined slot roof, not a fallback.
"""
import argparse
import json
from pathlib import Path
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from hero_cad.booleans import bounds, one_solid
from hero_cad.chamfers import resolve_edges
from hero_cad.face_history import subshapes
from hero_cad.geometry import volume
from hero_cad.ui.display_geometry import tessellate
# Running by script path places tools/ on sys.path.
from benchmark_audit_041 import slot_fin


def probe(distance, mesh_invalid=False):
    doc, target, _, _, refs = slot_fin()
    builder = BRepFilletAPI_MakeChamfer(doc.solid_shapes[target])
    for edge in resolve_edges(refs, doc.solid_shapes[target], doc.face_lineages[target]):
        if builder.Contour(edge) == 0:
            builder.Add(distance, edge)
    row = {'distance_mm': distance, 'selected_edges': len(refs)}
    try:
        builder.Build()
        row['builder_done'] = builder.IsDone()
        if not builder.IsDone():
            return row
        shape = builder.Shape()
        row['null'] = shape.IsNull()
        if shape.IsNull():
            return row
        row.update(topology_valid=BRepCheck_Analyzer(shape).IsValid(),
                   solids=len(subshapes(shape, TopAbs_SOLID)),
                   faces=len(subshapes(shape, TopAbs_FACE)), volume_mm3=volume(shape))
        if row['topology_valid'] or mesh_invalid:
            try:
                row['triangles'] = tessellate(shape).GetNumberOfCells()
            except ValueError as error:
                row['mesh_error'] = str(error)
            row['missing_mesh_faces'] = sum(BRep_Tool.Triangulation_s(TopoDS.Face_s(f), TopLoc_Location()) is None
                                            for f in subshapes(shape, TopAbs_FACE))
    except Exception as error:
        row['error'] = str(error)
    return row


def alternative(distance):
    """Explicit stipulated roof: lower extrusion + triangular prism + end cones.

    Only radius=1, center distance=12, vertical fin height=10 and d>=1.
    This is a new construction from known dimensions, with no ancestry mapping.
    It is not invoked by HERO and does not resolve general chamfer intent.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakePrism
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
    from hero_cad.booleans import run
    doc, target, sid, slot, _ = slot_fin()
    fin = doc.feature(target)
    from dataclasses import replace
    doc.replace_feature(replace(fin, parameters=replace(fin.parameters, distance=10-distance)))
    z = 15-distance
    polygon = BRepBuilderAPI_MakePolygon()
    for point in ((10, 9, z), (10, 11, z), (10, 10, z+1)):
        polygon.Add(gp_Pnt(*point))
    polygon.Close()
    triangle = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    roof = BRepPrimAPI_MakePrism(triangle, gp_Vec(12, 0, 0)).Shape()
    result = doc.solid_shapes[target]
    for tool in (roof, *(BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(x, 10, z), gp_Dir(0, 0, 1)), 1, 0, 1).Shape()
                        for x in (10, 22))):
        result = one_solid(run(BRepAlgoAPI_Fuse, result, tool))
    mesh = tessellate(result)
    return {'distance_mm': distance, 'topology_valid': BRepCheck_Analyzer(result).IsValid(),
            'solids': len(subshapes(result, TopAbs_SOLID)), 'volume_mm3': volume(result),
            'bounds_mm': bounds(result), 'triangles': mesh.GetNumberOfCells(),
            'scope': 'Explicit reconstruction only; no feature-reference ancestry'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mesh-invalid', action='store_true')
    parser.add_argument('--alternative', action='store_true')
    args = parser.parse_args()
    result = {'fixture': '40x30x5 base, face-attached slot radius 1, center distance 12, Join height 10 mm',
              'native': [probe(d, args.mesh_invalid) for d in (.5, .9, .99, .999, 1., 1.001, 1.2)]}
    if args.alternative:
        result['explicit_roof_experiment'] = [alternative(d) for d in (1., 1.001, 1.2)]
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

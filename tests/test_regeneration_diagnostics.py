"""Failures are classified at evaluation time, not inferred from row order."""
from dataclasses import replace
from OCP.TopAbs import TopAbs_EDGE
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle
from OCP.TopoDS import TopoDS
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.face_history import subshapes
from hero_cad.sketch import Circle
from hero_cad.history_inspection import first_failure, feature_history_text


def failing_branches():
    doc = Document(); box = doc.features[0].id
    refs = tuple(doc.edge_reference(e)[1] for e in subshapes(doc.shape,TopAbs_EDGE))
    chamfer = doc.add_chamfer(box,refs,.5)
    sid = doc.add_sketch('XY'); hole = Circle(15,15,2); doc.add_entity(sid,hole)
    cut = doc.add_extrusion(sid,hole.id,distance=20,operation='cut',target_id=chamfer)
    # A separate body and a second, independently failing circular reference.
    source = doc.add_sketch('XY'); circle = Circle(60,15,3); doc.add_entity(source,circle)
    body = doc.add_extrusion(source,circle.id,distance=10)
    ref = next(doc.edge_reference(e)[1] for e in subshapes(doc.solid_shapes[body],TopAbs_EDGE)
               if BRepAdaptor_Curve(TopoDS.Edge_s(e)).GetType() == GeomAbs_Circle
               if (lambda r: r.curve_type == 'circle' and r.center[2] == 10)(doc.edge_reference(e)[1]))
    second = doc.add_chamfer(body,ref,.5)
    return doc, box, chamfer, sid, cut, source, circle, body, second


def fail(doc, box, source, circle):
    doc.set_box(BoxParameters(height=.25))
    doc.update_entity(source,replace(circle,radius=4))


def test_independent_valid_and_failed_branches_undo_redo_and_reopen(tmp_path):
    doc,box,first,sid,cut,source,circle,body,second = failing_branches()
    assert first_failure(doc) is None
    fail(doc,box,source,circle)
    assert first_failure(doc) == first
    assert not doc.statuses[first].valid and doc.statuses[first].blocked_by is None
    assert not doc.statuses[second].valid and doc.statuses[second].blocked_by is None
    assert doc.statuses[cut].blocked_by == first
    assert doc.statuses[sid].valid and doc.statuses[source].valid and doc.statuses[body].valid
    text = feature_history_text(doc,cut)
    assert 'Status: Blocked by unresolved dependencies' in text and 'Blocked by: #2 · Chamfer 1' in text
    assert 'OCCT' in feature_history_text(doc,first)
    assert 'Unresolved chamfer edge' in feature_history_text(doc,second)
    definitions = doc.features
    doc.save(tmp_path/'failures.starcad')
    reopened = Document.load(doc.path)
    assert reopened.features == definitions and reopened.statuses == doc.statuses
    doc.undo(); assert doc.statuses[second].valid and first_failure(doc) == first
    doc.undo(); assert all(s.valid for s in doc.statuses.values()) and first_failure(doc) is None
    doc.redo();doc.redo()
    assert doc.features == definitions and doc.statuses == reopened.statuses

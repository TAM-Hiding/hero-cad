# Parametric edge chamfers — Work Order 035

## Workflow

1. Finish sketch editing. Choose **Select edges** and select one straight edge
   belonging to one current solid body. Use Shift-click to deselect extra edges
   if needed. Chamfer is unavailable for a face, a curved edge, multi-selection,
   stale/ambiguous ownership, or a sketch currently being edited.
2. Choose **Chamfer…** in the existing toolbar or floating tool island.
3. Enter a positive distance in millimetres (default 1 mm). The field preserves
   raw numeric precision, including scientific notation. Supported parameter
   range: 0.000001–100000 mm; the actual limit depends on available material and
   OCCT's ability to construct a valid solid.
4. Choose **Preview result**, or **Apply** to evaluate and commit. Preview uses
   the existing operation panel's non-pickable preview actor and a candidate
   Document. It changes neither authoritative history nor Undo/Redo. Changing
   the value discards that candidate; Cancel/Escape restores the accepted model.
   Preview is explicit to avoid evaluating a complex history on every keystroke.
5. The browser gains **Chamfer 1**, **Chamfer 2**, etc., as separate ordered
   features. Names follow the existing derived-label convention. A purple marker
   distinguishes chamfers; the entry shows current/historical/unresolved status.
6. Select the feature to edit its distance in **Properties → Edit**, or use its
   **Edit Operation…** context action to reopen the same preview panel. Apply
   keeps the feature UUID. **History** shows the target, segment endpoints,
   adjacent face ancestry, direct dependencies and regeneration diagnostics.

Chamfers consume their explicit target body and produce a new current body,
using the same ordered history and transaction model as extrusions/Booleans.
Undo/Redo supports creation, edits, deletion of unreferenced chamfers, and
recovery after upstream invalidation. Existing dependent features prevent unsafe
feature deletion. Chamfer results can feed further Boolean/extrusion operations,
face sketches, or separate one-edge chamfer features.

## Native evaluation

`chamfers.py` invokes `BRepFilletAPI_MakeChamfer.Add(distance, edge)` and Build.
This is an equal-distance chamfer on the two adjacent faces, nominally 45° at a
right-angle corner; it is not a general distance-and-angle tool. No manually
constructed cutting solid is used. A straight edge alone does not guarantee
that a particular distance can be chamfered successfully.

OCCT builds tangent contours automatically. The implementation checks for exactly
one contour containing exactly one edge, rejecting automatic chain propagation
before Build. The result must be one kernel-valid, connected, positive-volume
solid with a measurable material change. Native exceptions and invalid/excessive
results become useful operation diagnostics.

Existing OCCT Modified/Generated/IsDeleted face ancestry is propagated through
the chamfer builder. Its uniquely generated bevel face receives a construction
origin scoped to the chamfer UUID. This is a small extension of the existing
face lineage system, allowing planar support-face sketches and later edge
selection without replacing the topology architecture. When OCCT does not expose
a unique supported face, existing conservative face-resolution rules still apply.

Primary API reference: [OCCT 7.9 MakeChamfer header](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/src/BRepFilletAPI/BRepFilletAPI_MakeChamfer.hxx).
The implementation also checks the installed OCP 7.9.3 binding's actual overloads.

## Edge reference boundary

There was no persistent edge-reference mechanism to reuse: viewport edge/cell
numbers are temporary. The feature therefore stores a narrow checked witness:

- Explicit target feature UUID (also the sole direct dependency).
- Canonically ordered straight-segment endpoints in model coordinates, using
  the existing checked-geometry convention of 9 decimal places.
- The two adjacent faces' sorted construction ancestry tokens.

Creation verifies actual current-body ownership and a unique witness match.
Regeneration scans only the specified upstream body and requires exactly one
matching segment with the same adjacent ancestry. Traversal order and display
meshes never determine persistence. Missing/changed geometry and ambiguity never
fall back to a nearest edge, an index, or another body's corresponding edge.

An upstream change that leaves the selected segment and adjacent ancestry intact
can survive (tested: widen a box while retaining an unchanged bottom Y edge).
Changed length, translation, disappearance, splitting/merging or changed adjacent
ancestry may instead make the chamfer **UNRESOLVED**, even where a human could
recognize a related edge. This conservative failure is intentional. Edge
reassignment and general persistent topological naming are deferred.

Direct failed creation/distance edits abort before publishing candidate native
state or appending history. Upstream edits that invalidate an unchanged chamfer
retain its definition and suppress its output/dependents with diagnostics.
Undoing that upstream edit restores valid output. No stale chamfer solid is used.

## Persistence and scope

Documents containing chamfers use minimal schema **v12**, with the existing
feature record and `target_id`, `edge` and `distance` parameters. No native B-rep,
viewport index or mesh is serialized. Strict parsing checks nested references,
coordinates, ancestry and distances. Versions 1–11 remain readable; documents
without chamfers keep their existing minimum version. v12 requires this HERO-CAD
version to open; older applications cannot interpret the new feature type.

One straight edge and equal distance per feature only. Curved edges, face-wide
selection, multiple-edge operations, unequal distances, angle entry, tangent
chains, variable chamfers and fillets are deferred. A seam/non-manifold edge or
an edge without two identified adjacent faces is unavailable. Complex/tiny
chamfers can still fail native construction. No automatic reference repair,
background evaluation, new dependencies, new caching or general incremental
regeneration is introduced. Preview and commit retain the established sequential
regeneration behavior; large connected solids can remain expensive.

## Validation

`tests/test_chamfers.py` checks exact box volume reduction and bevel angle, native
validity, positive/excessive distances, atomic kernel/edit failures, regeneration,
unchanged/invalidated upstream edges, ambiguous reference rejection, standalone
Join/Cut and extrusion histories, an eight-bore cut solid, native tangent-chain
refusal, bevel-attached sketch transport, further chamfers/downstream cuts,
Undo/Redo/recovery and strict save/reopen/schema behavior.

`tests/test_chamfer_ui.py` exercises real face/edge picks and command availability,
positive/exact entry, candidate preview/cancel, creation, browser/Properties/history,
distance editing, failed edits, Undo/Redo, save/reopen, subsequent picking, normal
extrusion panel reuse and a nonblank rendered-solid framebuffer check.

See [VALIDATION.md](../VALIDATION.md) for final commands/results and environment.

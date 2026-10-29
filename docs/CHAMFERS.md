# Parametric edge chamfers — Work Orders 035 and 038

## Workflow

1. Finish sketch editing. Choose **Select edges** and select one straight, circular
   or circular-arc edge belonging to one current solid body. Use Shift-click to deselect extra edges
   if needed. Chamfer is unavailable for a face, an ellipse/freeform edge,
   multi-selection, stale/ambiguous ownership, or a sketch currently being edited.
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
   keeps the feature UUID. **History** shows the target, checked edge geometry,
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
constructed cutting solid is used. An eligible curve type alone does not
guarantee that a particular distance can be chamfered successfully.

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
- For a line, canonically ordered segment endpoints in model coordinates.
- For a full circle, its center, radius and canonical unsigned unit axis. No
  endpoint, seam, curve origin, local X direction or raw parameter is stored.
- For a partial circular arc, the same circle geometry plus unordered endpoints
  and the geometric midpoint along the trimmed arc. The midpoint distinguishes
  complementary arcs, including semicircles with identical endpoints.
- Coordinates/radii/axis components use the existing checked-geometry convention
  of 9 decimal places. Axis sign follows its largest absolute component. Edge
  reversal, reversed circle axes and harmless circle parameter-origin changes
  therefore preserve the witness.
- The two adjacent faces' sorted construction ancestry tokens.

Creation verifies actual current-body ownership and a unique witness match.
Regeneration scans only the specified upstream body and requires exactly one
matching curve geometry with the same adjacent ancestry. Traversal order and
display meshes never determine persistence. Missing/changed geometry and ambiguity never
fall back to a nearest edge, an index, or another body's corresponding edge.

An upstream change that leaves the selected curve and adjacent ancestry intact
can survive (tested: widen a box while retaining an unchanged bottom Y edge).
Changed length/radius/arc endpoints, translation, disappearance, splitting/merging
or changed adjacent ancestry may instead make the chamfer **UNRESOLVED**, even where a human could
recognize a related edge. This conservative failure is intentional. Edge
reassignment and general persistent topological naming are deferred.

Direct failed creation/distance edits abort before publishing candidate native
state or appending history. Upstream edits that invalidate an unchanged chamfer
retain its definition and suppress its output/dependents with diagnostics.
Undoing that upstream edit restores valid output. No stale chamfer solid is used.

## Persistence and scope

Straight-only chamfer documents retain their exact **v12** record layout and
minimum version. A circular/arc chamfer raises the document to **v13**, adding only
`curve_type`, `center`, `radius`, `axis` and `midpoint` inside the existing `edge`
record. Full circles have empty endpoints and a null midpoint; arcs have two
sorted endpoints and an on-circle midpoint. `target_id`, `distance`, UUIDs and
feature dependencies are unchanged. No native B-rep, viewport index or mesh is
serialized. Strict parsing checks field sets, finite coordinates/radius, unit
canonical axes, on-circle arc points, ancestry and distances. Versions 1–12
remain readable; documents without curved chamfers keep their previous minimum
version. Applications supporting only v12 cannot open v13 documents.

One straight, circular or circular-arc edge and equal distance per feature only.
Ellipses, B-splines/freeform curves, face-wide selection, multiple-edge operations,
unequal distances, angle entry, tangent chains, variable chamfers and fillets are
deferred. A seam/non-manifold edge or an edge without two identified adjacent
faces is unavailable. Complex/tiny
chamfers can still fail native construction. No automatic reference repair,
background evaluation, new dependencies, new caching or general incremental
regeneration is introduced. Preview and commit retain the established sequential
regeneration behavior; large connected solids can remain expensive.

## Circular and partial-arc behavior

Native hole-rim chamfers work at either end of a through-hole; the opposite rim
keeps its radius/elevation. Native outer boss-rim chamfers also work. Both produce
conical bevels with validated volume and bounds. Existing face ancestry propagates
to remaining planar/cylindrical faces and seeds the conical bevel. The viewport
can select these faces normally, but conical/cylindrical faces cannot host
sketches. Eligible planar faces still support sketches and downstream operations.

An independent semicircular boss rim (made by cutting a cylinder in half) can be
chamfered, edited and reopened with its original feature UUID. Arc references also
recognize minor/major arcs and are insensitive to traversal direction. Native
construction can still fail at an arc's end connections or at excessive distances.

**Rounded-slot ends:** their semicircular references are recognized, but the
standard obround opening in the regression fixture requires OCCT to include the
tangent straight edges. Preview/Apply reports that automatic edge-chain
propagation is unsupported and leaves the document/history intact. The slot
perimeter is not chamfered as a fallback. Multi-edge support remains deferred.

Only geometric classification/description and the minimal persistence extension
change in the existing UI path. Explicit preview, Properties editing, sequential
regeneration, Undo/Redo, orange surfaces, warm charcoal controls, ivory text,
rounded corners and placement below HERO Tools remain as before.

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

`tests/test_circular_chamfers.py` adds concave hole and convex boss volume/bounds
checks, independent partial arcs, seam/axis/orientation invariance, complementary
arcs, similar rims and body/ancestry scoping, ambiguity, malformed v13 references,
legacy v12 compatibility, native failure atomicity, slot-chain refusal, upstream
invalidation/recovery and downstream planar-face sketch/Cut. The UI suite includes
real circular/arc edge picks, preview/cancel/apply, Properties, Undo/Redo,
save/reopen, conical-face picking and retained dialog colors/position.

# Parametric edge chamfers — Work Orders 035, 038 and 039

## Workflow

1. Finish sketch editing. Choose **Select edges** and select one or more
   straight, circular or circular-arc edges on one current solid. Shift-click
   adds/removes edges. Every selected edge is highlighted. Cross-body, mixed
   face/edge, stale, unsupported or ambiguous selections disable Chamfer with
   an explanation. No unsupported member is silently dropped.
   Alternatively, right-click one edge and choose **Select Tangent Chain**.
   Review the highlighted chain, orbit normally, Shift-click to adjust, or clear
   the selection before continuing. The action changes selection only.
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
   keeps the feature UUID and complete edge collection. Properties shows target,
   selected-edge count and status; the shared distance is the only editable
   chamfer parameter. **History** shows the count, distance and dependencies,
   with individual curve witnesses/ancestry in its technical-details section.
   Edge reassignment and per-edge distances are not provided.

Chamfers consume their explicit target body and produce a new current body,
using the same ordered history and transaction model as extrusions/Booleans.
Undo/Redo supports creation, edits, deletion of unreferenced chamfers, and
recovery after upstream invalidation. Existing dependent features prevent unsafe
feature deletion. Chamfer results can feed further Boolean/extrusion operations,
face sketches, or separate one-edge chamfer features.

## Native evaluation

`chamfers.py` uses one `BRepFilletAPI_MakeChamfer` for the whole collection.
It calls `Add(distance, edge)` only for edges not already in an added contour,
then Build once. It never stacks independent chamfers on intermediate solids.
This is an equal-distance chamfer on the two adjacent faces, nominally 45° at a
right-angle corner; it is not a general distance-and-angle tool. No manually
constructed cutting solid is used. An eligible curve type alone does not
guarantee that a particular distance can be chamfered successfully.

OCCT builds tangent contours automatically. Before Build, every edge in every
native contour must belong to the explicit selected set, and every selected edge
must be covered. Extra edges produce a diagnostic asking for Select Tangent Chain
or explicit full-contour selection. Missing/duplicate resolved edges are rejected;
there is no partial operation. Multiple contours and closed contours are supported. The result must be one kernel-valid, connected, positive-volume
solid with a measurable material change. Native exceptions and invalid/excessive
results become useful operation diagnostics.

Existing OCCT Modified/Generated/IsDeleted face ancestry is propagated through
the chamfer builder. Its uniquely generated bevel face receives a construction
origin scoped to the chamfer UUID. For a multi-edge feature, a unique generated
face is keyed by a digest of its persistent input edge witness, not a native face
or edge number. Single-edge bevel keys stay unchanged. If several inputs generate
the same face or one input generates several faces, no unique bevel root is
invented; existing conservative attachment rules apply. This is a small extension of the existing
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

The immutable ChamferParameters collection contains 1–256 distinct witnesses,
canonically sorted by checked geometry and ancestry. Viewport click order does not
determine persistent identity or native construction order. Creation verifies
actual current-body ownership for every member and a unique witness match.
Regeneration classifies the specified upstream body's edges once for the entire
collection and requires exactly one matching geometry/ancestry per witness. Traversal order and
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
If any member becomes unresolved, the entire Chamfer output and its dependents
are suppressed; the stored collection is never reduced. Undoing the invalidating
upstream edit restores valid output. No stale chamfer solid is used.

## Persistence and scope

Single-edge straight documents retain their **v12** layout; single-edge
circle/arc documents retain **v13**. Multi-edge features use **v14**, replacing the
single `edge` field with an `edges` array (2–256 entries) of the same checked
reference records. UUIDs, target dependency and shared distance are unchanged.
V14 also permits a checked 64-character bevel segment digest for multi-edge
construction-face ancestry/attachments. Legacy single-edge bevel roots are
unchanged. No native object, viewport index, selection, chain option or mesh is
serialized. Tangent expansion is an explicit selection step, not a regeneration
instruction to discover new edges later.

Versions 1–13 remain readable. Saving documents without multi-edge features keeps
their previous minimum schema. Strict parsing rejects empty/oversized/duplicate
collections, malformed members, mixed legacy/collection keys and unsupported
versions. Curved reference validation from #38 still applies. Applications that
support only v13 cannot open v14 documents.

Shared equal distance only. Ellipses, B-splines/freeform curves, face-wide
selection, unequal/per-edge distances, angle entry, variable chamfers and fillets
remain deferred. Seam/non-manifold edges and edges without two identified
adjacent faces are unavailable. Complex/tiny chamfers or incompatible edge sets
can still fail native construction. No automatic repair, new dependencies,
background evaluation, geometry cache or incremental regeneration is introduced.
Preview and commit retain sequential regeneration; large solids can remain costly.

## Explicit tangent-chain selection

The context action starts with exactly one eligible current edge. It walks
analytic endpoint tangents of eligible lines/circles/arcs in that body. Endpoints
must coincide within **1e-7 mm**, matching the existing kernel/profile tolerance;
outgoing tangents must be opposite within **1e-5 radians** (about 0.00057 degrees).
This accepts numerical noise without treating ordinary sharp corners as tangent.
No new preference or construction evaluation is involved.

Non-tangent corners, unsupported/non-manifold edges, disconnected geometry and
other bodies bound expansion. At multiple eligible tangent continuations, the
whole expansion is refused with a diagnostic and the original selection remains.
Choices are checked before the visited set, so traversal order/closed loops cannot
hide a branch. A visited set terminates closed loops; more than 256 edges is
refused. Edge orientation reversals do not change outgoing geometric tangents.
The existing selection list and combined highlight mesh display the result;
orbit, Shift toggles and clearing retain their established behavior.

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

**Obround slots and pockets:** Select Tangent Chain on one opening edge selects
the two straight and two semicircular edges of the closed perimeter. Selecting
all four manually works too. Native through-slot and blind-pocket opening
chamfers are verified as one operation, with editable distance and save/reopen.
Selecting only one, two or three edges of the required contour is refused.

Explicit preview, orange surfaces, warm charcoal controls, ivory text, rounded
corners and placement below HERO Tools remain as before. The dialog adds a concise
selected-edge count beside the target; there is no redesign.

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

`tests/test_multi_chamfers.py` adds native block/mixed/slot/pocket collections,
exact volumes/bounds, single-builder evaluation, native contour coverage, shared
edits, failure atomicity, v14/legacy persistence, upstream recovery and generated
bevel attachments/downstream operations. Analytic traversal tests cover closed
slots, open chains, sharp corners, orientation, endpoint/angular tolerances,
unsupported boundaries, ambiguity and disconnected geometry. Branching is tested
with real native open edge/face graphs, not published nonmanifold solids.

`tests/test_multi_chamfer_ui.py` adds real right-click chain action, highlights,
Shift addition/removal, preserved manual batches, cross-body rejection,
preview/cancel/failure/apply, shared Properties edits, Undo/Redo, save/reopen,
bevel/outer-face picks and retained operation appearance/position/focus.

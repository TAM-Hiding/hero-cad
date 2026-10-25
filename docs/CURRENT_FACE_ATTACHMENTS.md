# PR #24 — creating references to current planar faces

## Reproduction and confirmed causes

The exact user document was not supplied. A solid cylinder followed by a separate
central-hole cut and two offset slot cuts worked on merged PR #23; 45 additional
short cutter-depth/position/angle combinations did not reproduce the rejection.
A hollow cylinder built from concentric outer/inner circles **does reproduce the
same error on both end caps after its first slot cut**. A second slot preserves
the failure; save/reload on the baseline cannot repair it because regeneration
repeats the same deterministic naming decisions.

The reproducible chain is:

1. `extrusion_faces` associated circular source edges using their center alone.
   Concentric circles with different radii both matched two source edges, so
   neither cylindrical wall received its source boundary identity. The initial
   caps still accepted sketches through their direct Start/End names.
2. After Cut, the evaluated-face signature publisher refused planar faces with
   unnamed neighbors. Both end caps touched those unnamed walls, so neither was
   published despite existing in a valid evaluated solid.
3. `identify_face` required exactly one entry in that conservative publication
   map *before* it tried PR #23's source-local support. Thus explicit selection
   could not establish a new reference even where a safe point/root was known.

The circular-edge association now checks **center and radius**, recovering the
proper distinct outer/inner wall identities. No B-rep construction changes.
The publisher and historical source-reference protections remain conservative.

## New selection and historical recovery are separate

For a new explicit face selection, Document first verifies actual `IsSame`
membership in exactly one **current evaluated body**. This check does not rely on
whether semantic maps or lineage metadata publish the face. Missing geometry,
ambiguous owning bodies and nonplanar surfaces have distinct diagnostics.

Existing published semantic references still use the existing path. Otherwise:

1. An interior user pick (or the existing bounded API interior-point search)
   establishes a witness on the selected analytic face.
2. If a known planar root can support PR #23's FaceSupport, create that reference
   directly even if its neighborhood was not published. Verify immediately that
   its strict resolver identifies exactly the selected face. Separate split
   regions receive distinct current identities and their own witnesses.
3. Without usable source support, store an optional **FaceSnapshot** witness
   with a geometry digest scoped by the existing owning-feature UUID. Verify that
   precisely one face in that body matches before permitting creation.

The digest uses an oriented plane, surface area/centroid, and sorted per-wire
line/circle boundary descriptors: endpoints, circle center/radius/axis, arc
midpoint and length. Full circles do not depend on the periodic seam endpoint.
Sorting removes face/edge/wire enumeration order from identity. Coordinates are
rounded to 1e-9 mm for this *verification descriptor only*, below the existing
1e-7 mm classification tolerance; document parameters/B-reps are unchanged.
Unsupported boundary types produce a specific unsupported-condition message.
This covers the line/circular boundaries of the current sketch tools, not a
universal representation of imported surfaces.

Only a digest, the interior point and any already-known origin tokens are
persisted—no authoritative B-rep, mesh or raw face index. The sketch's existing
attached_frame remains its resolved/last-resolved frame. Snapshot frames use
world-origin projection onto the analytic plane and deterministic up, so an
arbitrary in-plane OCCT surface origin cannot move the sketch after enumeration
changes. No camera information defines the frame.

## Existing references stay strict

`resolve_attachment` never invokes the new-reference factory to rescue a stored
reference. Existing semantic/legacy references keep their exact rules; source
support keeps PR #23's ancestry/plane/interior-point and merge-count protections.
A snapshot requires a unique geometry-digest match in its explicit historical
parent body, agreement with any recorded origins and interior containment of the
stored point. If checked geometry changes or disappears, the result is missing;
multiple matches are ambiguous. There is no nearby-plane, closest-centroid,
old-index or cached-frame fallback. Geometry changes with **no usable ancestry**
may therefore unresolve a snapshot even when a human could identify the face.
A new explicit selection can establish a new reference without reviving or
rewriting the old broken one.

The ordinary reported cylinder path now retains ancestry, so extrusion-distance,
hole-radius and slot-dimension edits use source-relative recovery rather than
snapshot matching. Tests also intentionally suppress history to exercise safe
current-geometry creation and refusal after unsupported changes.

## Persistence and limits

`.starcad`, units, feature IDs, atomic saves and existing size limits remain.
V1–v9 load unchanged. Optional snapshots use **v10**; ordinary semantic/source
references retain their existing schemas. Missing metadata is not guessed during
load. Snapshot fields, coordinate finiteness, known-token encoding and mutually
exclusive snapshot/source support are validated. Statuses and native caches
regenerate; Undo/Redo snapshots retain immutable reference metadata.

Snapshot verification is intentionally conservative: changing trims, segmentation,
position, orientation or size can fail its fingerprint. It cannot distinguish an
identical geometric replacement with no distinguishing history, nor recover a
fundamentally edited unknown face. Known ancestry remains preferred. Comprehensive
edge naming, general imported boundaries, graphical repair and automatic legacy
reassignment remain outside this correction. Reference creation adds no UI
layout or modeling features.

## Desktop checks

1. In XY create concentric circles of radius 15 and 2 mm, extrude the annular
   region 10 mm. Pick the top near (0,-11), New Sketch, create a slot from
   (-8,-5) with radius 1.5 and center distance 16; Cut through the body.
   Both end caps must still enable New Sketch in toolbar and floating island.
2. Create another top sketch and cut a second slot at Y=5. Create additional
   independent sketches on the remaining top and bottom. Do this without a
   restart or returning to an earlier feature. Use both normal selection and
   right-click while the selection filter is Faces or Edges.
3. Repeat with a solid cylinder followed by a separate central through-hole.
   Also try XZ/YZ. Change original extrusion depth to 14 mm, hole radius to
   2.5 mm and a slot radius/distance. Valid source-supported attachments should
   follow, retain local dimensions and reenter with the expected camera view.
4. Save/reopen before and after the cuts. Add more sketches on each end. Repeat
   Undo/Redo, face selection, sketch reentry, Preview/Cancel and Apply. Main
   toolbar and island must agree; no stale selection requires restarting.
5. Check historical failure protection: edit a supporting region until its
   witness is removed or becomes ambiguous. Existing sketch geometry/parameters
   remain with an unresolved diagnostic and suppressed dependents; Undo restores
   them. A fresh choice on another valid current region must remain available.
6. Open older documents and verify sketches/extrusions/Booleans, thin-line
   selection, navigation, Shift gestures, grid/snaps and save/reopen.

Fully absent history is a controlled provider fixture in automated tests; no new
UI switch is added to manufacture it on the desktop. Local environment/results
are in VALIDATION.md. Physical laptop acceptance remains for the reviewer.

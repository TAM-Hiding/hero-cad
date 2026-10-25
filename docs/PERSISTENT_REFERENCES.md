# PR #23 — persistent face-reference foundation

## Existing architecture and limits

This extends the reference system introduced in PRs #15/#19. It does not replace
feature history or introduce a universal topological naming service.

| Layer | Existing identity / matching | Role and limitation |
|---|---|---|
| Ordered features | Immutable feature UUID and explicit earlier dependencies | Defines the evaluated history stage; historical parents remain available |
| Sketch entities | Entity UUID, profile boundary/member UUIDs | Stable construction inputs across edits and persistence |
| Box faces | Semantic ±X/±Y/±Z | No face index |
| Extrusion caps/sides | Start/end or source boundary UUID + segment identity | Seed mapping uses OCCT prism Generated(edge); parameter endpoints associate source edges within kernel tolerance |
| Boolean faces | Transitive seed ancestry, sibling counts and edge-neighbor ancestry hashed into an evaluated-face signature | Unique signatures only; previously no persisted source ancestry or point for recovery after a signature changed |
| Viewport selection | VTK cell → current OCCT face/edge; transient index and IsSame | Valid only until display regeneration; never persisted |
| Sketch attachment | Parent feature UUID + semantic/evaluated face reference; existing local frame | Previously evaluated references resolved only by the exact signature |

OCCT shape identity associates history output with *this evaluation's* actual
oriented result faces. It is not a persistent ID. Seed side-edge matching is an
existing construction-specific geometric association, not a nearest-face fallback.

## Reference data and ancestry

FaceReference keeps its existing parent/face/boundary/segment fields. Eligible
newly picked Boolean faces additionally carry **FaceSupport**:

- `origins`: sorted unique canonical construction tokens already used by the
  existing lineage system (source feature UUID + semantic face/boundary key).
- `root`: one known planar construction ancestor from those tokens.
- `anchor`: the pick point's two coordinates in that ancestor's local frame.
- `sense`: the initial sketch normal direction relative to the root convention.
- `count`: the number of result faces sharing the same ancestry at attachment.

The parent UUID identifies the current occurrence/history stage. The evaluated
signature identifies that occurrence's original neighborhood. Origins describe
historical ancestry: two separate current regions can share them without being
the same current face. Root choice is deterministic at creation and is then
stored; regeneration never switches to a different convenient ancestor.

The actual viewport pick is projected to the analytic plane and must classify
strictly inside the chosen face. Left-click and right-click paths carry that
point, independent of the selection filter. A contextual click on an already
selected face preserves the selection batch and makes that face current. API
callers without a pick get a bounded, deterministic interior UV witness, not an
assumed centroid (which could lie in a hole). If that search cannot establish a
witness, exact legacy identity remains available without recovery metadata.

Box and New Body semantic references already persist reliable construction IDs;
they retain their existing representation. The new metadata applies to eligible
evaluated Boolean faces, including operation extrusions and Combine results.

Extrusion seed faces are retained separately from evaluated operation outputs.
Boolean history composes existing tokens through Modified/Generated and surviving
unchanged faces; IsDeleted explicitly excludes an unchanged-source candidate.
Only descendants actually found in the accepted result receive those tokens.
All existing New Body/Join/Cut/Intersect and Combine paths use the same builders
as their geometry evaluation, including each accepted multi-tool Join step.
Unknown history is not invented. Immediate event kinds and a complete ancestry
DAG are not serialized; the feature definitions retain the operation chain and
the reference retains its transitive known construction roots.

`Document.face_lineages` and `source_faces` are derived evaluation caches.
`Document.face_descendants(construction_reference, evaluated_feature_id)` queries
all known descendants of a seed face, without implying that one is the intended
attachment. These caches contain native faces and are never authoritative stored
geometry. They publish only after successful candidate regeneration.

## Frames and conservative resolution

No second world-space sketch plane is stored. SketchParameters.attached_frame
remains the existing resolved frame (or last resolved frame on failure). New
supported references derive that frame from their stored construction root:
origin/U follow the root, V follows the stored normal sense. Cap roots use the
source sketch U/V regardless of signed sweep direction. Side roots follow their
existing semantic segment frame. Camera orientation never participates.
Thus a moving/rotating root transports sketch coordinates instead of leaving a
world-coordinate witness behind. The initial origin may be outside a trimmed
region, as with the pre-existing full supporting-plane sketch convention.

Resolution first requires the stored ancestry and its known planar root. It then:

1. Refuses a decrease below the stored sibling count (possible merge/deletion).
2. Filters descendants to the root's supporting plane, not a nearby plane.
3. Accepts an existing unique exact evaluated signature when available.
4. Otherwise classifies the transported source-local point in the descendants.
   Exactly one interior candidate resolves; boundary or overlapping candidates
   are **ambiguous**; no supported candidate is **missing**.

FeatureStatus.reference_state exposes `resolved`, `ambiguous` or `missing` for
direct attachments. Existing browser/tooltips/properties report the diagnostics.
Unresolved sketches keep parameters, UUIDs, local geometry and their last frame,
but do not publish sketch shapes or downstream solids. The last frame never
substitutes for missing supporting geometry. Restoring inputs or Undo recovers
resolution. Unrelated features remain editable. Forward/cyclic dependencies and
invalid candidate transactions retain their existing rejection behavior.

A reference resolves against its explicit parent at its position in history.
Appending a later Cut does not silently reparent every earlier sketch to the
latest body. Editing that referenced parent's earlier inputs can change its
output topology and invoke the new descendant resolution.

## Persistence and compatibility

`.starcad`, the `star-cad` marker, millimetres, strict validation, size limits and
atomic saves are unchanged. **Version 9** adds the optional support object only
when needed. Roots/tokens, bounded finite local coordinates, normal sense and
multiplicity are validated. Unsupported versions/fields are rejected.

Existing v1–v8 files load. A legacy evaluated reference without metadata remains
exact-signature-only; no click intent is guessed during migration. Files without
new support retain their earlier schema/fields. Save/reload keeps feature IDs,
reference metadata and local sketch geometry; OCCT shapes/history caches and
resolution statuses regenerate from definitions. Undo/Redo snapshots include
support through immutable feature parameters.

## Deliberate limits

- This is face ancestry, not comprehensive persistent edge tracking.
- Only reliable named construction roots and OCCT-exposed relationships apply.
  Unknown ancestry, curved roots and unpublishable ambiguous signatures retain
  existing restrictions; no arbitrary imports or face-index fallback is added.
- Ancestry changes, disappearance of the stored root, a removed witness, sibling
  merges/count reductions, or ambiguous boundary points may remain unresolved.
  This deliberately rejects some potentially recoverable cases.
- No nearest centroid/plane selection, tolerance-inflated healing, automatic
  region reassignment, reference repair UI or aggressive legacy migration.
- Frames follow the source root convention. Not every possible reshape is a
  rigid attachment transform; no surface warping or constraints are introduced.
- Interior witness search is bounded; an actual interior UI click is preferable
  for very thin/complex faces. Metadata is bounded to 512 root tokens.
- No serialized B-reps/meshes, document extension change, new modeling tools,
  launcher, Push/Pull, Settings redesign or engine rewrite.

## Desktop acceptance checklist

1. Create a 40×30×10 block. On its top, sketch a 4×4 pocket at U=18,V=13 and
   Cut inward 3 mm. Pick the remaining top near (5,5), create a second sketch,
   draw a circle and optionally extrude it as New Body. Finish.
2. Edit the original pocket rectangle to U=-2,V=12,width=44,depth=6. The top
   splits into two regions. The second sketch must remain resolved on the lower
   region with unchanged local geometry/frame. Change block dimensions while
   retaining support; inspect attachment motion and camera alignment on reentry.
3. Undo/Redo the split repeatedly. Select both top regions, then right-click the
   first selected region and New Sketch. It must use the clicked face while
   preserving the batch before entering sketch mode. Other tools/picking must
   still work. Save/reopen and reenter all surviving sketches.
4. Repeat with an attachment picked near (5,15) before widening the pocket. The
   wider slot removes its witness: expect an unresolved sketch, retained
   parameters, suppressed dependents and an explanatory tooltip. Undo restores it.
5. Expand the cutter to cover the full top layer. The block remains valid but
   the original top is deleted. Do not accept the stored old plane as support.
   Save/reopen the unresolved model and confirm Undo or restoring dimensions
   recovers it. New unrelated origin sketches should remain editable.
6. Repeat ordinary dimension edits with Join/Intersect operation extrusions and
   Combine results. Check face-normal alignment, Shift gestures, grid/snapping,
   exact dimensions, preview/Cancel, and selection after history changes.
7. Open older `.starcad` examples. Confirm semantic and valid exact evaluated
   references still regenerate; no new metadata or migration guess is required.

Boundary ambiguity, reversed enumeration and malformed metadata are also covered
by automated tests; an exact boundary click need not be reproduced by eye.
Local environment and test results are recorded in VALIDATION.md. Physical
Ubuntu 22.04/laptop acceptance remains for the reviewer.

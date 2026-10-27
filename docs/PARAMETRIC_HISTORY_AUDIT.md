# Parametric history audit — Work Order #028

Baseline: `e9b13ff9f0dcd24d9f94e49b8b265a293ed87c16` (merged PR #27).
This work order supersedes the earlier proposed #028 startup-visibility scope.
No startup visibility, geometry algorithm, document schema or dependency changes
are included here. This report describes the inspected implementation rather
than treating older milestone descriptions as current behavior.

## Assessment

**Retain the architecture.** HERO-CAD already has a useful parametric foundation:
ordered immutable definitions, explicit earlier-feature references, full sequential
regeneration, transactional publication, recoverable unresolved states, and
parameter-based persistence. A new feature graph or timeline engine is unnecessary
for the next inspection improvements. This is not yet a complete history editor
or a general solution to topological naming.

Two bounded defects were corrected: restoring deleted unresolved operations and
publishing active-body state before final compound construction succeeded. Tests
exercise real kernel geometry; the final-construction error is injected because
it is an exceptional failure path, not an observed ordinary modeling failure.

## Architecture and capability inventory

| Capability | Status | Current implementation and limits |
|---|---|---|
| Feature creation/order | Implemented | `Feature` is frozen and UUID-based. `Document.features` is an ordered tuple. Creation appends; `set_features` validates the entire candidate. 1–1000 features, exactly one base box. No user reorder/insert-before/rollback cursor. |
| Dependencies | Implemented, bounded | References must be known origin planes or earlier feature UUIDs. Missing/self/forward/cyclic references fail. Extrusion and Boolean reference tuples must match their parameter inputs; face sketches must name their solid parent. There is no scheduler or stored reverse graph. |
| Sketch-to-extrusion | Implemented | Source sketch UUID, outer/hole IDs and optional sorted line-member IDs. A line loop's UUID derives from its member UUIDs, not enumeration order. Geometry edits regenerate later operations. Changing primitive region topology is a hard rejection; temporarily opening a previously accepted line profile is recoverable. |
| Face-attached sketches | Implemented, partial naming coverage | Parent history-stage UUID, semantic face or evaluated reference, optional ancestry support/snapshot, and last resolved frame. Local entities remain unchanged when the supporting frame moves. Missing/ambiguous support suppresses sketch output and dependent geometry. |
| Extrusion/Boolean history | Implemented | New Body/Join/Cut/Intersect, explicit targets/tools, signed distance and Through All Cut. Successful material operations consume active inputs and publish a new active result; historical input shapes remain available for references. Tools must be current bodies at that point in history. |
| Parameter editing | Implemented | Box/entity/extrusion properties and the existing operation panel replace immutable definitions through document transactions. UI is type-specific; no expressions, constraints or universal parameter inspector. |
| Regeneration | Implemented | Synchronous full replay in order; no incremental dirty subgraph. Visibility-only transactions reuse native caches. OCCT B-reps are authoritative; VTK meshes are disposable. |
| Errors | Partial | `FeatureError`/`last_failure` describe rejected transactions. `FeatureStatus` records accepted unresolved features; blocked descendants include the parent's diagnostic. No durable error log, separate failed/blocked taxonomy or dedicated error inspector. |
| Undo/Redo | Implemented; defect fixed | Immutable snapshots regenerate before stack movement. No-op edits preserve history; a new edit clears Redo. Failed edits/restores leave state intact. Restoring a deleted unresolved operation now works. Undo stacks are session-only. |
| Deletion | Implemented, conservative | Surviving direct references and extrusion boundary/member references block deletion. Explicit parent+dependent batch deletion is atomic and undoable. No automatic cascade dialog, reparenting or reference repair. Base box deletion is prohibited. |
| Save/reopen | Implemented | Strict JSON versions 1–11, stable UUIDs, selected parameters/reference metadata, optional sketch visibility. Rebuilds geometry and statuses; does not serialize native shapes, caches or Undo stacks. Same-directory temporary write, flush/fsync and atomic replacement. |
| Browser/history presentation | Partial | Entries follow feature iteration, but box is grouped under `Body 1`; sketches/extrusions/Combines are top-level. Types, some parameters, current/historical bodies and UNRESOLVED labels/tooltips are exposed. This is not a body ownership tree or full history timeline. |
| Suppression | Missing as a user operation | Unresolved dependencies suppress evaluation output automatically. Sketch visibility and base-box display hiding are presentation only, not feature suppression. No persisted enabled/suppressed flag. |

Principal implementation files: `src/hero_cad/features.py`, `document.py`,
`persistence.py`, `profiles.py`, `line_profiles.py`, `booleans.py`, `attachments.py`,
`face_history.py`, `face_geometry.py`, `ui/main_window.py`, `ui/operation_panel.py`.

## Transaction and failure behavior

`set_features` first evaluates a candidate, then appends the previous definitions
to Undo and publishes the new definitions/shapes/statuses. `_restore` similarly
evaluates before moving either stack. Rejected proposals never become features.
Accepted recoverable errors retain the feature definition but publish no output
for that feature; a later reference to it receives an unresolved-dependency error.
Independent features can still regenerate. Dirty state compares definitions with
the last saved definitions, not stack depth.

An unsuccessful existing Boolean does **not** consume its valid input bodies:
those inputs remain active. The viewport can therefore show the last successful
inputs alongside a failed history entry. This is deliberate current behavior,
not a cached successful output of the failed operation. Future status UI should
make that distinction explicit, especially before exporting/using geometry.

### Corrections in this PR

1. **Undo of deleted unresolved features.** Previously `_regenerate` decided an
   operation was new by whether its UUID existed in the current model. Deleting
   an unresolved Boolean or line extrusion removed that UUID. Undo then rejected
   the restored operation's recoverable error, preventing restoration of accepted
   history. `_restore` now explicitly requests restoration semantics. Dependency
   validation and hard errors still apply; new invalid operations are still
   rejected by ordinary edits. Loading already allowed recoverable failures.
2. **Final compound atomicity and diagnostics.** `active_body_ids` previously
   changed before `compound(...)` ran, and errors there escaped without a
   `FeatureError`/`last_failure`. Final construction now completes before any
   candidate cache is published, and failures identify the document stage.
   Failed edits, Undo and Redo preserve definitions, all published caches and
   both stacks.

No topological matching rules were loosened, and no failed geometry is replaced
with an old shape. Tests also cover recovery after restoring the upstream input.

## Dependency and topology risks

### Persisted identity is not a face index

| Reference layer | Identity | Stability boundary |
|---|---|---|
| Features/entities | UUID | Stable through parameter edits, history and persistence; not itself a persistent OCCT subshape ID. |
| Box | Semantic ±X/±Y/±Z | Construction-specific faces. |
| Prism caps/sides | Start/end; source boundary UUID + segment identity | Supports known construction faces, including line sides and planar slot/rectangle sides. Curved walls contribute ancestry but cannot host sketches. |
| Boolean output | Explicit result feature UUID + ancestry/neighbor signature | OCCT Modified/Generated/IsDeleted and unchanged faces feed a transitive source-token map. Unique planar signatures only. |
| Supported evaluated reference | Stored source tokens, fixed planar root, local witness, normal sense, sibling count | Can recover a unique interior descendant after some splits; rejects lost roots, ambiguous boundaries and sibling-count reductions. |
| Snapshot reference | Scoped geometry digest + interior witness, optional known origins | Exact checked geometry only; changing geometry may unresolve it. Cannot distinguish identical replacement geometry without distinguishing history. |
| Viewport | VTK cells/transient OCCT face/edge enumeration | Rebuilt and selection cleared after regeneration; never used as stored attachment identity. |

The existing mechanism is adequate for the supported construction operations and
tested edits, with conservative failures. It is **not** a complete topological
naming guarantee. Source ancestry can be incomplete; symmetric regions can have
indistinguishable neighborhoods; witness removal/merges and trim changes can
invalidate references. Snapshot fallback is intentionally less parametric.
Legacy evaluated references remain exact-signature-only; migration does not guess
new intent. There is no comprehensive persistent edge-reference system for future
fillets/chamfers. See [persistent references](PERSISTENT_REFERENCES.md) and
[current-face references](CURRENT_FACE_ATTACHMENTS.md).

References resolve against the named parent's output **at its history stage**.
A later Cut does not reparent an earlier sketch to the latest result. That is
essential for reproducibility but must be made clear in an inspector.

Other bounded risks and gaps found during inspection:

- Origin sketches currently require inclusion of their canonical plane but do
  not reject extra earlier references; box references are not constrained to an
  empty tuple. Normal creation emits canonical forms, but hand-authored files or
  direct API callers can add artificial dependencies. A compatibility decision
  and malformed-file fixtures should precede tightening this validation.
- Creation checks are not one universal policy: new Boolean/profile operation
  errors are rejected, while generic `set_features` can accept blocked features
  or attachment failures. Normal face creation resolves the reference first.
  Define the import/API contract before changing these semantics.
- `last_failure` represents rejected evaluation, not every early input validation
  failure (for example, deleting a referenced feature raises `ValueError` before
  evaluation). Browser statuses describe the accepted document. They should not
  be presented as the same error channel.
- Full synchronous regeneration and full snapshots have no large-model timing
  guarantee. Native historical solids are retained during evaluation. No stress
  claim for 1000 complex features is made.
- No global feature suppression, edit-in-place rollback boundary, automatic
  dependent deletion or reference reassignment exists. These need explicit
  semantics, not just new buttons.

## Verification

New `tests/test_history_foundation.py` covers deletion/restoration of unresolved
Boolean and line-profile chains; retained diagnostics and absent stale output;
recovery; final-compound failure atomicity for edits/Undo/Redo; rejection of new
invalid operations; face-attached Cut regeneration, protected/batch deletion and
save/reopen. Existing focused suites cover upstream entity edits, dependency
validation, current and historical face references, Boolean modes, signed caps,
split/merge ambiguity, traversal-order independence, malformed files and recovery.

Exact commands, results and environmental limitations are recorded in
[VALIDATION.md](../VALIDATION.md). Kernel validation, volume/bounds and persisted
identities are checked; desktop rendering is not claimed by kernel-only tests.

## Recommended work orders

1. **Read-only history inspector, no schema change.** Add order numbers and a
   selected-feature summary to the existing browser/properties. Show type, UUID,
   typed parameters, direct parents/dependents, current/historical body role,
   attachment strategy and full error. Derive relationships from references;
   do not create a second authoritative graph. Clearly distinguish hidden,
   unresolved/blocked and consumed historical geometry. Acceptance: inspection
   changes no document/history/dirty state and reflects Undo/Redo/Open immediately.
2. **Dependency/error contract hardening.** Decide canonical box/origin references
   and new blocked-feature policy, with legacy compatibility fixtures. Separate
   rejected proposal, direct evaluation failure and blocked descendant displays;
   retain root-cause links. Add a failure matrix across editing, loading and
   history restoration. Avoid storing diagnostics as authoritative model data.
3. **Explicit reference repair.** Show missing parent/face and attachment strategy;
   allow an intentional user-selected replacement with a preview of downstream
   consequences, one atomic undoable transaction and save/reopen tests. Never
   choose a nearest face automatically. Expand topology fixtures before adding
   edge-dependent operations such as fillets/chamfers.
4. **Suppression and controlled history editing.** Design suppression, insertion,
   reorder and rollback rules, including consumed bodies and dependent failures,
   before adding UI/schema. Test invalid cycles/forward references, suppression
   chains, recovery, Undo and persistence. Keep any timeline as a view over the
   existing authoritative ordered definitions.
5. **Performance only when measured.** Profile representative multi-feature parts
   before incremental regeneration/caching. Any optimization must preserve the
   tested atomic publication, historical parent evaluation and reference rules.

The next step should be inspection and diagnostics, not an architecture rewrite.

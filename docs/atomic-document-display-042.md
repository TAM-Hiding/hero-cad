# Atomic document and display updates — Work Order 042

Inspection baseline: `d2d556f8edc2e88a1a7b4b987eef4abe1d31cb26`
(merged PR #41). Findings recorded before behavior changes.

## Original publication boundaries

- `Document.set_features` evaluates geometry, publishes native reference caches,
  then replaces definitions and mutates Undo/Redo. `_restore` similarly publishes
  before the window has a chance to prepare display data.
- `MainWindow.apply_dimensions` calls those mutators and only afterward calls
  `refresh`. Box, extrusion, chamfer and sketch-entity Properties share this gap.
- `refresh` resets transient input/profile state, changes visibility/fields and
  then calls `display_solids`. A meshing exception can therefore occur after
  both document and presentation metadata have changed.
- Open/New assign `self.document` before refresh. Undo/Redo, deletion, creation
  and entity insertion commit through Document before refreshing the viewport.
- `Viewport.set_shape` already builds triangles and edges before assigning
  mapper inputs, but publishes `faces` and normals before completing edge maps.
  Later failures can leave picking metadata inconsistent. There is no reusable
  prepared-display object for the document/window boundary.
- Operation preview evaluates a separate Document and tests a surface mesh,
  but Apply regenerates again and refreshes after committing. Preview does not
  preflight the final wire/picking presentation. Failed preview restoration and
  Cancel also remesh the original model.
- Sketch display uses cached paths, while guide/camera callbacks and widget
  synchronization are intertwined with presentation. These should not become a
  second document model or a general renderer/caching rewrite.

The implementation and validation below address these boundaries without changing
the modeling algorithms or saved-document format.

## Chosen implementation

`Document.candidate()` creates an ordinary Document staging copy without running
its constructor or evaluator. Immutable definitions and evaluated B-reps/maps are
retained as inputs; Undo/Redo lists are copied so candidate mutations cannot alter
committed history. Existing mutators, including the leaf-sketch fast path and
unresolved-dependent policy, evaluate the proposal once. `adopt_candidate` checks
owner/baseline history/savepoint and copies the evaluated result into the original
Document object. It does not regenerate. Path and saved-feature metadata remain
owned by the original document. There is no parallel document/history system.

`Viewport.prepare_shape` builds triangles, boundaries, face/edge maps, analytic
normals and detached VTK mappers without changing actors. `SketchView.prepare_features`
likewise stages changed sketch, foreground, selection-highlight and preview layers
with a private cache update. Unchanged layers retain their meshes. Support-face
resolution/triangle extraction is also preflighted. VTK data is reference-counted;
mesh buffers are not deep-copied. Existing actors and their appearance are retained.

`MainWindow.edit_document` evaluates a candidate, prepares those display resources,
then publishes document/native state and mapper references synchronously, without
rendering, signals or event-loop processing inside the swap. Previous references
are retained until installation completes; an installation exception restores
the document, mappers, maps and support/sketch state. Only after publication are
old selections cleared; normal refresh synchronizes browser/Properties and renders.
Prepared data is handed to that refresh so it is not built twice.

| Path | Boundary and behavior |
|---|---|
| Box/extrusion/chamfer/sketch Properties | Existing mutator on candidate → native validation → solid/sketch/support preparation → adoption and display swap → ordinary refresh. Failed edits leave pending user text available for correction. |
| Undo/Redo | Restore on a staging copy, prepare display, adopt its evaluated state and history stacks together. Pending-text Undo retains the existing discard-text-first behavior. |
| Open/New | Prepare the replacement document and display before assigning it to the window; existing save/discard/cancel prompts remain. |
| Feature/entity deletion and sketch/entity creation | Use the same candidate preparation before changing browser context or selection. Existing deletion/reference guards remain. |
| Sketch visibility | Presentation-only candidate transaction; no solid regeneration or remeshing when the retained solid identity/visibility is unchanged. |
| Base-box visibility | Prepare before updating presentation metadata; a failure restores the action's checked state and retains the old valid mappings. |
| Ordinary refresh | Prepare the complete model display before resetting fields/profiles or replacing actor maps. Direct external model mutations remain the caller's responsibility (see limits). |
| Operation Preview/Apply | Preview uses the same Document evaluator/policy. Apply completes wire/maps/sketch/support preparation and adopts that evaluated candidate, eliminating the former second regeneration. |
| Preview invalidation/Cancel | Retain and restore the prior solid mappings/selection instead of rerunning a mesher that may be failing. Candidate and preview-mesh references are released on invalidation/cancellation/commit. |

The preview surface is reused on Apply only when the visible body collection
matches; a visibility-driven change requires the corresponding new display mesh.
Source-sketch auto-hide is included in the one staged feature transaction, so it
does not create an extra Undo entry. Changes to that preference invalidate preview.

## Failure semantics and diagnostics

A rejected geometry edit leaves committed definitions, caches and stacks intact.
A successfully evaluated upstream edit may still leave chamfers/attached features
unresolved and block their dependents. Those states are accepted when they were
accepted by the existing Document policy; this PR does not require every feature
status to be valid before publication. Save/reopen and Undo/Redo retain that policy.

Display failures use the existing `FeatureError`/`FeatureStatus`/`last_failure`
records, with stages `display_preparation`, the existing detailed `tessellation`
stage, or `viewport_presentation` for an installation failure. Stale publication
is distinguished as `document_publication`. Geometry errors retain their existing
specific stage or receive `geometry_evaluation`. Updating `last_failure` is the
intentional diagnostic change on rejection; geometry/history remain unchanged.
No transient errors, native shapes, VTK meshes or new metadata enter serialization.
No schema, dependency, precision or reference-matching changes are included.

## Regression coverage

`tests/test_atomic_updates_042.py` covers:

- Staging isolation, stale/wrong-owner refusal and adoption without regeneration.
- Real successful extrusion Properties edits: validity, mass, bounds, viewport
  bounds, one Undo entry, save/reopen, Undo and Redo.
- Geometry rejection and injected tessellation, edge conversion, picking-map,
  detached mapper, sketch/highlight layer and support-face preparation failures.
- An injected failure after mapper installation: restore the previous document,
  meshes, picking maps, selection and support/sketch resources.
- Undo/Redo/Open/New/deletion/refresh failures, leaf-sketch fast-path failures,
  failed visibility changes and save/reopen after failed Properties edits.
- Expected unresolved downstream chamfers/Cuts after accepted upstream edits.
- Apply with a valid preview but failing final wire preparation; retry then
  adoption with no regeneration and no redundant matching-surface tessellation.
- Cancel while both mesh-building functions are unavailable: restore cached state.
- Unchanged Properties during an active preview restore its retained baseline,
  rather than treating the temporarily empty viewport as reusable solid display.

The existing leaf-sketch CPU benchmark and rapid-input/debounce tests now count actual `Document._regenerate`
calls rather than constructor invocations, since staging intentionally bypasses
the constructor and uses candidate instances. Their zero-evaluation/one-evaluation assertions remain. Existing
attachment, picking, save/load, profile, appearance and framebuffer tests are kept.

## Performance reproduction

Use the same harness against baseline and revised sources on the same host:

```sh
LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb PYTHONPATH=.:/path/to/baseline/src xvfb-run -a .venv/bin/python tools/benchmark_atomic_updates_042.py --output /tmp/baseline.json
LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb PYTHONPATH=.:src xvfb-run -a .venv/bin/python tools/benchmark_atomic_updates_042.py --output /tmp/revised.json
```

The deterministic connected 5/20/50-feature fixtures reuse the PR #41 benchmark.
The last through-hole Cut's distance alternates 5.5/6 mm, with the same downstream
fin chamfer where present. Each sample performs a real Properties edit followed
by Undo and Redo. Three samples per case; initialization is outside timing. Total
latency includes normal Qt/VTK refresh/render; no fixed CI timing assertion is used.
The shared display-mesh preparation metric is tessellation/conversion plus edge
sampling. It excludes small map/mapper/overlay and widget synchronization costs,
which remain in total latency. Publication timing measures candidate adoption,
not the entire UI refresh. Timings overlap and are not additive stage partitions.
A framebuffer check requires shaded-body pixels, not just guides or background.
Peak RSS is cumulative process high-water memory, not per-part allocation or a
leak test. Native B-rep inputs and unchanged meshes are shared, not deep-copied;
old/new prepared resources coexist until a successful swap or failed candidate
is released. This temporary retention is necessary for rollback.

Final baseline/revised runs executed sequentially after the release suite,
with identical shaded-body pixel counts in each pair. AMD EPYC 9V74, nine
visible logical CPUs, Linux 6.18.57/glibc 2.39, Python 3.12.14, OCP 7.9.3.1
(wheel 7.9.3.1.1), Qt 6.8.3, VTK 9.6.2; software GL / TCP-Xvfb, viewport
**672×708**. These shared-host three-sample medians are not laptop guarantees.

| Features | Source | Properties total ms | Regenerate ms | Mesh prep ms | Adopt ms | Peak RSS MiB |
|---:|---|---:|---:|---:|---:|---:|
| 5 | Baseline | 80.9 | 31.3 | 20.3 | 0.000 | 599.3 |
| 5 | Revised | 87.2 | 31.6 | 21.2 | 0.028 | 598.5 |
| 20 | Baseline | 395.7 | 226.5 | 122.3 | 0.000 | 632.3 |
| 20 | Revised | 402.3 | 231.0 | 122.3 | 0.011 | 632.9 |
| 50 | Baseline | 1588.6 | 964.6 | 547.2 | 0.000 | 749.5 |
| 50 | Revised | 1511.9 | 930.3 | 505.6 | 0.011 | 753.3 |

| Features | Source | Step | Total ms | Regenerate ms | Mesh prep ms |
|---:|---|---|---:|---:|---:|
| 5 | Baseline | Undo | 93.8 | 30.6 | 20.7 |
| 5 | Baseline | Redo | 93.9 | 31.4 | 20.7 |
| 5 | Revised | Undo | 120.5 | 30.6 | 24.2 |
| 5 | Revised | Redo | 122.0 | 35.7 | 21.4 |
| 20 | Baseline | Undo | 412.2 | 220.4 | 127.4 |
| 20 | Baseline | Redo | 450.1 | 235.4 | 139.3 |
| 20 | Revised | Undo | 421.7 | 226.1 | 129.1 |
| 20 | Revised | Redo | 433.0 | 246.0 | 125.1 |
| 50 | Baseline | Undo | 1623.4 | 983.2 | 546.6 |
| 50 | Baseline | Redo | 1589.5 | 947.3 | 533.6 |
| 50 | Revised | Undo | 1521.2 | 943.8 | 496.9 |
| 50 | Revised | Redo | 1530.8 | 950.1 | 531.2 |

Every measured edit, Undo and Redo made **one regeneration, one surface build
and one edge build** in both versions. Revised adoption itself was below 0.03 ms
in these samples. No identical candidate is evaluated a second time for
publication. The leaf-sketch reuse tests and existing CPU benchmark separately
verify zero solid regeneration/display rebuilding for that fast path.

The 5-feature Properties sample increased 6.3 ms (7.8%); Undo/Redo increased
about 27/28 ms. At 20 features Properties increased 6.5 ms (1.7%); at 50 it
decreased 76.7 ms (4.8%). Do not interpret the decreases as an optimization claim.
Staging now includes retaining the old state, detached mapper/layer preparation
and installation before UI synchronization. Small-model fixed UI/GL costs and
run-to-run scheduling/mesher variation remain in the totals; these samples do
not isolate a precise cause for every difference. Importantly, structural counts
exclude an extra expensive regeneration or tessellation. Peak RSS is similar in
these runs (about 750 versus 753 MiB at the final case), not proof of leak freedom.

A suitable follow-up is to profile/coalesce fixed publication/refresh work on
small models if desktop testing makes that latency material. No general cache
or scheduler is justified by these measurements. Operation Apply is separately
tested to perform **zero additional regeneration** and reuse the matching preview
surface; this report does not claim a measured wall-time speedup for that path.

Raw timings, calls, native/Python source fingerprints, framebuffer pixel counts
and memory observations: [baseline JSON](benchmarks/atomic-042-baseline.json) and
[revised JSON](benchmarks/atomic-042-revised.json).

## Full validation

Final full X11/software-GL suite: **802 passed, 149 upstream warnings, no failures
or skips**, in 236.52 s. This includes **25 new transaction regressions**. The
standard desktop-file validator is installed in this environment, so the previous
PR's validator skip is now a pass. Existing framebuffer checks remain enabled.

Latest focused transaction/preview/sketch-reuse tests: 52 passed. Required document
suite: 23 passed. `pip check`, Python compilation and whitespace checks pass.
The existing leaf-sketch CPU benchmark completes all six cases with zero solid
regeneration/display rebuilding; its instrumentation was moved to Document-class
methods so it follows staging copies.

Two intermediate regressions were caught and fixed: the retained `world_path`
query and unchanged-native-geometry support-overlay reuse. Existing assertions
were preserved. Exact commands, intermediate results, environment setup and
remaining limitations are recorded in [VALIDATION.md](../VALIDATION.md).

## Remaining limits and follow-ups

- The guarantee covers model evaluation and required model-display preparation,
  plus exception rollback during the synchronous reference installation. It is
  not recovery from process termination, native crashes, out-of-memory termination
  or graphics-driver failures. VTK/OpenGL can report errors without raising a
  Python exception; the existing nonblank framebuffer tests remain important.
- Camera/guide updates, zoom-driven sketch quality adjustments and Qt widget
  synchronization run after a prepared geometry publication. They are not a new
  fully transactional UI framework. A failed later quality adjustment retains
  the already prepared geometry; there is no promise to roll back an entire
  window layout, preference write or asynchronous render callback.
- Code that directly mutates the live Document and then calls window.refresh
  bypasses the window's staging boundary. Refresh itself preserves prior actor
  data on preparation failure, but cannot undo an arbitrary external mutation.
  Application editing entry points listed above use the staged path. A future
  programmatic API should use this boundary rather than expose raw mutable state.
- Candidate staging copies the Undo/Redo pointer lists, not their immutable
  snapshots or geometry. Very long history lists should be profiled separately.
  New evaluated caches must be included in the explicit publication field list.
- There is no thread-safe multi-writer document API. The baseline check rejects
  stale candidate publication; it does not add concurrency or background modeling.
- Preview still needs its initial candidate evaluation and mesh. Apply needs final
  boundary/picking/layer preparation and may need a new surface if visibility
  differs. No general mesh cache, dependency scheduler or renderer rewrite is added.
- Future work: exercise a supplied large user document, improve non-exception
  rendering diagnostics, and consider narrowly scoped camera/widget error handling
  only if concrete failures justify it. Keep existing strict reference identity
  and explicit unresolved-dependency behavior.

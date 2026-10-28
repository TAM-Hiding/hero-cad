# Safe sketch entity commits — Work Order 034

Baseline: `37f3404` (main after PR #33). See
[PR #32 profiling](SKETCH_COMMIT_PERFORMANCE.md) for the original diagnosis.

## Existing workflow

The construction controller emits an entity; `MainWindow.entity_created` commits
pending property edits, calls `Document.add_entity`, selects the entity and
refreshes the UI. Entity insertion replaces immutable sketch parameters through
`set_features`. Previously every entity change ran ordered regeneration, rebuilt
solid shapes, face maps/lineage and the final compound, then recorded Undo.
Refresh rebuilt/tessellated the visible solid compound, picking maps and volume,
updated sketch display, browser, Properties/status/actions, then rendered.

The measured dominant costs were ordered solid regeneration and solid display
reconstruction. Skipping display reconstruction alone was unsafe: regeneration
replaced the native shapes underpinning the retained picking maps.

## Boundary and publication

`Document._leaf_sketch_shapes` accepts only one existing sketch's entity changes:

- Feature count/order, UUID, type, references, visibility, plane, attachment and
  resolved frame must all remain unchanged.
- No feature may reference the changed sketch. Checking the existing authoritative
  `Feature.references` directly is sufficient: without a direct consumer there
  cannot be a transitive consumer. No dependency graph is added.
- Every current feature status must be valid. Unresolved histories fall back.
- Global entity/feature UUID collisions are rejected as in full regeneration.
- Build and validate the candidate sketch before publishing any changed state.

Only that sketch's evaluated wire/edge compound is replaced. The final solid
compound, solid shapes, face maps, lineage, source faces, active body IDs and
statuses remain the **same objects**. Other evaluated sketches are retained too.
The normal transaction records immutable definitions in Undo, clears Redo and
resets the failure diagnostic. A failed build leaves definitions, caches and
both stacks unchanged.

`refresh(reuse_unchanged_solids=True)` is requested only by entity creation and
property application. It skips `display_solids` only when the displayed document
and evaluated solid compound are the exact same objects and base visibility is
unchanged. Consequently native faces/edges, VTK meshes and picking maps survive
together. Selection clearing and all normal sketch/browser/property/action/status
synchronization remain. Fit requests and ordinary refresh always rebuild.
Operation previews cancel through the existing restoration path before this
check. PR #33's existing support overlay reuse remains effective for leaf edits;
its settings, opacity, frames, snapping, camera and render behavior are unchanged.

## Conservative behavior and limits

Consumed sketches (even edits to unused entities within them), changed frames or
attachments, multiple definition changes, feature insertion/deletion/reordering,
extrusions/Booleans, upstream edits and unresolved histories use full regeneration.
Undo/Redo deliberately keep their existing full restoration and presentation
rebuild, including recovery of previously unresolved downstream features.
Save/reopen retains the existing schema and rebuilds geometry on load.

This is not general incremental regeneration or a geometry cache. Long histories
still incur definition/UUID scans and browser/sketch updates. Active sketch
rebuilding still scales with its entity count. Consumed-sketch edits and history
navigation can remain slow. The user's `test8.starcad` was not supplied; only
synthetic public fixtures were used. No private documents were added.

## Reproduction and measurement

Run from the repository root in the pinned Python 3.12 environment:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=.:src .venv/bin/python tools/benchmark_leaf_sketch_commit.py
```

For baseline, run the same script with the unchanged baseline source directory
first in `PYTHONPATH`, followed by `.`. The script reuses PR #32's fixture and
real completion slot. Five independently constructed fixtures per row; setup is
outside timing. Existing-feature counts exclude the active sketch. The 100-row
adds an unused origin sketch to reach exactly 100. The Boolean fixture has eight
successive through-depth cylindrical Cuts on the box (17 existing features).

Render is disabled, so measurements are CPU-side commit latency, not GPU time,
frame rate, or a guarantee of desktop responsiveness. No CI timing thresholds.
"Insertion" includes immutable replacement, boundary/UUID checks and history
publication. "Regeneration" excludes sketch construction; "sketch build" counts
all sketch evaluation in the baseline and just the changed sketch afterward.
"UI sync" is total minus document and solid-display time. Each column is its own
median, so rounded stage medians need not sum exactly to the total median.

CPU stage medians in milliseconds; baseline and optimized runs executed
sequentially after the test suite, on the same host.

| Existing features | Entities | Version | Insertion | Regeneration | Sketch build | Solid display | UI sync | Total |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | 10 | Baseline | 0.056 | 0.740 | 0.180 | 1.967 | 2.766 | 5.893 |
| 1 | 10 | Optimized | 0.090 | 0.000 | 0.253 | 0.000 | 2.728 | 3.081 |
| 25 | 10 | Baseline | 0.272 | 15.328 | 0.970 | 98.372 | 3.620 | 118.669 |
| 25 | 10 | Optimized | 0.277 | 0.000 | 0.304 | 0.000 | 2.818 | 3.436 |
| 75 | 10 | Baseline | 0.739 | 42.743 | 2.390 | 284.246 | 4.671 | 335.501 |
| 75 | 10 | Optimized | 0.780 | 0.000 | 0.298 | 0.000 | 4.287 | 5.443 |
| 100 | 10 | Baseline | 0.927 | 54.393 | 3.024 | 366.425 | 5.774 | 431.066 |
| 100 | 10 | Optimized | 0.878 | 0.000 | 0.297 | 0.000 | 4.621 | 5.778 |
| 75 | 50 | Baseline | 0.791 | 42.877 | 2.885 | 289.849 | 5.682 | 342.788 |
| 75 | 50 | Optimized | 0.707 | 0.000 | 0.798 | 0.000 | 5.191 | 6.721 |
| 17-cuts | 10 | Baseline | 0.257 | 142.201 | 1.205 | 125.866 | 3.784 | 270.442 |
| 17-cuts | 10 | Optimized | 0.220 | 0.000 | 0.270 | 0.000 | 2.731 | 3.250 |

At 75 existing features / 10 entities, total CPU latency dropped from
335.501 to 5.443 ms (about 62×); at 100 features, 431.066 to 5.778 ms
(about 75×). The eight-Cut fixture dropped from 270.442 to 3.250 ms.
Full solid regeneration and display reconstruction were absent on every
optimized sample. These synthetic results do not measure the user’s stress file.

## Regression coverage

`test_leaf_sketch_commit.py` covers repeated lines/circles and numeric edits to a
non-terminal unused face sketch, identity of all retained native solid state,
Undo/Redo/savepoint behavior, atomic sketch failures and duplicate IDs, consumed
sketch edits, upstream edits, unresolved fallback and Undo recovery, and
save/reopen of a face sketch on Boolean geometry with matching topology/references.

`test_leaf_sketch_commit_ui.py` exercises the real entity completion/property
application path, mesh/picking/support overlay identity, X-ray opacity, face and
edge picks, creation of an attached sketch from the retained picked face, full
history display rebuild, and document/visibility/geometry invalidation.
Existing document/history/sketch/attachment/viewport tests remain authoritative
for the full regeneration pathway and interactive input behavior.

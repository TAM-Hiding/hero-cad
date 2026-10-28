# Sketch commit profiling — Work Order 032

Baseline: main d8c066589f71fd5d59033dba9afb91491783f5da.

Run `.venv/bin/python tools/profile_sketch_commit.py` for document medians
(five independently constructed fixtures). Run
`QT_QPA_PLATFORM=offscreen PYTHONPATH=.:src .venv/bin/python tools/profile_sketch_commit_ui.py`
for CPU-side UI medians (three independently constructed fixtures).
The UI procedure explicitly disables Render: this host cannot initialize OpenGL.
These are synthetic separated circular extrusions, not the user's actual model.
No performance threshold is asserted in CI.

| Existing features | Active lines | Document commit ms | CPU UI commit ms |
|---:|---:|---:|---:|
| 1 | 10 | 0.861 | 5.764 |
| 1 | 50 | 1.266 | 7.863 |
| 1 | 100 | 1.749 | 10.110 |
| 1 | 250 | 3.348 | 12.718 |
| 25 | 10 | 14.944 | 121.461 |
| 75 | 10 | 44.461 | 343.433 |

Existing-feature counts exclude the active sketch. UUIDs vary between runs.
Setup is outside timing. UI timing invokes the real entity_created completion
slot, excluding pointer routing and GPU rendering. cProfile follows the timed
samples; its times are diagnostic and are not interchangeable with wall medians.

## Path and measured costs

LineTool constructs a validated Line, then the sketch controller emits completion.
MainWindow.entity_created applies pending numeric edits if necessary, calls
Document.add_entity, selects the new entity, and calls refresh. add_entity replaces
immutable sketch parameters and runs set_features. Full ordered regeneration
rebuilds earlier sketches, extrusions, face lineage and the final compound before
appending an Undo snapshot and clearing Redo. Refresh clears profile caches,
rebuilds solid display meshes and volume, updates sketch display, rebuilds the
browser, updates Properties/status/actions, and renders. Profile picking itself
is separate; extrusion regeneration does resolve its source profiles.

History length dominates this fixture. At 75 features the document transaction
accounts for about 44 ms of the 343 ms CPU path. The UI profile is dominated by
solid tessellation/VTK mesh construction (tens of thousands of point/cell/normal
insertions), with browser and sketch updates much smaller. Active sketch size
also adds cost, but 250 lines in a small document remains about 13 ms here.

## Optimization decision

A trial skipped display_solids after commits to sketches with no consumers,
while retaining document regeneration. CPU medians became 3.785/5.421/5.920/11.314
ms for the four small-document cases, and 22.487/51.923 ms for 25/75 features.
**This trial is NOT shipped.** Regeneration creates fresh OCCT shapes; retaining
old face/edge display mappings can break identity-based face attachment/picking.
A latency improvement is insufficient evidence of correctness.

Recommended follow-up: coordinate reuse of unchanged evaluated solid shapes and
their disposable display mappings, with explicit invalidation for dependencies,
failed regeneration, Undo/Redo, file replacement and visibility changes. This
requires a separately scoped design and identity/attachment regressions. Avoid
merely skipping refresh or asynchronously publishing mismatched geometry/maps.
No production optimization, model/schema/history change, or logging is included.

## Validation and limitations

77 focused tests passed: test_line_profiles.py, test_sketch_editing.py,
test_document.py plus two temporary UI checks of the rejected trial. Those trial
checks are not shipped. Native UI profiling aborted with unavailable OpenGL;
CPU profiling disables Render and cannot establish interactive GPU latency.
The full suite was not run. Reproduce on the user's real document and desktop
before selecting a broader optimization. Baseline and final production behavior
are identical; no before/after speedup is claimed for this PR.

## Work Order 034 follow-up

The coordinated, entity-only leaf-sketch optimization and new measurements are
documented in [LEAF_SKETCH_COMMIT_PERFORMANCE.md](LEAF_SKETCH_COMMIT_PERFORMANCE.md).
The rejected mesh-only shortcut above remains rejected.

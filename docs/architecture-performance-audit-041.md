# Architecture, performance and geometry reliability audit — Work Order 041

Baseline: merged PR #40, `b38c144d7a5f9b3103b35ccd9a05b753c7e5ce17`.
Linux desktop, offline mechanical modeling; millimetres throughout.

## Assessment and implemented scope

Retain the architecture. Immutable feature definitions, conservative references,
ordered candidate evaluation and transactional publication provide a sound base.
The expensive paths are full ordered regeneration and solid display preparation,
not accidental regeneration on ordinary camera movement. Complexity and the type
of features matter more than their count alone.

This PR adds repeatable benchmarks, a raw kernel investigation tool, focused
regressions and stage-specific diagnostics. It changes neither geometry algorithms
nor accepted parameters. It does not add a fallback chamfer, clamp distances,
change reference matching, redesign history, alter document versions or add dependencies.

A local shape-indexing optimization was evaluated and removed. In a 50-feature
model, wall instrumentation attributed 0.756 s of 2.677 s to face propagation
(nested within Boolean/chamfer time). Replacing pairwise descendant matching with
an OCCT indexed map gave 26.85 versus 26.59 ms in a nine-sample isolated
propagation experiment: insufficient evidence of material improvement. Native
history queries remained expensive. No production performance claim is made.

## Architecture inventory

| Responsibility | Authoritative implementation | Findings |
|---|---|---|
| Definitions, UUIDs, parent references | `features.py`, `sketch.py` | Frozen dataclasses; explicit earlier-feature IDs. No second graph is needed. |
| Evaluation, transactions and history | `document.py` | Ordered evaluation; candidate maps publish after final compound construction. Undo/Redo store definitions and regenerate. |
| Sketch regions and extrusion | `profiles.py`, `line_profiles.py`, `geometry.py` | Analytic wires/faces, exact boundary membership and holes. Display paths are not modeling input. |
| Join/Cut/Intersect | `booleans.py` | Non-destructive, sequential OCCT operations; accepts one valid positive-volume solid. Face-contact Join checks the Fuse result. |
| Chamfer | `chamfers.py` | Body-scoped checked edge witnesses; explicit contour coverage; one native builder; validates before publishing ancestry. |
| Face identity | `attachments.py`, `face_history.py`, `face_geometry.py` | Semantic construction faces, ancestry witnesses and strict geometry snapshots have different deliberate recovery limits. |
| Persistence | `persistence.py`, `Document.save/load` | Parameters only; strict v1–v14 reader, minimal writer version, bounded payload, same-directory flushed atomic replacement. |
| Inspector/diagnostics | `history_inspection.py`, `FeatureStatus`, `FeatureError` | Derived from evaluation results; never causes regeneration. PR #40 supplies blocked-parent links. |
| Display and picking | `ui/display_geometry.py`, `viewport.py`, `picking.py` | Disposable meshes and transient subshape indices; native B-rep remains authoritative. |
| Operation lifecycle | `ui/operation_panel.py`, `main_window.py` | Candidate document → display preparation → Apply through the existing document transaction. |

Regeneration validates references and identifiers in feature order. Historical
solids remain available for references; `active_body_ids` identifies current
outputs after consumption. Failed existing operations suppress their output and
block dependents; valid independent branches remain. A newly requested or directly
edited invalid chamfer is rejected atomically. This distinction is intentional:
an accepted upstream change may leave a downstream feature unresolved rather than
silently retaining obsolete output. Restoring the definitions recovers it.

`_leaf_sketch_shapes` is an existing, narrow fast path: one unused sketch's entity
edit, unchanged frame/identity/references, all statuses valid. It retains all native
solid maps and display picking identities. Visibility-only changes also reuse
geometry. Other edits, Undo/Redo and load perform full regeneration. No general
incremental feature cache exists.

## Rendering and responsiveness

`MainWindow.display_solids` collects visible active bodies and builds a compound.
`Viewport.set_shape` performs native meshing, per-face VTK triangle conversion,
analytic UV normal evaluation, boundary-edge sampling and analytic picking maps.
Surface, edge and highlight actors are retained; actors are not recreated for
every refresh. CAD faces keep separate vertices so corners are not smoothed away.

Solid meshing uses **0.02 mm linear / 0.08 rad angular deflection**. Camera/style
updates reuse meshes. Zoom-adaptive sketch curves are a separate bounded display
policy, not evidence of solid regeneration. OCCT may retain triangulations on
native shapes, but Python-to-VTK conversion and normal calculation run again on
`set_shape`. Benchmarks use newly regenerated shapes for cold mesh measurements.
Sketch paths cache by entity UUID plus frame, immutable entity parameters and
quality band; removed IDs are pruned. Profile-region classification caches per
sketch during inspection and is cleared on document refresh. Solid, sketch and
profile caches therefore have different lifetimes; none is a second feature
history.

Current opportunities and costs:

- `refresh` normally rebuilds solid display; the existing leaf-edit reuse path is
  deliberately narrower. Preview builds a new candidate, Apply evaluates it again,
  and Cancel/failed-preview restoration can rebuild the original display. Reusing
  candidate geometry or cached meshes needs careful document/shape/visibility/
  picking invalidation, rather than just skipping refresh.
- Face propagation repeatedly queries `Modified/Generated/IsDeleted`; evaluated
  face signatures scan adjacency. These become expensive over long Boolean chains.
- `picking.candidates` projects every polyline segment in Python. Edge picking
  grows with sampled boundary points; face picking uses VTK's cell picker.
  `selected_mesh` also scans cell IDs to extract highlights. This is a separate
  interaction cost from regeneration and meshing.
- Every render computes style/contrast and clipping from current scene state.
  No kernel call or solid tessellation was observed in camera/style/selection
  regression checks. No renderer rewrite is justified by this audit.

### Reproduction and measurements

From the repository root, with the pinned Python 3.12 environment:

```sh
PYTHONPATH=.:src .venv/bin/python tools/benchmark_audit_041.py --samples 3 --output /tmp/audit-cpu.json
LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb PYTHONPATH=.:src xvfb-run -a .venv/bin/python tools/benchmark_audit_041.py --samples 3 --viewport --output /tmp/audit-rendered.json
PYTHONPATH=.:src .venv/bin/python tools/probe_chamfer_041.py --mesh-invalid --alternative --output /tmp/chamfer-probe.json
```

For an unchanged baseline, place a detached baseline checkout's `src` before `.`
in `PYTHONPATH`, using this same benchmark harness. The JSON records dependency
versions, source and harness digests, commit, CPU, display settings and sample
counts. When overriding `PYTHONPATH`, source digests identify the modules actually
tested; the commit field identifies the launching checkout. `--features 5 20 50 100`
selects cases individually. There are no normal-CI
wall-time or frame-rate thresholds. Optional profiling:

```sh
PYTHONPATH=.:src .venv/bin/python -m cProfile -o /tmp/audit.prof tools/benchmark_audit_041.py --features 50 --samples 1 --output /tmp/profile-case.json
```

These are connected mechanical parts, not independent boxes used to inflate
feature count: an 80×70×5 plate, a face-attached joined rounded fin, and a grid of
through holes. The 20/50/100-feature cases also include a four-edge fin chamfer.
The 5-feature case has one hole; the others have 8/23/48 holes. Model A is slightly
more complex than the suggested rectangular solid. Model B is a plate with an
upright rib, rather than a supplied real-world bracket. No user model was provided.

Construction measures initial ordered evaluation plus a second evaluation for
reference-derived chamfer creation. It does **not** measure repeated interactive
authoring. Load includes disk read, JSON parsing and regeneration. Regeneration
recreates a document from the same definitions. Per-feature rows come from a
separate line-traced pass and include tracing overhead; the normal regeneration
column is uninstrumented. Individual column medians need not sum exactly.

Viewport updates include display preparation and a real render at 800×600.
Navigation samples orbit plus clamp/clipping/render; face selection includes
highlight/render, while edge picking is a query. They are synchronous latency
samples, not an interactive FPS guarantee. A framebuffer color-range check rejects
blank rendering; zero rebuild counters distinguish navigation from modeling cost.
Peak RSS is sampled after each CPU pass, before that case's viewport pass. It is
process high-water memory including Python, Qt/VTK/OCCT, retained histories and
earlier cases (including their viewports), not per-part allocation or a leak
measurement.

Sequential runs after both full test suites completed; three samples per CPU
stage and at least five navigation/selection samples. Host: Intel Xeon Platinum
8573C, nine visible logical CPUs, Linux 6.18.57/glibc 2.39, Python 3.12.14,
OCP 7.9.3.1 (wheel 7.9.3.1.1), VTK 9.6.2, Qt 6.8.3, NumPy 2.5.4.
Rendering: Mesa llvmpipe (LLVM 20.1.2), software GL, TCP-Xvfb, 800×600.
This shared host has ordinary run-to-run scheduling/meshing variation.
The diagnostics build contains no accepted performance optimization; differences
between these runs are **not evidence of a speedup**. Construction is one sample.

| Features | Source | Build ms | Load ms | Regenerate ms | Native mesher ms | VTK/normals ms | Edge mesh ms |
|---:|---|---:|---:|---:|---:|---:|---:|
| 5 | Baseline | 62.7 | 49.7 | 46.5 | 11.2 | 18.3 | 0.9 |
| 5 | Diagnostics | 93.1 | 59.0 | 65.9 | 18.6 | 22.5 | 1.4 |
| 20 | Baseline | 760.0 | 397.0 | 404.9 | 98.9 | 87.1 | 4.7 |
| 20 | Diagnostics | 613.2 | 413.2 | 388.2 | 85.0 | 94.3 | 4.5 |
| 50 | Baseline | 3894.1 | 1654.9 | 1576.6 | 440.9 | 216.6 | 8.3 |
| 50 | Diagnostics | 3122.0 | 1619.8 | 1537.6 | 463.9 | 221.2 | 9.6 |
| 100 | Baseline | 8764.7 | 4496.5 | 4551.6 | 1604.5 | 387.8 | 16.1 |
| 100 | Diagnostics | 8721.8 | 4691.5 | 5294.5 | 1562.8 | 449.0 | 19.9 |

| Features | Source | Viewport update ms | Orbit/render ms | Face selection/render ms | Edge query ms | Peak RSS MiB |
|---:|---|---:|---:|---:|---:|---:|
| 5 | Baseline | 61.1 | 16.5 | 17.6 | 1.0 | 488.3 |
| 5 | Diagnostics | 63.0 | 18.2 | 23.6 | 1.2 | 492.0 |
| 20 | Baseline | 212.0 | 21.6 | 29.8 | 4.6 | 668.1 |
| 20 | Diagnostics | 213.6 | 25.1 | 38.0 | 4.5 | 666.0 |
| 50 | Baseline | 733.0 | 29.8 | 39.8 | 11.1 | 792.8 |
| 50 | Diagnostics | 741.5 | 29.8 | 41.0 | 9.8 | 800.6 |
| 100 | Baseline | 2193.4 | 38.5 | 53.5 | 31.5 | 948.8 |
| 100 | Diagnostics | 2029.0 | 40.4 | 50.0 | 32.3 | 1003.6 |

Every viewport-only run recorded **0 regeneration, 0 tessellation and 0 edge-mesh
rebuilds**, with a nonblank framebuffer. Mesh counts agree between sources:
1,288 / 6,372 / 15,912 / 31,812 triangles. Raw files include per-feature timing
rows, boundary sample counts and renderer capabilities:
[baseline JSON](benchmarks/audit-041-baseline.json) and
[diagnostics JSON](benchmarks/audit-041-diagnostics.json).

At 100 features the baseline spends about 4.6 s regenerating and 2.2 s on a
new viewport update, versus 38.5 ms orbit/render and 31.5 ms for the sampled
edge query. Native meshing and Python-to-VTK/normal conversion are separate
measurable costs. The data supports targeted regeneration/display/picking
investigation, not conflating every slowdown with camera motion.

## Chamfer boundary investigation

The deterministic fixture is a 40×30×5 rectangular base, a sketch attached to +Z,
a slot with 1 mm radius / 12 mm center distance (2 mm width), Join extrusion of
10 mm, and all four upper perimeter edges at Z=15. All edges resolve and the
builder covers the complete explicit contour.

| Requested distance (mm) | Native builder | Topology | Solids / faces | Display triangles from raw result | Application behavior |
|---:|---|---|---|---:|---|
| 0.5 | Done, non-null | Valid | 1 / 15 | 1752 | Accepts |
| 0.9 | Done, non-null | Valid | 1 / 15 | 1908 | Accepts |
| 0.99 | Done, non-null | Valid | 1 / 15 | 1812 | Accepts |
| 0.999 | Done, non-null | Valid | 1 / 15 | 1760 | Accepts |
| 1.0 | Done, non-null | **Invalid** | 1 / 15 | 1911 | Rejects during result validation |
| 1.001 | Done, non-null | **Invalid** | 1 / 15 | 5918 | Rejects during result validation |
| 1.2 | Done, non-null | **Invalid** | 1 / 15 | 63038 | Rejects during result validation |

See [raw probe data](benchmarks/audit-041-chamfer.json). Rejected results were
meshed only with the explicit investigation flag; HERO rejects them before display.
Triangulation can succeed for an invalid solid and is not geometric validation.
Likewise builder completion and positive computed mass do not prove validity.
Mass values from invalid B-reps are diagnostic observations, not physical volumes.
Triangle counts may vary with mesher execution; no CI test requires exact counts.

The failure stage **reproduced here is post-builder result validation**, not edge
resolution, feature commit, actor creation or tessellation. The precise reported
"OCCT did not generate a display mesh" failure did not reproduce with these
specified dimensions and the pinned OCCT 7.9.3 environment. The user's actual
saved document, detailed dimensions and operation sequence were not supplied.
It would be incorrect to attribute that original message to invalid topology
without inspecting that specific result.

The nominal top-face consumption explains why this is a geometric boundary, but
is not proof that OCCT correctly performed the intended transition: the rejected
raw shape still has 15 faces and fails `BRepCheck_Analyzer`. This audit does not
claim a particular defective native surface or OCCT bug has been isolated.

### Diagnostics and preservation

Chamfer errors now carry an optional stable stage through existing `OperationError`
→ `FeatureError.status` / `Document.statuses` → history inspector:
`edge_resolution`, `input_validation`, `chamfer_construction`, `result_validation`
and `reference_publication`. Failed result messages identify the builder/result
boundary, validity, solid count and diagnostic mass. Extra inspection runs only
on rejected results. Successful operations retain their existing validation cost.
The requested distance is never changed.

Missing/empty face triangulations raise a display-only `DisplayMeshError` with
`tessellation` stage, transient face index, native mesher completion/status flags
and quality settings. Its message explicitly leaves the geometric cause open.
Display diagnostics do not rewrite geometry statuses or become serialized history.
These stages locate observed failure; they are not a claim that every possible
kernel exception now has a precise geometric explanation.

Regressions check valid volume/bounds and usable meshes below the limit, controlled
failure/validity at and above it, unchanged object identities and Undo/Redo stacks
on rejection, unchanged serialized bytes after a failed distance edit, safe
save/reopen, failed-preview cancellation, and display restoration after an injected
mesh failure. `Viewport.set_shape` already prepares surface and wire meshes before
replacing actors/maps; tests verify that either preparation failure retains the
previous meshes, maps and selected geometry. Successful previews clear transient
old selections before presenting the candidate.

A valid B-rep can still fail display preparation in a direct Properties refresh,
which is outside the operation-panel preview transaction. Existing `apply_dimensions`
commits the kernel-valid document before `refresh`. This broader presentation
atomicity gap is documented below; it is not represented as fixed by the new
preview tests. A graphics-driver failure after VTK starts rendering likewise is
not generally rollback-safe.

### Face-consuming alternatives: feasibility, not a fallback

The investigation tool explicitly reconstructs **this one stipulated fin roof**:
shorter lower extrusion, a triangular prism along the center segment and end
cones, fused with the base. All three results validate as one solid and mesh:

| Distance (mm) | Top Z (mm) | Volume (mm³) | Result |
|---:|---:|---:|---|
| 1.0 | 15.000 | 6257.321531 | Ridge, top face consumed |
| 1.001 | 14.999 | 6257.294390 | Ridge lowered 0.001 mm |
| 1.2 | 14.800 | 6251.893213 | Ridge lowered 0.2 mm |

This establishes that a valid stipulated continuation is geometrically feasible;
it does not make every overextended chamfer unique. It reconstructs from known
slot dimensions and provides **no ancestry mapping** for the replacement faces.
It is available only in the investigation CLI and is never called by application
operations. General support would need explicit intent rules, concave/intersecting
case exclusions, native history propagation/reference handling, topology-change
validation and bounded preview computation. Surface trimming and alternative
sequences were reviewed conceptually, not established as working universal methods.

## Reference stability and history audit

| Change tested | Observed result | Interpretation |
|---|---|---|
| Base width 40→45 under joined fin/chamfer/Cut | Resolves; downstream valid; save/reopen and Undo/Redo stable | Fin's support/edge geometry is unchanged. |
| Slot radius 1→1.5 | Fin updates; stored chamfer rim unresolved; downstream Cut blocked | Curved/slot witnesses require exact geometry. Conservative refusal, not wrong-edge attachment. |
| Fin distance 10→11 | Chamfer unresolved; dependent Cut blocked | Upper rim moved; general extrusion-edge transport is not implemented. |
| Insert unused XZ sketch before chamfer | Remains valid | Feature position is not identity. |
| Insert unrelated hole Cut before chamfer; explicitly retarget body UUID | Remains valid despite changed edge count | Same checked rim witnesses resolve; no index fallback. This test uses an explicit definition edit, not automatic retargeting. |
| Narrow fin so chamfer cannot fit, with sketch attached to its surviving top | Chamfer unresolved; face sketch blocked; Undo recovers | No stale cached attachment used. Does not claim a valid face-consuming native chamfer. |
| Remove referenced feature/entity | Existing deletion guards reject surviving references | Intentional dependency protection. Batch deletion/restore covered by existing history tests. |
| Suppress feature | Unsupported | Visibility is not suppression; no suppression system added. |

These results are verified after save/reopen and history restoration. Existing
semantic-box tests cover transported principal box edges; circular/slot edges do
not inherit that special case. Existing persistent/current-face suites cover
split, merge, missing and ambiguous descendants. General face snapshots deliberately
fail after checked geometry changes. References are never resolved by edge index,
nearest geometry or traversal order.

## Technical debt and UX consistency

1. **Presentation failures after kernel commit.** Properties updates and some
   general refresh/open paths can publish kernel-valid geometry before display
   preparation fails. A narrow staged-display transaction should be evaluated
   separately, including document caches, history stacks, selection and actor maps.
2. **Repeated operation evaluation/display.** Candidate preview, Apply regeneration
   and restoration are coupled through UI methods. Candidate adoption must preserve
   transaction semantics, current baselines and attached-frame normalization;
   simply assigning the preview document is unsafe.
3. **Native history and Python adjacency scans.** Several modules enumerate shapes
   and derive relationships repeatedly. Duplication exists between modeling
   `face_history.subshapes` (generic shape explorer) and display `subshapes`
   (indexed typed shapes). They have different return-type contracts. Do not merge
   them without measuring and checking callers.
4. **Failure policies differ by feature type.** Existing chamfer direct edits are
   atomic; accepted upstream edits can suppress dependents. Some primitive profile
   failures are hard errors while line-profile gaps are recoverable. This should
   be documented/tested as policy before introducing additional modeling tools.
5. **Broad UI exception handling.** The operation panel can restore a normal failed
   preview, but restoration itself can raise. General OpenGL exceptions and blank
   output are not a fully isolated transaction. Current successful real render
   checks do not prove every driver or machine behaves identically.
6. **Diagnostics are partly structured.** Root dependencies, face resolution and
   new chamfer stages are inspectable, but most reasons remain text. A stable
   programmatic error code/detail contract should extend these existing records,
   not parse human strings or add a parallel diagnostic store.

Tool activation, Escape/Cancel, quick-input parsing, selected-edge collections,
shared operation definitions, feature creation/editing, Properties/history
synchronization and Undo/Redo use the existing implementations. The new tests
exercise real candidate documents and viewport actors. Existing UI suites remain
the wider coverage for extrusion/combine input and selection behavior. No toolbar,
Properties layout or command workflow redesign is included.

## Future geometry-aware previews

Extend the existing candidate-document and preview-actor path. Compare accepted
input and candidate topology only after validation; retain parameters and last
valid model. Native builder `Modified/Generated/IsDeleted` information and current
face lineages can identify some affected references. They do not yet describe
all removed volume or establish intent after a topology transition.

| Future capability | Existing foundation | Missing work |
|---|---|---|
| Translucent removed/added material | Input body + validated candidate | Optional Common/Cut comparisons, cost budgets, separate non-pickable overlays |
| Disappearing face indicators | Native deletion/history + source ancestry | Distinguish disappearance/merge/split, affected downstream references, clear severity |
| Consequence callouts | Exact requested parameters + candidate bounds | Explicit semantic measurements (e.g. fin height loss), not inferred warnings on every operation |
| Programmatic inspection | UUIDs, immutable parameters, statuses, blocked-parent and stage fields | Stable operation/result codes and structured details; versioned contract design |
| Controlled alternative construction | Proven one-fixture reconstruction | Intent boundary, user-visible method, reference ancestry, validity and computational limits |

Ordinary valid operations should display normally. Valid but consequential results
could show material/topology differences and affected references. Ambiguous,
invalid or overly expensive operations should explain the observed limitation and
preserve the input. Never silently clamp parameters, choose another edge, switch
construction methods or assume that an overextended chamfer has one continuation.
No AI API, external control layer or autonomous modeling is implemented here.

## Prioritized follow-up sequence

| Priority/category | Proposed work | Evidence/benefit | Complexity | Regression risk |
|---|---|---|---|---|
| P1 correctness | Stage display preparation before Properties/Open publication | Confirmed code-path gap above; prevent kernel-valid but undisplayable state from surprising the UI | Medium | Medium–high: state/stacks/actors must agree |
| P1 performance | Profile native Boolean/history calls on supplied detailed user parts | Repeated full regeneration and native history dominate connected-part growth | Medium investigation; changes TBD | Low for profiling, high for generic incremental evaluation |
| P2 performance | Cache candidate display data / eliminate redundant preview restoration work | Full surface conversion repeats; per-face normal extraction has measurable CPU cost | Medium | Medium: visibility and picking-map invalidation |
| P2 performance | Spatial/projected acceleration for edge picking | Linear screen-space segment scans grow with boundary samples | Medium | Medium: occlusion/tolerance/selection identity |
| P2 architecture | Extend existing transient diagnostics with stable codes/details | Automation and UI can inspect causes without parsing text | Small–medium | Low–medium: preserve defaults and file format |
| P2 modeling UX | Explicit reference repair with affected-dependent preview | Slot/extrusion edge edits safely unresolved, but recovery requires deliberate reselection | Medium–large | High: never attach to unrelated geometry |
| P3 geometry/preview | Prototype constrained face-consuming fin continuation with ancestry | The stipulated ridge experiment validates but has no persistent mapping | Large | High: degenerate/intersecting cases |
| Later features | Resume new modeling tools after targeted correctness/performance work | Avoid accumulating unmeasured state coupling | Per-tool | Per-tool |

No additional PRs are created by this audit. These are sequenced recommendations,
not claims that all listed work fits one maintenance pass.

## Validation and limits

The unchanged baseline full X11 suite passed **755 tests**, skipped **1** and
reported 148 upstream warnings. The final full suite passed **776 tests**, skipped
**1** and reported 149 upstream warnings: **21 additional passing regressions,
no new or existing failures in the supported test environment**. The skip is the
uninstalled standard desktop-file validator; the real launcher/framebuffer test
passed. Warnings come from VTK's NumPy 2.5 array-shape deprecation.

Focused geometry/reference suites passed 152 tests; the required document suite
passed 23. New kernel/viewport cases passed 21, including nonblank actual-frame
checks. `pip check`, Python compilation and whitespace checks passed. Initial
Qt-offscreen/Unix-socket-X11 attempts were unsuitable for this sandbox and are
recorded, with commands and outcomes, in [VALIDATION.md](../VALIDATION.md). The
accepted full runs used software GL and TCP-X11 inside the isolated sandbox;
normal local reproduction should use the README's ordinary Xvfb command.

The measurements are synthetic, local Linux results, not a rating of the user's
NVIDIA laptop or a guarantee for arbitrary complex models. There is no supplied
real part, desktop manual signoff, physical input latency measurement, driver
comparison or leak soak test. The exact original tessellation failure remains
unreproduced; both real invalid-result and injected display-failure boundaries
are covered. No rendering framework, solver, schema or feature-history rewrite
is warranted by the measured evidence.

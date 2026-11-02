# Work Order 043 — multi-profile extrusion

## Architecture decision (before implementation)

Extend the existing ProfileView selection and region classifier. Selection belongs
to one sketch: ordinary click replaces, Shift toggles, and Shift on another sketch
keeps the current set with feedback. Existing Escape clears/cancels without edits.
The existing ordered feature engine owns one resulting connected solid per feature.
Multiple regions therefore support Cut and Join against one explicit target;
disconnected New Body and multi-profile Intersect are rejected explicitly.
No sketch/profile is consumed. Auto-hide remains visibility metadata.

Extend immutable extrusion parameters with exact additional region references
(outer, holes and line members). Canonical order uses outer UUIDs. Single-profile
records keep their previous representation; multi-profile records require v15.
Every region resolves through the existing classifier, without healing or fallback.
Region-scoped cap keys distinguish multiple prism caps in existing face ancestry;
legacy single-profile cap identities retain their original meaning.

Build each requested prism then use the existing validated multi-tool Boolean and
face-history path in one candidate evaluation. This reduces feature count, without
claiming a native Boolean speedup. A failed tool rejects the entire new feature.
Preview/Apply retain PR42's staging, display preflight and preview reuse. No second
feature engine, selection system, geometry cache or multi-solid body is introduced.


## Interaction and lifetime

Normal click replaces; Shift-click toggles; normal blank click clears. Shift on
blank/ambiguous geometry preserves the set; cross-sketch Shift preserves it with
feedback to click without Shift to switch. Coincident candidates remain refused.
Right-click on a selected region retains the batch; on a different valid region
it replaces the batch before opening the existing extrusion context menu.
All selected faces share the existing orange actor and foreground sketch pass.
Entering Extrude preserves the complete set. Existing Escape/Cancel exits the
operation/profile workflow and clears selection; it does not restore old highlights.
Successful Apply, source edits, history/document refresh, entering another sketch
and leaving the workflow clear references/highlights/cache through existing paths.

## Geometry, persistence and limits

Cut supports disconnected tool regions against one explicit current target, with
signed distance and Through All. Each tool must actually remove material; any
failed tool rejects the whole new operation. Invalid direct edits of a multi-profile
feature also preserve its last accepted result and history. Join uses the existing validated
multi-tool Fuse, including valid face contact and tools that bridge to the target.
All requested tools must yield one connected valid solid. New Body requires one
profile; multi-profile Intersect is refused rather than applying sequential Common
to disconnected tools. No body splitting or native multi-solid output is added.

All source entities remain in their sketch, whether selected, unused or previously
extruded. Auto-hide only changes sketch visibility in the same Undo transaction;
edit the sketch or use browser-scoped Select Profile to reuse hidden regions.
The existing 256-entity analysis limit, even/odd holes/islands, conservative overlap
rejection and line-gap recovery remain. Primitive topology changes reject atomically;
opened line loops become unresolved and suppress dependent output until repaired.

The first outer/hole/line reference retains the legacy fields. A v15
`additional_profiles` list stores remaining immutable records with explicit
`outer_id`, `hole_ids`, `line_ids`. All selected records sort by outer UUID;
holes/members are exact identities, never substituted by geometry or list order.
Empty/duplicate/malformed additional sets are rejected. V1–v14 readers remain
available and single-profile saves retain their former minimal version. Old app
versions cannot read v15 files. Sketch dependencies still name one source sketch
and one target. Region caps use `(start/end, outer UUID, None)` in existing ancestry;
legacy caps remain `(start/end, None, None)`. Existing planar-face attachment
resolution and Boolean history propagate these roots; no traversal indices persist.

## Measured six-pocket comparison

Command: `.venv/bin/python tools/benchmark_multi_profile_043.py --output docs/benchmarks/multi-profile-043.json`.
Five samples per scenario, CPython 3.12.14, OCP 7.9.3.1, VTK 9.6.2, Qt 6.8.3,
Linux x86-64. Six radius-2 circles cut 3 mm into a 40×30×20 mm base.
Medians in this hosted environment (no hardware timing assertions):

| Measurement | Six individual Cuts | One multi-profile Cut |
|---|---:|---:|
| Operation evaluation/history, ms | 480.50 | 120.77 |
| Full document regeneration, ms | 143.42 | 118.03 |
| Final display preparation, ms | 95.58 | 91.58 |
| Extrusion feature entries | 6 | 1 |
| Total feature entries (box/sketch included) | 8 | 3 |
| Kernel validity | Valid | Valid |
| Resulting volume, mm³ | 23773.80532894 | 23773.80532894 |

Operation measurement sums the six normal single-feature transactions versus one
multi-feature transaction, excluding sketch creation and interaction/render time.
Regeneration reconstructs the complete final document from definitions. Display
preparation measures the actual detached viewport surface, edge mesh, native face/
edge picking maps, normals and mappers for the final shape, once in each scenario;
it excludes installation/frame presentation and intermediate individual previews.
The harness invokes the existing preparation method with only its model-span
fallback, without creating a Qt window. The reduced evaluation cost mostly avoids
re-evaluating earlier cuts across six separate commits. Native sequential Boolean
work remains; no general geometry speedup is promised. Raw samples and harness
fingerprint are in [the report](benchmarks/multi-profile-043.json).

## Verification and follow-up

New regression tests cover click/Shift/toggle/clear/Escape, six orange framebuffer
regions before/after zoom, cross-sketch policy and coincident ambiguity; six cuts,
mixed circle/rectangle/slot and line regions, nested material/holes, signed bosses
and cap attachments, Through All, atomic invalid New Body/Join/Cut/Intersect,
source reorder/dimensions/deletion guards, unresolved line recovery, one-step
Undo/Redo, save/reopen, unused/previously used profile reuse, full preview,
cancellation, injected display failure and preview reuse without regeneration, and failed direct Properties distance edits.
The existing legacy fixture and single-profile suites run unchanged.

Possible follow-ups are an explicit union-of-tools Intersect design and a native
batched Boolean benchmark if larger real models show a need. Neither requires
expanding this PR's body architecture. Color, formatting, arcs and fillets remain
outside this work order. Real desktop GPU/high-DPI checks remain manual; automated
rendering here uses Xvfb and software OpenGL.

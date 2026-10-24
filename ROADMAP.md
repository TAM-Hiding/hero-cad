# Roadmap

## M0 — v0.0.1 foundation

Small Python package; Ubuntu installation; Qt shell; viewport navigation; model browser; millimetre properties; one regenerating OCCT box; kernel and GUI checks; dependency/license decision. Validation status is tracked in VALIDATION.md.

## M1 — useful local document

First slice (v0.0.2): versioned save/load of parameters with validation and atomic replacement, unsaved-change handling, and undo/redo for parameter edits.

Remaining M1: STEP export with round-trip checks and additional simple primitives. Establish feature identities only as required by multiple features.

## v0.0.3 — viewport refinement and transient selection

Address the first physical-laptop report: independent CAD boundary lines, bounded zoom, face/edge picking with highlighting, and compact standard-view presets. Retain the existing lighting, colors and thin default edges. Document Ubuntu 22.04/Python 3.12 and XCB prerequisites. No sketch tools or persistent topology references in this slice.

## v0.0.4 — sketch foundation

Ordered feature IDs/references and transactional regeneration; XY/XZ/YZ sketch planes; contextual Line and Rectangle tools (diagonal drag and latched Shift edge-first); numeric entity editing; mixed transient solid selection; adjustable screen-space picking; v2 persistence with legacy migration; undo/redo. Preserve thin edges and the established orange. Tighten maximum zoom-in by 20%.

Physical acceptance gate: test each sketch plane, live previews, both rectangle gestures, numeric edits, reentry, Save/Open, Undo/Redo, multi-selection and navigation on the laptop. **Do not start extrusion until this milestone is physically tested and accepted.**

## v0.0.5 — light sketch additions

Circle and latched Shift-slot construction using the existing tool controller; editable curve parameters and analytic kernel geometry. Add a visual adaptive sketch-grid toggle and red X/yellow Y/blue Z world-origin-axis toggle. V3 files retain loading of v1/v2. No snapping, solver, extrusion or other modeling expansion.

## v0.0.6 — visibility, grid snapping and precision UX

Fix confirmed near-plane clipping after restoring the camera for a larger sketch. Add exact major/minor grid subdivisions, independent grid/origin snapping, screen-space tolerance, snap markers/readout, and automatic/manual session grid spacing. Preserve real solid occlusion, thin lines, gestures and numeric edits. No extrusion.

## v0.0.7 — adaptive curves and center snapping

Screen-space curve display targeting 0.25-pixel deviation, cached by zoom quality bands; exact center snapping for circles and both slot ends before ordinary grid targets. Independent Center Snap toggle and distinct feedback. Test 0.02 mm circles, zoom/resize, mesh reuse on pan/orbit and all sketch planes. No stored geometry/history/extrusion changes.

## v0.0.8 — contextual face-normal camera views

Shift-right-double-click aligns to the exact plane of the face under the cursor, independent of selection filter, using deterministic up and approximate zoom preservation. Keep Shift-right-drag pan and transient selections. Add one-level Previous View restore and brief nonplanar/miss feedback. Compound-angle fixtures verify the camera without introducing new modeling operations.

## v0.0.9 — sketch editing and dimensions

Atomic multi-entity/sketch deletion with dependency rejection and Undo/Redo; browser/viewport context actions; live cursor dimensions with exact typing for line length, rectangle width/depth, circle radius and slot radius/center distance. Keep camera gestures, snapping and v3 documents. No extrusion.

### Deferred: independently sized slot ends

This needs a deliberate schema migration (independent End A/End B fields with legacy equal-radius loading), analytic external tangent points and non-semicircular cap sweeps, matching adaptive display paths and picking, plus center snaps and preview/property updates. Require `abs(radius_a - radius_b) < center_distance`, valid closed wires and area/bounds checks across arbitrary angles and all sketch planes. Keep center distance independent of the radii and test equal-radius compatibility, undo and persistence. This cross-cutting geometry/format change is deferred from the usability PR; current slots retain one shared radius.

## PR #13 — v0.0.10 parametric profile extrusion

Select material by clicking inside an analytic region; extrude isolated rectangles/circles/slots or outer regions with holes as separate signed-depth bodies. Preserve source UUIDs and exact hole sets through dimensional regeneration, files and history. Reject touching/overlapping regions and defer line-chain construction. Source topology changes require explicit reselection rather than guessing. New Body only; no booleans or sketch-on-face.

Stop after this PR. **Do not start PR #14 automatically.** Its scope requires a separate user instruction.

## M2 — small mechanical workflow

Face selection and stable reference strategy, booleans, basic sketch entities and dimensions, then a deliberately limited constraint solver and extrude workflow. Each operation needs geometric correctness and failure recovery tests.

## Later

History presentation/reordering, bold/construction line styles, fillets/chamfers, assemblies only if needed, packaging and STR-GZR OS integration. Evaluate performance with real mechanical parts.

AI-assisted modeling eventually proposes explicit, reviewable feature/parameter edits through the same document operations as the UI. It must not bypass validation or become a prerequisite. No AI implementation in M0.

## v0.0.11 / PR #15 — planar face sketches

Named box faces, extrusion caps and reliably identified Rectangle/Slot planar sides support attached sketches, regeneration, v5 files and unresolved-reference recovery. Circle walls/slot arcs and unknown face ownership are rejected. Reassign-plane and general topological naming remain deferred. No cuts/booleans or new sketch primitives. Do not begin PR #16 automatically.

## v0.0.12 / PR #17 — parametric material operations

Join/Cut/Intersect feature history, explicit body consumption, New Body/material-operation extrusion, directional Through All, modeless candidate previews and explicit display modes. Boolean-result face attachments and general topology naming remain deferred. Stop after PR #17; do not begin PR #18 automatically.

## PR #18 — HERO-CAD rebrand and migration preparation

Rename the application/distribution/CLI/package, preserve all .starcad contracts, prepare hero-cad repository metadata and local installation/owner migration instructions. No layout or modeling changes; no placeholder logo. Repository rename is an owner action after merge. Stop after PR #18.


## PR #19 — sketch visibility and face reliability

All sketch planes retain translucent current-body context. Multiple sketches can share a face. Eligible planar Boolean output faces use unique source ancestry + CAD adjacency fingerprints, scoped to the selected evaluated feature. Ambiguous/missing identities remain an explicit limitation; general topological naming and plane reassignment remain deferred. No new sketch/modeling tools are added. Stop after opening PR #19; do not merge automatically or begin subsequent feature work.


## PR #20 — closed profiles and viewport refinement

Simple closed Line loops (including concave/dovetail profiles) use the existing selectable material-region/extrusion/Boolean pipeline. Independent loops and mixed primitive holes work; endpoint graphs use 1e-7 mm tolerance and stable member UUIDs. Crossing/branch/overlap trimming and mixed line/arc chains remain deferred. Off/Celadon/Orange session X-Ray and conservative solid mesh/analytic-normal refinement are included. No fillets, chamfers, new tools, construction planes, rotary sketch, surface warp or document-extension migration. Stop after opening PR #20; do not merge automatically.


## PR #21 — floating tool island and shared commands

Movable viewport overlay with Compact/Medium/Expanded presets, responsive command columns, collapse and View-menu visibility. QSettings preserves layout across launches outside documents. Existing QAction objects supply shared command behavior/state across island, toolbar, menus and shortcuts. Slot explicitly enters the existing CircleTool slot stages. Dynamic plugins, scripting, new modeling tools and major layout changes remain out of scope. Stop after opening PR #21; do not merge automatically or begin further feature work.

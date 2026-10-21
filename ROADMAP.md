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

## M2 — small mechanical workflow

Face selection and stable reference strategy, booleans, basic sketch entities and dimensions, then a deliberately limited constraint solver and extrude workflow. Each operation needs geometric correctness and failure recovery tests.

## Later

History presentation/reordering, bold/construction line styles, fillets/chamfers, assemblies only if needed, packaging and STR-GZR OS integration. Evaluate performance with real mechanical parts.

AI-assisted modeling eventually proposes explicit, reviewable feature/parameter edits through the same document operations as the UI. It must not bypass validation or become a prerequisite. No AI implementation in M0.

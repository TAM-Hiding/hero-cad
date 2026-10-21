# Roadmap

## M0 — v0.0.1 foundation

Small Python package; Ubuntu installation; Qt shell; viewport navigation; model browser; millimetre properties; one regenerating OCCT box; kernel and GUI checks; dependency/license decision. Validation status is tracked in VALIDATION.md.

## M1 — useful local document

First slice (v0.0.2): versioned save/load of parameters with validation and atomic replacement, unsaved-change handling, and undo/redo for parameter edits.

Remaining M1: STEP export with round-trip checks and additional simple primitives. Establish feature identities only as required by multiple features.

## M2 — small mechanical workflow

Face selection and stable reference strategy, booleans, basic sketch entities and dimensions, then a deliberately limited constraint solver and extrude workflow. Each operation needs geometric correctness and failure recovery tests.

## Later

Ordered feature history, fillets/chamfers, assemblies only if needed, packaging and STR-GZR OS integration. Evaluate performance with real mechanical parts.

AI-assisted modeling eventually proposes explicit, reviewable feature/parameter edits through the same document operations as the UI. It must not bypass validation or become a prerequisite. No AI implementation in M0.

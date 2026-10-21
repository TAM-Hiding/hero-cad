# Roadmap

## M0 — v0.0.1 foundation

Small Python package; Ubuntu installation; Qt shell; viewport navigation; model browser; millimetre properties; one regenerating OCCT box; kernel and GUI checks; dependency/license decision. Validation status is tracked in VALIDATION.md.

## M1 — useful local document

Versioned save/load of parameters with validation and atomic writes, unsaved-change handling, undo/redo for parameter edits, STEP export with round-trip checks, additional simple primitives. Establish feature identities only as required by multiple features.

## M2 — small mechanical workflow

Face selection and stable reference strategy, booleans, basic sketch entities and dimensions, then a deliberately limited constraint solver and extrude workflow. Each operation needs geometric correctness and failure recovery tests.

## Later

Ordered feature history, fillets/chamfers, assemblies only if needed, packaging and STR-GZR OS integration. Evaluate performance with real mechanical parts.

AI-assisted modeling eventually proposes explicit, reviewable feature/parameter edits through the same document operations as the UI. It must not bypass validation or become a prerequisite. No AI implementation in M0.

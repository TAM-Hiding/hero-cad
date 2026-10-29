# Read-only feature history inspector

Select a feature in the model browser, then open **Properties → History**.
The **Edit** tab retains the existing parameter and operation controls. The
History tab stays selected as you browse other features; **Edit Parameters**
explicitly returns to the Edit tab and focuses its field; its text can be selected
and copied but not edited. Long summaries wrap and scroll inside the panel.

The inspector reports:

- Derived feature label/type, one-based position in the complete ordered history,
  and the persistent feature UUID in a secondary Technical identifiers section. Labels such as “Sketch 2” are generated from
  the current order, not stored user-defined names.
- Direct parents and direct dependents, labeled by type and history position.
  Roles distinguish supporting faces, source profile sketches, Boolean target bodies
  and Boolean tool bodies. The same roles appear beside dependents, describing how
  they use the selected feature. Canonical origin planes are named explicitly. These are direct relationships,
  not a transitive dependency tree.
- Current regeneration status and the full existing error message. **Valid**,
  **Unresolved**, and **Blocked by unresolved dependencies** are derived from the
  current feature and its direct parents' statuses.
- A separate geometry role: **Current resulting body**, **Historical geometry**
  consumed by a later operation, or **No evaluated output** for an invalid feature.
  Hiding a sketch is display metadata and does not suppress feature evaluation.
- Box dimensions; sketch frame, attachment strategy and entity counts; extrusion
  source, operation, extent, signed distance/direction, target and profile IDs;
  Combine operation, target and tools. Through All's stored distance is explicitly
  distinguished from its evaluated depth. Values use up to 17 significant digits.

Selecting a sketch entity shows its owning sketch's history. Its individual
dimensions remain in **Edit**, so large sketches do not dump thousands of entity
parameters into the feature summary. Selecting an origin plane or a grouping
entry clears the feature summary and shows the selection prompt.

The summary follows normal creation, accepted parameter changes, deletion,
Undo/Redo, New/Open and visibility changes. It describes the accepted document;
unapplied editor values and errors from rejected proposals are not stored feature
parameters/statuses. Existing selection behavior is preserved: changing browser
selection may apply valid pending edits or refuse invalid ones, just as before.
Switching to History does not apply edits or regenerate the model.

Changing an extrusion from **New Body** to **Join** may invalidate downstream
face references. The inspector continues to show the original supporting face
and target-body relationships, together with available unresolved/blocked
diagnostics. It neither substitutes references nor changes regeneration.

## Implementation and limits

`history_inspection.feature_history_text` reads `Document.features`, each feature's
references and parameters, `Document.statuses` and `active_body_ids`. Relationships
are derived on demand in history/reference order, with no second graph or stored
history. It does not invoke regeneration, profile analysis or the geometry kernel.
The existing browser/property refresh path updates the selected summary; the
visibility-only fast path updates it without rebuilding geometry. Identical text
is not replaced, preserving scroll/selection during redundant refreshes.

This is an inspector, not a timeline editor. It adds no reordering, rollback,
suppression, reference repair, naming fields, dependency navigation links or
geometry operations. Regeneration diagnostics remain the existing text, which
can include UUIDs. Source/snapshot attachment strategy is identified, but full
ancestry metadata is not expanded into a graphical face-history view. No
document schema, runtime dependencies or viewport behavior changed.

Tests cover order, direct references, all supported feature types, error/status
distinctions, 1000-feature history formatting, stored precision, actual browser
selection, existing editors, visibility, Undo/Redo and save/reopen. Inspection
tests forbid regeneration and assert document/cache/history state is unchanged.
See [VALIDATION.md](../VALIDATION.md) for results and environment limits.


## Regeneration indicators and first-failure navigation

The model browser retains operation-color stripes and adds a warning symbol and
UNRESOLVED label for direct failures, or a muted blocked symbol and BLOCKED label
for a failed required dependency. The earliest direct failure is bold. Tooltips
include the evaluator diagnostic and, for blocked output, the dependency's history
position, type and UUID. Icons and text distinguish states without relying on color.
Row height, selection, visibility and context actions are retained; rebuilding
also preserves existing expansion/collapse state.

`FeatureStatus.blocked_by` is transient evaluation metadata, set only at the
existing dependency-block branch in ordered regeneration. It is neither serialized
nor a second status graph. Independent branches continue evaluating and can have
their own direct failures. History uses this same authoritative status and adds a
human-readable failed-parent link. Existing parameters, UUIDs and dependency
roles remain available in the read-only inspector.

**View → Go to First Unresolved Feature** selects and scrolls to the earliest
direct evaluation failure in ordered history, reveals Properties → History and
focuses its diagnostic text. If only blocked/unclassified failures are available,
it chooses the earliest unresolved feature. The action is disabled for valid
history and respects the existing pending-edit selection guard. Browser and
History update through ordinary regeneration, file opening and Undo/Redo.

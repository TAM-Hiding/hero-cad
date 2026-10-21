# Architecture

## Responsibilities

- `features.py`: immutable feature definitions, box parameters, stable UUIDs and regeneration status/errors.
- `sketch.py`: immutable line/rectangle/circle/slot/sketch parameters and canonical local-to-world plane frames.
- `document.py`: ordered regeneration, transactional edits, saved state and undo/redo snapshots.
- `persistence.py`: strict versioned JSON serialization and legacy migration.
- `geometry.py`: OCCT solids and analytic sketch lines, circular edges, rectangle wires and tangent slot wires; kernel validity checks.
- `tools.py`: UI-independent construction state machines, latched Shift mode, preview/completion/cancellation.
- `ui/main_window.py`: browser, contextual actions, numeric properties and file lifecycle.
- `ui/viewport.py`: camera/navigation routing, transient mixed solid selection and display orchestration.
- `ui/sketch_view.py`: plane camera, ray/plane mouse conversion, sketch actors and tool adapter.
- `ui/display_geometry.py`: disposable double-precision VTK meshes with OCCT face/edge mappings.
- `ui/picking.py`: screen-space distance to projected segments, independent of display width.
- `ui/snapping.py`: local origin/grid target selection using projected screen distance.
- `ui/guides.py`: session grid preferences and disposable major/minor/axis meshes.
- `app.py`: QApplication lifecycle.

## Feature history and regeneration

A document stores an ordered tuple of immutable `Feature` values. Each has a UUID, type, typed parameters and optional references. Canonical `plane:XY`, `plane:XZ`, `plane:YZ` references are immutable origin nodes. References must resolve to origin nodes or earlier features: missing, self, cyclic and forward references are rejected. This is ordered history validation, not a general graph scheduler. Exactly one box and zero or more sketches are supported. Box dimensions retain the existing API.

All candidate features regenerate in sequence before the document changes. Box generation produces a valid OCCT solid; sketches produce compounds of analytic straight edges and closed rectangle wires transformed into their plane. A successful candidate replaces shapes, feature definitions and per-feature valid statuses together and appends one undo snapshot. Failure leaves the previous features, shapes and undo stacks intact, and exposes `last_failure` with the failing feature ID and invalid/error status. UI displays the error; invalid candidate features are not silently persisted or inserted into history. No downstream geometry operation consumes references yet.

No-op edits add no history. Undo/Redo rebuilds and validates before moving the snapshot between stacks. Dirty state compares the current immutable features with the saved snapshot. Stable feature/entity IDs survive edits, undo and persistence; they are not OCCT subshape identities. Persistent topological naming is out of scope.

## Sketch geometry and input

Local XY coordinates map through an explicit orthonormal plane frame. XY uses +X/+Y, XZ +X/+Z, YZ +Y/+Z. Rectangle parameters are one position, positive width/height and angle; both construction paths use this single representation. Edge-first depth is the signed perpendicular projection of the third point. For negative depth the corner shifts, preserving positive dimensions and the requested footprint. JSON preserves Python double values; no decimal rounding is applied during serialization. OCCT tolerances still apply.

The viewport distinguishes button presses, moves/drags, releases and modifiers. It routes navigation separately from construction; Shift-right is latched and translated to a middle-button pan. Shift-left selection never becomes VTK's Shift-left pan. `ToolController` forwards construction events to one state machine; the viewport does not contain per-tool stages. Rectangle stages are start, diagonal drag, first edge, depth. Shift is sampled at initiation only. Line uses start/end clicks. Invalid zero-length geometry remains uncommitted with inline feedback. Escape drops the preview and returns to selection; completing a valid entity starts the next placement with the same tool. Browser changes, Undo/Redo and regeneration clear unfinished previews.

The Circle tool uses the same handle/hint/preview interface: normal press/drag/release commits a circle; Shift at initiation latches slot mode, release locks radius, and a second-center click commits the slot. Slot parameters are first center, radius, center-to-center distance and angle. The kernel wire consists of two tangent straight edges and two exact semicircular arcs. Circles use an exact gp_Circ edge. Viewport curve sampling uses the screen-error policy described below; the legacy `entity.points` fallback remains available to non-viewport callers. Neither path is used for analytic curved kernel geometry. No constraint solver or speculative plugin registry is introduced.

Sketch mode hides the solid and other sketches, saves the model camera, and shows the active sketch axes/origin. Finish restores the camera and all completed geometry. Select allows orbit; mouse coordinates always intersect the actual plane rather than assuming screen coordinates equal model coordinates. Reentering restores a perpendicular view. Numeric changes use the document transaction path and preserve unchanged values beyond displayed precision.

## Rendering and selection

OCCT B-rep is authoritative; VTK display data is disposable. Faces tessellate at 0.1 mm linear/0.2 rad angular tolerance, respecting placements and winding. Unique B-rep edges are sampled separately and drawn one pixel wide; triangle edges are disabled. The existing surface colors, background and lighting remain.

Face picking maps VTK cells to whole OCCT faces. Edge picking measures projected segment distance using a 2–10 logical-pixel radius (default 6), converts for device pixels, and rejects candidates behind the front surface. Shift toggles `(kind, index)` members, permitting mixed face/edge selections; switching the filter retains the set. Highlights are combined display meshes, excluded from picking and camera-fit bounds. Geometry regeneration clears the transient set. Sketch picking maps a displayed polyline to its persistent entity UUID, with single-entity editing in this milestone.

Camera parallel scale is clamped relative to the bounding diagonal; increasing its lower bound by 1.25 reduces maximum magnification to 80% of the previous limit. All wheel/dolly interactions reset clipping. Display/pick tolerances do not constrain stored model dimensions.

## Persistence

V3 stores format, version, units, ordered features with IDs/types/references, and parameters. Sketch parameters include canonical plane ID, origin/U/V frame and typed entities with UUIDs. Explicit stored frames must match the canonical origin plane; arbitrary frames are not supported. V1 box files migrate to one box feature with a new UUID, retained on the next save. Files store no B-reps, meshes, selections, camera, tool previews or undo stacks.

Schema validation rejects unknown fields and versions, duplicate keys, invalid dimensions/IDs/frames and dependency errors. The loader builds a replacement document before swapping it into the window. After an unsaved-change Save prompt it rereads the selected file, since Save may have updated it. V2/v3 are limited to 4 MiB; save enforces the same limit before touching a destination. Legacy v1 retains 64 KiB. Feature/entity count limits bound synchronous work but are not performance guarantees.

Saving uses a same-directory temporary file, flush/fsync and os.replace; cleanup occurs on failure, and the path/savepoint update only after replacement. This prevents partial target files, not all power-loss scenarios or concurrent writes. Pending numeric property edits participate in Save/Discard/Cancel. Browser selection changes commit valid pending edits; invalid edits retain the previous selection. Untouched displayed decimals preserve the stored value.

## Scope and future work

One box, origin-plane sketches and synchronous full regeneration keep this foundation small. Feature deletion/reordering, constraints, dependent solids and persistent topology references require their own designs/tests. No extrusion before physical acceptance of v0.0.4. No network, AI, accounts, telemetry, database, background workers or new dependencies.

## View guides

`ui/guides.py` owns session-only grid/axis visibility. Grid lines lie in the active sketch frame and follow the camera focal point; automatic major spacing uses 1/2/5 steps targeting about 100 logical pixels, with ten minor intervals per major and bounded display line counts. Camera modifications update the disposable guide meshes. Origin axes pass through world zero in red X/yellow Y/blue Z. All guides are unlit, unpickable and excluded from camera-fit bounds. Grid lines receive a depth offset behind sketch entities. Guides never enter document history or persistence. Axes remain available outside sketch mode; grid visibility is restricted to an active sketch.

The loader accepts v1/v2 files; v2 permits only its original line and rectangle types. V3 extends the entity set with circles and slots and retains all prior validation and atomic saving.

## v0.0.6 — visibility and precision input

Confirmed failure mechanism: finishing a large sketch restored the pre-sketch orthographic eye position, which could be inside the enlarged scene. Parallel zoom changes scale without moving that eye. `ResetCameraClippingRange` alone retains a positive near plane and cannot include geometry behind the camera. A reproduced radius-150 circle plus slot, with solid and axes hidden, had 25/247 sampled curve points clipped after Finish at the restored 104.033 mm camera distance; their normalized depths reached −0.020457. The same camera clipping state changed with orbit angle. Fit recovered the geometry by moving the eye back. This establishes a clipping defect independently of solid occlusion, grid/axis depth, and curve sampling.

`Viewport.update_clipping` computes bounds of visible model geometry (and any live preview), finds the nearest bound-corner depth, and backs the orthographic eye along its viewing direction only when needed to leave a small positive margin. Focal point, orientation and parallel scale do not change; projected XY positions are invariant. It then resets near/far to those bounds. Regeneration, sketch transitions, camera interaction, wheel and Fit refresh clipping. Guides/highlights/snap markers remain excluded from model bounds. Depth testing, solid visibility/depth writes and ordinary sketch line offsets are unchanged. Grid lines retain their existing modest guide-only offset.

`ui/guides.py` now uses major/minor meshes with a 10:1 interval ratio. Automatic major spacing targets roughly 100 logical pixels using 1/2/5 model-space steps; manual spacing defines the minor interval. Spacing is computed even while grid lines are hidden. Dense manual grids cap display line counts using integer interval strides; snap spacing is not changed.

`ui/snapping.py` accepts local UV, cursor XY and a local-to-screen projection callback. It first considers local (0,0), independently of grid snapping, then nearby lattice intersections and accepts a target only within eight logical pixels (converted once to device pixels by the Qt adapter). Clipped projection targets are rejected. Origin priority and local-frame semantics allow future attached/offset origins without world-zero special cases. Every construction phase uses this one input path before the existing tool state machine. It never creates constraints or modifies existing entities. Circle/slot radius comes from two snapped points; rectangle depth remains perpendicular to its first edge.

Gold/magenta unpickable point actors and status text report snap state; cancellation, regeneration, tool/settings changes and leaving the viewport clear transient feedback. All grid/snap controls are session preferences; v3 persistence is unchanged. No new dependencies or modeling operations.

## v0.0.7 — adaptive curve display and center targets

`ui/curve_display.py` chooses curve segment counts from analytic radius and orthographic physical pixels/mm (`render_height / (2 * parallel_scale)`). It uses the stable sagitta relation `step = 4 asin(sqrt(error / (2 radius_pixels)))` with a 0.25-pixel target. Counts round upward into power-of-two bands (minimum 32/full circle, maximum 32768). Each slot semicircle uses half the full-circle count. The cap bounds work for extremely large mostly-offscreen curves and can exceed the pixel target at that limit. Projection of an orthonormal plane cannot stretch beyond this bound, so orbit does not require finer samples.

`SketchView.prepare_display` runs before rendering, catching wheel/direct camera scale changes, resize and HiDPI render-size changes. It compares immutable visible feature definitions and quality-band counts before replacing the base mesh. Per-entity paths are cached for their current parameter/frame/count combination, and removed IDs are pruned. Pan/orbit and zoom changes within a band leave the base mesh unchanged. Highlights and picking use the same sampled paths. Circle/slot tools also expose their analytic preview entity so radius/slot previews can resample on zoom without changing the tool stage. No recursive renders occur in the render-start callback.

`center_targets` reads circle X/Y and slot first/second center directly from current parameters in the active sketch. Snapping preserves origin priority, then picks the nearest eligible entity center before considering the grid, within the existing 8-logical-pixel screen tolerance. Center Snap is independently toggleable, session-only and defaults on. Blue feedback and `SNAP: CENTER` distinguish it from grid/origin. Numeric edits and Undo are reflected on the next pointer event without retaining mesh-derived center references. No constraints or persistent feature references are created by snapping.

No kernel, schema, feature-history or extrusion changes.

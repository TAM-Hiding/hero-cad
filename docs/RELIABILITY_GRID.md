# PR #22 — Join, interaction recovery and grid appearance

## Confirmed causes and changes

**Join:** `combine` required positive Common volume for all operations before
running Fuse. A face-to-face protrusion has zero common volume, even when OCCT
can fuse it into one manifold solid. Join now tries the actual non-destructive
Fuse and accepts only exactly one BRepCheck-valid, positive-volume solid.
Disconnected, point-contact and edge-contact results still fail. Pending tools
are tried in turn so a connected chain can be joined in any tool order. Cut and
Intersect retain their positive-overlap precheck. The accepted builder continues
feeding the existing transient face-reference propagation; no new naming system
or persisted ancestry is introduced. Current evaluated-body validation remains
in the document layer.

**Interaction recovery:** `ProfileView.clear()` removed the region selection and
highlight but retained `active`. Refresh/Undo and viewport Escape called this
without ending profile routing. Subsequent clicks could still go to profile
picking instead of normal face/edge picking, despite there being no highlighted
profile. Operation Cancel also restored display without ending this routing.
History transitions and cancellation now synchronize the checkable shared action
and profile router, clear temporary selections/preview state, and refresh command
availability. Apply and Cancel discard the preview candidate and disable its
Apply button. Existing shape refresh rebuilds OCCT-to-mesh selection mappings.
Escape cancels unfinished construction and returns to Select. Undo/Redo cancel
unfinished geometry but preserve the chosen construction tool when its active
sketch remains valid. Camera, X-Ray, visibility and saved layout are preserved.

Reproduction precision: the retained routing is reproducible with Select Profile
active across Undo and with Escape after profile selection. A clean ordinary
New Body commit already switches off Select Profile; that exact sequence alone
did not reproduce every reported lock-up. Regression coverage includes the
reported New Body → Undo → face pick → Cut sequence and repeated history steps,
as well as the confirmed stale-mode conditions. No claim is made that this
diagnoses every possible desktop input failure.

## Grid controls

In sketch mode, open **Grid appearance** beside Grid in the existing toolbar:

- Color: Light Grey (default), White, muted Orange, Purple or Celadon.
- Grid Scale: off by default; shows local U/V coordinate labels in millimetres.
- Fade Grid in X-Ray: off by default; reduces grid/label opacity in both Celadon
  and Orange X-Ray, and immediately restores normal opacity with X-Ray Off.

The three appearance preferences persist between launches in application
QSettings under `grid/v1`, outside documents and Undo. Grid visibility, automatic
spacing and all snap toggles retain their existing behavior.

Major lines use every tenth existing minor-grid interval and are brighter than
minor lines. Dense minor lines fade gradually; the original bounded-line display
and adaptive 1/2/5 spacing remain. Snapping uses the original exact interval even
when grid lines or labels are hidden. Axis colors, thin sketch curves, model
precision, `.starcad` schema and extension are unchanged.

Labels use a 13-pixel font (approximately 10 pt at 96 DPI). They anchor to exact
local major coordinates on origin and attached planes. If an axis is offscreen,
the nearest major line is used. Projection/clipping and conservative text boxes
skip offscreen/overlapping labels; at most 32 reusable unpickable labels exist.
Extreme oblique views may show few or no labels. Labels are a view overlay and
can be switched off to avoid covering geometry; they do not attempt to solve
layout around every sketch entity. The old conservative evaluated-face identity
limitations remain: substantial topology changes may unresolve attachments
rather than redirect them. For example, changing a through-hole into a blind hole
can change the face signature. No face-reference rewrite is included.

## Desktop test checklist (Ubuntu 22.04 / 24.04)

1. Extrude a rectangle as New Body. On its end face, sketch a smaller rectangle,
   then Join outward 10 mm. Preview/Apply must give one connected body. Save,
   reopen and change the first extrusion distance; the protrusion must follow.
2. Cut two holes in a block, sketch a protrusion on the remaining top face and
   Join outward. Change an earlier dimension while retaining the same topology.
   Confirm regeneration and save/reopen. Test disjoint, edge-only and point-only
   Combine Join inputs; they must be rejected without changing the document.
3. On a solid face, create a circle; accidentally extrude inward as New Body.
   Undo, select the original face, then use the original profile for Cut. Repeat
   Undo/Redo/Undo, face selection, New Sketch, Line, Escape. No restart needed.
4. Activate Select Profile, select a region, then Escape. Face/edge selection
   must work again. Repeat with Cancel in an extrusion preview and a multi-body
   Combine preview. No stale preview, profile highlight or enabled Apply remains.
5. Confirm toolbar, island and menu checks agree; camera, layout, X-Ray and body
   visibility should survive Undo/Redo and cancellation. Mouse orbit/pan, Shift
   construction and Shift-right-double-click alignment must still work.
6. On XY, XZ, YZ and a face sketch, inspect all five colors and scale labels.
   Pan, zoom and resize: labels show actual local mm coordinates without overlaps.
   Major lines are every ten minor intervals. Snap with labels/grid hidden and
   shown; the same construction points must result.
7. Enable X-Ray fading, switch Celadon/Orange/Off and confirm immediate restoration.
   Disable fading and verify X-Ray no longer changes grid appearance. Restart:
   color, scale and fade preferences must remain; reopen an existing `.starcad`.

Physical laptop checks remain for the reviewer; automated results and exact
local environment are recorded in VALIDATION.md.

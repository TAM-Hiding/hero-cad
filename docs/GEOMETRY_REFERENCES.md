# Existing geometry references while sketching

Enter a sketch attached directly to a planar solid face, then choose Line,
Rectangle, Circle, or Slot. Move near an edge of a displayed solid lying on
the active plane. A temporary geometric symbol shows the exact placement
point and an optional edge highlight identifies the contributing model boundary.
The status bar reports MODEL ENDPOINT, MODEL CENTER, MODEL MIDPOINT, MODEL EDGE, or MODEL CURVE.
The same acquisition works when drawing construction lines and circles.

## Snap appearance

Open **Settings → Preferences → Appearance** for midpoint shape, color, size,
line weight, reference highlighting and optional centerline guides. Defaults are
14 logical pixels, 1.5-pixel strokes, palette colors and reference highlighting.
Guide display defaults off. Red, Green and Blue are available directly, and
Palette uses the existing experimental palette's RGB controls.

| Acquired reference | Default symbol |
| --- | --- |
| Supported endpoint or vertex | Hollow square |
| Straight-edge midpoint | Hollow triangle |
| Circular or slot center | Circled crosshair |
| Arbitrary analytic boundary location | Hollow diamond |
| Grid or sketch origin | Crosshair |

The midpoint can instead use the traditional overlapping C/L centerline mark
(℄), drawn with vector strokes. These are fixed-size display symbols and retain
their apparent size across model zoom. Hardware rasterization can limit very
thin strokes. There is no new intersection snapping or persistent centerline
constraint.

**Show temporary centerline guides** draws a dashed, dash-dot or dotted guide
perpendicular to an acquired straight edge at its midpoint. At a supported
circle/slot center, it draws the sketch's local U/V directions. The display
length follows indicator size. Guide color is independent of indicator color.
Guides clear on reference release, numeric input, tool changes and sketch exit.
They are visual references and do not provide additional snap targets.

In **Settings → Experimental → UI Palette → Sketch**, endpoint, midpoint,
edge-location and centerline colors inherit Center snap marker unless explicitly
overridden. Palette export/import includes optional snap appearance settings.
Existing v1 palettes and application preferences load normally. Importing an
older palette keeps the current shape, size and guide settings. Invalid options
are rejected before any preferences change. Appearance settings are stored with
application preferences and never in native model documents.

Supported references include straight-edge endpoints, circular-arc endpoints,
straight-edge midpoints, arbitrary positions along straight segments and analytic
circular arcs, and centers of analytic circular edges or arcs. Inner hole boundaries are eligible. A full
circle's artificial seam vertex is excluded. Geometry is read from current OCCT
edges, independent of the viewport's tessellation and edge thickness.

Acquisition uses an eight-logical-pixel radius at any zoom and accounts for the
viewport's physical pixel scale. On a face sketch, the priority is

1. Precise points: enabled origin, enabled completed-sketch centers, endpoints,
   and supported model endpoints/centers.
2. Straight-edge midpoints from either source.
3. Nearest analytic straight or circular boundary location from either source.
4. Enabled grid intersections.
5. Free cursor placement.

Within a priority group, the previously acquired point has a two-logical-pixel
retention preference. Origin and centers also have a two-pixel preference to keep
small circles/slots usable beside nearby endpoints. Candidates must still lie
within the original eight-pixel radius. Stable source order breaks ties, with the
origin first. Model references are independent of grid and Center Snap toggles.
Center Snap controls active-sketch centers; endpoints, midpoints and boundaries
remain available independently.

Completed entities in the active sketch supply these references on any supported
sketch plane, including construction geometry:

| Entity | References |
| --- | --- |
| Line | Endpoints, midpoint, straight boundary |
| Rectangle | Corners, four edge midpoints, boundaries, geometric center |
| Circle | Center, analytic circumference |
| Slot | Both arc centers, straight-edge midpoints, tangent endpoints, trimmed boundaries |

The same vector symbols, colors, source-highlight toggle and optional guides apply
to sketch and model targets. A sketch highlight outlines its source entity; a
solid highlight outlines the contributing edge. Temporary preview entities never
supply targets. Shared endpoints are supported; the existing region arrangement
does not expose arbitrary intersection-point snaps, and none are added here.

A slot's first center has no special snap class. If it coincides with the origin,
Origin Snap explains the different crosshair. Tests cover solid and sketch slots
at/away from the origin with Origin Snap on/off. Defining-point differentiation
is a possible future entity-editing feature, not current snapping semantics.

Snapping feeds all construction stages through the existing tool controller.
For an edge-first rectangle, the depth point still controls perpendicular depth.
Numeric dimensions retain their existing behavior and can override the cursor
dimension. A snap marker describes the acquired input point, while the shape's
existing dimensional rules determine its final parameters.

Eligible geometry must lie on the sketch plane within 0.0000001 mm. Both line
endpoints must lie on it. Circles must have a coplanar center and parallel normal,
including trimmed arcs. Parallel edges on other planes and edges crossing the
plane are excluded. Direct solid-face sketches acquire edges of the currently
displayed bodies. Hidden/historical bodies, origin-plane sketches and
construction-plane sketches do not supply model acquisition in this release.
Noncircular curved-edge locations, ellipse centers, and off-plane projection
remain outside the supported target set. Orthographic projection, including
oblique camera views, is supported; edge-on/nonunique curve acquisition is rejected.

## Persistence and future constraints

An acquired point becomes an ordinary double-precision coordinate in the sketch's
local frame. It survives native save/reopen, Undo/Redo, and downstream modeling
through those existing parameter paths. The sketch retains its existing plane
attachment, including that attachment's regeneration behavior. Changing an edge
length does not automatically constrain an acquired endpoint to the changed edge.

Snap results, display edge indices, and acquisition caches are transient. Future
associative constraints should resolve a reliable source reference through the
existing attachment/history system and store it as an explicit constraint with
its own unresolved behavior. A viewport edge index has no persistent identity.
The native format and schema are unchanged by this work.

## Adaptive numeric popup

During mouse drawing, the popup keeps one stable footprint per tool stage and
relocates only when the pointer enters a 14-pixel guard around it. Movement picks
an available nearby corner away from the pointer. Mouse moves that land directly
on a popup child are forwarded to the existing drawing handler after relocation.
Tiny viewports may lack enough room to avoid every point.

Press **Tab** or type to enter stationary numeric mode. For mouse entry, **hold
Ctrl before moving toward the field**, then click it. Tab switches fields, Enter
confirms the stage, and Escape cancels. Resizing keeps the field accessible.
Readouts use the sketch editors' existing nine decimal places and remove trailing
zeros. There is no global configurable decimal-precision setting in this version.
Formatting never rounds the stored tool dimension or committed parameter.
The existing bounded island dirty-region repair remains in place.

## Planar loyalty

The active sketch frame determines where geometry exists. References supply local
coordinates within it. The camera only determines observation. Input continues
through the existing camera-ray/sketch-plane intersection and frame transforms;
rotating the camera does not change the frame. Coplanar model acquisition cannot
attach a sketch to another face. Exact coordinates are committed through normal
entity transactions. Regression tests cover oblique views on +X, +Y and +Z faces.

The current Shift + double-right-click gesture still aligns to a visible planar
face, including during sketching; it changes the camera only. A dedicated Look at
Sketch recovery control and off-plane Projected Geometry Snap are future work.

## Operator acceptance checks

1. On a box face, draw a rectangle between opposite corners, then acquire its
   corners, midpoint, edge and center while drawing more geometry. Disable grid
   snapping and check exact Properties coordinates and matching symbols.
2. Start one construction line at a completed-sketch midpoint and end it at a
   model midpoint. Test ordinary line endpoints, circle circumference and both
   slot centers. Construction entities must remain excluded from profiles.
3. Compare slots at/away from the origin with Origin Snap on/off. Only a center
   coincident with the enabled origin should use origin feedback.
4. Draw a rectangle through the popup's initial position. Repeat Slot radius and
   second-center placement. Confirm uninterrupted tracking, calm relocation and
   cleanup on completion, Escape and tool changes.
5. Enter radius 2.000001 with Tab, then by holding Ctrl before approaching the
   field. Move the cursor while editing, use Tab/Enter/Escape and resize the
   window. Check the stationary accessible field and preserved exact value.
6. Repeat popup/island overlap in Compact, Medium and Expanded layouts, at
   50%/100% opacity, and after pan/zoom/resize. Check readable controls with no
   amber residuals. Try triangle/C/L, colors, weight and temporary guides.
7. Mix model, sketch, grid and free placement at ordinary zooms and on a sloped
   face. Rotate away from normal; confirm the active sketch frame is unchanged.
   Off-plane references must remain unavailable.
8. Save/reopen, Undo/Redo and use the acquired geometry in New Body, Join and Cut.
   Export STL/STEP and confirm normal face/edge selection after Finish Sketch.

Automated results and separate actual desktop verification are recorded in
[VALIDATION.md](../VALIDATION.md). Repeat the checklist on the operator's Linux/
NVIDIA workstation; software-rendered verification does not establish every GPU
or display-server combination.

# Existing geometry references while sketching

Enter a sketch attached directly to a planar solid face, then choose Line,
Rectangle, Circle, or Slot. Move near an edge of a displayed solid lying on
the active plane. A temporary geometric symbol shows the exact placement
point and an optional edge highlight identifies the contributing model boundary.
The status bar reports MODEL ENDPOINT, MODEL CENTER, MODEL MIDPOINT, or MODEL EDGE.
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
| Model straight-edge midpoint | Hollow triangle |
| Circular or slot center | Circled crosshair |
| Arbitrary straight-edge location | Hollow diamond |
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
straight-edge midpoints, arbitrary positions along straight segments, and centers
of analytic circular edges or arcs. Inner hole boundaries are eligible. A full
circle's artificial seam vertex is excluded. Geometry is read from current OCCT
edges, independent of the viewport's tessellation and edge thickness.

Acquisition uses an eight-logical-pixel radius at any zoom and accounts for the
viewport's physical pixel scale. On a face sketch, the priority is

1. Nearest precise point among the enabled sketch origin, enabled active-sketch
   circle/slot centers and construction-line endpoints, and supported model
   endpoints and centers.
2. Straight model-edge midpoints.
3. Nearest projected point on a straight model edge.
4. Enabled grid intersections.
5. Free cursor placement.

Within a priority group, an acquired point has a two-logical-pixel retention
preference. This reduces switching between nearby candidates while keeping the
original acquisition radius. Ties use stable traversal order within the unchanged
evaluated scene. Model references are independent of grid and Center Snap toggles.
Outside direct face-sketch editing, existing origin/center/grid behavior applies.

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
Arbitrary curved-edge locations, ellipse centers, and off-plane projection are
outside the supported target set.

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

## Operator acceptance checks

1. On a box face, draw a rectangle between opposite corners. Check its local
   dimensions against the face and repeat with grid snapping disabled.
2. Start a line at an edge midpoint, then at another location along the edge.
   Check MODEL MIDPOINT and MODEL EDGE feedback. Move away and switch tools to
   check that the marker/highlight clear.
3. On a face containing a circular hole, start a circle or construction circle
   at MODEL CENTER. Check its exact center in Properties.
4. Mix an acquired model point, an existing sketch center, a grid point, and
   free placement. Repeat at ordinary near/far zoom levels and on a sloped face.
5. Save/reopen and use the resulting profile in New Body, Join, or Cut. Try
   Undo/Redo and STL/STEP export. Confirm ordinary selection after Finish Sketch.
6. Choose the Triangle and C/L midpoint symbols, try Red and Green, and adjust
   size/weight. Toggle source highlighting and enable a colored centerline guide.
   Check that zoom preserves apparent symbol size and acquisition coordinates.
7. Create a Slot near the visible island so the numeric popup overlaps it.
   Move through radius and second-center stages, then complete or cancel. Check
   that the controls restore cleanly. Repeat in Compact, Medium and Expanded
   layouts, with lower popup opacity, and after pan/zoom/resize.

Automated results and the separate desktop verification are recorded in
[VALIDATION.md](../VALIDATION.md).

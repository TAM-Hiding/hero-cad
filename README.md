# STAR-CAD

Lightweight, Linux-native parametric mechanical CAD for STR-GZR OS. Fusion-inspired workflow, with a small, understandable toolset. No accounts, subscriptions, cloud requirements, or telemetry. AI-assisted modeling is a future capability; ordinary modeling must always work offline.

## v0.0.12 / parametric solid operations

A Qt desktop app with an Open CASCADE box, editable sketches, model browser and properties panel. All model coordinates are millimetres; the B-rep and stored parameters are authoritative, not the display mesh. The dark blue-gray background, shaded solids and one-pixel boundary lines are retained.

### Sketch workflow

1. Expand **Origin**, select **XY**, **XZ** or **YZ Plane**, then choose **New Sketch**.
2. The camera faces the plane orthographically; axes and origin appear. Origin-plane editing temporarily hides solids. Face-attached editing retains translucent solids and other sketches as placement references.
3. Choose **Line**, **Rectangle** or **Circle** in the contextual sketch toolbar. Placement previews appear while moving the cursor.
4. Choose **Select**, then click an entity (or its browser entry) to edit numeric parameters in Properties. Click **Apply entity parameters** to commit.
5. Choose **Finish Sketch** to restore the previous model view. Select an existing sketch and choose **Edit Sketch**, or double-click its browser entry, to return.

| Tool/input | Result |
|---|---|
| Line: click, click | Two endpoints; edit X1/Y1/X2/Y2 later |
| Rectangle: left press, diagonal drag, release | Axis-aligned rectangle |
| Rectangle: Shift-click, click, click | First corner, first-edge endpoint, perpendicular depth; arbitrary rotation |
| Circle: press center, drag radius, release | Editable center X/Y and radius |
| Circle with Shift at press: drag radius, release, then click | Slot with editable first-center X/Y, radius, center distance and angle |
| Escape during construction | Cancel preview and return to Select |
| Escape or blank click in Select | Clear selection |

Shift only needs to be held for the **first** edge-first rectangle click. Both rectangle methods create the same editable entity: X/Y position, width, height and angle in degrees. Positive angles rotate from local U toward V. A negative perpendicular depth shifts the stored corner to keep width and height positive. Circle radii and slot radii/center distances must be at least 0.000001 mm. Shift only needs to be held at the initial press for slot mode; releasing the radius gesture locks it, and the next click sets the second end center. Zero center distance is rejected; use a circle for that case. Slot distance is **center-to-center**, so total length is distance + twice the radius.

**Grid** toggles exact model-space major/minor grid lines. Automatic spacing follows zoom in 1/2/5 steps, with **ten minor subdivisions per major interval** (for example 10 mm / 1 mm). Major lines are brighter; minor lines are finer in appearance. Disable **Auto Grid** to set the manual **mm minor** interval; majors remain ten times that interval. The status bar reports the current major/minor spacing. Extremely dense manual grids display a bounded subset of reference lines to keep interaction responsive; the chosen snap interval remains unchanged.

**Snap to Grid** snaps new construction points to nearby minor-grid intersections within **8 logical screen pixels**, regardless of grid visibility or line thickness. **Origin Snap** independently prioritizes the local sketch origin within that tolerance; it works with grid snapping off. Both default on. **Center Snap** independently targets exact circle centers and both slot-end centers in the active sketch. Snap priority is **Origin → Center → Grid**, with the nearest center chosen among competing entities. Center targets come directly from parameters, regardless of display detail. Gold feedback marks a grid snap, magenta identifies the origin, and blue identifies a center. Center snapping defaults on and works with the grid hidden or grid snapping off. The status bar shows local U/V coordinates and `SNAP: GRID`, `ORIGIN`, `CENTER` or `FREE`. Feedback is shown while using a construction tool; invalid/edge-on plane intersections do not create points.

All tools use the same snapped input (including existing circle/slot centers): line endpoints, rectangle corners/first edge/depth point, circle center/radius endpoint, and slot first center/radius endpoint/second center. For rotated rectangles the final depth is the perpendicular projection of the snapped cursor point. A circle's radius is the distance between the snapped center and radius endpoint; it need not be a multiple of the grid interval. Numeric edits preserve their exact entered values and are never snapped. Existing geometry is unchanged when grid settings change.

**Origin Axes** toggles world-coordinate lines through (0,0,0): **X red, Y yellow, Z blue**, in sketch and model views. The sketch origin remains visible independently. Grid, axis and snapping settings last for the application session and are excluded from selection, Fit, document saves and Undo.

The sketch editor displays nine decimal places and preserves untouched higher-precision stored values. Coordinates are limited to ±1,000,000 mm; minimum line length and rectangle side are 0.000001 mm. These are input limits, not manufacturing accuracy guarantees. Storage and the CAD kernel use double-precision coordinates.

Circle and slot display polylines adapt to zoom and viewport resolution, targeting **0.25 physical pixels** of deviation. A 0.02 mm-radius circle gains detail as it is magnified. Live previews, highlights and picking use the same display policy. Pan/orbit reuse meshes; zoom/resize only changes detail when crossing a quality band. Stored parameters and analytic OCCT circles/arcs are unchanged. A safety cap of 32768 segments per full circle bounds work at extreme magnification of enormous mostly-offscreen curves; the pixel target can be exceeded when that cap is reached.

Origin frames: XY uses U=+X/V=+Y (normal +Z); XZ uses U=+X/V=+Z (normal −Y); YZ uses U=+Y/V=+Z (normal +X). Face-attached sketches use their own analytic local frame (see below).

### Exact dimensions during placement

After starting a shape, move the cursor to establish direction, then **type a dimension** or press **Tab** to focus the visible input field. You can also click that field during click-based construction stages. The popup stays near the start of each stage so it can be reached by the pointer, offset 98 logical pixels right and 68 down (80 right / 50 down farther than the original). Its position is clamped inside the viewport. **View → Dimension popup opacity** adjusts the entire popup from 100% to 0% (Off). At 0% the popup and numeric-entry activation are disabled, leaving mouse-only construction available; raise opacity to restore it. This preference lasts for the application session and is not stored in documents. Valid typed values update the preview immediately without changing the document. Pointer movement pauses while editing to preserve the chosen direction. **Tab** locks the current value and moves to the next field; **Enter** locks and completes the current construction stage. **Escape** cancels the entire unfinished shape, including typed values. Positive finite values from 0.000001 to 1000000 mm are accepted, subject to entity coordinate limits. Numeric entry bypasses snapping for the specified dimension and retains the cursor direction; untouched mouse-only gestures and Shift modes work as before.

| Placement stage | Typed fields |
|---|---|
| Line second point | Length |
| Circle radius | Radius / Diameter (Tab switches) |
| Shift-slot radius, then second center | Radius / Diameter (Tab switches), then Center distance |
| Diagonal rectangle | Width and Depth (Tab switches) |
| Shift edge-first rectangle | Width, then perpendicular Depth |

For example, start a circle, drag outward, press Tab, type `0.02`, then Enter. Within the radius stage, Tab switches between Radius and Diameter; Shift+Tab switches back. An empty field can be skipped before typing. Switching a specified value converts it and selects the new value for replacement; Enter accepts either representation. Diameter entry also works for the shared end size of Shift-slots, before their center-distance stage. For drag-based tools, start typing or press Tab before releasing the mouse; releasing while the field is active waits for Enter. For a slot, hold Shift at the initial press, type the radius and Enter, move toward the second center, then type its center-to-center distance and Enter. You can release the mouse while the input is open; placement waits for Enter or Escape. Numeric values are stored as double precision without display rounding. For line length, endpoints encode the length at floating-point precision.

### Selection, context actions and deletion

In Select, **Shift-click** toggles sketch entities. The model browser also supports extended selection with Ctrl/Shift. **Delete / Backspace** removes selected sketch entities or entire unreferenced sketches in one transaction; Undo restores the whole batch. These keys keep their normal text-editing behavior in numeric fields. The base box cannot be deleted in this milestone. Features referenced by surviving features cannot be deleted; the status bar explains the dependency.

Right-click a sketch curve or browser entry for **Edit Parameters**, **Edit Sketch** and **Delete**, as applicable. Right-clicking an unselected entry selects it; right-clicking a selected entry retains the batch. Shift-right remains reserved for pan and face-normal alignment. Only implemented context actions are shown. Slot ends retain their shared radius; independently sized ends are deferred (see ROADMAP.md).

### Material profiles and extrusion

1. Draw a **Rectangle**, **Circle** or **Shift-slot** in an origin-plane or resolved face-attached sketch.
2. Choose **Select Profile** and click **inside the material**, away from its boundary. The selected material region receives an orange fill; holes remain empty. This mode is independent of the face/edge filter. Enter the sketch if a solid obscures its plane, or if multiple sketches coincide.
3. Choose **Extrude…** in the toolbar or context menu. In the modeless operation panel choose New Body, Join, Cut or Intersect and an explicit target for material operations. Enter a signed distance: positive follows the sketch normal, negative reverses it. Click Preview result, inspect/navigate, then Apply or Cancel. Zero distance is rejected. Negative New Body remains a new body, never an implicit Cut.
4. The browser lists the extrusion. Select it to edit its signed distance in Properties, or choose **Edit Sketch** to modify source dimensions. Source edits regenerate the extrusion through persistent sketch/entity IDs. Undo/Redo covers creation, parameter edits and deletion; Save/Open regenerates the same bodies.

**Holes:** a boundary with fully contained closed loops extrudes as material minus its immediate holes. Further nesting alternates empty/material: an island inside a hole is a separate selectable profile. Rectangles, circles and slots can form outer boundaries or holes, including rotated shapes. Several isolated regions can be extruded with separate feature entries. One region is selected per extrusion.

**Safety limits:** overlapping, touching or coincident boundaries are not split into new regions. Affected containing regions and nested descendants are unavailable; separate unambiguous regions can still be selected. Boundaries closer than 0.0000001 mm are treated as ambiguous. Line-chain regions are deferred: a sketch containing any Line entity cannot supply an extrusion profile, even if some lines are open or remote. Use a separate sketch for those lines. Profile analysis supports at most 256 closed entities per sketch. Unsupported cases receive feedback rather than silently filling a hole or choosing another region.

Extrusions store the source sketch UUID, outer entity UUID and exact hole UUID set. Dimension/position edits preserve those references. A change that would add/remove a hole, change nesting or make boundaries intersect is rejected atomically. Delete the extrusion, change the region topology, then reselect and extrude; Undo can recover the earlier state. Referenced source sketches and boundary entities cannot be deleted while their extrusion survives.

Extrusions support **New Body, Join, Cut and Intersect**, without taper, drag-depth manipulation or general overlapping sketch-region construction. Bodies are not implicitly fused; their volumes sum even if bodies overlap. The initial box remains in the document but is hidden after creating an extrusion or opening a document with extrusions, so it cannot cover the new part. **Settings → Show base box** restores it; this display preference does not modify geometry. By default, deleting all extrusion bodies restores the base box. An explicit Settings toggle overrides these defaults for the session, including after New/Open and Undo/Redo. The toggle also works when the box is the only solid; hiding it does not delete or suppress its dependent features. The status bar reports the volume of displayed bodies, explicitly a sum when several are shown.

### Sketch on a planar face

Right-click a visible supported solid face and choose **New Sketch**. This picks the actual analytic OCCT face independently of the face/edge filter, selects it, and enters an orthographic sketch view. Existing tools, Shift gestures, dimensions, grid and local-origin/center snapping work unchanged. While editing a face sketch, existing solids remain visible at 35% opacity with their boundary edges, and other sketches remain visible for placement context. Viewport entity selection is restricted to the active sketch. Finish restores opaque solids; origin-plane editing retains its isolated view. Finish Sketch restores model view; select the sketch in the browser and choose Edit Sketch (or double-click it) to reenter and align again. Shift-right drag and Shift-right double-click retain pan and Look At Face.

Supported references:
- Box: **+X, −X, +Y, −Y, +Z, −Z**.
- Extrusion: **Start Face** at the source plane and **End Face** at signed extrusion distance.
- Planar sides of Rectangle boundaries (four named edges) and Slot boundaries (two straight tangent segments), including hole walls. These use the source entity UUID and parameter-defined segment identity; no generated face index is stored.
- Circle walls and rounded Slot ends are curved and cannot host a sketch. Unknown/imported faces with no supported feature identity are rejected. Arbitrary compound orientations are supported mathematically; no transform/import operation is added in this release.

The browser and sketch properties identify the parent and semantic face. Changing box dimensions, extrusion distance or source boundary dimensions regenerates attached planes while retaining local entity coordinates, dimensions and UUIDs. Caps inherit the source U direction and retain their initial normal sense through signed-depth reversal; sides use their boundary anchor and source normal. Frames come from geometry, never the camera. Presentation keeps projected world Z upward with a world Y fallback near Z poles.

A lost semantic side marks the sketch **UNRESOLVED**, preserves its entities and last resolved frame, and suppresses its display and downstream bodies. The browser tooltip/properties explain the failed reference; unresolved sketches cannot be entered. Restoring the supported source boundary (including Undo) resolves it again. Parent deletion is blocked while dependents survive. Reassign Sketch Plane is deferred; no substitute face is chosen automatically.

### Combine bodies, cut extrusion and previews

Select two or more **current body** features in the browser (Ctrl/Shift), or select faces/edges on multiple visible bodies, then choose **Combine…** from the context menu or toolbar. The panel lists the target and all selected tool bodies. Choose Join, Cut or Intersect, **Preview result**, then **Apply**. For Cut, the target is the body retained; all other selected bodies are subtracted. Join accepts connected chains in any tool order. Inputs retain their UUIDs and parameters as historical features; only current resulting bodies are displayed. Unrelated bodies remain separate. Historical inputs can still be edited, but cannot be reused as current Boolean targets without removing/undoing their consuming operation.

For an extruded cut, select a closed material profile and choose **Cut**, confirm its target, then choose **Specified distance** or **Through All**. A top-face sketch usually needs a negative distance (for example −5 mm) to enter the solid because its normal points outward. Through All has an explicit +/− direction and recomputes sufficient reach from the target's actual bounds after each edit; it does not store an oversized fixed cutter. It starts at the sketch plane and cuts in the selected direction only. All modes respect the original profile's exact hole set.

The orange shaded preview replaces the normal body rendering, including all current result bodies, so the target is not drawn underneath it. Navigation remains available. Changing a field clears the stale preview; Preview result revalidates it before Apply. Cancel leaves document/history untouched. **Edit Operation…** in a feature context menu or its Properties opens the same panel; combine tool membership is fixed to the selected set, while operation and target can be changed. Recreate a Combine to change that set.

Operations require one valid connected positive-volume solid result. Disconnected, touching-only, zero-volume, non-intersecting and split-result operations are rejected conservatively. Initial invalid operations cannot be applied. If an accepted operation later loses overlap after an upstream edit, its parameters remain with an unresolved error and no stale result body; restoring inputs or Undo recovers it. Missing/forward/cyclic references remain hard errors. Synchronous OCCT preview can take time on complex inputs; no background worker is added.

**Face-reference limit:** new sketches cannot be attached to Boolean output faces, including Join/Cut/Intersect extrusion outputs. Such faces have no semantic naming contract in this release and report the limitation. Existing sketches remain attached to their explicitly referenced original feature, even when that feature becomes historical. Changing a referenced New Body extrusion into a Boolean extrusion invalidates its old cap/side references explicitly, retaining unresolved sketch geometry. Plan needed face sketches before the operation, or use origin-plane sketches for subsequent features. No general topological renaming is attempted.

### Explicit display modes

Choose **View → Display Mode**: Shaded with CAD Edges (default), Shaded, CAD Wireframe, or Mesh Debug. CAD Wireframe uses real B-rep edges and exposes hidden edges; Mesh Debug intentionally exposes tessellation triangles. Face/edge selection still uses CAD topology in every mode. W/S/P no longer invoke inherited VTK display shortcuts. Display mode is session-only, survives regeneration, and never changes saved geometry. Sketch construction/numeric fields and the existing camera shortcuts remain available.

### Documents and editing

The existing box workflow remains: edit Width (X), Depth (Y), Height (Z), then **Apply dimensions**. Box inputs display three decimal places and range from 0.001–100000 mm. Untouched higher-precision values are retained.

**Ctrl+S** saves, **Ctrl+Shift+S** saves as, **Ctrl+O** opens, **Ctrl+N** starts fresh; **Ctrl+Z / Ctrl+Shift+Z** undo/redo feature and entity edits. Undo first cancels unapplied property edits. Changing browser selection or finishing a sketch commits pending property edits; invalid edits keep the current selection. Save also commits pending fields. In-progress cursor previews are not document geometry and are not saved.

The title's `*` marks unsaved changes. New/Open/Close offer Save, Discard or Cancel; cancelled or failed saves retain the document. Undo history is session-only. Documents use versioned `.starcad` JSON in millimetres. Format v3 stores ordered feature IDs, dependencies, box parameters, origin-plane frames and sketch entities. Existing v1–v5 documents still load. Saving without extrusions writes v3; documents containing ordinary New Body extrusions write v4 with stable source/profile references and signed distance. Boolean features and material-operation extrusions write v6 with operation, target, extent and direction; v1–v5 files continue to load. Face-attached sketches write v5 with semantic parent-face references and last resolved frames. Older application versions cannot open newer format versions. Numeric parameters round-trip without deliberate decimal rounding.

Saves flush a complete same-directory temporary file before atomic replacement. Failed writes retain the previous file. Strict schema validation rejects unknown fields/versions, duplicate JSON keys, invalid IDs, missing/forward/cyclic dependencies and invalid geometry. V2–v6 files are limited to 4 MiB, 1000 features and 10000 entities per sketch; legacy v1 retains its 64 KiB limit. No autosave or concurrent-writer locking.

This milestone supports **one base box, multiple origin-plane/face-attached sketches and parametric extrusion bodies**, ordered regeneration and transactional validity/error reporting. It does not include constraints, general topological naming or feature reordering. Sketch and solid selection support multiple entities; Properties edits one current entity/feature at a time. Extrusions consume their referenced source sketch during regeneration.

## Ubuntu setup

Primary automated target: Ubuntu 24.04 x86-64, CPython **>=3.12,<3.13**, X11/XWayland and OpenGL 3.2+. v0.0.2 also passed a user-reported physical laptop test on **Ubuntu 22.04 with Python 3.12**. Ubuntu 22.04's system Python 3.10 does not satisfy this requirement. Keep the system Python unchanged; use a separate Python 3.12 interpreter and a dedicated venv. Other Python versions and ARM are not declared supported.

### Interpreter on Ubuntu 24.04

```bash
sudo apt update
sudo apt install python3.12-venv
```

### Interpreter on Ubuntu 22.04

If Python 3.12 is already installed separately, proceed to the common steps below. One option for installing it alongside system Python is the **third-party [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa)**. Review that provider before adding it; this is not an Ubuntu-maintained repository. The exact interpreter-install procedure was not recorded in the laptop report, so these PPA steps are guidance, not a reproduction of that test.

```bash
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv
```

Do not change `/usr/bin/python3`, replace the system interpreter, or install app packages with sudo pip.

### Common runtime dependencies and application setup

Qt's XCB plugin needs system libraries in addition to the PySide6 wheel. Missing libraries prevented the initial laptop launch; installing them resolved it. See [Qt's X11 requirements](https://doc.qt.io/qt-6.8/linux-requirements.html).

```bash
sudo apt update
sudo apt install libgl1 libegl1 libgl1-mesa-dri libxcb-cursor0 libxkbcommon-x11-0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 \
  libxcb-image0 libxcb-render-util0 libxcb-randr0 libxcb-xfixes0 libxcb-xkb1 \
  libxcb-sync1 libxcb-shm0 libx11-xcb1 libxrender1
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
QT_QPA_PLATFORM=xcb star-cad
```

Run these commands from a checkout of this repo. Installation needs network access; the application does not. `python -m star_cad` is an alternative entry point. The lock file records the tested development environment; `pip install -e '.[dev]'` resolves transitive dependencies afresh. Binary dependencies are substantial (Qt, OCCT, VTK); lightweight here describes product scope, not a tiny download.

Controls: left drag orbits when no construction tool is active; middle drag or **Shift-right drag** pans; wheel zooms. **F / Fit all** frames visible geometry. Standard Isometric, Front, Top and Right views are available outside sketch mode. Zoom is bounded relative to model size; maximum magnification is reduced by 20% from v0.0.3. Finishing a larger sketch can move the orthographic camera backward along its viewing direction to keep geometry in front of its near plane; scale and focal point are retained. Real solids still occlude curves behind them. Sketch mode starts perpendicular to its plane; orbiting in Select remains possible, and reentering the sketch restores its plane view.

**Shift + right-double-click** on a visible planar solid face aligns the camera exactly perpendicular to it, centers the clicked face location, and switches to orthographic projection. It works in either face or edge selection mode and preserves selections and document parameters. Ordinary **Shift-right drag** still pans; tiny movement within the desktop drag threshold is ignored to keep double-clicks steady.

Alignment keeps orthographic zoom; from perspective it converts apparent scale at the clicked face to an approximate matching orthographic scale. Camera up follows projected world Z, using world Y near the Z poles, so repeated alignment has deterministic roll. The camera views the oriented face from its outward-normal side. **Previous View** restores the full camera state from before the latest successful alignment, including position, pan, zoom and projection; this is a single session-only restore slot, not document Undo or a full view-history stack. Curved faces, empty space and hidden solids produce brief status feedback and leave the camera/previous-view slot unchanged. Analytic OCCT planes are supported; planar fitting of spline surfaces is not included. This camera operation does not create a sketch or face attachment.

Choose **Select faces** or **Select edges** and click for the existing orange highlight. **Shift-click toggles** entities in a mixed face/edge selection; an ordinary click replaces it. Changing the filter retains the selection. Escape/blank clicks clear it. Dragging does not select. Regeneration clears solid selections; transient topology is never saved. The picking-radius control defaults to **6 logical screen pixels**, adjustable from 2–10, independently of the one-pixel edge display and zoom. Hidden solid edges remain unselectable. The same hit radius is used for sketch selection. The radius preference is session-only.

## Tests

```bash
sudo apt install xvfb libgl1-mesa-dri
LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb xvfb-run -a .venv/bin/pytest -q
.venv/bin/pip check
```

Kernel-only checks: `.venv/bin/pytest tests/test_document.py -q`.
Full tests require a working GL context; Qt offscreen alone is not evidence that rendering works. See [VALIDATION.md](VALIDATION.md) for actual results and limits.

## Design and licensing

See [ARCHITECTURE.md](ARCHITECTURE.md), [ROADMAP.md](ROADMAP.md), and [DEPENDENCIES.md](DEPENDENCIES.md). STAR-CAD source is MIT, retaining the repository's original license. STAR-CAD makes use of Open CASCADE Technology. Its libraries and other dependencies retain their own licenses; the app's MIT license does not relicense them.

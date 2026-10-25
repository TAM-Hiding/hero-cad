> Historical records below PR #18 retain the original STAR-CAD commands and repository URLs as tested. Current commands are in README.md and MIGRATION.md; the old document-format marker remains intentional.

# M0 validation

Environment: Ubuntu 24.04.3 x86-64, CPython 3.12.14. Versions are recorded in requirements-dev.lock.

- Clean venv installation of pinned PySide6/OCP/VTK and editable application: succeeded.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not camera_controls'`: **10 passed, 1 deselected**. Checks real OCCT solid validity, volume and bounds after editing, invalid parameters, atomic rebuild failure, tessellation bounds, Qt property Apply, model browser and Fit method invocation.
- `.venv/bin/pip check`: passed.
- `python -m compileall -q src` and `git diff --check`: passed.

## Ubuntu CI — passed

[Verified run](https://github.com/TAM-Hiding/star-cad/actions/runs/39523303345), code commit `7ffe326d6a883a68e50845b98096c39a9aa129c7`: Ubuntu 24.04.5 x86-64, CPython 3.12.15, Xvfb with Mesa software OpenGL.

- Fresh installation from requirements-dev.lock and editable app: passed.
- `pip check`: passed.
- `LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb xvfb-run -a python -m pytest -q`: **11 passed**, one upstream VTK/NumPy deprecation warning.
- Qt mouse events changed the camera for orbit and pan; wheel changed orthographic zoom.
- Render readback contained the expected background and a substantial shaded model surface. This stronger assertion rejects the corrupt framebuffer seen locally.

This verifies the automated desktop smoke test on that runner, not every Linux graphics stack.

## Local display limitation

The local container cannot open X server listening sockets: Xvfb reports `Cannot establish any listening sockets`. Qt offscreen can instantiate the window and process a property edit, but VTK's EGL fallback reports failure to initialize OpenGL/shaders. Thus **visible 3D rendering and orbit/pan/zoom are not locally verified**. Passing the offscreen widget test must not be interpreted as render success. No screenshot from that environment is accepted as evidence.

The full Xvfb test suite includes mouse-driven orbit, middle-button pan, wheel zoom and a nonblank rendered-pixel assertion. It is configured in GitHub Actions for a normal Ubuntu runner. Native Wayland, a physical GPU, manual UX and STR-GZR OS integration remain untested.

No boolean, sketch, export or save/load operations exist or are claimed. M0 passes the automated Ubuntu desktop smoke test. Manual usability remains to be checked on a real desktop.

## v0.0.2 — local documents and Undo/Redo

Local command: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not camera_controls'`.
**34 passed, 1 deselected**. New checks cover parameter-file round trips with real OCCT volume/validity, strict format rejection, saved-state Undo/Redo, branching/no-op history, rebuild failure, failed flush/replacement preserving the original file, Save As, pending editor text, and Save/Discard/Cancel flows. Opening the current file after a Save prompt reloads the saved changes. Untouched higher-precision values survive the three-decimal editor.

`pip check`, compileall and diff whitespace checks pass. No dependencies changed. File-dialog choices and prompt answers are controlled in automated UI tests; native file-dialog interaction and manual desktop usability still require a laptop. The local GL/socket restriction documented above remains; [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39525104228) passed for code commit `d64fde5086919ec36eb2292b6e84844f7fe42d0b`: **35 passed, 1 upstream VTK/NumPy deprecation warning**, CPython 3.12.15, Xvfb and Mesa software OpenGL. This includes the original rendered-pixel and orbit/pan/zoom regression checks. Fresh package installation and pip check also passed.

## Physical v0.0.2 acceptance and v0.0.3 follow-up

The [supplied physical laptop report](docs/DESKTOP_TEST_0.0.2.md) records Ubuntu 22.04 / Python 3.12 startup, geometry editing, navigation and save/reload success after installing missing XCB dependencies. Two nonblocking viewport issues were reported: triangle diagonals and extreme zoom. This is user-reported manual evidence, separate from CI.

v0.0.3 adds separate OCCT edge display, transient face/edge selection, highlighting, bounded zoom and orientation presets. Local tests use Qt offscreen; the render checks still require working GL in CI. New tests check unique CAD boundary lines, located curved display geometry, whole-face mapping, edge picking and occlusion, clearing on regeneration/Escape, click versus drag, orientation, model-relative camera limits, zoom stress and highlight pixels. [Full CI run](https://github.com/TAM-Hiding/star-cad/actions/runs/39553028345), code commit `be9ff36cafd33c8b1299ce9bf20c90d99fbb8b67`: **44 tests passed on Ubuntu 22.04 and 44 on Ubuntu 24.04**, Python 3.12.15, Xvfb/Mesa software OpenGL. Both fresh installations and pip check passed. Render tests verify a planar-face center has no diagonal line, face and edge highlights produce orange pixels, clearing restores the original face, and repeated wheel zoom stays bounded and Fit recovers. Local offscreen checks: 42 passed, 2 render checks deselected. Compileall and whitespace checks passed. No dependencies changed. Native HiDPI behavior, subjective highlight appearance and the fixes on the user's physical laptop are not yet verified.

## v0.0.4 — sketch foundation

User reports v0.0.3 physically accepted on Ubuntu 22.04/Python 3.12: clean faces, successful face selection, desired orange highlight. Requested follow-ups are tighter zoom and generous invisible edge picking.

New checks cover ordered feature IDs/dependencies, transactional errors, each plane transform, analytic OCCT sketch lengths/bounds/validity, both rectangle modes and rotated perpendicular geometry, tool previews/Shift latching/cancellation, numeric UI edits, sketch reentry, mixed selection, pixel-based hit radius at three zooms, legacy migration, exact parameter persistence, undo/redo and file size failure safety. Render tests also require green preview, orange selected entity, cyan completed line and the expected background.

Local rendering remains unavailable: Qt offscreen reports EGL/OpenGL shader initialization failure. Native hover cursor motion is not delivered by Qt offscreen; the hover test explicitly sends a Qt MouseMove event, while press/release/drag tests use QTest. Neither substitutes for physical mouse testing. Full Xvfb/Mesa tests remain required in CI on Ubuntu 22.04 and 24.04 with Python 3.12.

Manual acceptance outstanding: physical GPU/HiDPI, picking feel, sketch tool gestures and camera transitions, native dialogs, very large sketch responsiveness. Limits: one box; independent sketches; no deletion/reordering, snapping, solver, circles/slots, sketch-on-face or extrusion. No dependencies changed.

### Verified v0.0.4 results

- Local: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not camera_controls and not sketch_render'`: **70 passed, 3 deselected**. Kernel-only `tests/test_document.py`: **23 passed**. `pip check`, compileall and `git diff --check` passed.
- [Full Ubuntu CI run](https://github.com/TAM-Hiding/star-cad/actions/runs/39559608045), code commit `f27dc6bf5b68a08592c25e4ef1833cb9666c4601`: **73 passed on Ubuntu 22.04 and 73 passed on Ubuntu 24.04**, CPython 3.12.15, Xvfb/Mesa software OpenGL. Fresh installation and dependency checks passed. Eight upstream VTK/NumPy deprecation warnings per job.
- The first CI run caught an overly strict preview pixel threshold: a one-pixel antialiased line blends with the background. The corrected test requires the preview's green chroma, completed line's cyan chroma, selected entity's orange chroma, sufficient colored pixels, and expected background; the white origin cannot satisfy it. No render checks were skipped in CI.

v0.0.4 is ready for physical acceptance, not yet physically accepted. On the laptop, try all three planes, both rectangle gestures (release Shift after initiation), live line previews, numeric edits, sketch reentry, Save/Open and Undo/Redo. Check Shift-right/middle pan, mixed face/edge Shift-selection, 2/6/10-pixel picking and zoom recovery. **Extrusion remains blocked until that acceptance.**

## v0.0.5 — circles, slots and guides

Physical v0.0.4 feedback: user reports easy edge picking, mixed Shift selections across face/edge filters, successful sketches/rectangle Shift method and angle editing, and smooth interaction without observed lag. Save/reopen and sketch Undo/Redo were not explicitly confirmed in that report.

This pass adds Circle/Shift-slot tools, editable radius/center-distance/angle, exact OCCT circular edges/tangent slot wires, a visual sketch grid and a world-axis toggle. New tests cover analytic perimeter and enclosed area on XY/XZ/YZ, gesture latching/cancellation and invalid inputs, exact persistence and v2 compatibility, numeric edits/undo/reentry/picking, guide toggles and plane transforms, camera-independent guide settings, and rendered curves/grid. Local rendering still requires CI's functioning OpenGL. No dependencies changed.

Outstanding manual checks: Circle drag/release; Shift-slot radius release and second center; angle/radius/distance editing; grid at different zoom/pan levels on all planes; red X/yellow Y/blue Z axis toggle in sketch and model views; save/reload and Undo/Redo. Grid is visual only, guides are session-only, circles have no rotation parameter, zero-length slots are rejected.

### Verified v0.0.5 results

- Local kernel regression and new curved geometry: `tests/test_document.py tests/test_curves.py`: **36 passed**. Full local non-render suite: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not camera_controls and not sketch_render and not curves_and_grid_render'`: **89 passed, 4 deselected**. Compileall, dependency compatibility (`uv pip check`) and whitespace checks passed.
- [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39661529529), code commit `05339ac2a95601de6451db8e27c24e4c6cb843fa`: **93 passed on Ubuntu 22.04 and 93 on Ubuntu 24.04**, Python 3.12.15, Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Twelve upstream VTK/NumPy warnings per job. No render checks were skipped.
- Rendered checks detect cyan curved entities, orange slot selection, visible grid pixels and restored output when the grid is switched off. Existing solid-render/navigation and sketch-preview checks also pass.

Ready for physical testing; v0.0.5 has not yet been accepted on the laptop. No extrusion implemented.

## v0.0.6 — sketch visibility and precision grid

Physical v0.0.5 feedback: user confirms circles/slots work well and reports save/close/reopen success. Reported a partial, angle-dependent loss of outer-circle segments after Finish/orbit/zoom out. The original document and exact dimensions were not supplied.

### Investigation before changing rendering

Reproduced on unmodified v0.0.5 using a radius-150 XY circle and Slot(-30,0,10,60,20), finished back into the pre-sketch camera, then set parallel scale to 210. To isolate clipping, hid the solid/boundary actors and origin axes; no grid is visible outside sketch mode. At the original restored eye distance 104.033395 mm, 25 of 247 sampled curve points lay outside the near plane; normalized projected depth ranged from −0.020457 to 0.466834. Azimuth changes altered the missing set. Fit moved the eye to 819.574524 mm and recovered the scene. This reproduces the reported visual mechanism without any occluding solid, grid or axes.

Actual confirmed cause in this reproduction: the restored orthographic eye can lie inside the enlarged scene. Resetting a positive near/far range cannot show curve segments behind that eye; parallel zoom alone does not move it. Curve points and display bounds remain present. Ordinary solid occlusion after Finish is separately expected behavior, not the reproduced defect.

Fix: move the orthographic eye backward only enough to contain visible scene bounds plus a positive depth margin, retaining focal point, orientation and scale, then recompute near/far. The same reproduction has zero clipped points at the tested angles (first recovered distance 184.583247 mm, scale still 210). No global depth-disable or new sketch depth offset. Hidden solids and real visible-solid occlusion have separate rendered regressions.

### Automated and manual coverage

New checks reproduce the legacy clipping state before applying the fix and verify unchanged screen XY coordinates afterward. They cover large circles/slots on all three planes after orbit/pan/zoom/Fit, major/minor model-space distances and bounded density, snapping within/outside the screen tolerance at three zooms on every plane, hidden-grid snapping, origin priority and independent origin toggle, local offset-frame semantics, snapped line/rectangle/both circle-slot gestures, numeric precision, save/load and undo/redo. Rendered tests sample points around the full outer circle; check visible solids occlude and hidden solids do not; distinguish minor grid pixels and gold/magenta feedback.

Local OpenGL remains unavailable; numeric projection and Qt event checks run offscreen. Full pixel verification requires Ubuntu Xvfb/Mesa CI.

Manual retest: draw an outer circle larger than the initial box view with slots inside it; Finish, orbit through shallow/steep angles, zoom out/in, pan and Fit. Confirm the full unobstructed outer circumference remains visible. Repeat on XY/XZ/YZ and with grid/axes toggled. A curve genuinely behind the visible box must still be obscured. Then try both snapping toggles, hidden-grid snaps, origin priority, automatic/manual intervals and all construction gestures, plus Save/close/reopen and Undo/Redo. If missing segments persist, supply the .starcad file and camera/view steps; the exact original scene has not been available.

### Verified v0.0.6 results

- Local: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not render and not visible_solids'`: **109 passed, 9 deselected**. `tests/test_document.py`: **23 passed**. Compileall, `uv pip check` and whitespace checks passed.
- [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39668415360), code commit `14ac13582d39966a6f86a54208501653a79f76c2`: **118 passed on Ubuntu 22.04 and 118 on Ubuntu 24.04**, Python 3.12.15, Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Thirty-three upstream VTK/NumPy deprecation warnings per job. No render checks skipped.
- Render verification passes for unobstructed outer-circle sample patches on every origin plane at multiple viewing angles, slots in the same scene, zoom/Fit recovery, real opaque solid occlusion, hidden-solid non-occlusion, major/minor grid pixels and distinct grid/origin snap markers. Existing thin-line selection, gestures, documents and undo/redo checks pass.

PR #6 is ready for the targeted physical retest above. The reproduced clipping mechanism is fixed; the original user scene still needs laptop confirmation. No extrusion implemented.

## v0.0.7 — adaptive curves and exact centers

Physical v0.0.6 feedback: user reports improved behavior after merging. Additional feedback described polygonal 0.02 mm-radius circles under magnification and requested exact circle/slot-end center snaps; grid snapping was positively accepted.

The prior UI used the fixed 0.02 mm sampling fallback, leaving small full circles at 16 segments. New display-only sampling targets 0.25 physical pixels of sag, with upward power-of-two quality bands and a 32768/full-circle safety cap. The analytic OCCT circle/slot arcs and v3 document precision are unchanged. Cap-limited extreme offscreen cases may exceed the target.

New tests measure actual chord-midpoint deviation for 0.02 mm circles and rotated slot arcs at four pixel densities; verify zoom/resize resampling, mesh reuse on pan/orbit, consistent highlight/pick paths, preview refinement without losing Shift-slot stage, and exact document round trips. Center tests verify stored local target coordinates, both rotated slot centers, entity-before-grid and origin priority, independent toggles, current edited/Undo centers, screen tolerance at two zooms and mouse placement on all three planes. Pixel tests sample analytic locations between the former tiny-circle facets on every plane and detect the blue CENTER marker.

Local OpenGL remains unavailable; rendered tests require Ubuntu Xvfb/Mesa CI. Manual retest: magnify a radius-0.02 mm circle and slot, zoom in/out, pan/orbit and select curves. With grid snapping off, start a line near the center of an existing circle and each slot end; check blue CENTER feedback and exact numeric endpoints. Repeat XY/XZ/YZ and the Shift-slot gesture; Save/reopen and Undo/Redo.

### Verified v0.0.7 results

- Local non-render suite: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not render and not visible_solids'`: **129 passed, 13 deselected**. Kernel/document/curve regression suite: **36 passed**. Compileall, dependency compatibility and whitespace checks passed.
- [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39685266109), code/test commit `3cda0f16ac9b0d96bbdf38ba10155f63562750c3`: **142 passed on Ubuntu 22.04 and 142 on Ubuntu 24.04**, Python 3.12.15, Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Thirty-seven upstream VTK/NumPy warnings per job. No render checks skipped.
- Pixel checks pass at exact analytic positions between the former 16-sided tiny-circle facets on XY/XZ/YZ, and detect the blue center marker. Existing visibility/occlusion, grid/origin snaps, Shift gestures, precision files and Undo/Redo regressions pass. The outer-circle visibility test now samples fixed analytic positions independently of quality-band sample counts.

Ready for physical small-curve and center-snap acceptance. HiDPI behavior was checked by simulated render-size changes, not a physical HiDPI display. No extrusion or stored geometry/history changes.

## v0.0.8 — contextual face-normal camera alignment

User reports v0.0.7 merged/pulled and working well. This pass is camera-only: exact analytic planar-face alignment under the cursor with Shift-right-double-click, deterministic up, clicked-point focus, orthographic scale preservation/perspective conversion, and full Previous View snapshot restore. Face/edge filter and selections are untouched.

New tests cover located compound-angle OCCT planes and reversed orientation, projection back to the exact plane, deterministic unit up including pole cases, face picking while the edge filter is active, mixed selection/highlight retention, document/solid immutability, orthographic scale and full prior-state restoration, perspective vertical/horizontal angle conversion, curved/missed/hidden face rejection preserving prior state, drag-threshold/jitter conflicts, non-Shift right-double-click, subsequent pan/alignment/restore, and preserving an active Shift-slot construction when the solid is hidden. A rendered regression checks the compound-angle face surface, orthogonal/equal tangent projection and restored image.

Arbitrary-angle shapes are automated test fixtures only; the application still has no rotation/import modeling command. Source data remains unchanged. Local offscreen checks cannot validate OpenGL output; full Ubuntu Xvfb/Mesa CI remains required. No dependencies changed.

Manual retest: in either selection filter, Shift-right-double-click different box faces at off-center points. Check perpendicular orthographic view, unchanged zoom and selection, then Previous View restoring the panned/orbited view. Pan with Shift-right-drag immediately before/after alignment; try minor pointer jitter and releasing Shift during a pan. Curved faces require a future imported/created curved-solid workflow for physical testing (cylinders are tested in fixtures). During sketch mode, the hidden solid should produce a brief no-visible-face message and leave placement intact. Previous View is one level and session-only; spline-surface plane fitting and sketch-on-face are outside this pass.

### Verified v0.0.8 results

- Local non-render suite: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q -k 'not render and not visible_solids'`: **142 passed, 14 deselected**. Document regression suite: **23 passed**. Final face-specific non-render checks: **13 passed, 1 deselected**. Compileall, dependency compatibility and whitespace checks passed.
- [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39689912673), code/test commit `a5ee7a821ca2b6fed4e09eaccfc34a5019ba00a8`: **156 passed on Ubuntu 22.04 and 156 on Ubuntu 24.04**, with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. No render checks skipped.
- Rendered compound-angle alignment and Previous View image restoration pass alongside existing sketch visibility, selection, snapping, gesture, save/reopen and Undo/Redo regressions.

Ready for the physical gesture checks above. No geometry, feature parameters, history or extrusion changes.

## v0.0.9 — sketch editing, deletion and interactive dimensions

User physically accepted v0.0.8 face-normal alignment. This pass adds transactional sketch/entity deletion, multi-selection, context actions and transient cursor dimension entry. No dependencies, schema changes or extrusion. Unequal slot radii were evaluated and deferred with geometry/schema validation requirements in ROADMAP.md.

Targeted tests cover atomic deletion across sketches, dependency rejection, deleting the active sketch, browser and viewport selection/context behavior, native text-field Backspace, numeric circle/slot placement on XY/XZ/YZ, exact radius/distance/rectangle parameters, directed line/edge-first rectangle dimensions, invalid values, cancellation, typed input during mouse release, navigation conflicts, persistence and Undo/Redo. Local Qt offscreen can verify event/document behavior but cannot verify OpenGL pixels; full Xvfb/Mesa CI is required.

Manual acceptance: start circle placement, type radius and Enter; Shift-start a slot, type radius/Enter then center distance/Enter. Try releasing the mouse during typing. Test rectangle Width/Tab/Depth/Enter, rotated edge-first Width then Depth, and line Length. Check invalid/zero/negative/nonfinite values and Escape without document changes. With Select, Shift-click several curves, right-click a selected curve and Delete; Undo/Redo the batch. Repeat through browser selection and Delete/Backspace, delete an active sketch, save/reopen, and verify Shift-right pan/double-click plus snapping still work. Verify cursor readout legibility/position on the physical display.

### Verified v0.0.9 results

- Local full non-render suite before the last right-drag regression: **166 passed, 15 deselected**. Final sketch-editing and face-view gesture checks: **29 passed, 2 deselected**. Document regression suite: **23 passed**. Compileall and whitespace checks passed. The cursor readout was visually inspected and given explicit contrasting text/input colors.
- Initial pixel regression exposed variable viewport dimensions when property forms resized the docks. The test now fixes viewport dimensions so pixel comparisons measure geometry changes. It detects both selected circles, nonblank remaining geometry after deletion, and baseline restoration after Undo.
- [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39694622555), code/test commit `e45541b15da34f2627979b9ce6fda5f4f6f6016f`: **182 passed on Ubuntu 22.04 and 182 on Ubuntu 24.04**, Python 3.12.15 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Forty-four upstream VTK/NumPy deprecation warnings per job; no render checks skipped.
- Existing adaptive curves, snapping, visibility/solid occlusion, camera alignment/Previous View, mouse gestures, numeric precision, files and Undo/Redo regressions pass. New rendered checks verify both orange-selected circles, their removal with a visible remaining line, and restored baseline pixels after Undo.

Ready for physical cursor-entry, context-menu and deletion acceptance. Separate End A/End B radii remain deferred. No extrusion implemented.

## v0.0.9 follow-up — accessible live dimensions

Physical feedback: PR #9 works except the dimension popup did not present a discoverable way to enter values. Code inspection confirms that the field was hidden until a numeric viewport key and the popup ignored all mouse input; it also only refreshed numeric previews on Tab/Enter. A keyboard-focus check on the original code passed locally after activating the window, so focus loss is not claimed as the reproduced root cause.

The follow-up exposes a clickable field, Tab activation and live valid-value previews, with explicit construction focus, stage-anchored popup position and direction preservation during editing. Active editing is independent of field visibility so mouse-only releases still work. New tests use actual QApplication focus routing after selecting a toolbar tool, click-hit testing, Qt Tab traversal, live circle/rectangle previews before any document commit, release while typing and Escape cancellation.

Manual retest: choose Circle, press/drag outward, press Tab before releasing, and type a radius. Confirm the preview updates as each valid number is entered; release the mouse and press Enter to commit. Repeat by typing directly without Tab. Start a Line, click the visible dimension field, type a length and Escape; no line should be committed. Test rectangle Width/Tab/Depth and Shift-slot radius/distance, mouse-only placement and camera gestures. Local OpenGL remains unavailable; full rendered validation requires Xvfb/Mesa CI.

### Verified follow-up results

- Local non-render suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -k 'not render and not visible_solids'`: **171 passed, 15 deselected**. Final focus-specific rerun after first-key preview refinement: **4 passed**. Compileall and whitespace checks passed. The visible editor was visually inspected with contrasting text and a clear input border.
- [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39696438576), code/test commit `36416e003748c16a4478b9201a29147e78f2f6c9`: **186 passed on Ubuntu 22.04 and 186 on Ubuntu 24.04**, Python 3.12.15 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Forty-four upstream VTK/NumPy deprecation warnings per job; no render checks skipped.
- New actual-focus, Tab, click access and live preview tests pass alongside mouse-only construction, Shift gestures, snapping, rendering/occlusion, camera alignment, deletion/history and persistence regressions.

Ready for physical input acceptance using the steps above. No document format or modeling-operation changes.

## Dimension popup offset and opacity

Move the stage-anchored popup an additional 80 logical pixels right and 50 down (total 98/68 from the anchor), retaining viewport clamping. View → Dimension popup opacity provides a session-only 0–100% slider for the whole widget through QGraphicsOpacityEffect. Zero hides the popup and disables activation of its hidden input; turning it off while editing releases keyboard focus and restores mouse placement. Geometry, file format and construction state remain unchanged by the preference.

Local targeted checks: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_dimension_focus.py -q`: **6 passed**. New coverage checks offset, viewport clamping, 50% effect opacity, zero visibility across pointer updates and new placements, restored visibility, unchanged document state while adjusting opacity, and hiding during active input without blocking mouse release. Existing actual-focus/click/Tab/live-preview tests also pass. Local OpenGL is unavailable; full Xvfb/Mesa CI remains required.

Manual retest: start a sketch shape and open View → Dimension popup opacity. Try 100%, 50% and Off over the CAD viewport, then restore. Confirm the box is farther out of the way, translucent at intermediate values, and absent/click-through at zero; try mouse placement while off and numeric input after restoration. Check near all viewport edges and on the physical display's scaling setting.

Verified [full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39701080911), code/test commit `7c0a9a31e1c33386e8323e44e701007a22ef0102`: **188 passed on Ubuntu 22.04 and 188 on Ubuntu 24.04**, including all existing rendered checks, using Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Forty-four upstream VTK/NumPy warnings per job; no render checks skipped. Compileall and whitespace checks pass. Physical popup translucency and display scaling remain the manual checks above.

## Radius/diameter construction entry

Add paired Radius and Diameter inputs to circle and Shift-slot radius stages. Tab/Shift+Tab switches representations, including before any value is entered; entered sizes convert exactly through the existing radius parameter, with the converted input selected for replacement. Both sizes appear in the live readout and share one lock. Slots retain their separate center-distance stage. Stored geometry, numeric precision and file schema are unchanged.

Targeted focus tests cover circle and slot diameter placement on XY/XZ/YZ, live preview before document commit, empty-field Tab switching, bidirectional conversion, exact stored half-diameter, and unchanged slot center-distance entry. Manual check: drag a circle, Tab to focus Radius, Tab again for Diameter, enter a size, toggle back/forward and Enter. Repeat with Shift-slot; check invalid/zero/negative input and Escape, then opacity Off/restore. Local OpenGL is unavailable; full Xvfb/Mesa CI is required.

Verified results: local `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_dimension_focus.py -q`: **12 passed**. Compileall and whitespace checks passed. [Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39702642746), code/test commit `eddd67c66365255a9f7df44640fd54cc2530e40f`: **194 passed on Ubuntu 22.04 and 194 on Ubuntu 24.04**, including all rendered checks with Xvfb/Mesa. Fresh pinned installation and pip check passed. Forty-four upstream VTK/NumPy warnings per job; no render checks skipped. Ready for physical Tab/diameter acceptance using the steps above.

## PR #13 — v0.0.10 profile regions and extrusion

User accepted the sketch usability passes and requested reliable first extrusion with click-inside material selection, holes where safe, stable references and no automatic PR #14. The uploaded screenshot was unavailable at its supplied path; implementation and validation use the written requirements and generated mechanical fixtures.

The implementation supports analytic Rectangle/Circle/Slot boundaries, strict nesting and immediate holes, with islands as separate regions. Touching/crossing/coincident boundaries invalidate affected regions and ancestors/descendants; isolated regions elsewhere remain eligible. Any sketch containing Lines is explicitly rejected for extrusion because arbitrary line-chain closure/splitting is deferred. Analysis is capped at 256 closed entities. No Join/Cut, taper, face-attached sketch, arbitrary overlapping-region construction or drag-depth preview is implemented. New bodies remain independent of the initial box, which is session-hidden after creation/open and can be restored from View.

Local checks so far: full non-render suite **217 passed, 16 deselected** before the final rotated multi-hole and model-view/Open regressions. Final kernel/extrusion/document checks **57 passed**. Final extrusion UI checks **6 passed, 1 deselected**. Compileall and whitespace checks passed. Local OpenGL is unavailable, so rendered tests require Ubuntu Xvfb/Mesa CI.

Coverage includes exact analytic volume, kernel validity and normal-axis bounds for rectangle/circle/slot prisms in both directions on XY/XZ/YZ; circle/slot/rectangle holes and rotated outer boundaries; even/odd islands; overlapping/touching/duplicate rejection; isolated-region survival; stable source IDs under dimensional edits and entity reordering; atomic failure if holes/nesting change; reference-protected deletion; distance edits, Undo/Redo, save/load and malformed v4 rejection. UI checks exercise interior and hole clicks independently of edge selection, context Extrude, cancelled/zero distance, source-edit regeneration, model-view picking, hidden base box on reopen, active-mode clearing, Shift-right pan conflicts and extrusion deletion. New rendered checks require visible selected material, nonblank shaded plate pixels, background visible through the hole and solid material beside it.

Manual acceptance: draw an isolated rectangle, choose Select Profile, click inside it and Extrude…; enter +5 then edit the feature to −5. Repeat circles and Shift-slots on XY/XZ/YZ. Draw a rectangular plate with an interior circle/slot, click the plate material and extrude; orbit and look through each hole. Click inside a hole and confirm no parent region is selected. Edit outer width and hole radius in the source sketch; check regenerated part dimensions and depth, Save/close/reopen and Undo/Redo. Try overlapping/tangent loops and a Line-containing sketch: they must produce feedback and no unintended solid. Delete a referenced boundary/sketch and check dependency feedback; delete the extrusion first to allow source changes. Restore the demo box via View and confirm separate-body behavior. Verify opacity/Tab dimensions and existing camera gestures still work physically.

### Verified PR #13 results

- [Final full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39712089326), code/test commit `fd4c1865cdc54fc7eeb954a63453eccca962a293`: **235 passed on Ubuntu 22.04 and 235 on Ubuntu 24.04**, Python 3.12.15 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Forty-six upstream VTK/NumPy deprecation warnings per job; no render checks skipped.
- Render verification detects the selected material fill, a nonblank shaded plate and viewport background through its circular hole, with material visible beside it. All prior rendering, curve precision, snapping, deletion, dimension entry and camera regressions pass. Undo of last-extrusion deletion restores a visible part by hiding the demo box again.
- Local kernel/document checks: **57 passed**; successful final extrusion UI run: **6 passed, 1 deselected**. Two other local Qt-offscreen reruns aborted in `GetRenderWindow().Render()` while selecting the translucent region; this environment lacks working OpenGL. Those aborts are recorded rather than treated as render validation. Both final proper-GL Ubuntu jobs pass, including the affected event paths and Undo visibility fix. Compileall and whitespace checks passed.

Ready for physical extrusion/profile acceptance using the instructions above. PR #14 has not been started. Separate-body/line-chain/overlap limits remain as documented; no boolean operations were added.

## PR #13 rendering follow-up — empty sketch obstruction

Reported: occasional grey/obstructed sketch view, recovered by navigation; choosing a tool and clicking could restore grid dominance. The original scene has not been supplied. Reproduced a concrete clipping defect with a radius-0.02 mm circle extruded 0.01 mm, Fit, then entering an empty YZ sketch. The old range was 0.0581649475–0.1777228839 mm; the new eye was 10 mm from its plane. With no visible model/preview bounds, clipping returned early and projected the origin to depth 83.1549569. Choosing Line and pressing at the origin retained the stale range. This confirms one consistent failure path, not every possible reported visual artifact.

Fix: active-plane viewport footprint contributes only clipping bounds, including with grid hidden. Active-edit rendering refreshes clipping before drawing so first clicks, previews and direct camera movement cannot retain a stale range. No new depth offsets, globally disabled depth tests, geometry changes or next-feature work.

Local targeted command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_sketch_clipping_followup.py -q -k 'not render'`: **6 passed, 2 deselected** before restricting the pre-render callback to active editing. New tests cover all planes with grid visible/hidden, empty-plane depth before/after tool selection and first click, hidden solids, preview/cancel, stale-range repair on render, preserved camera projection/scale, visible grid pixels and a visible completed curve over the grid. Full proper-GL CI is required; local OpenGL is unavailable.

Manual retest: Fit a small extrusion, start an empty sketch on each origin plane, select Line/Circle and click, hover, release and Escape. Try grid on/off, orbit/pan, zoom/Fit and reenter. Existing curves should remain visible while editing; real solids should still occlude source geometry after Finish. If the original grey region persists, record its screenshot and .starcad document/steps so the remaining failure can be isolated.

Verified [branch push CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39714267018), code/test commit `237b450abfbd861e9a2ffd5c6ae808f1b7de1405`: **243 passed on Ubuntu 22.04 and 243 on Ubuntu 24.04**, Python 3.12.15 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed. Forty-nine upstream VTK/NumPy deprecation warnings per job; no rendered checks skipped. New pixel checks confirm an empty grid is visible immediately and a completed curve remains visible over it. Existing real-solid occlusion, Previous View snapshots, sketch tools, snapping, dimensions and extrusion regressions pass. Compileall and whitespace checks passed.

## PR #14 — sketch rendering fixes

The user explicitly authorized a regular PR limited to the clipping follow-up above and immediate deletion redraw. Refresh previously rendered the solid before replacing sketch meshes, then left the previous frame onscreen until another event. Refresh now renders after all scene changes (Fit already renders at that point). The existing multi-selection deletion pixel test now disables capture-triggered rendering and checks immediate deletion, Undo and Redo frames.

Manual deletion check: delete one entity, several entities, the last entity and an entire unreferenced sketch from viewport/browser. Each should disappear immediately without clicking or moving the camera; Undo/Redo should immediately restore/remove it. Check preview/selection clearing and save/reopen. No feature or document-format changes.

Verified PR #14 [full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39715245562), code/test commit `228250b98d7dbf967781a494587459ea2cc02696`: **243 passed on Ubuntu 22.04 and 243 on Ubuntu 24.04**, Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check passed; 50 upstream VTK/NumPy warnings per job. Immediate deletion/Undo/Redo frame capture disables implicit rerendering. Local clipping checks: 6 passed, 2 deselected; compileall and whitespace checks passed. Initial CI collection failed because a transferred test file was truncated; the corrected remote tree was verified byte-for-byte against the local checkout before this successful run.

## PR #15 — v0.0.11 planar face sketches

Scope: supported analytic solid faces, semantic references, parametric local frames, UI workflow and v5 persistence. No booleans/cuts, projection, curved sketches or new primitives.

Local `.venv/bin/python -m pytest tests/test_document.py tests/test_sketch.py tests/test_extrusion.py tests/test_face_attachments.py -q`: **104 passed**. Initial Qt-offscreen UI run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_face_attachment_ui.py -q -k 'not render'`: **10 passed, 1 deselected** before the final world-up presentation adjustment. Qt-offscreen reports unavailable OpenGL shaders; this is event/document validation only, not rendered acceptance. Compileall and whitespace checks pass. Full Ubuntu 22.04/24.04 Xvfb/Mesa suite is pending.

New kernel checks cover six box faces, signed Start/End caps in XY/XZ/YZ, all Rectangle/Slot planar sides, hole-wall identity under entity reordering, local/world transforms and plane coincidence, box/source/distance edits, compound-angle located fixtures, downstream extrusion validity/volume, Undo/Redo, v5 save/reopen, malformed frames/cyclic dependencies, nonplanar/unknown rejection and unresolved reference preservation/suppression/recovery. UI checks cover right-click picking in edge-filter mode, exact circle and Shift-slot entry, browser/properties, camera normals/projection, reentry, Undo/Redo, unresolved feedback and moved-frame display cache/pixels.

Physical acceptance:
1. Right-click the box top → New Sketch; draw a circle with exact radius, Finish, change box height. Reenter and confirm circle remains on top with unchanged radius/local center; Save/Open and Undo/Redo.
2. Rectangle → Extrude 10; New Sketch on End Face → Shift-slot; Finish, change depth to 20. Slot must follow the cap with identical local radius/center distance. Repeat Start Face and negative depth on XY/XZ/YZ.
3. Create a sketch on each rectangle planar side and a slot's straight side, including a rectangular hole wall. Edit source angle/width/radius and check consistent attachment. Curved walls must report rejection.
4. Confirm grid/origin/center snapping, exact dimensions and Shift construction, pan and Look At Face remain functional. Right-clicking an already-selected face retains its batch.
5. Automated compound-angle fixture checks exact analytic coincidence and perpendicular orthographic camera, with no product transform/import operation.
6. Lost-side fixture (primitive replaced with same UUID) must show UNRESOLVED, retain local geometry, suppress dependent extrusion and recover on Undo or restoring the boundary. No substitute face or silently stale solid.

Limits: named sides cover Rectangle parameter edges and Slot straight tangents only. Reassign Sketch Plane is deferred; restore the supported parent or remove dependent features explicitly. Legacy topology-change rejection for existing material-region holes remains unchanged. No PR #16 work.

### Verified PR #15 results

[Final full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39717778223), code/test commit `ff5a91cb87854c67b2620751995777db4c894ba5`: **285 passed on Ubuntu 22.04 and 285 on Ubuntu 24.04**, Python 3.12 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check pass. Fifty-four upstream VTK/NumPy warnings per job; no render checks skipped. Local final kernel/document command above: **105 passed** after adding the signed-depth reversal regression. Compileall, whitespace checks and remote/local source comparison pass.

New rendered checks confirm a finished attached curve is visible on its host face, a bottom-face curve remains hidden behind the solid, and moving a parent updates cached display coordinates and visible pixels. The initial full run exposed two existing model-selection tests reaching a stale ('sketch', None) browser key; the new properties display made that invalid key observable. Deselecting in model view now returns to a valid box browser entry. Both existing tests and the full final suite pass. Cap frames retain their initial normal sense through signed-depth reversal, preventing local-coordinate mirroring; v5 roundtrip covers that state.

Ready for the physical Box/Extrusion acceptance steps above. Compound-angle behavior is verified with located OCCT fixtures; the product still adds no transform/import operation. Reassign-plane and unsupported curved/unknown faces remain explicitly deferred. PR #16 has not been started.

## Sketch visibility usability follow-up — Settings and reference geometry

User's supplied plate/cylinder screenshot illustrates placing a new cylinder off the plate after the plate disappeared during face-sketch editing. The screenshot was available locally and inspected. This pass is limited to always-available base-box visibility and visible placement context for face sketches.

Local event/document checks: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_sketch_reference_visibility.py -q -k 'not render'`: **4 passed, 2 deselected**, before adding active-sketch identity to the highlight cache key. Compileall and whitespace checks pass. Local Qt-offscreen has shader errors and does not validate rendering; full Ubuntu 22.04/24.04 Xvfb/Mesa tests are pending.

New regressions cover hiding the only box, empty display/picking, session preference across refresh/history/New, unchanged document/history and file geometry, preservation of pending numeric fields and in-progress circle placement, translucent solid/reference-sketch visibility, active-sketch-only viewport picking, reentry/Finish opacity and isolated origin sketches. Pixel checks require visible plate context, grid and curves during face sketching, plus empty/restore frames for the base-box toggle.

Manual acceptance: Settings → Show base box off/on before any extrusion; repeat while drawing and with pending numeric edits. Enter a new sketch on an extrusion End Face and verify plate outline, hole outlines, other sketch curves and grid remain visible. Position a circle inside the plate, Finish and extrude. Reenter, Undo/Redo and reopen; reference context should stay available. Try clicking source curves while editing: viewport picks only active entities. Finish restores opaque solids. Hidden base geometry and all attachments remain in the saved document. Visibility preferences are session-only. No new modeling operation.

### Verified PR #16 results

[Final full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39719969443), code/test commit `927575e7449105e6861762809efd2716e7ab823a`: **291 passed on Ubuntu 22.04 and 291 on Ubuntu 24.04**, Python 3.12 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check pass. Sixty-two upstream VTK/NumPy warnings per job; no render checks skipped. Compileall, whitespace and remote/local source comparisons pass.

The first rendered run found no untinted cyan pixels from the source rectangle: opaque foreground edges/grid can cover coincident curves on deeper source planes, while translucent layers also change the apparent curve color. Face-edit solid edges now share 35% opacity and its grid uses 40% opacity; Finish/origin editing restores ordinary opacity. The regression compares rendered frames with/without source curves to require an actual visible contribution rather than a particular untinted color. It also verifies grid contribution, visible plate context, active curves, empty hidden-box output and restored nonblank geometry. Full final render and existing model-occlusion tests pass.

Ready for physical retest using the supplied plate/cylinder workflow above. This PR contains only the requested Settings/base-box control and face-sketch placement visibility; no new geometry operation or document-format change.

## PR #17 — v0.0.12 Boolean operations, cut extrusion and display modes

Authorized by the attached PR #17 specification; stop after this PR. No PR #18 work.

Local kernel/document command: `.venv/bin/python -m pytest tests/test_booleans.py tests/test_document.py tests/test_extrusion.py tests/test_face_attachments.py -q`: **109 passed**. Covers exact box/box and box/cylinder mass/bounds/validity, connected-chain Join order, disjoint/touching rejection, atomic invalid creation, retained failed operation/recovery, signed New Body, blind and Through All cuts on all origin planes/both extrusion signs, target thickness/source edits, unrelated bodies, dependencies, invalidated prism-face references, history and v6/legacy persistence. Compileall and whitespace pass.

A local Qt-offscreen legacy extrusion UI run aborted in VTK rendering; this environment lacks working OpenGL, so no UI/render acceptance is claimed from that run. Full Ubuntu 22.04/24.04 Xvfb/Mesa suite pending. New UI tests cover explicit Combine target/tool context, preview Cancel/Apply, cut mode/extent editing, four display modes, W/S/P suppression, topology selection and nonblank result previews. Existing extrusion tests now exercise explicit Preview/Apply rather than the retired immediate distance dialog.

Manual desktop acceptance:
1. Select intersecting current plate/cylinder features → Combine → Join → Preview → Apply. Join the result with a third intersecting cylinder; edit an upstream radius/depth and verify regeneration. Source definitions must remain historical, while only current results display.
2. New Sketch on box/ordinary extrusion top → circle → Extrude → Cut. Select the intended target. Use signed depth −5 mm for an outward top normal; Preview, inspect, Apply; Edit Operation and change to −8 mm. Positive depth points outward and must not silently become a cut.
3. Change extent to Through All, choose the direction entering the target, Preview and Apply. Change target thickness; the hole must remain through. Repeat opposite sweep signs and XY/XZ/YZ. A negative New Body must remain a separate prism.
4. Preview invalid/disjoint/touching or fully removing/splitting cuts: explanatory error, Apply disabled, Cancel leaves document/history untouched. Pan/orbit/zoom during valid preview. Multiple bodies require an explicit target; unrelated bodies remain unchanged.
5. Edit a source to remove overlap: existing operation retains parameters, reports unresolved, generates no stale body and recovers on Undo/restoring overlap. Save/Open and Undo/Redo the full operation chain.
6. View → Display Mode: all four modes; real CAD edges in CAD Wireframe versus triangulation in Mesh Debug. Test face/edge mixed selection, hitbox, navigation, Look At Face, Previous View and W/S/P. Numeric-entry focus must retain typing behavior. Regeneration must retain selected mode.
7. New sketches on Boolean results are explicitly unavailable (no semantic output-face naming). Existing sketches keep their named historical parent; changing a prism feature to a Boolean operation must mark old cap/side attachments unresolved without replacing geometry.

Conservative limits: one connected solid per result; positive-volume overlap required (touching-only Join rejected); at most 31 Combine tools; synchronous preview; original Combine membership retained when editing (recreate to change membership). Through All is one-directional from the sketch plane and obeys extrusion coordinate/depth limits. No fillets/chamfers, direct face Push/Pull, STEP export, patterns, projection or constraints.

### Verified PR #17 results

[Final full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/39723886693), code/test commit `bd43be4fdceb4293639b1632dc2a9f4718707040`: **320 passed on Ubuntu 22.04 and 320 on Ubuntu 24.04**, Python 3.12 with Xvfb/Mesa software OpenGL. Fresh pinned installation and pip check pass. Sixty-seven upstream warnings per job; no render checks skipped. Local kernel/document suite: **109 passed**. Compileall, whitespace and remote/local source comparisons pass.

The initial full run exposed a redundant direction=-1 state in signed-distance New Body extrusions that v4 files correctly defaulted to +1. Signed-distance mode now canonicalizes that unused field, retaining exact geometry and legacy feature equality on reopen; Through All retains its explicit direction. UI regressions were corrected to reproject pick coordinates rather than reuse VTK renderer scratch state, inspect the operation panel's validation message after Cancel, and recognize the new current-body browser label. The final full suite passes all existing extrusion/save-reopen checks and all new operation/mode tests.

New rendered checks require nonblank output in every display mode, a visible difference between genuine CAD wireframe and mesh triangulation, and visible orange candidate geometry. Context/preview tests confirm target/tool selection, no document mutation before Apply, Cancel restoration, one committed operation, historical input labels, Undo/Redo, blind-to-Through-All editing and changed target thickness. Existing camera, face attachment, curve precision, snapping, live dimensions, deletion, grid and reference visibility regressions pass.

Ready for physical bracket-Join, through-hole and blind-pocket acceptance using the steps above; no user .starcad bracket file was supplied, so its exact geometry is a manual check. Boolean-result face attachments, touching-only/split-result operations, Combine membership editing and asynchronous preview remain limited as documented. PR #18 has not been started.

## PR #18 — HERO-CAD rebrand and repository migration preparation

Merged PR #17 was cloned after workspace maintenance removed the prior transient checkout. Rename targets the application/UI strings, Python distribution, console command, import package, current documentation, metadata and workflow install label. No repository settings or logo assets are changed; version remains 0.0.12 and .starcad format/schema stay unchanged.

A fresh Python 3.12 venv installed the pinned requirements, then the new editable distribution via .venv/bin/python -m pip install --no-deps -e .; installation succeeded as hero-cad-0.0.12. .venv/bin/python -m pip check: no broken requirements.

Before renaming, six document fixtures were written/validated with the unchanged star_cad package at commit 7b39cdf23731ed63f9a929b3674d56b43140b5e0. They cover v1 box, v2 line/rectangle, v3 curves, v4 holed extrusion, v5 face-attached slot/prism and v6 Boolean/Through All cuts. File hashes and kernel volume/body counts are committed with their provenance.

Local targeted command: .venv/bin/python -m pytest tests/test_rebranding.py -q -k 'pre_rename or installed_package': **7 passed, 3 deselected**. The tests verify installed entry-point metadata, unchanged source fixture bytes, all schema versions, regeneration, Undo/Redo, save/reopen and identical v3–v6 JSON. New GUI tests check HERO-CAD titles/file filters and run both the actual hero-cad executable and python -m hero_cad from outside the checkout, using test-only event-loop inspection/automatic exit. No production smoke-test hook was added.

Full Ubuntu 22.04/24.04 Xvfb/Mesa suite and real GUI launcher checks are pending. Local Qt offscreen is not render acceptance. Compileall, whitespace and stale-import audit are required before review.

Manual acceptance: use MIGRATION.md to replace the old editable distribution; run hero-cad and python -m hero_cad, confirm HERO-CAD title/name, open an existing sketch/face-attachment/extrusion/Boolean .starcad file, edit and regenerate, Undo/Redo and Save/reopen. Verify installation scripts/desktop shortcuts use the new command; there is no bundled desktop entry. The repository remains TAM-Hiding/star-cad for this PR; owner rename and final logo integration are explicitly separate post-merge actions. No subsequent feature work.

### Verified PR #18 results

[Full Ubuntu CI](https://github.com/TAM-Hiding/star-cad/actions/runs/40130793626), code/test commit 926429f859672ac29061ad99723d28f71cd5b4e0: **330 passed on Ubuntu 22.04 and 330 on Ubuntu 24.04**, Python 3.12 with Xvfb/Mesa software OpenGL. Clean editable installation and pip check pass. Sixty-seven upstream warnings per job; no render checks skipped.

The actual installed hero-cad command and python -m hero_cad both launch successfully from outside the checkout. Test-only event-loop inspection confirms the visible HERO-CAD main window, Qt application/display names and existing version; each process exits normally. No production test hook or CLI flag was added. File dialogs retain .starcad filters under the new brand.

The immutable pre-rename v1–v6 fixtures load, regenerate, preserve source bytes, survive Undo/Redo and save/reopen, and retain identical v3–v6 JSON content. All existing sketch, extrusion, face attachment, Boolean, precision, camera, keyboard/display-mode, file and rendered regressions pass with hero_cad imports. An AST audit rejects stale old-package imports in source/tests; the serialized star-cad marker, migration examples and historical validation commands/URLs are intentional exceptions.

Local clean install: hero-cad-0.0.12; pip check reports no broken requirements. Local core/kernel suite: **140 passed**; targeted installed-package/legacy-fixture checks: **7 passed, 3 deselected**. Compileall, whitespace and remote/local source comparisons pass.

MIGRATION.md contains the existing-install upgrade instructions and owner-only post-merge repository rename checklist. The remote remains https://github.com/TAM-Hiding/star-cad.git. No repository rename/settings change, logo asset, visual-layout change, dependency upgrade or subsequent feature work was performed. The owner still needs to carry out the post-merge GitHub rename and check Actions in the renamed repository.


## PR #19 — sketch visibility and evaluated planar faces

Baseline: merged PR #18, main 27705f4f7ab330bc9a65bba4d8a6a713ca9e7979.
Dedicated branch: sketch-face-reliability in TAM-Hiding/hero-cad.

Root causes confirmed in source and reproduced by regression models:

- Origin sketches explicitly hid solids; attachment-only display gates also hid other sketch references and kept the grid opaque.
- Profile picking treated reference solids as opaque occluders even while editing the active sketch.
- Boolean regeneration deliberately discarded face maps. Global face lookup also searched consumed historical bodies rather than only displayed current results.
- No permanent face-occupied state exists. Unsupported Boolean faces prevented sequential face sketches after cuts; finished curves could additionally hide the underlying face's New Sketch action.

Fixes unify translucent sketch context (35% bodies, 40% grid), preserve active entity/profile picking through bodies, strengthen active profile highlighting, propagate OCCT Boolean face ancestry, publish unique planar ancestry/adjacency identities and scope new selections to active evaluated results. Historical attachment resolution stays at the referenced feature's ordered output. Ambiguous/lost identities remain unresolved with parameters retained and downstream geometry suppressed. See ARCHITECTURE.md for the naming algorithm/limits and SKETCH_FACE_TESTING.md for physical desktop instructions.

Environment: Ubuntu 24.04.3 x86-64, CPython 3.12.14, unchanged requirements-dev.lock pins, clean .venv-pr19 editable installation. The runner could not install apt packages into its system cache, so apt-downloaded Xvfb/X11 libraries were extracted under /tmp/hero-pr19-x11 and used without changing project dependencies. Xvfb ran in the same shell over local TCP because the runner's UNIX socket setup was unavailable:

```bash
LD_LIBRARY_PATH=/tmp/hero-pr19-x11/usr/lib/x86_64-linux-gnu /tmp/hero-pr19-x11/usr/bin/Xvfb :110 -screen 0 1600x1000x24 -ac -nolisten unix -listen tcp
# In the same test shell after Xvfb is ready:
DISPLAY=localhost:110 LD_LIBRARY_PATH=/tmp/hero-pr19-x11/usr/lib/x86_64-linux-gnu LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb .venv-pr19/bin/python -m pytest -q
```

Final complete suite: **358 passed, 79 upstream VTK/NumPy deprecation warnings in 84.47 seconds**, with no skips. This includes real Qt/VTK render checks (body/curve/profile/grid/snap pixel contributions and nonblank output), actual console/module subprocess launches, existing gesture conflicts, v1–v6 fixture hashes/unchanged serialization, all existing modeling operations, persistence and Undo/Redo.

Additional checks:

- `.venv-pr19/bin/python -m pytest tests/test_document.py -q`: **23 passed**.
- `.venv-pr19/bin/python -m pytest tests/test_evaluated_faces.py -q`: **22 passed**.
- `.venv-pr19/bin/python -m pip check`: **No broken requirements found**.
- `.venv-pr19/bin/python -m compileall -q src tests` and `git diff --check`: passed.

The 28 new kernel/UI cases cover XY/XZ/YZ body context, rectangle/Slot screwdriver cuts, separate Combine Cut and operation extrusion, both split coplanar top regions plus the floor, repeated same-face sketches, successive plate-hole cuts, every planar face in representative Cut/Join/Intersect models, ordinary dimension/depth changes, arbitrary compound-angle Boolean faces, history-order binding, face-order independence, ambiguity refusal, unresolved downstream suppression/recovery, v7 save/reload and sketch reentry. Existing render/visibility expectations were updated for the deliberately visible translucent context. The complete suite caught active-profile occlusion and weak orange highlighting; both were corrected before the final clean run.

Ubuntu 22.04 is not locally tested for this PR; the unchanged GitHub Actions matrix will run on Ubuntu 22.04 and 24.04 after publication. No physical desktop testing is claimed. Owner desktop checks remain in SKETCH_FACE_TESTING.md. The .starcad suffix and star-cad marker remain unchanged; only documents with evaluated-face references require v7. No geometry operations, new tools, document extension or major UI layout changes are introduced. Stop after opening PR #19; do not merge automatically.


## PR #20 — closed line profiles, dual-color X-Ray and display refinement

Baseline: PR #19 merged at main 65c6ff6a6a549dee2e90813da78a3893078a3807,
with the user's successful laptop test reported. Branch: closed-profiles-xray.
No changes to dependencies, major UI layout, exact modeling precision or file extension.

Implementation findings/results:

- The prior profile classifier explicitly rejected any source sketch containing a Line. It now builds simple endpoint-graph cycles, with UUIDv5 keys derived from sorted line membership, and passes their exact wires into the existing hole classifier/prism/preview/Boolean path.
- The documented endpoint tolerance is absolute 1e-7 mm, matching existing kernel/region tolerance and independent of zoom. Stored endpoints/source edge curves are not moved. Chained tolerance clusters with excessive diameter, crossings, overlaps, duplicates and branch networks reject profile analysis. Open chains stay unfilled; independent remote open chains no longer disable valid closed profiles. The existing 256-entity bound includes lines.
- V8 stores referenced line_ids for exact membership validation and deletion protection. Existing v1–v7 files and primitive-only serialization remain supported. A line vertex can be edited one endpoint at a time: accepted line extrusions become unresolved without stale output until original members close again. Save/reload and Undo/Redo retain this state and recovery. Existing primitive-only topology rejection stays unchanged.
- X-Ray Off/Celadon/Orange synchronizes toolbar and View menu. Explicit 85% opacity overrides automatic 35% sketch context, with Off restoring prior behavior. Separate preview/sketch/guide actors retain their styles; a brighter warm selection distinguishes Orange bodies. Modes are session state, not geometry or serialized data. No opacity slider.
- Solid rendering previously used 0.1 mm / 0.2 rad meshing with no point normals. Implemented 0.02 mm / 0.08 rad, circular CAD-edge sampling respecting the angular target, and oriented/located analytic UV normals. Separate per-face vertices preserve sharp corners. Exact B-reps/volume and selection IDs remain unchanged, and ordinary camera/X-Ray changes reuse meshes. Undefined normals on unsupported exotic singular surfaces retain mapper fallback. No screen-adaptive solid remeshing or geometry operations are added.

Automated environment: Ubuntu 24.04.3 x86-64, CPython 3.12.14, existing editable .venv-pr19 with unchanged requirements-dev.lock. Same extracted Xvfb/X11 libraries as PR #19; the actual test run used Qt XCB and Mesa software OpenGL. Xvfb and tests ran in one shell over local TCP (UNIX socket setup is unavailable in this runner):

```bash
LD_LIBRARY_PATH=/tmp/hero-pr19-x11/usr/lib/x86_64-linux-gnu /tmp/hero-pr19-x11/usr/bin/Xvfb :122 -screen 0 1600x1000x24 -ac -nolisten unix -listen tcp
# In the same shell, after Xvfb becomes ready:
DISPLAY=localhost:122 LD_LIBRARY_PATH=/tmp/hero-pr19-x11/usr/lib/x86_64-linux-gnu LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb .venv-pr19/bin/python -m pytest -q
```

**Full suite: 415 passed, no skips, 85 upstream VTK/NumPy deprecation warnings in 94.15 seconds.**

Targeted new tests: tests/test_line_profiles.py + tests/test_surface_display.py: **48 passed**. tests/test_profiles_xray_ui.py under Xvfb/Mesa: **9 passed**. The 57 new cases cover triangles/trapezoids/concave polygons/dovetails, XY/XZ/YZ and signed distances, independent loops/open chains, endpoint tolerance without source mutation, rejected arrangements, primitive/line holes, New Body/Join/Cut/Intersect and directional Through All, exact kernel volume/validity, stable membership/order/direction, v8 persistence, temporary open-loop recovery/downstream suppression, line-side attachments and deletion protection. UI tests draw the principal dovetail with normal Line clicks and grid snapping, Finish, click its interior, Preview/Apply New Body or a Cut through the block, Undo/Redo and reopen. Further tests exercise numeric vertex editing, X-Ray/menu synchronization, selection/preview pixel differences, style isolation and zero remeshing during camera/X-Ray changes. Small-radius normals, refined triangle counts, located curves and sharp corner normals are checked directly. Existing tests cover all prior workflows, v1–v6 fixture hashes/serialization and v7 face attachments, launcher subprocesses and mouse gestures.

Final targeted document + line-profile + surface-display run: **71 passed**. Invalid/missing extrusion sources retain their existing FeatureError transaction contract, with an additional regression case. Pip check: **No broken requirements found**. Compileall and git diff --check pass. Standard desktop commands remain in README.md; detailed physical checks and remaining profile limits are in PROFILE_TESTING.md. Ubuntu 22.04 is not locally tested in this PR; the unchanged Actions matrix runs Ubuntu 22.04/24.04 after publication. No physical laptop/GPU results are claimed for PR #20. Stop after opening PR #20; do not merge automatically or begin subsequent features.


## PR #21 — floating tool island and shared Qt command catalogue

Baseline: merged PR #20 at main 57390818139da48afc2b36b2aed31c5d399f40df;
user reported the program/laptop test looked good. Branch: floating-tool-island.
No new modeling operations, document/schema changes or dependencies.

Implemented a viewport-owned dark QFrame overlay with header dragging,
Compact/Medium/Expanded sizes, one/two/three-column reflow, scrolling when
necessary, collapse/expand and View-menu visibility. Effective placement/size
clamp on viewport resize while requested placement/preset remain; a small
224×180 viewport minimum keeps a header/column usable. QSettings stores
layout in tool_island/v1, separately from document geometry and Undo.
Context updates preserve layout, collapse state and the active tool.

ui/commands.py catalogues stable IDs/context/disabled reasons around existing
QAction objects. Island QToolButtons use setDefaultAction on those same actions;
registration does not reconnect callbacks or copy shortcuts. The sketch toolbar
dropdown dispatches the same tool actions, with checks synchronized from the
existing ToolController. Slot is an explicit CircleTool slot-mode alias, using
its existing Shift-circle stages and dimensions. Existing menus/toolbars/keys
remain; relevant face/browser actions reuse the shared actions. Parameterized
curve-context callbacks and some file/property actions remain intentionally
outside the static catalogue. No plugin/scripting system or feature-engine
rewrite. A stale browser key during Undo/refresh was caught in the first UI
run and fixed with tolerant status lookup before the accepted full runs.

Environment: Ubuntu 24.04.3 x86-64, CPython 3.12.14, a new .venv-pr21 installed
from unchanged requirements-dev.lock followed by --no-deps -e . . Test windows
use isolated INI preferences; a fresh Python interpreter also verifies saved
layout values, avoiding dependence on Qt's in-process settings cache.

The runner lacks system-installed Xvfb/X11 dependencies and UNIX socket setup.
Apt-downloaded libraries/Xvfb were extracted under /tmp/hero-pr21-x11; Qt XCB
and Mesa software OpenGL supplied real rendering. Server and tests run in the
same shell, with the test command starting only after the server is reachable:

```bash
LD_LIBRARY_PATH=/tmp/hero-pr21-x11/usr/lib/x86_64-linux-gnu /tmp/hero-pr21-x11/usr/bin/Xvfb :134 -screen 0 1600x1000x24 -ac -nolisten unix -listen tcp
# Same shell, after Xvfb is ready:
DISPLAY=localhost:134 LD_LIBRARY_PATH=/tmp/hero-pr21-x11/usr/lib/x86_64-linux-gnu LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb .venv-pr21/bin/python -m pytest -q
```

**Final full suite: 434 passed, no skips, 85 upstream VTK/NumPy deprecation
warnings in 104.15 seconds.** The earlier full run before the small-window
safeguard also passed all 433 then-existing tests.

19 new island cases cover initial placement/visibility, preset reflow and
readable button dimensions, header dragging and bounds, unchanged camera/model
state, collapse/expand across contexts, real settings restoration (including a
fresh-process read), View-menu show/hide, viewport resize and smallest ordinary
window handling, malformed preferences, shared enabled/action/check state,
origin/planar-face sketch creation, curved-face rejection, Slot via existing
construction, active-tool stability, grid synchronization, one history step per
activation, profile/extrusion preview+commit and Combine dispatch, shortcut
activation counts, mouse/wheel consumption over the panel, actual outside-widget
face/edge picking and zoom, and layout/X-Ray retention across New/history.
Existing tests cover all geometry/persistence/undo/gesture/render workflows,
including PR #20's line-profile and X-Ray behavior and real launcher subprocesses.

Additional checks: sketch/construction/editing kernel tests **27 passed**;
compileall and git diff --check pass; pip check reports **No broken requirements
found**. Captured and visually inspected real Qt/VTK screenshots of Expanded,
Compact and Collapsed states; files are committed under docs/screenshots, with
screenshots, command-architecture limits and physical laptop instructions in
[docs/TOOL_ISLAND.md](docs/TOOL_ISLAND.md).

Ubuntu 22.04 is not locally tested for this PR; the unchanged Actions matrix
runs Ubuntu 22.04 and 24.04 after publication. No physical laptop/GPU testing
is claimed for PR #21. Stop after opening PR #21; do not merge automatically.

## PR #22 — Join, Undo recovery and grid appearance

Environment: Ubuntu 24.04.3 x86-64, Python 3.12.14, PySide6 6.8.3,
cadquery-ocp 7.9.3.1.1, VTK 9.6.2. Clean copied-interpreter `.venv-pr22`
installed from requirements-dev.lock followed by `pip install --no-deps -e .`.
No dependency/configuration/schema changes. Qt xcb with actual Xvfb TCP display,
1600×1000×24, Mesa software OpenGL. Local Ubuntu 22.04 and physical laptop
checks were not run; the existing GitHub Actions 22.04/24.04 matrix is retained.

Commands (Xvfb and pytest ran in the same shell; this environment requires a TCP
DISPLAY rather than UNIX sockets):

```
export LD_LIBRARY_PATH=/tmp/hero-pr22-x11/usr/lib/x86_64-linux-gnu
export DISPLAY=localhost:151 LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb
/tmp/hero-pr22-x11/usr/bin/Xvfb :151 -screen 0 1600x1000x24 -ac -nolisten unix -listen tcp &
.venv-pr22/bin/python -m pytest -q
.venv-pr22/bin/python -m pytest tests/test_booleans.py tests/test_document.py -q
.venv-pr22/bin/pip check
.venv-pr22/bin/python -m compileall -q src tests
git diff --check
```

Full suite: **449 passed**, 87 upstream VTK/NumPy deprecation warnings. A full
run before the final label contrast adjustment passed in 169.29 seconds; final
verification includes that adjustment. Kernel/document checks: **51 passed**.
`pip check`: no broken requirements; compileall and diff checks passed.
No skips. Render checks compare real pixels, including new local-coordinate
labels on a face-attached sketch and resizing. Actual running-app capture was
visually inspected; brighter labels with a subtle backing remain readable over
translucent bodies. Screenshots were review intermediates, not app assets.

New coverage: outward face-contact Join on extruded and multiply-cut targets,
positive-volume overlap, edge/point/disconnected rejection, valid B-rep/volume,
order-independent face-contact chains, upstream edits and save/reload; New Body
→ Undo → face picking → Cut, repeated history and construction cancellation;
preview cancellation and command state; all five grid colors, exact major/minor
intervals, nonoverlapping local labels, adaptive spacing, X-Ray fading, persisted
appearance, unchanged snapping on XY/XZ/YZ, face labels and resize.

A separate baseline extraction of merged main (7f357f5) confirmed:

```
clean New Body commit then Undo: profiles.active=False, action.checked=False
Select Profile then Undo:       profiles.active=True,  action.checked=True
Escape afterward:               profiles.active=True,  action.checked=True
```

Thus retained temporary profile routing is established; the clean accidental
New Body sequence alone was not a universal reproduction of the reported issue.
Earlier regression runs caught an overbroad tool reset during Undo (corrected to
retain a valid selected tool) and an old test expecting canceled profile routing
to stay active (updated to explicitly reselect for the next operation). Final
runs retain existing snapping/gesture/precision tests.

See docs/RELIABILITY_GRID.md for root causes, limits and desktop acceptance
instructions. Existing conservative topology-reference limitations remain;
substantial topology changes may unresolve attachments. Preview remains
synchronous. No Ubuntu 22.04 or physical laptop result is claimed here. Open
PR #22 for review and stop without merging or starting later feature work.

## PR #23 — persistent geometry references / ancestry foundation

Local environment: Ubuntu 24.04.3 x86-64, Python 3.12.14, PySide6 6.8.3,
cadquery-ocp 7.9.3.1.1, VTK 9.6.2. Fresh `.venv` created with copied Python
interpreter; requirements-dev.lock installed, then `pip install --no-deps -e .`.
Qt xcb, real Xvfb TCP display 1600×1000×24 and Mesa software OpenGL. Local
Ubuntu 22.04 and physical laptop acceptance were not run. Existing CI matrix
for Ubuntu 22.04/24.04 remains unchanged; no CI success is claimed here.

Commands (Xvfb and pytest in the same shell; TCP is required in this workspace):

```
export LD_LIBRARY_PATH=/tmp/hero-pr23-x11/usr/lib/x86_64-linux-gnu
export DISPLAY=localhost:166 LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb
/tmp/hero-pr23-x11/usr/bin/Xvfb :166 -screen 0 1600x1000x24 -ac -nolisten unix -listen tcp &
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_document.py tests/test_persistent_references.py -q
.venv/bin/python -m compileall -q src tests
.venv/bin/pip check
git diff --check
```

Results:

- **470 passed**, 87 upstream VTK/NumPy deprecation warnings, **123.13 seconds**,
  no skips. Final full run includes the contextual multi-selection witness test.
- Required document/new reference checks: **41 passed**, 2.71 seconds.
- Earlier full run: 469 passed / 125.06 seconds before the final context-batch
  refinement; focused final viewport tests: 3 passed / 3.58 seconds.
- `pip check`: no broken requirements; compileall and diff checks passed.
- No dependency, authoritative B-rep precision, new geometry tool or extension
  changes. V9 adds optional support metadata while legacy data stays readable.

Coverage includes stable semantic roots and ordinary size edits; source-local
frame transport; real one-to-two top-face splits with recorded common ancestry;
unique interior descendant recovery; ambiguous boundary / removed witness / lost
root / deleted supporting face; conservative merge refusal; shuffled OCCT
subshape traversal; New Body, Join/Cut/Intersect operation extrusions and Combine;
legacy exact-only v7 behavior plus existing v1–v8 regressions; metadata/UUID/frame
persistence; malformed metadata; Undo/Redo, blocked downstream features and
unrelated editing; atomic rejection without replacing reference caches; actual
left/right picks, sketch reentry, diagnostics and correct context target while
preserving a selected batch. Existing render checks use real OpenGL pixels and
continue passing; there is no new visual layout to approve.

Initial regression runs exposed expected schema-number changes (new enriched
references save v9), and old tests equating two entire references created by
separate pixel-rounded clicks. Tests now distinguish the stable current face
identity from the per-attachment witness while still requiring exact stored
metadata/feature equality across save/reload. Existing legacy serialization
fixtures remain unchanged. No existing geometry/gesture tests were removed.

See docs/PERSISTENT_REFERENCES.md for the prior architecture inventory, collection
through OCCT Modified/Generated/IsDeleted, source-local resolution rules, schema
compatibility, explicit limits and the desktop acceptance checklist. Persistent
edge naming, arbitrary ambiguous initial faces, unknown ancestry, sibling merges
and aggressive repair remain out of scope. A cached historical plane never
permits evaluation after support is missing. Open PR #23 for review, do not merge
automatically, and do not begin later feature work.

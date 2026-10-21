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

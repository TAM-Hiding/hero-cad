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

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

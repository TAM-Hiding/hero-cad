# STAR-CAD

Lightweight, Linux-native parametric mechanical CAD for STR-GZR OS. Fusion-inspired workflow, with a small, understandable toolset. No accounts, subscriptions, cloud requirements, or telemetry. AI-assisted modeling is a future capability; ordinary modeling must always work offline.

## v0.0.3 / viewport and selection

A Qt desktop shell with a 3D viewport, dockable model browser and properties panel. Starts with one Open CASCADE box. Edit width (X), depth (Y), and height (Z), then **Apply dimensions** to regenerate its solid. Dimensions are millimetres, entered to 0.001 mm, in the range 0.001–100000 mm. These are input limits, not a manufacturing accuracy guarantee. Geometry uses OCCT double-precision B-rep; the display mesh is not the model.

One document and one box, now with local **New, Open, Save, Save As, Undo and Redo**. No export, sketches, boolean tools, or feature timeline yet.

Documents use `.starcad` files: versioned, human-readable JSON in millimetres. Opening validates the file and rebuilds the CAD solid. Saves write and flush a temporary file in the destination directory, then atomically replace the target; failed writes keep the previous file intact. No autosave or multi-process file locking yet.

**Ctrl+S** saves, **Ctrl+Shift+S** saves as, **Ctrl+O** opens, **Ctrl+N** starts fresh; **Ctrl+Z / Ctrl+Shift+Z** undo/redo. Save includes any pending property edits. Undo first cancels unapplied property edits, then reverses applied dimension changes. Applying a new edit after Undo clears Redo. The title's `*` marks unsaved changes. New/Open/Close offer Save, Discard or Cancel; cancelled or failed saves keep the current document open. Undo history is session-only and resets on New/Open.

The property editor displays three decimal places. Untouched higher-precision dimensions loaded from a file are preserved; their stored values appear in tooltips. Document format v1 accepts only a single box, millimetres, finite numeric dimensions and the defined fields; unknown versions/units/fields, duplicate keys and files larger than 64 KiB are rejected.

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

Controls: left drag orbits, middle drag (or Shift-left) pans, wheel zooms; **F** or **Fit all** frames the model. Zoom is bounded relative to the current model's bounding diagonal; both wheel and right-drag dolly respect the limits. Isometric, Front, Top and Right presets fit the model.

Choose **Select faces** or **Select edges**, then left-click geometry for an orange highlight. Blank clicks or **Escape** clear selection. Dragging continues to orbit rather than selecting. Face selection highlights the entire OCCT face, not one mesh triangle; edges come from actual B-rep boundaries, so planar faces have no internal diagonal lines. Normal edges remain one pixel wide, with the original background, face color and lighting. Selection is single-item and transient: Apply, Undo/Redo and New/Open clear it. It is not stored in files or a stable reference across regeneration. Hidden edges are not selectable through solid faces. Properties are committed together when Apply is clicked. A failed geometry rebuild leaves the previous document intact.

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

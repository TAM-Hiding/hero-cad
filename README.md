# STAR-CAD

Lightweight, Linux-native parametric mechanical CAD for STR-GZR OS. Fusion-inspired workflow, with a small, understandable toolset. No accounts, subscriptions, cloud requirements, or telemetry. AI-assisted modeling is a future capability; ordinary modeling must always work offline.

## v0.0.2 / local documents

A Qt desktop shell with a 3D viewport, dockable model browser and properties panel. Starts with one Open CASCADE box. Edit width (X), depth (Y), and height (Z), then **Apply dimensions** to regenerate its solid. Dimensions are millimetres, entered to 0.001 mm, in the range 0.001–100000 mm. These are input limits, not a manufacturing accuracy guarantee. Geometry uses OCCT double-precision B-rep; the display mesh is not the model.

One document and one box, now with local **New, Open, Save, Save As, Undo and Redo**. No export, sketches, boolean tools, or feature timeline yet.

Documents use `.starcad` files: versioned, human-readable JSON in millimetres. Opening validates the file and rebuilds the CAD solid. Saves write and flush a temporary file in the destination directory, then atomically replace the target; failed writes keep the previous file intact. No autosave or multi-process file locking yet.

**Ctrl+S** saves, **Ctrl+Shift+S** saves as, **Ctrl+O** opens, **Ctrl+N** starts fresh; **Ctrl+Z / Ctrl+Shift+Z** undo/redo. Save includes any pending property edits. Undo first cancels unapplied property edits, then reverses applied dimension changes. Applying a new edit after Undo clears Redo. The title's `*` marks unsaved changes. New/Open/Close offer Save, Discard or Cancel; cancelled or failed saves keep the current document open. Undo history is session-only and resets on New/Open.

The property editor displays three decimal places. Untouched higher-precision dimensions loaded from a file are preserved; their stored values appear in tooltips. Document format v1 accepts only a single box, millimetres, finite numeric dimensions and the defined fields; unknown versions/units/fields, duplicate keys and files larger than 64 KiB are rejected.

## Ubuntu setup

Initial target: Ubuntu 24.04 x86-64, CPython 3.12, X11/XWayland and OpenGL 3.2+ (Mesa software rendering works for CI). Other Python versions and ARM are deliberately not declared supported yet.

```bash
sudo apt update
sudo apt install python3.12-venv libgl1 libegl1 libxcb-cursor0 libxkbcommon-x11-0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
QT_QPA_PLATFORM=xcb star-cad
```

Run these commands from a checkout of this repo. Installation needs network access; the application does not. `python -m star_cad` is an alternative entry point. The lock file records the tested development environment; `pip install -e '.[dev]'` resolves transitive dependencies afresh. Binary dependencies are substantial (Qt, OCCT, VTK); lightweight here describes product scope, not a tiny download.

Controls: left drag orbits, middle drag (or Shift-left) pans, wheel zooms; **F** or **Fit all** frames the model. Properties are committed together when Apply is clicked. A failed geometry rebuild leaves the previous document intact.

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

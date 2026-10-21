# STAR-CAD

Lightweight, Linux-native parametric mechanical CAD for STR-GZR OS. Fusion-inspired workflow, with a small, understandable toolset. No accounts, subscriptions, cloud requirements, or telemetry. AI-assisted modeling is a future capability; ordinary modeling must always work offline.

## v0.0.4 / parametric sketching foundation

A Qt desktop app with an Open CASCADE box, editable sketches, model browser and properties panel. All model coordinates are millimetres; the B-rep and stored parameters are authoritative, not the display mesh. The dark blue-gray background, shaded solids and one-pixel boundary lines are retained.

### Sketch workflow

1. Expand **Origin**, select **XY**, **XZ** or **YZ Plane**, then choose **New Sketch**.
2. The camera faces the plane orthographically; axes and origin appear. The solid is temporarily hidden so it cannot obscure the sketch.
3. Choose **Line** or **Rectangle** in the contextual sketch toolbar. Placement previews appear while moving the cursor.
4. Choose **Select**, then click an entity (or its browser entry) to edit numeric parameters in Properties. Click **Apply entity parameters** to commit.
5. Choose **Finish Sketch** to restore the previous model view. Select an existing sketch and choose **Edit Sketch**, or double-click its browser entry, to return.

| Tool/input | Result |
|---|---|
| Line: click, click | Two endpoints; edit X1/Y1/X2/Y2 later |
| Rectangle: left press, diagonal drag, release | Axis-aligned rectangle |
| Rectangle: Shift-click, click, click | First corner, first-edge endpoint, perpendicular depth; arbitrary rotation |
| Escape during construction | Cancel preview and return to Select |
| Escape or blank click in Select | Clear selection |

Shift only needs to be held for the **first** edge-first rectangle click. Both rectangle methods create the same editable entity: X/Y position, width, height and angle in degrees. Positive angles rotate from local U toward V. A negative perpendicular depth shifts the stored corner to keep width and height positive. Line and rectangle parameters use double-precision numbers; they are not snapped to a grid. The sketch editor displays nine decimal places and preserves untouched higher-precision stored values. Coordinates are limited to ±1,000,000 mm; minimum line length and rectangle side are 0.000001 mm. These are input limits, not manufacturing accuracy guarantees.

Origin frames: XY uses U=+X/V=+Y (normal +Z); XZ uses U=+X/V=+Z (normal −Y); YZ uses U=+Y/V=+Z (normal +X). Only origin planes are supported.

### Documents and editing

The existing box workflow remains: edit Width (X), Depth (Y), Height (Z), then **Apply dimensions**. Box inputs display three decimal places and range from 0.001–100000 mm. Untouched higher-precision values are retained.

**Ctrl+S** saves, **Ctrl+Shift+S** saves as, **Ctrl+O** opens, **Ctrl+N** starts fresh; **Ctrl+Z / Ctrl+Shift+Z** undo/redo feature and entity edits. Undo first cancels unapplied property edits. Changing browser selection or finishing a sketch commits pending property edits; invalid edits keep the current selection. Save also commits pending fields. In-progress cursor previews are not document geometry and are not saved.

The title's `*` marks unsaved changes. New/Open/Close offer Save, Discard or Cancel; cancelled or failed saves retain the document. Undo history is session-only. Documents use versioned `.starcad` JSON in millimetres. Format v2 stores ordered feature IDs, dependencies, box parameters, origin-plane frames and sketch entities. Existing v0.0.2/v0.0.3 format-v1 box documents load and are written as v2 on their next save; older app versions cannot open v2 files. Numeric parameters round-trip without deliberate decimal rounding.

Saves flush a complete same-directory temporary file before atomic replacement. Failed writes retain the previous file. Strict schema validation rejects unknown fields/versions, duplicate JSON keys, invalid IDs, missing/forward/cyclic dependencies and invalid geometry. V2 files are limited to 4 MiB, 1000 features and 10000 entities per sketch; legacy v1 retains its 64 KiB limit. No autosave or concurrent-writer locking.

This milestone supports **one box and multiple independent sketches**, ordered regeneration and transactional validity/error reporting. It does not include extrusion, booleans, constraints, snapping, sketch-on-face references, circles/slots, entity deletion, or feature reordering. Sketch selection is single-entity; solid face/edge selection supports multiple entities. Dependency references establish order but do not yet drive dependent modeling operations.

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

Controls: left drag orbits when no construction tool is active; middle drag or **Shift-right drag** pans; wheel zooms. **F / Fit all** frames visible geometry. Standard Isometric, Front, Top and Right views are available outside sketch mode. Zoom is bounded relative to model size; maximum magnification is reduced by 20% from v0.0.3. Sketch mode starts perpendicular to its plane; orbiting in Select remains possible, and reentering the sketch restores its plane view.

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

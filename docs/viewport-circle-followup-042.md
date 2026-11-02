# PR #42 follow-up — purple viewport and circle entry

Investigation baseline: `a267f7ede52a31ac949043ba62aee7364e32b074` on
`atomic-document-display-042`; comparison main (after #41):
`d2d556f8edc2e88a1a7b4b987eef4abe1d31cb26`.
This updates the same PR and retains its document/display transactions.

## Confirmed viewport defect

An unclaimed **3** keystroke in model view reaches the inherited
`QVTKRenderWindowInteractor.keyPressEvent`. The pinned Qt/VTK adapter forwards
`KeyPressEvent` and `CharEvent` to VTK. Its native interactor style toggles
`RenderWindow.StereoRender` into **RedBlue** stereo.

This reproduces the screenshot's distinctive effect: the entire VTK framebuffer,
including background and guides, loses its green channel; Qt panels stay normal.
`renderer.GetBackground()` and actor color/opacity settings do not need to change.
It is a transient render-window mode, not proof of malformed geometry or a shader
failure. The control event changes no Document definitions/history and adds no
actors. Stereo draws both eye views, adding render/compositing work.

| Source | Before: stereo / corner RGB | After one 3 | After second 3 | Median render ms before / on / after |
|---|---|---|---|---|
| PR #42 before correction | Off / (23,31,41) | On / (31,0,31) | Off / (23,31,41) | 7.53 / 19.84 / 6.89 |
| Main after #41 | Off / (23,31,41) | On / (31,0,31) | Off / (23,31,41) | 8.02 / 20.74 / 7.56 |
| Corrected #42 | Off / (23,31,41) | Off / (23,31,41) | Off / (23,31,41) | 6.62 / 6.68 / 6.99 |

With stereo on, the **maximum green component across the whole framebuffer was
zero**; with it off, 204. The stock probe's main-renderer actor count stayed 16.
These are seven-sample synchronous-render demonstrations on one software-GL host,
not CI timing limits or a laptop performance guarantee. See
[raw measurements and environment](benchmarks/viewport-stereo-042.json).

**Classification:** this keyboard shortcut hazard predates #42. The same Qt key
reproduces it on main; the relevant key route was unchanged by #42. It also explains
why saving/reopening would retain correct geometry and restore normal colors:
stereo belongs to the runtime render window and is not serialized as CAD state.

**Original incident limit:** the user's actual keystroke/focus state and document
were not supplied. The Join-to-purple transition itself has not been established.
This is a confirmed route to the same distinctive appearance and slowdown, not a
claim that every magenta display fault has this cause. An unclaimed number reaching
the viewport is a plausible trigger; the precise historical event remains unknown.

### Small correction

Consume key **3** in the viewport's press/release fallback, alongside its existing
suppression of unwanted native VTK shortcuts. Construction numeric routing runs
**first**, so typing 3 as a circle radius still works. Text editors and Properties
keep owning their input. No rendering mode, color palette, geometry, actor cache,
shader, history rule or serialization behavior is changed. There is no new command
or recovery framework.

On the unpatched build only, pressing 3 again in the model viewport is a confirmed
way to turn the accidental native mode off. The corrected build ignores that
unclaimed shortcut instead of enabling stereo.

## Join, preview and recovery investigation

The deterministic fixture has a 60×40×5 plate, two independent 3 mm-radius posts,
a slot handle joined into one post, and a face-attached circular rod profile.
There are three active bodies before the rod and four after a successful New Body.
An attached profile at x=25 contacts the handle and can Join; moving it to x=90
makes the explicit Join disconnected and rejected.

The test matrix exercises:

- Successful Join and successful-preview cancellation.
- Disconnected Join failure, followed by Cancel.
- Failed Join → smaller rod as New Body.
- Failed Join → source-sketch deletion.
- All five flows with X-ray **Off** and **Orange**.
- Invalid numeric preview and injected display-conversion interruption after an
  already valid preview, followed by a successful new operation.
- Supporting-face sketch enter/exit, support overlay cleanup and subsequent
  camera orbit/pan/render without rebuilding solid display data.

The Join/cancel matrix **did not reproduce purple corruption** by itself on the
branch before the keyboard correction or afterward. The additional interruption
cases also retain normal appearance on the corrected branch. Native geometry and accepted history
remain intact on rejected/canceled operations. Tests compare actor identities
across both renderer layers, layer numbers, palette/background, temporary preview
and support visibility, restored native picking maps, stereo state, actual frame
colors and continued modeling. No leaked actors or persistent extra scene resources
were found in these controlled transitions. No speculative Join/renderer/cache
changes were made.

## Circle radius/diameter investigation

`ConstructionDimensions` maps Diameter to `Radius = value/2`; Radius is passed
through unchanged. Circle preview and completion both use the tool's stored Radius.
These paths and their mode labels were inspected, and were unchanged by #42.

The real Qt-input tests verify both modes for **1, 2.5, 4.99999, 9.99998 and 10 mm**:

| Requested mode/value | Expected stored radius | Expected diameter | Result |
|---|---:|---:|---|
| Radius 4.99999 | 4.99999 | 9.99998 | Verified |
| Diameter 9.99998 | 4.99999 | 9.99998 | Verified |
| Diameter 4.99999 | 2.499995 | 4.99999 | Verified |
| Radius 10 | 10 | 20 | Verified |
| Diameter 10 | 5 | 10 | Verified |

Checks include the live preview, committed Circle parameters, analytic OCCT circle
radius, actual extruded bounds/volume, Properties radius and save/reopen. Additional
near-fit tests cover direct typing, Tab-to-focus and clicking the editor, including
a second circle after Diameter entry. Existing multi-plane/slot conversion and
snapping/precision tests remain enabled. A numeric radius of 3 is explicitly
verified after suppressing the native shortcut.

**The reported radius/diameter mismatch was not reproduced.** There is no evidence
here for changing the conversion, labels or numeric formatting. No circle/tool
behavior was altered speculatively. These tests do not establish what the user's
original active field/focus sequence was. If the mismatch recurs, a captured input
sequence showing the active field and resulting stored radius would narrow that
remaining boundary; an original saved model would help distinguish an input error
from a later display issue.

## Validation

Before correction, the initial follow-up tests produced **19 passed / 1 failed**:
the unclaimed-3 test enabled native stereo as expected. After correction, the new
frame check was calibrated to the existing shaded blue/green palette rather than
assuming every dim isometric box face has RGB channels above 110. The stereo flag
and exact before/after framebuffer assertions remain; the test also excludes a
blank background/guide-only image. Existing tests were not removed or weakened.

- Final focused run (new follow-up, dimension focus, precision and #42 atomic
  transaction tests): **84 passed**, 16 upstream warnings, 39.99 s.
- Full suite: **829 passed, no failures or skips**, 165 upstream VTK/NumPy warnings,
  252.67 s. All original 802 tests are retained; 27 follow-up cases are added.
- `pip check`: no broken requirements. Python compilation and `git diff --check`
  pass. No dependency, schema or modeling changes.
- The original input incident and exact Join-triggered event remain unreproduced;
  they are not silently classified as fixed. The hidden native stereo route is
  reproduced on both old sources and prevented on the corrected branch.

Reproduction commands (normal desktop/Xvfb):

```sh
LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb xvfb-run -a .venv/bin/pytest tests/test_viewport_circle_followup_042.py tests/test_dimension_focus.py tests/test_precision.py tests/test_atomic_updates_042.py -q
LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb xvfb-run -a .venv/bin/pytest -q
```

This sandbox uses isolated TCP-Xvfb in place of its restricted Unix-socket
transport. Dependencies remain pinned; no package or file-format changes occur.
Remaining limits are the unreproduced original Join trigger, the unconfirmed circle
incident, and the lack of the user's NVIDIA desktop/model for direct reproduction.
No general renderer optimization, new numeric mode or UI redesign is justified.

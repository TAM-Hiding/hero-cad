# PR 44 follow-up — predictable X-Ray opacity

Under **Settings → Preferences → Viewport**, both opacity controls accept integer
percentages from 0 to 100, update immediately, and persist in application settings.
They do not change RGB colors, the selected Off/Orange/Celadon mode, CAD geometry,
sketch definitions, profile selection, document dirty state or Undo/Redo history.

| Context | Surface opacity |
|---|---|
| Model view, X-Ray Off | 100% |
| Sketch editing, Enable Sketch X-Ray checked | Sketch X-Ray Opacity (default 35%) |
| Sketch editing, Enable Sketch X-Ray unchecked | 100% |
| Model view, Orange or Celadon selected | General X-Ray Opacity (default 85%) |

Sketch editing owns the opacity while active, including when Orange/Celadon is
selected. Finish restores the general model-view opacity without changing either
saved percentage or the selected mode. Changing the general value while sketching
saves it for model view; it does not override the active sketch percentage. The
existing high-contrast CAD edge outlines may remain opaque for legibility even
when the shaded surface is transparent. Operation-preview opacity is independent
and unchanged.

## Confirmed cause and correction

The numeric preference validator and signal path correctly accept 10%. The failure
occurs when Qt assigns **Restore Category Defaults** as the Preferences dialog's
default action: Enter can subsequently activate that action while committing a
numeric field. The trace is:

1. `viewport/v1/sketch_opacity = 10` (the requested input is accepted).
2. Restore Category Defaults receives `clicked` through default-button activation.
3. The Viewport category reset writes `sketch_opacity = 35` and `xray = Off`.

That explains the paired 35% reset and mode loss. A direct valueChanged/store test
misses this keyboard/default-button interaction. The reproduction explicitly
establishes the Qt default-button state because initial assignment varies with
platform/focus; ordinary fresh-dialog entry without that state need not fail.

The same trace and four Return/keypad-Enter regressions reproduce with the merged
#43 source (`6d5fd0fab4114aac6294dff7cc14c324496c37bb`) loaded in a detached
worktree, before any palette module exists. PreferencesDialog itself was unchanged
by the original #44 implementation. **This bug predates PR 44**; the palette
controller is not the cause.

Preferences dialog action buttons now opt out of automatic/default Enter behavior.
Numeric Enter commits the value and leaves the live dialog open. Reset and Close
remain explicit actions, usable by mouse or focused Space. There is no custom
keyboard router or changed modeling shortcut.

General opacity adds the existing typed preference pattern at
`viewport/v1/xray_opacity` (default 85, range 0–100). Its binding changes the cached
viewport percentage, existing actor properties and redraw only. It replaces the
previous model-view constant .85. The existing sketch percentage, checkbox,
precedence, lighting and contrast-edge rules stay intact. Neither opacity setter
calls set_xray_mode or writes the mode preference. RGB palette schema/registry,
import/export and live/no-Apply persistence are unchanged.

## Verification and scope

14 new cases cover the requested A–I matrix: actual typed Return/keypad Enter in
both color modes, sketch percentages 0/10/35/90/100, real framebuffer differences,
checkbox disable/re-enable, general opacity including Off, enter/finish/reenter,
fresh-process and window restart, Default/Custom RGB palette compatibility,
unchanged selection/tool/feature/native-mesh/history/serialization state, explicit
reset behavior and invalid/missing saved general-opacity handling. Evaluation and
solid-display-preparation spies reject inappropriate work. Existing tests remain
unchanged. Commands and final full-suite results are in VALIDATION.md.

Separately reported font-color inconsistencies remain a palette follow-up, not a
part of this opacity correction. No font/style/RGB behavior, geometry algorithms,
chamfer references or document schema are changed here. Automated rendering uses
Xvfb/software OpenGL; the original user's desktop event sequence/GPU is not
available, so the reproduction isolates the matching default-action mechanism
rather than claiming to have recorded that desktop session.

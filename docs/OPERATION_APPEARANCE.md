# Operation window presentation — Work Order 036

Chamfer, new Extrude, Edit Extrusion, and Combine use the existing OperationPanel
as a floating Qt dock window. They share one operation palette and opening
placement. Properties, the HERO Tools island, model browser, menus/toolbars,
viewport/grid and feature colors retain their existing presentation.

## Opening placement

The operation frame opens with its left edge aligned to the island, **3 logical
pixels below its actual displayed bottom edge**. It reads the widget's real size
and viewport-to-global position, rather than assuming preset dimensions. Compact,
Medium and **Expanded** (the existing largest preset), collapsed islands and moved
islands all use the same calculation. No preset names or island controls changed.

The screen containing the island's center supplies its available desktop area.
If the frame will not fit below, placement prefers above with the same gap. Its
horizontal position clamps to the screen; if neither vertical side fits, the
frame clamps within the available area. No cursor-relative operation placement
or persistent window attachment remains.

Qt's built-in scroll area keeps operation form controls reachable on small
screens. Initial sizing includes the actual floating frame. Opening finalizes
once after Qt's layout pass, then focuses/selects the primary numeric field (or
Operation for Combine, which has no numeric parameter). Cancel stops pending
opening/focus work. Moving/resizing the island after this does **not** move the
active dialog. A new operation recalculates placement from the island's current
location. Operation windows retain native dragging/resizing; validation with an
unchanged form hint preserves a manually chosen size. Layout growth can resize
or scroll the form within the remaining screen area without moving its origin.

Advanced extrusion editing and Combine now float on opening as well. They remain
the same native QDockWidget and existing form, not separate dialogs or a new
docking framework. Enter in the existing quick input keeps its established
Preview/Apply commit behavior. Advanced operations still require their existing
explicit Preview/Apply; focusing the spin box does not add an Enter-to-commit
handler. Existing Escape, Cancel, close and precision handling remain.

## Shared palette

`ui/operation_appearance.py` contains only scoped styling and bounded placement
helpers, not an application theme system. The primary orange is slightly lighter
than the proposed starting color for readable dark labels. The palette follow-up
keeps both orange surfaces and replaces cool teal controls with warm charcoal,
ivory text and a subdued sand-colored focus/selection accent.

| Element | Color |
|---|---|
| Operation/inline surface | `#B87743` |
| Secondary orange/title surface | `#874923` |
| Numeric inputs | `#302D2A` |
| Buttons | `#4A433D` |
| Hover | `#62574E` |
| Focus/active | `#D9B590` |
| Text on orange | `#241C16` |
| Text on inputs/buttons | `#F2EAE1` |
| Border/accent | `#B6875D` |

Apply has a distinct dark fill/accent and weight. Focus/hover states and disabled
controls use explicit scoped rules. Internal operation surfaces have 8 px corners,
inline surfaces 6 px, buttons 5 px and inputs 4 px. Existing application fonts are
inherited. The native title-bar controls retain their Qt/platform behavior.

## Inline dimensions

ConstructionDimensions receives the matching scoped stylesheet and an object
name only. Its layout margins, compact input padding, opacity preference,
stage-relative anchor and event/validation code remain intact. It still anchors
98 logical pixels right and 68 below the existing stage/cursor reference,
clamped inside the viewport; it never uses the island placement helper.

Numeric precision, live preview, snaps, Radius/Diameter Tab navigation, Slot
center-distance entry, Enter and Escape retain their previous behavior.

## Platform limits

No frameless custom window or custom chrome/drag handler was introduced. Qt may
itself implement a floating QDockWidget as a Tool window with a frameless flag;
that is its existing native implementation. Internal rounding is explicit;
outer corners/title decorations remain Qt/window-manager dependent.

Placement uses Qt's logical/global screen geometry including the window frame.
A compositor that restricts programmatic top-level placement (notably some
Wayland configurations) may override the requested coordinates. No workaround
that replaces native window management is added. XCB/software-OpenGL behavior
is verified locally; other desktops are not claimed tested.

References: [Qt QWidget geometry](https://doc.qt.io/qt-6/qwidget.html#pos-prop),
[Qt window geometry](https://doc.qt.io/qt-6/application-windows.html#window-geometry).

## Regression coverage

`tests/test_operation_appearance.py` checks actual preset geometry/gap/alignment,
collapsed/moved islands, independent window movement/resizing and fresh opening
placement, above/right boundary fallback, negative screen origins, cramped-screen
scroll access, native Qt window flags, scoped/computed palette properties and
unchanged island/unrelated styles. It also checks immediate Chamfer typing/Enter,
advanced Extrude focus and explicit confirmation, Combine Preview/Apply, and Slot
center-distance precision, geometry-relative anchoring, Tab/Escape behavior.

The existing quick extrusion test's advanced-edit expectation was updated from
'docked' to 'floating'. Parameters/preview/commit assertions remain intact.
Existing chamfer, extrusion, Boolean and dimension-focus tests continue testing
the real model/keyboard paths; style checks avoid screenshot-pixel comparisons.
See [VALIDATION.md](../VALIDATION.md) for final commands and results.

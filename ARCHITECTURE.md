# Architecture

## Boundaries

- `app.py`: QApplication lifecycle and entry point.
- `document.py`: immutable box parameters and a document owning its regenerated solid. No Qt or VTK imports.
- `geometry.py`: direct OCP operations and validity/volume queries. No custom geometry kernel or generic backend interface.
- `ui/main_window.py`: model browser, property editor, explicit Apply action, status and error reporting.
- `ui/viewport.py`: OCCT face tessellation converted to double-precision VTK points; Qt viewport and camera interaction.

Data flows from editor → validated parameters → OCCT solid → display tessellation. The B-rep remains authoritative. Mesh tolerance (0.1 mm linear, 0.2 rad angular) affects visualization only. OCCT tolerances still apply; input decimal places do not imply arbitrary precision.

## Parametric state

The sole feature is a box rooted at (0,0,0), with positive X width, Y depth and Z height. Document initialization creates a real solid. An edit builds and validates a replacement before updating parameters and shape. Errors are reported at the UI boundary. Editing does not reset the camera; Fit all is explicit.

No feature graph is invented for one feature. When additional features arrive, introduce stable feature identities and ordered recomputation in a dedicated history module. Keep feature definitions independent of widget state. Until then `Document.parameters` is the complete feature definition. There is no serialized format yet.

## Rendering choice

Use VTK's supported PySide6 widget and trackball camera rather than hand-written OpenGL or native OCCT window integration. VTK already comes with the selected OCP wheel. Display code handles face locations and reversed winding. Viewport picking and persistent topology references are deferred.

## Constraints

All operations are synchronous for this tiny model. Larger operations will need measured responsiveness work before adding background workers. No network code, AI service, telemetry, plugin framework, database, or dependency injection layer. Test actual kernel results and rendered output; never substitute a rendered cube for a CAD solid.

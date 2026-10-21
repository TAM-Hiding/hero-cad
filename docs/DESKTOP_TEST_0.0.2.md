# v0.0.2 physical desktop acceptance report

Date: October 20, 2026. Source: Tomoki's supplied test report and screenshot. Platform reported: Ubuntu 22.04, separately installed Python 3.12, physical laptop. GPU/driver versions and exact interpreter-install steps were not recorded.

Result: **PASS for tested core workflows**, with two nonblocking viewport issues.

| Workflow | User-reported result |
|---|---|
| Launch and desktop panels | Pass after installing missing XCB dependencies |
| Initial box rendering and dimension regeneration | Pass |
| Orbit and pan | Pass |
| Zoom | Pass in normal use; extreme magnification destabilizes rendering |
| Save, open and reload | Pass |
| Dimensions preserved through save/reload | Pass |

Ubuntu 22.04's default Python 3.10 was insufficient for the current >=3.12,<3.13 requirement. Python 3.12 was installed alongside it, without replacing system Python. Missing Qt XCB system libraries, including libxcb-cursor0, initially blocked launch; installing dependencies resolved it. These are setup/documentation findings, not geometry failures. README now separates interpreter setup from runtime dependencies.

Preserve: dark blue-gray background, current face shading/lighting, thin boundary lines, compact side panels and large central viewport. Optional line-width customization can wait; thin remains the default.

Follow-up for v0.0.3: remove internal tessellation diagonals, bound zoom, add face/edge selection and highlighting, and add compact orientation presets if practical. The attached screenshot shows the planar-face diagonals and original visual baseline. This report validates v0.0.2 only; it does not claim the subsequent fixes have been physically retested, or that workflows absent from the table were manually verified.

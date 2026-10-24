# Dependency decision — M0

Scope: Ubuntu 24.04 x86-64 / CPython 3.12. Pins deliberately stay on OCCT 7.9 rather than introducing OCCT 8 at the foundation milestone.

| Component | Selection | Reason / license |
|---|---|---|
| Qt Python binding | PySide6 6.8.3 | Official Qt binding; pip abi3 Linux wheels. LGPLv3/GPLv3/commercial choices; this app uses QtCore/Gui/Widgets/Test under the applicable LGPL terms. |
| OCCT Python binding | cadquery-ocp 7.9.3.1.1 | Thin direct OCP API, CPython 3.12 manylinux_2_31 x86-64 wheel installs on Ubuntu 24.04. Binding Apache-2.0; underlying OCCT is separately LGPL-2.1 with Open CASCADE exception. |
| Viewport | VTK 9.6.2 | Required by this OCP distribution already; Qt interactor avoids coupling geometry to a specific GUI binding. BSD-3-Clause, with bundled third-party notices. |
| Alternative considered | pythonocc-core | Mature direct OCCT API and Qt display helpers; upstream documents conda installation and LGPLv3. Not selected because OCP's pip wheel gives a verified single-venv installation path. No claim that pythonocc is incompatible. |

No CadQuery scripting/framework dependency is used. OCP imports as `OCP`, not `OCC` or the unrelated PyPI package `OCP`. `requirements-dev.lock` records installed transitive versions; regenerate only after installing and testing in a clean Python 3.12 environment. Pins are not cross-platform guarantees or a security audit.

## Upstream sources checked

- [OCP repository and Apache license](https://github.com/CadQuery/OCP)
- [Selected OCP wheel metadata/files](https://pypi.org/project/cadquery-ocp/7.9.3.1.1/)
- [pythonocc-core upstream](https://github.com/tpaviot/pythonocc-core)
- [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html)
- [OCCT 7.9.3 LGPL text](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/LICENSE_LGPL_21.txt)
- [OCCT exception](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/OCCT_LGPL_EXCEPTION.txt)
- [VTK license and notice](https://vtk.org/about/#license)

HERO-CAD makes use of Open CASCADE Technology software. Dependencies are installed as separate shared libraries/packages and remain replaceable. When packaging binaries later, preserve all upstream copyright/license notices, provide the applicable corresponding sources and modifications, preserve relinking/replacement rights required by LGPL, and audit bundled transitive libraries. The OCCT header exception is limited; it does not remove the LGPL obligations for its libraries. M0 distributes application source, not a frozen binary bundle. This decision does not constitute a completed binary-distribution compliance audit.

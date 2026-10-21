# Contributor instructions

- Read README.md, ARCHITECTURE.md and DEPENDENCIES.md before changing foundations.
- Keep Linux desktop mechanical CAD and fully offline use central. No telemetry, accounts or mandatory services.
- Preserve the existing MIT license. Check dependency licenses and wheel compatibility before adding or upgrading libraries.
- Keep parameters/document state separate from widgets. Geometry is OCCT B-rep; display meshes are disposable.
- Use millimetres and explicit axis conventions. Reject non-finite and invalid dimensions. Build and validate before committing state.
- Avoid speculative abstractions, generic plugin systems or premature feature graphs.
- M0 excludes sketch constraints, AI, manufacturing/simulation suites and a full timeline.
- Run `.venv/bin/pytest tests/test_document.py -q` for geometry changes and the README's Xvfb full suite for UI changes. Run `pip check` after dependency changes.
- Verify CAD operations using kernel validity, bounds and mass properties. UI tests must check real document updates. Render checks must detect blank output.
- Never claim untested operations or platforms work. Record commands, results and environmental limits in VALIDATION.md.
- Preserve user work and submit changes on a branch with a reviewable PR. Do not merge without instruction.

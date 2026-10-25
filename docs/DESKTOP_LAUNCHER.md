# Ubuntu desktop launcher — PR #27

This integrates the current local checkout/virtual environment with the user's
application menu. It is **not** an installer, bundled executable, package manager
or automatic updater. No root permissions or shell activation are needed after
setup. Ubuntu GNOME menu appearance and dock pinning still need desktop review.

## Install / update the launcher

From the updated checkout, using the existing Python 3.12 environment:

```bash
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/hero-cad-install-launcher --icon "/absolute/path/to/approved-hero-cad.png"
```

There is **no final approved logo image in the repository**. Supply the approved
bronze armillary/gear HERO-CAD artwork. See [the reserved artwork location and
export requirements](../assets/branding/README.md). Setup intentionally fails with
an actionable message if artwork is missing or invalid. It does not create a
replacement logo. A square 512×512 PNG is recommended; PNG 32–4096 px or a
self-contained SVG with a square positive viewBox is supported.

Then open Ubuntu **Applications**, search **HERO-CAD**, and launch it. Right-click
the application icon and choose **Add to Favorites / Pin to Dock** as offered by
your GNOME version. Launching the menu entry, rather than a terminal Python
process, is recommended for testing dock identity. The app's desktop-file name
and X11 instance class match the generated `hero-cad.desktop` entry.

Setup is repeatable: it updates one entry, rather than adding numbered copies.
If an unmanaged/custom `hero-cad.desktop` already exists, back it up or move it
first; the command will not overwrite it silently. You do not need to make the
applications-menu desktop entry executable or grant it desktop-folder trust.

## Installed per-user files

Under absolute `$XDG_DATA_HOME`, or `~/.local/share` by default:

- `applications/hero-cad.desktop` — Name HERO-CAD, GenericName Parametric
  Mechanical CAD, Graphics/Engineering categories, Terminal=false.
- `hero-cad/launch.py` — a small generated startup wrapper.
- `hero-cad/launcher.json` — paths owned by this setup, used for repeatable removal.
- `icons/hicolor/<size>/apps/hero-cad.png`, or the scalable SVG equivalent — a copy
  of the supplied approved artwork. It remains valid if the original image moves.

The entry follows the [freedesktop Desktop Entry specification](https://specifications.freedesktop.org/desktop-entry/latest-single/).
Exec is an argument vector, not a shell command: `/usr/bin/env` runs the
**absolute environment-specific Python path** with the generated wrapper. There
is no Python lookup through PATH. This also avoids desktop implementations'
executable-existence checks on percent-escaped environment paths. Paths are
resolved at setup and quoted/escaped for desktop-entry parsing, including spaces.
Control characters in paths are rejected with an error.

The wrapper uses that exact Python to run the installed `hero-cad` console script;
it does not rely on a shebang accepting an interpreter path with spaces. It
preserves the inherited environment, defaults `QT_QPA_PLATFORM` to `xcb` only when
unset, and points the app at the copied icon. It does not source `.bashrc`, run an
interactive shell, require VIRTUAL_ENV, change directories or rewrite library
paths. The usual Qt/XCB system libraries must already be installed as described
in README. It cannot recreate terminal-only custom exports: if your installation
needs custom environment values, make those available to the desktop session.

Standard output and errors append to
`${XDG_STATE_HOME:-~/.local/state}/hero-cad/launcher.log` (absolute XDG paths only).
If startup fails, read this log and verify the environment still exists. It is a
local diagnostic log, not telemetry. Setup/removal never deletes documents,
preferences, logs or unrelated application files.

## Maintenance / removal

| Change | Action |
|---|---|
| Pull source updates in the same editable checkout | Launcher continues using that checkout. Rerun editable install if entry points/packaging change. |
| Rebuild the virtual environment at the same path | Reinstall HERO-CAD into it; rerun launcher setup to refresh paths and icon. |
| Move/rename the checkout or virtual environment | Reinstall from its new location and rerun setup using its new `.venv/bin/hero-cad-install-launcher`. |
| Change the approved icon | Rerun setup with the new approved file. |
| Remove launcher integration | Run `.venv/bin/hero-cad-install-launcher --uninstall` before deleting the environment. |
| Environment already deleted | Use another HERO-CAD environment's uninstall command, or remove only the generated files listed in `hero-cad/launcher.json`. |

Uninstall is repeatable and removes only the files tracked by setup. PNG icon
sizes from prior setup runs are also tracked. Empty directories may remain.
If GNOME retains a stale favorite after moving/removing an entry, unpin it and
pin the updated Applications entry. A desktop login/session refresh may be needed
if the menu caches old entries; setup does not restart your desktop.

## Validation / Ubuntu checklist

Automated tests validate generated paths and artwork references, missing/invalid
artwork, repeat installation, isolated XDG storage, environment preservation and
removal. A real GIO desktop-entry launch with an unactivated/empty PATH exercises
paths containing spaces, percent, dollar, backtick, quote and backslash characters.
`desktop-file-validate` is used when available. A real application startup smoke
check uses the installed console entry point under Xvfb and checks its window
identity. These checks do not replace GNOME dock testing.

On the Ubuntu 22.04 laptop:

1. Update/reinstall the editable environment and run setup with the final approved
   square icon. Optionally run `desktop-file-validate` on the generated entry.
2. Close terminal-launched HERO-CAD. Launch from Applications with no activated
   venv. Check title, approved icon and a nonblank model viewport.
3. Pin to Dock, close the app, launch from the pinned icon; verify a single grouped
   application icon rather than a second Python/unknown icon.
4. Open an existing `.starcad` file; edit a sketch, extrude/Boolean, save/reopen and
   Undo/Redo. Check Settings and all existing quick controls.
5. Rerun setup: confirm one Applications entry. Test a checkout/environment path
   containing spaces if practical. After a move/rebuild, regenerate the launcher.
6. Uninstall, verify its menu entry disappears, and confirm documents/preferences
   remain. Reinstall if you want to keep using it.

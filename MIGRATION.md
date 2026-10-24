# HERO-CAD migration

## What PR #18 changes

- Application/display/window name: HERO-CAD.
- Python distribution and console command: hero-cad.
- Python package/module launcher: hero_cad / python -m hero_cad.
- Version remains 0.0.12; this is an identity migration, not a feature release.
- Planned repository: https://github.com/TAM-Hiding/hero-cad.

This PR targets the existing https://github.com/TAM-Hiding/star-cad repository.
It does not rename the repository, change remote settings, alter CAD behavior or
layout, or add logo assets. The owner performs the GitHub rename after merging.

## Existing local installation: after merging PR #18

Keep your .starcad files where they are. The checkout directory may still be
named star-cad; changing its directory name is optional and is not required by
Python or the application.

From your existing checkout, update your clean working branch using your usual
Git workflow (preserve any local edits first). For an unmodified main checkout:

    git switch main
    git pull --ff-only

Activate its existing Python 3.12 environment, remove only the old distribution,
and install the new one. Uninstalling the distribution does not delete documents
or source files:

    source .venv/bin/activate
    python -m pip uninstall star-cad
    python -m pip install -r requirements-dev.lock
    python -m pip install --no-deps -e .
    python -m pip check
    hash -r
    QT_QPA_PLATFORM=xcb hero-cad

The module alternative is:

    QT_QPA_PLATFORM=xcb python -m hero_cad

For a fresh environment, deactivate the old environment, create a separate
Python 3.12 venv, and follow README.md's installation commands. Keep the system
Python unchanged. Dependencies and their pins are unchanged.

Update any personal launch scripts, shell aliases or desktop entries:
use hero-cad (or an absolute path to .venv/bin/hero-cad), Name=HERO-CAD,
and python -m hero_cad where applicable. No desktop launcher or icon asset
is shipped in this repository, so there is no bundled launcher to migrate.
Old star_cad imports and the star-cad console command are not compatibility
aliases; user scripts must update those names.

## Document compatibility contract

Continue opening and saving .starcad files. The JSON format identifier remains
exactly "star-cad", and schema versions 1–6, feature/entity IDs, frames, dimensions,
Boolean references and precision rules remain unchanged. No .hero extension,
schema bump or on-disk branding rewrite is introduced.

Older v1/v2 files retain the loader's existing migration-on-save behavior.
Versions 3–6 retain their existing serialization. Existing Boolean output-face
attachment limits and other modeling limits remain unchanged.

The legacy name is intentional in document fixtures/schema tests, historical
validation commands and pre-migration CI URLs. Current source imports and
current launch/install instructions use the new package and CLI.

## Repository links before the owner renames GitHub

README and package metadata advertise the planned hero-cad URL. Until the owner
has completed the post-merge rename, use the existing repository to clone:

    git clone https://github.com/TAM-Hiding/star-cad.git hero-cad
    cd hero-cad

After the owner rename, new checkouts use:

    git clone https://github.com/TAM-Hiding/hero-cad.git
    cd hero-cad

Historic Actions/PR URLs in VALIDATION.md are preserved as recorded; do not
rewrite those evidence links solely for branding.

## Post-merge owner checklist (not performed by this PR)

1. Merge PR #18 in TAM-Hiding/star-cad after CI and desktop acceptance.
2. In GitHub repository settings, rename star-cad to hero-cad.
3. Confirm the new repository page, default branch, issues, pull requests and
   Actions history are available at https://github.com/TAM-Hiding/hero-cad.
4. Update local Git remotes to the matching transport:

       git remote set-url origin https://github.com/TAM-Hiding/hero-cad.git
       git fetch origin
       git remote -v

   For an SSH checkout instead use:

       git remote set-url origin git@github.com:TAM-Hiding/hero-cad.git

5. Check any external links, local helper scripts, integrations or branch checks
   owned outside this repository. This PR does not modify those settings.
6. Run the existing Actions workflow in the renamed repository and verify both
   Ubuntu jobs pass. Checkout uses the current repository context, not a pinned
   star-cad repository name.
7. Verify a clean install launches hero-cad with a HERO-CAD title and opens an
   existing .starcad model. Retest sketch, extrusion, Boolean, Undo/Redo and Save.
8. Integrate final approved bronze armillary-sphere emblem assets separately.
   Do not add a placeholder logo as part of this migration.

Stop after PR #18. No subsequent feature work is included.

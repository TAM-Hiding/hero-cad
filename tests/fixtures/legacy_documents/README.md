# Pre-rename compatibility fixtures

Generated and validated using the unchanged star_cad package from merged PR #17,
commit 7b39cdf23731ed63f9a929b3674d56b43140b5e0, before the PR #18 package migration.

- v1: legacy box-only schema (the writer uses its historical JSON structure).
- v2: legacy line/rectangle schema (the v3 writer's compatible entity subset, version 2).
- v3: origin-plane circle and slot.
- v4: profile extrusion with an internal circular hole.
- v5: face-attached slot and extrusion.
- v6: face-attached circle, New Body extrusion, Boolean Cut and Through All cut.

manifest.json records source commit, exact file hashes, kernel volume, active-body
count and feature types. Keep these fixtures byte-for-byte unchanged when changing
branding. The internal star-cad format marker and .starcad suffix are intentional
compatibility contracts, not stale application branding.

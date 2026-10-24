# PR #20 — desktop acceptance checks

Use the PR branch, Python 3.12 and the pinned dependencies. Launch `hero-cad`
from the activated editable installation on the Ubuntu laptop. Automated
kernel/Qt/render results are recorded in VALIDATION.md; these instructions
cover physical interaction and the preferred appearance on the actual GPU.

## Dovetail channel — primary test

1. Keep the initial 40 × 30 × 20 mm box visible. Start a sketch on XZ.
2. Confirm the box remains visible. Turn off Auto Grid and use 1 mm minor
   spacing with Snap to Grid enabled.
3. Choose Line and draw four independent segments, clicking both ends of each:
   (2,4) → (12,4) → (10,10) → (4,10) → (2,4), in local U/V millimetres.
4. Finish Sketch. Choose Front and Select Profile, then click inside the
   dovetail near (U=7,V=7). Only its intended enclosed material should highlight.
5. Extrude → Cut, target the box, distance **-30 mm**. XZ's positive normal is
   -Y, so a negative distance cuts into the box along +Y. Preview, inspect,
   then Apply. Also try Through All with negative direction.
6. Verify the dovetail channel traverses the block and stays one valid solid.
   Save/reopen the `.starcad` file. Change block depth and use Through All;
   the channel must continue through it. Undo/Redo edits and operations.
7. Repeat in a new document with New Body and a signed distance. Both positive
   and negative distances should produce the standalone dovetail prism.

## Profiles, exact members and editing

- Draw a triangle, trapezoid, L-shaped concave polygon and a loop with more
  than four sides. Repeat on XY and YZ and on an attached face.
- Put two separated closed line loops in one sketch. Each interior should
  select independently. Add a remote open chain: it should remain unfilled
  without disabling the independent loops.
- Add a circular hole inside a closed polygon, or a closed polygon hole inside
  a rectangle. Region highlighting and the extrusion must retain the holes.
- Edit one shared vertex through the two adjacent lines' Properties entries.
  After changing the first endpoint the extrusion should report UNRESOLVED
  and remove stale output; after changing the neighboring endpoint to close
  the original loop, the extrusion and dependents should recover. Local
  geometry remains editable. Undo/Redo should restore each stage.
- Deleting a referenced source line should be rejected with an explanation.
  Deleting the extrusion first allows normal source-line deletion.
- Try Join and Intersect with an overlapping line-profile prism. Use the same
  preview/target workflow as rectangles, circles and slots.
- Leave an obvious gap (e.g. 0.01 mm), create a bow-tie crossing, duplicate a
  segment or add a branch. These must never yield an unintended filled face.
  The unsupported cases should provide status feedback.

## X-Ray and selection

1. Use the toolbar X-Ray dropdown and View → X-Ray in turn. Off, Celadon and
   Orange must stay synchronized. Neither operation should dirty a document.
2. Celadon should retain the existing grey-cyan tone; Orange should use the
   warm preview tone. Both use subtle 85% opacity, with no opacity slider.
   Inspect channels/interior geometry from several angles.
3. Select faces and edges in each color. Orange mode uses a brighter warm
   selection to keep the picked geometry distinguishable.
4. Enter a sketch while X-Ray is enabled. It should retain the chosen mode
   and 85% body opacity. Finish/reenter, Undo/Redo and Open another document;
   the session mode should remain. Off restores 35% sketch-body context and
   normal opaque solids after Finish. Settings → Show base box still works.
5. Change X-Ray while an extrusion/Boolean preview is open. The preview must
   retain its separate color/opacity, and the old committed target must not
   reappear underneath. Cancel and Apply should restore the chosen body style.
6. Confirm sketch curves, dimensions, grid, snaps and selection overlays keep
   their own colors. Check all existing View display modes and mouse gestures.

## Curved surfaces and file compatibility

- Magnify a radius-0.02 mm circle extrusion, a normal-sized cylinder, circular
  holes and slots. Curves should look smoother, with continuous surface lighting.
  The display uses 0.02 mm linear / 0.08 rad angular deflection, so extreme
  magnification can still reveal the fixed tessellation silhouette.
- Inspect the same scene in Mesh Debug: triangles are expected there. Return
  to Shaded with CAD Edges; box/prism corners must stay sharp and CAD boundaries
  thin. Pick curved faces, caps and edges before/after regeneration.
- Pan/orbit/zoom should stay responsive without rebuilding the solid meshes.
- Open older v1–v7 documents and check existing geometry, attachments and
  Booleans. Documents containing line-profile extrusions or line-side references
  now save as v8; older app versions cannot open these. The extension remains
  `.starcad`, and sketch/extrusion dimensions remain analytically exact.

## Documented limits

Endpoint connectivity uses **1e-7 mm**, the existing absolute kernel/region
tolerance, independent of screen scale. Parameters and source edge curves are
not moved or rewritten to close gaps; transient wire vertices use kernel
tolerance. Ordinary visibly open chains stay unfilled.

Only simple cycles of whole line entities qualify. Shared-edge/branch networks,
crossings, overlaps and duplicates reject line-profile analysis; automatic
trimming, planar-arrangement splitting and mixed line/arc chains are deferred.
Keep unsupported networks in another sketch. Independent primitive loops and
holes remain supported. There is a 256-total-entity profile-analysis limit.
Changing selected member IDs or hole topology never substitutes another region.
Existing PR #19 face-reference limitations still apply to regenerated results.

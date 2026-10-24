# PR #19 — desktop verification

Use the PR branch with Python 3.12 and the pinned dependencies. Run `hero-cad`
from the activated editable installation. These are physical-desktop checks;
automated kernel/Qt/Xvfb results are recorded separately in VALIDATION.md.

## Cylinder, screwdriver slot, origin-plane context

1. Create an XY sketch with a radius-10 mm circle centered at the origin.
2. Finish and extrude it as New Body, +10 mm. Leave Show base box off.
3. Right-click the end face → New Sketch. Draw a rectangle across the whole
   top: for example local corner (-15, -2), width 30, depth 4. Alternatively
   use a Shift-slot with centers (-15, 0)/(15, 0) and radius 2.
4. Select its material profile and Cut the cylinder by -3 mm. The cut should
   leave two separate top regions and a planar floor at world Z=7 mm.
5. Start a new sketch on XZ, then repeat on YZ and XY. The cut cylinder and
   its slot must remain visible at 35% opacity. Pan, orbit, zoom, Fit, switch
   tools and place geometry. Curves, numeric dimensions, origin/grid/center
   snaps and profile selection must still work through the reference body.
6. Toggle Settings → Show base box while editing. Its visibility must follow
   the preference without cancelling a preview or changing geometry. Finish
   restores opaque bodies and the prior camera view. Check the View display
   modes as well; Shaded hides edges and CAD Wireframe retains its wire mode.

## Three regions and repeated sketches

1. On the cut cylinder, look down from above. Right-click inside the first
   top region, away from an edge → New Sketch; draw a small circle and Finish.
2. Repeat on the other top region, then on the slot floor. Each sketch must
   have its own browser entry and the correct plane, without a camera roll
   determined by the prior viewing direction.
3. Create another sketch on the first top region. Also right-click a finished
   curve lying on that face: its context menu should retain Edit Parameters,
   Edit Sketch and Delete, and include New Sketch for the face underneath.
4. Reenter each sketch and change one entity. Other sketches' local parameters
   must remain independent. Change cylinder radius (e.g. 10 → 12) or cut depth
   (-3 → -4); attachments should follow their own parent faces.
5. Save as `.starcad`, reopen, reenter each sketch, Undo/Redo further edits.
   The same faces and local dimensions must regenerate. Undo history itself
   is session-only, as before.

## Two holes and correct history state

1. Make a 50 × 25 × 10 mm plate. Sketch a radius-2 circle near one end of its
   top and Cut through it (Through All, negative direction).
2. Right-click the remaining top face of that result, create another sketch
   and Cut a second hole near the other end.
3. Reenter both sketches independently and change each radius. Both holes
   should regenerate. The first sketch references its original plate; the
   second references the first Cut result, never the latest second Cut.
4. Undo/Redo the second operation and sketch, save/reopen, and repeat edits.

## Join, Intersect, invalidation and compatibility

- Combine overlapping bodies with Join and Intersect, or use those extrusion
  modes. Right-click eligible planar result faces and create/reenter sketches.
  Curved faces must still reject New Sketch with brief planar-face feedback.
- Shorten the screwdriver cutter so it becomes an internal pocket instead of
  splitting the top. Old split-face sketches should become UNRESOLVED with
  explanatory properties, retaining their entities and last frame. Dependent
  extrusions must produce no stale solid. Undo should recover the attachments.
- Open existing v1–v6 `.starcad` models with ordinary sketches, extrusions,
  attachments and Booleans. Regeneration, save/reopen and Undo/Redo should
  retain their established behavior. Documents with new Boolean-face sketches
  use v7; older application releases cannot open them.

## Remaining limits

Only analytic planar faces with a unique supported ancestry/neighbor signature
are eligible. Missing OCCT history, symmetric indistinguishable regions, or
split/merge changes in the same ancestry group can invalidate a reference even
when a similar face remains. The application must report that limitation,
never guess a nearest/coplanar face. Later operations do not retarget older
sketches. Plane reassignment and general topological naming remain deferred.

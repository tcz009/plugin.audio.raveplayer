# Direction C — TRIPPY RAVE (3.9.33 / 1.6.41 study)

**Status: art study only. Nothing is wired, committed or deployed.** No file in
`resources/art/`, `static/art/`, `routes.py`, `test/` or `preview.jpg` was
touched; the rejected `hardening/3.9.32-art-duplicates` and
`hardening/1.6.40-art-duplicates` branches are untouched. This folder is the
whole deliverable.

---

## 1. What the owner actually said

> directions A/B are "not like rave... we've got this trippy gravy thing going
> on. I don't know what these things look like." The new icons are too
> clean/literal.

Direction A (BIG MARK) drew **one tidy vector object** per row — a ghetto
blaster, a mic, a Yagi, a crescent. Direction B (MONOGRAM) drew **one bespoke
letterform** per row. Both are legible and both are *designed*; neither is
**rave**. They are the visual language of a modern streaming app that happens to
stock rave content. The accepted art is the opposite: acid-house flyer print —
flat spot field, a fat ink blob, a bad riso registration, a smiley, and a
hand that visibly shook.

So C is not "A plus texture". C keeps the accepted DNA and rebuilds the mark as
a **melted, hand-drawn, grinning thing**.

---

## 2. Reading the accepted originals

`rave.png`, `tapepacks.png`, `jungle.png`, `hardcore.png`, `pirate.png`,
`toronto.png`, `preview.jpg`, `THEME-2026.md`:

| What they do | Why it reads rave |
|---|---|
| One flat spot field (acid / magenta / cyan / paper / orange) | photocopied flyer stock, not a UI surface |
| One **heavy ink mass**, generous and slightly clumsy | screen-print block, weight over refinement |
| Exactly **one second colour**, used only as a misregistration plate | bad registration is the whole charm |
| Coarse halftone + scanlines + grain, visible at 100 % | printed object, not a render |
| Crop marks, `RP-xx` code, signal bars | sticker/press-sheet furniture, family glue |
| **The smiley** — `rave.png` is a winking acid smiley with a play triangle for an eye; `icon.png` is the same face | the identity is a *face*, not a logo |
| Shapes are simple but the edges are not precious | they were cut, not drawn in a vector tool |

The accepted marks are literal objects (cassette, bolt, mask) but they are
**rendered as print**, and the brand tile is a **face**. A/B reproduced the
objects and dropped the print, the face and the hand.

---

## 3. What C changes

1. **Melt.** Every mark sags. `add_melt()` scans the glyph's own alpha, finds the
   flat underside and hangs teardrop drips off it; `warp()` bends the whole
   silhouette with two sine bands and a cubic "gravity" term. Nothing sits
   straight.
2. **Hand-drawn ink.** Outlines are dense paths displaced by two sine harmonics
   (`wobble()`), so edges breathe; every stroke is drawn with a taper and round
   caps (`Pen.line`). No clean bezier survives.
3. **Smileys are a family motif** — cassette (reels = eyes), transmitter head,
   crescent moon, skull. The accepted `rave.png` face is the ancestor.
4. **Hard chromatic misregistration.** Two plates (magenta + cyan, or acid +
   cyan, etc.) are taken from the same alpha but each is **warped on its own
   phase and offset**, so the edges separate unevenly like a real bad print run.
   A/B had one tidy shadow plate.
5. **Squiggles, sparkles, spatter, riso suns.** Marker squiggles ride the marks
   (tape ribbon, mic cable, bass line), ink spatter sits beside them, and a
   radial halftone "sun" in a plate colour sits under them.
6. **Still the accepted system underneath**: one spot field, ink body, crop
   marks, `RP-xx`, signal bars, 512-space glyphs, halftone, scanlines, grain.

Deliberate limits: no drug imagery, no third-party marks, no wordmark, one idea
per tile, and the field colour is still the only "real" colour — the plates are
registration, not decoration.

---

## 4. Why A and B failed the rave test

| | A — BIG MARK | B — MONOGRAM | C — TRIPPY RAVE |
|---|---|---|---|
| Mark | one crisp object | one bespoke letter | one melted, grinning object |
| Edge | confident bezier | typographic curve | wobbly marker line |
| Second colour | single offset shadow | single offset shadow | two plates, separately warped |
| Face | none | none | 4 of 9 (cassette, mast, moon, skull) |
| Motion | none | none | drips, sag, spatter, squiggles |
| Reads as | "designed icon set" | "designed icon system" | "sticker off a 1991 flyer" |
| 64 px | very good | very good | good; two rows need a re-cut (below) |

A and B answer "is it individually designed?" C answers the owner's actual
complaint: *what does this thing look like?* It looks like the thing on the
front of `rave.png`.

---

## 5. The nine samples

Nine rows, chosen to cover every menu type the 38-row rollout will touch: a tape
genre, a show/podcast, a live station, a live genre, a quick filter, downloads,
a pirate collection, curated, and a category row.

| Row | Mark | Face | 64 px read |
|---|---|---|---|
| `tapepacks` — Rave Tape Packs | cassette whose reels are eyes, ribbon squiggle | grin | strongest of the set |
| `podcasts` — Podcasts | melting dynamic mic, cable loops into a squiggle | – | strong |
| `kool` — Kool FM | tapering lattice mast + grinning aerial ball + arcs | wink | strong (tower reads, face rewards 256) |
| `radio-jungle` — Jungle | soundsystem cabinet, bass squiggle, palm sprouting behind it | – | speaker reads; the foliage is the busiest element |
| `dreamscape` — Dreamscape | melting crescent with wink + thrown sparkles | wink | very strong silhouette |
| `downloads` — Downloads | fat down-arrow, sagging tip, magenta speed ticks | – | strong |
| `pirate` — Pirate Radio | torn jolly-roger, grinning skull, crossbones | grin | strong |
| `curated` — Curated Gems | sagging gem, melted facets, sparkles | – | strong |
| `rave-nights` — By Rave & Venue | big-top, sagging canvas, stripes, scalloped hem | – | strong |

**Colour distribution** (same rhythm as the accepted 20): acid ×3, magenta ×2,
cyan ×3, paper ×1. Plates always two of magenta / cyan / acid, never the field.

**64 px honesty:** `radio-jungle` is the one I would re-cut first — the speaker
is the read and the palm is decoration, so the foliage could be simplified.
`kool` carries its face only at 256; the lattice tower does the 64 px work.
Everything else is unambiguous in the row mock (`direction-c-64px-rows.png`)
next to the accepted originals at the same size.

---

## 6. Files

| File | What it is |
|---|---|
| `direction-c-contact-sheet.png` | the review surface: 9 rows, each at **64 / 128 / 256 actual** + a **64 px Kodi list row**; accepted originals at 64 px in the header |
| `direction-c-1to1.png` | all nine at native 256, nothing scaled — judge melt / registration / hand-line at 100 % |
| `direction-c-64px-rows.png` | every sample as a 64 px row on a dark list panel, with the accepted originals at 64 px underneath for family comparison |
| `sample-<row>.png` | the 256 px tile for each row |
| `64/`, `128/`, `256/` | each sample exported at the three sizes |
| `build_direction_c.py` | the generator (Pillow + numpy, build-time only) |
| `RATIONALE.md` | this note |

Reproduce with:

```sh
python3 build_direction_c.py
```

The script reuses the palette, fonts and render scale of
`scripts/make-art.py` (imported read-only) so tokens cannot drift, but the whole
C pipeline — wobble, melt, warp, plates, riso sun, spatter — is new. It writes
only into this folder.

---

## 7. Recommendation

If the owner wants the accepted `rave.png` feeling, **C is the direction**: it is
the only one of the three built from the same three ingredients (ink mass, bad
registration, a face).

If approved, the rollout would:

1. Re-cut `radio-jungle` (simplify the crown) and confirm `downloads` at 64 px.
2. Draw the remaining 29 rows in this language — each needs its own object and
   its own melt, not a shared template. Budget accordingly: C is slower per tile
   than A or B.
3. Decide whether the code tags stay `RP-xx` placeholders or get renumbered.
4. Only then: wire `MENU_ART` / `FILTER_ART`, render Kodi 256 + web 512, bump
   **3.9.33 / 1.6.41**, commit, and **not deploy** until the owner sees a device
   smoke test.

Until then: no branch changes, no version bump, no deploy.

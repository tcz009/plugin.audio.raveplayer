# Duplicate-row stickers — direction study (3.9.33 / 1.6.41)

**Status: art study only.** No wiring, no version bump, no commit, no deploy.
The rejected `hardening/3.9.32-art-duplicates` and
`hardening/1.6.40-art-duplicates` branches are untouched and must not be
deployed. Nothing here writes to `resources/art/`, `static/art/`, `routes.py`,
the tests, or `preview.jpg`.

Seven representative rows are drawn in **two distinct directions**, each at
64 / 128 / 256 px with a 64 px row simulation, plus a native-256 1:1 board.
The full 38-row rollout waits for a direction decision.

---

## 1. Why 3.9.32/1.6.40 failed (diagnosis, not blame)

Two separate faults:

1. **Coordinate bug.** `make-duplicate-art.py` called
   `build_icon(..., size=512)`. `build_icon` allocates a `size * SS` canvas
   (1024 px) but every glyph painter is authored in a fixed **512** coordinate
   space. The glyph therefore landed in the top-left quarter at half size, then
   the whole canvas was downsampled. On a 256 px Kodi tile the mark occupied the
   top-left **128 px**, with a large empty field around it. That is the visual
   signature of the rejected sheet.
2. **Concept bug.** The glyph kit was shared: one lattice tower for every radio
   genre, a globe for both One Nation and World Dance, a cloud for both
   Mixcloud and SoundCloud, a "2" for Garage Nation. At 64 px those collapse
   into the same silhouette — a template with the label swapped.

This study does not reuse any of those glyphs or files. The render path is
`build_icon(size=256)` (glyph 512-space, canvas 512, downsample to 256), which
is the accepted original path.

**Production note for later:** do not reuse `build_icon(size=512)` for the web
assets until its glyph-coordinate scaling is fixed. Render the web 512 from a
1024 master whose glyph layer is scaled to 1024 (or draw all glyphs in
normalised coordinates). This is a wiring-stage fix, not part of the study.

---

## 2. What was referenced

- **Accepted originals:** `rave.png`, `tapepacks.png`, `jungle.png`,
  `hardcore.png`, `moxser.png`, `toronto.png`.
- **Accepted Toronto proof:** `docs/theme-2026/toronto-icon-sheet.png`
  (256 / 128 / 64 actual + 64 px row art).
- **Primitives/quality bar:** `scripts/make-art.py` and
  `docs/THEME-2026.md` — one spot-colour field, ink glyph, one partner-ink
  misregistration plate, halftone, 45° hatch, scanlines, crop marks, code,
  signal bars.
- **Precedent for type as mark:** `moxser.png` (the "M" is the glyph).
- **Constraints:** no drug imagery, no third-party logos/trademarks, no
  wordmark, one idea per tile, must read at 64 px.

---

## 3. Direction A — BIG MARK

**One oversized, custom-drawn object per row. No type.**

The mark fills roughly 65–75 % of the tile, is drawn as a single ink mass, and
is cut by two or three knocked-out details (reels, windows, ropes, stars). The
silhouette does the work; the texture is the shared print pass. This is the
direct continuation of the accepted `tapepacks` / `jungle` / `hardcore` /
`toronto` language.

Samples:

| Row | Object | Why it is that row |
|---|---|---|
| Rave Tape Packs | ghetto blaster | the machine the packs were played on; not another cassette |
| Podcasts | dynamic mic + cable | one object, unmistakable at 64 |
| Kool FM | pirate Yagi on a tower block | pirate broadcast from a roof, not the generic lattice tower |
| Dreamscape | heavy crescent + shooting star | the promoter's moon, one silhouette |
| Downloads | cassette unspooling into a down-arrow | the verb, with a tape-specific material |
| Radio Jungle | djembe + signal rings | jungle pressure, not a leaf/mask repeat |
| Rave Archive UK | VHS master + play triangle | the archive object, distinct from the audio cassette |

**Pros:** maximum individuality; closest to the accepted object language;
strongest answer to "individually designed, not batch-generated".
**Cons:** object recognition at 64 depends entirely on silhouette; a few rows
(Kool, Radio Jungle) need a small scene rather than one shape, so they are
busier. Extending to 38 needs 38 genuinely different objects and is slower.

---

## 4. Direction B — MONOGRAM

**One custom heavy letterform per row; the letter itself is built as the
subject.** Uses the accepted `moxser.png` precedent, but each letter is
hand-built, not a font with a texture behind it.

Samples:

| Row | Letter | Object built into the letter |
|---|---|---|
| Rave Tape Packs | R | the bowl counter opens into a tape reel; the leg is a ribbon |
| Podcasts | P | the bowl is a solid mic head with a slotted grille; the stem is a handle |
| Kool FM | K | the stem is a lattice mast, the arms are Yagi elements, signal rings off the top |
| Dreamscape | D | the counter holds a crescent moon; stars are knocked out of the face |
| Downloads | D | the counter is a down-arrow dropping into a tray; the stem carries a tape label |
| Radio Jungle | J | the stem is a mast with signal rings, the hook turns into a vine/leaf |
| Rave Archive UK | A | a big-top A: flag apex, tape-spine crossbar, play triangle in the counter |

**Pros:** survives 64 px better; reads as a coherent family; easy to extend to
38 without repeating silhouettes; very strong in a modern streaming list.
**Cons:** it is a family, and a family can be read as a system even when every
letter is bespoke. It is the opposite trade-off to A: less one-off weirdness,
more legibility and consistency.

---

## 5. Colour / texture

Each sample keeps the token rules: one spot colour, ink glyph, partner-ink
misregistration, halftone, hatch, scanlines, crop marks, code, signal bars.
The sample set deliberately varies the field so the rows do not read as a
single block:

| Row | Field | Misregistration |
|---|---|---|
| rave-tapes | acid | magenta |
| podcasts | magenta | cyan |
| kool | cyan | magenta |
| dreamscape | paper | magenta |
| downloads | orange | acid |
| radio-jungle | acid | magenta |
| rave-archive | paper | cyan |

The 38-row rollout will distribute acid / magenta / cyan / orange / paper
across the set the same way the accepted 20 do, not one colour per menu.

---

## 6. Files

All under `raveplayer/docs/theme-2026/directions-3.9.33/` (untracked):

| File | What it is |
|---|---|
| `direction-a-contact-sheet.png` | Direction A, 7 samples at 64 / 128 / 256 actual + 64 px row art |
| `direction-b-contact-sheet.png` | Direction B, same layout |
| `direction-1to1-preview.png` | all 14 at native 256, A above B, nothing scaled |
| `build_directions.py` | study generator; imports `make-art.py`, writes only into this folder |
| `DIRECTIONS.md` | this note |

The contact sheets are the review surface. Open the 1:1 board at 100 % to judge
the print texture; use the 64 px row art to judge list legibility.

---

## 7. Recommendation

**Artist's pick: A**, because the owner's note is specifically about
individually designed marks and A is the direct continuation of the accepted
object language. **If 64 px legibility and a coherent 38-tile family are the
hard constraints, pick B.** Do not mix the two: a mixed set would read as two
systems, which is the original problem in a new form.

The sample set is a gate, not the finished 38. After approval the production
pass would:

1. Draw all 38 rows in the chosen direction (31 remaining + the 7 proofs
   re-cut to the final grid).
2. Render Kodi 256×256 and web 512×512 from the corrected master path.
3. Keep `test/test_theme_art.py` (the duplicate-art guard and the 64 px size
   checks) unchanged.
4. Wire `MENU_ART` / `FILTER_ART` and the web art map.
5. Bump **3.9.33 / 1.6.41**, commit, and **not deploy**.

Until then: no branch changes, no version bump, no deploy.

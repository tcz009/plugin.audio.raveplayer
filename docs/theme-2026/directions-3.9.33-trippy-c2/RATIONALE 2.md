# Direction C2 — TRIPPY RAVE, RE-CUT

**Status: art study only. Nothing is wired, committed or deployed.** No file in
`resources/art/`, `static/art/`, `routes.py`, `test/` or `preview.jpg` was
touched, and the Direction C folder (`directions-3.9.33-trippy/`) is unchanged.
This folder is the whole deliverable.

---

## 1. What the note actually asked for

> "It's better, but we're talking about raves — one looks like a TV, one looks
> like a banana."

Two separate faults, and only one of them is about the *treatment*:

| Fault | Tile | Cause |
|---|---|---|
| reads as a TV | `radio-jungle` (C) | a cabinet **with two fronds sprouting off the top edge** — the appendages became rabbit ears |
| reads as a banana | `dreamscape` (C) | a **crescent** — a curved wedge with nothing else to say it is a moon |
| not rave at all | `podcasts`, `kool`, `downloads`, `pirate`, `curated`, `rave-nights` (C) | dynamic mic, transmitter mast, down-arrow, jolly-roger, gem, big-top — none of them is on the rave list |

C2 changes **one thing**: the object in the middle. Every part of the print
treatment the owner liked is kept — one spot field, one ink mass, hard
chromatic misregistration, drips, halftone, scanlines, crop marks, `RP-xx`,
signal bars, and the `rave.png` grin.

---

## 2. The rules that produced C2

1. **One object, no appendages.** Both of the owner's failures are appendage
   failures: something added to a body changed which class of object the tile
   belonged to. C2 draws the object and nothing else — no fronds, no antennae,
   no ribbon loops, no decorative stalks.
2. **Nothing that belongs to another class.** No rectangle with a bright inner
   rectangle (TV), no crescent (banana/moon), no triangle on a stick (tent), no
   arrow, no letterform, no gem, no mic.
3. **The identifying detail lives *inside* the ink mass.** In this system the
   accent plate is the field colour, so a detail drawn on the field is
   invisible; every ID cue (spools, cone rings, record grooves, grin, label) is
   knocked out *of* the ink. The silhouette therefore stays a single clean
   shape, which is what survives at 64 px.
4. **Melt is capped.** Drips only hang from the flat underside of the mark,
   never more than three, never long enough to merge into a new shape
   (`add_melt` with `max_len` 44–58 in 512-space).
5. **Faces only where the object has a face-shaped panel** — cassette shell,
   flyer sticker, balloon, smiley. 4 of 9, same ratio as C, so the family motif
   survives the re-cut.
6. **6 % larger than C.** Glyphs are scaled up 1.06 after drawing so the mark
   owns more of the tile at 64 px.

---

## 3. The re-cut, tile by tile

| Row | C (rejected) | Why it failed | C2 (now) | 64 px read |
|---|---|---|---|---|
| `tapepacks` | cassette with a grin | object was right, drawing was soft | **cassette**, re-cut: tape window, two spools with teeth, label-band grin, alignment holes | cassette — **sure** |
| `podcasts` | dynamic mic | generic mic, and banned | **rave flyer**: ink sheet, torn hem, sticker grin, three line-up rules, door tag | flyer / gig poster — **sure** |
| `kool` | tapering mast with an aerial smiley head | mast is not on the list; the head made it a "tower" | **lazer / scan lines**: two fat beams running off the tile with hot cores, a scan-bar stack, projector head | light beams — **good** (needs the row label) |
| `radio-jungle` | cabinet with palm fronds | fronds became rabbit ears → **TV** | **speaker stack**: two cabinets, cone + dust cap, screws, feet, no appendages | speaker stack — **sure** |
| `dreamscape` | crescent with a wink | crescent → **banana** | **smiley balloon**: balloon, knot, curled string, dot eye + wink + grin | balloon — **sure** |
| `downloads` | down arrow | banned | **archive cassette**, tilted, hand-written label, no face | cassette — **sure** |
| `pirate` | torn jolly-roger | not on the list | **vinyl / turntable**: deck, record with grooves, label, spindle, tonearm | record deck — **sure** |
| `curated` | gem | banned | **acid smiley**, the `rave.png` face (two dot eyes + grin; C's play-triangle eye read as a beak at 64) | smiley — **sure** |
| `rave-nights` | melting big-top | banned | **glowsticks**: two fat tubes, hot cores, knocked-out weave gap so they read as two objects | crossed glowsticks — **good** |

Two deliberate choices worth naming:

* **`tapepacks` and `downloads` are both tapes.** Eight objects cover nine
  rows, and the one repeat is the object nobody has ever misread: `tapepacks`
  is the grinning cassette, `downloads` is the same physical thing hand-
  labelled and tilted (the tape you kept). The alternative was a ninth object
  that failed the blind test (§4), which is the exact problem C2 exists to fix.
* **The smiley lost the play-triangle eye.** `rave.png` has a dot eye and a
  play-triangle eye; at 64 the triangle plus the grin read as a beak. C2 keeps
  the grin (the actual `rave.png` motif) and uses two dot eyes.

---

## 4. The 64 px blind test

Method: each tile is rendered at 256, downsampled with LANCZOS to 64 (the same
path the skin takes), then judged **without the row label** — on a dark list
panel, at 4× nearest-neighbour, next to the accepted originals at the same
size. A mark passed only if I could name the object without guessing. This is
the test `whistle` and `mixtape spine` did not survive.

| Draw | Result at 64 | Verdict |
|---|---|---|
| cassette / tape reel | reads as a cassette | kept (twice) |
| acid smiley | reads as a smiley | kept |
| speaker stack | reads as a speaker cabinet | kept |
| vinyl / turntable | reads as a record deck | kept |
| glowstick | reads as two crossed tubes | kept (front/back weave gap added) |
| smiley balloon | reads as a balloon | kept |
| rave flyer | reads as a poster/flyer | kept |
| lazer / scan lines | reads as beams from a projector | kept, weakest of the nine |
| **whistle** | read as a camera/kettle — the L-shape plus ring is too small to parse | **cut** |
| **mixtape spine** | read as a phone/USB stick; a three-spines-in-a-crate version read as fingers | **cut** |
| **open tape reel** | read as a steering wheel / plug socket | **cut** |
| down-arrow, gem, big-top, dynamic mic, mast, jolly-roger, crescent | the objects C used | **cut** |

The vocabulary sheet (`c2-vocabulary-64px.png`) shows only what survived;
the cut list is printed at the bottom of it, so the next person does not
re-draw them.

---

## 5. The nine tiles

| Row | Object | Field | Plates | Code |
|---|---|---|---|---|
| `tapepacks` — Rave Tape Packs | cassette | acid | magenta / cyan | RP-03 |
| `podcasts` — Podcasts | rave flyer | magenta | cyan / acid | RP-27 |
| `kool` — Kool FM | lazer / scan lines | cyan | magenta / acid | RP-31 |
| `radio-jungle` — Jungle | speaker stack | acid | magenta / cyan | RP-34 |
| `dreamscape` — Dreamscape | smiley balloon | paper | magenta / cyan | RP-40 |
| `downloads` — Downloads | archive cassette | cyan | magenta / acid | RP-55 |
| `pirate` — Pirate Radio | vinyl / turntable | magenta | acid / cyan | RP-19 |
| `curated` — Curated Gems | acid smiley | acid | cyan / magenta | RP-06 |
| `rave-nights` — By Rave & Venue | glowsticks | cyan | magenta / acid | RP-25 |

Colour rhythm is the accepted rhythm: acid ×3, magenta ×2, cyan ×3, paper ×1;
plates are always two of magenta / cyan / acid, never the field. Codes are the
same `RP-xx` placeholders as C so the two sheets compare row for row.

**Faces:** cassette, flyer sticker, balloon, smiley — 4 of 9.

---

## 6. The print recipe (unchanged from C, imported not copied)

The generator imports Direction C's `build_direction_c.py` read-only and reuses
its `Pen`, `wobble`, `add_melt`, `spatter`, `warp`, `warp_alpha`, `shift`,
`halftone`, `scanlines`, `grain`, `grin`, `eye`, `squiggle` and furniture, and
C in turn loads palette/fonts from `scripts/make-art.py`. The treatment cannot
drift between the two directions; only the glyph painters are new.

Per tile, 512 design space rendered at 1024:

1. vertical gradient of the field colour (13 % toward paper at the top);
2. a riso halftone "sun" in plate 1, off-centre, blue-noise jitter;
3. one hand-drawn corner squiggle in plate 2, always top-left;
4. the glyph: hand-drawn wobble on every path, melt drips off the flat
   underside, ink spatter, optional rotation;
5. two chromatic plates taken from the same alpha, **each warped on its own
   phase** and offset (−7, −5) and (+6, +6), so the edges separate unevenly;
6. the ink body, warped with a sag term;
7. coarse halftone over the ink, scanlines, grain;
8. crop marks, `RP-xx`, signal bars, 1 px keyline;
9. downsample to 256 with LANCZOS, then 128 and 64.

---

## 7. Files

| File | What it is |
|---|---|
| `c2-contact-sheet.png` | the review surface: 9 rows, each at **64 / 128 / 256 actual**, a **64 px Kodi list row**, the accepted originals at 64 px in the header, plus `WAS` / `NOW` / `64 READ` per row |
| `c2-1to1.png` | all nine at native 256 — judge melt, registration and hand-line at 100 % |
| `c2-64px-rows.png` | every tile as a 64 px row on a dark list panel, accepted originals at 64 px underneath |
| `c2-before-after-64px.png` | the re-cut: C at 64 + 128 next to C2 at 64 + 128, with the object and the blind read for each row |
| `c2-vocabulary-64px.png` | the nine objects at 64 / 128 with names, plus the cut list |
| `sample-<row>.png` | the 256 px tile for each row |
| `64/`, `128/`, `256/` | every sample exported at the three sizes |
| `build_direction_c2.py` | the generator (Pillow + numpy, build-time only) |
| `RATIONALE.md` | this note |

Reproduce:

```sh
python3 build_direction_c2.py            # all sheets
python3 build_direction_c2.py --preview  # fast silhouette check only
```

The script writes only inside this folder.

---

## 8. What I would still watch

* **`kool` (lazer)** and **`rave-nights` (glowsticks)** are the two "good, not
  sure" reads. Both are rave objects; neither needs a caption to be *rave*,
  but each needs one glance rather than none. If the owner wants nine "sure"
  reads, the next move is to give `rave-nights` the flyer (venue listings are
  literally flyers) and move `podcasts` to a second cassette — the repeat this
  sheet already accepts.
* **38 rows from nine objects** means repeats, not new vocabulary. Cassette,
  smiley, balloon, flyer and speaker will each carry four or five rows; each
  repeat needs its own pose, not a recolour. Budget accordingly: the blind test
  is per-object, so repeats are cheap and new objects are expensive.
* **The whistle and the mixtape spine are allowed but not usable at 64 px in
  this treatment.** If a row needs them, they need a bigger silhouette (a
  whistle held in a hand-sized crop, three spines as a *block* with visible
  case ends), not a caption.
* Nothing here is wired: `MENU_ART` / `FILTER_ART`, the Kodi 256 and web 512
  renders, the **3.9.33 / 1.6.41** bump, commits and deploy all remain
  untouched until the owner approves the direction.

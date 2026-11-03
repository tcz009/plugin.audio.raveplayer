# Live Radio station tiles — 2026 sticker study

**Status: art study only.** No wiring, no version bump, no commit, no deploy.
Ten samples at 64 / 128 / 256 px plus a dedicated 64 px row mock, for owner
approval.

---

## 1. What this is

Ten original, code-drawn station tiles for the Live Radio rows, in the accepted
2026 screen-print language:

- one hero mark per row, readable at **64 px**;
- a bright field, ink glyph, hard two-plate chromatic misregistration;
- halftone sun, loose squiggles, scanlines, grain;
- crop marks, catalogue code and signal bars as the family glue.

The owner's brief is that the stations' identities should "blend in" with the
accepted stickers, not arrive as imported logos. These are **evocations**:
Kool FM gets the acid smiley / melted grin and a KOOL code texture; Rinse FM
gets broken ripple rings and a rinse wave, with no wordmark. The genre rows get
one distinct trippy/rave motif each — no shared transmitter, no template with
the label swapped.

### Coordinating with Direction C

The in-progress **Direction C (trippy rave)** study supplies the grammar:
wobbled ink, melt drips, two chromatic plates, riso sun, scanlines and grain.
This station set keeps that grammar but tunes it for a named-station list:

- **bigger, quieter silhouette** — one mark, not a scene;
- **0–3 drips**, not the full Direction C melt;
- **a calmer field** so the ink reads at 64 px;
- **KOOL code columns** as texture, and **no type at all** on Rinse.

It is not a fourth direction. It is a station-specific cut of the same family,
allowed to be a little bolder than the generic row study.

---

## 2. Rows and motifs

| Row | Motif | Field / plates | Why it reads at 64 px | Deliberately not copied |
|---|---|---|---|---|
| **Kool FM** | Melted acid smiley: X eye, spiral eye, dripped grin, magenta rim; KOOL code columns | acid / magenta + pink | one huge face; one X, one spiral, one bright grin; the code columns become texture | no Kool logo or wordmark; `KOOL` is only a code texture / tag |
| **Rinse FM** | Three broken ripple rings cut by one rinse wave; droplet with a cyan spiral at the eye | cyan / deep teal + pale cyan | concentric rings and a clear wave channel; a centre drop | no Rinse wordmark; no ring-logo trace — the rings are deliberately broken and offset |
| **Oldskool & Rave** | Melting clock face on an acid rave starburst, sagging into a puddle | magenta / acid + cyan | clock hands + four ticks + spikes; the puddle is the melt | no event, flyer or station logo |
| **Jungle** | Fiddlehead fern curled around a single eye, broad leaves behind the coil | acid / magenta + cyan | spiral + eye + leaf silhouettes; no mask repeat | no mask, no third-party mark; original botanical motif |
| **Drum & Bass** | Snare drum over a two-cycle sub-bass wave; crossed sticks behind | cyan / magenta + acid | drum + X + wave; the wave is a clean sine, not a scribble | no label or station logo; instrument build |
| **Hardcore** | Circular siren beacon: radial grille, lightning bolt, one jagged pressure ring | orange / acid + magenta | black disc + acid bolt + zigzag halo; unmistakable at 64 | no bolt or event copy; the bolt is drawn, not traced |
| **House** | Four kick drums around a jackin' clap star | paper / cyan + magenta | four drums + centre star; reads as a four-on-the-floor pattern | no house pictogram, no label/station logo |
| **UK Garage** | Warped roller door with canopy and side tracks; 2-step cyan chevrons; rewind loop | magenta / cyan + acid | door frame + slats + chevrons; the canopy stops it reading as a cassette | no "2" monogram, no station logo |
| **Breakbeat** | Vinyl snapped at the break; the two halves offset, wide jagged crack, play triangle | acid / cyan + magenta | broken black disc + bright gap + triangle | no label or break logo |
| **Pirate Stations** | Skull in headphones over crossed Yagi aerials | paper / magenta + acid | skull + acid headphones + crossed masts; one silhouette | no station logo; generic pirate-radio code |

The Kool code columns and the `KOOL-01` tag are the only station name on any
tile. They are small, repeated and low-contrast: at 256 px they read as a
sticker-code texture, at 64 px they collapse into texture. Rinse has no type.

---

## 3. Files

| File | What it is |
|---|---|
| `contact-sheet.png` | The review surface: all 10 rows at 64 / 128 / 256 actual, with a 64 px row mock and the accepted originals for a family check |
| `stations-1to1.png` | All 10 at native 256, nothing scaled — judge the ink, melt, misregistration and print texture at 100 % |
| `stations-64px-rows.png` | Dedicated 64 px Kodi/web list-row check, with the accepted originals strip |
| `samples/` | Per-station `-64.png`, `-128.png`, `-256.png` (30 files) |
| `build_stations.py` | The generator; writes only into this folder |
| `LEGAL.md` | The short nominative-use note |

The contact sheet is the approval surface. Use the 64 px row sheet for list
legibility and the 1:1 board for texture.

---

## 4. Reproduce

```sh
python3 build_stations.py
```

Requires Pillow and numpy (build-time only). On this machine the system
`python3` does not have Pillow; any Python with Pillow + numpy works. The
script imports palette/fonts from `../../../scripts/make-art.py` so the
family tokens stay identical, then writes only into this folder.

It does **not** write to `resources/art/`, `static/art/`, `routes.py`, the
tests, `preview.jpg`, git, or any deployed asset.

---

## 5. Next step

This is a gate, not the production pass.

1. Owner approves the direction (or asks for changes).
2. Only then: render the approved set at 256 (Kodi) and 512 (web) from the
   same master path, wire `MENU_ART`, and add the 64 px size test.
3. No commit and no deploy until that separate request.

Until then: sheet only.

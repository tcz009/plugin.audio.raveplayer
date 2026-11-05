# Look overhaul — 2026 sticker language everywhere

**Branch:** `feat/look-overhaul` (Kodi base `integration/3.9.48`, web base
`main` 1.6.51) · **Scope:** visual/UX only · **No deploy.**

The Rave Screen already carried the 2026 language (ink/paper, one spot per
surface, halftone, hard sticker shadows, baked Impact, RP print furniture).
This pass moves the same language into the plugin's native Kodi lists and the
web surface, without touching a parser, a route, a cache or a playback path.

**Design source:** [`docs/rave-screen/RAVE-SCREEN-DESIGN.md`](rave-screen/RAVE-SCREEN-DESIGN.md)
(and `WINDOWXML-CONTROL-MAP.md` beside it), with the accepted assets shipped in
[`script.raveplayer.ui/resources/art/rave-screen/`](../script.raveplayer.ui/resources/art/rave-screen/).
No new typeface, logo, wordmark or glyph was introduced. No font file ships.

---

## 1. At a glance

| Surface | Before | After |
|---|---|---|
| Kodi native list | one word per row, square cover stretched into 16:9 fanart, toast-only failures, About rows with no right column | sticker + cover + 16:9 fanart, Label2 facts, descriptions, visible STANDBY/ERROR rows with retry, labelled About sources |
| Rave Screen | close to the design, but uppercase row labels | sentence-case rows (hero still uppercases), same hero/rows/footer/Surprise geometry |
| Web | strong dark/paper themes, but rows had no fact column and focus used a 2 px inset | 48 px row unit, 8 px grid, acid 4 px focus bar + hard offset, mono Label2 facts, printed STANDBY/ERROR plates, ink focus ring on paper |
| Assets | 17.0 MB web stickers at 512 px | 7.8 MB at 256 px (−10.7 MB), every reference verified |

**Test totals:** Kodi **663 passed** (`python3 -m unittest discover -s test`);
web offline **507 passed** (`pytest test`); web browser suite **36 passed**
(`pytest test_e2e`, Chromium, no skips).

---

## 2. Kodi native lists

### 2.1 The semantics (what a row means now)

| Row kind | `icon` | `thumb` / `poster` | `fanart` / `landscape` |
|---|---|---|---|
| Tape pack (Archive, Latest, Favourites) | 256² cassette sticker (`tapepacks.png`) | the pack front | 1280×720 destination fanart |
| Live radio station | 256² `radio.png` | the station favicon, else `radio.png` | 1280×720 live fanart |
| Track inside a pack | 256² cassette sticker | the square pack cover | **brand 16:9 fanart** (was the cover, stretched) |
| Show / podcast / download / About | its destination sticker | same sticker (no cover exists) | 1280×720 fanart |

Kodi skins read different art slots: IconWall uses `poster` first, the info
panel uses `thumb`, the skinny list uses `icon`. All three are now set
explicitly, and `landscape` mirrors `fanart`, so a square image can never land
in a 16:9 slot. `archive_item`'s play URLs no longer carry a square `fanart`.

### 2.2 Right column and descriptions

Every root and hub row now carries a Label2 fact (≤16 chars, the existing
`ui.fact` budget) and a video `plot` (Kodi 22's `ListItem.Plot` resolves from
the video InfoTag). About & Sources had no second column at all; its fifteen
rows now read `GPL-3.0`, `archive.org`, `web-only`, `directory`, `mondon`,
`hardscore.com`, … instead of a second title. Track rows keep duration / year
facts and the artist-album-year-genre-track InfoTags shipped in 3.9.44.

### 2.3 Loading / empty / error status lines

Toasts are four seconds; an empty directory is permanent. New
`ui.status_item()` rows are real, focusable rows with a spot-colour tag and a
retry URL:

| Route | State | Row |
|---|---|---|
| `latest` | no source answered | `STANDBY  Nothing new right now` → OK retries `mode=latest` |
| `archive_list` | no docs | `STANDBY  Nothing in <section> right now` → OK retries the section |
| `search` | no docs | `STANDBY  No results for “q”` → OK retries the query |
| `downloads_menu` | no downloads | `STANDBY  No downloads yet` → OK refreshes |
| `fav_list` | no favourites | `STANDBY  No favourites yet`; the Downloads door stays visible |
| `archive_item` | no audio | `ERROR  This pack has no playable audio` → OK reloads the pack |
| `station_live` / `radio_tag` | no stream | `STANDBY  …` → OK rescans |

Loading itself remains Kodi's own directory spinner plus one short toast (a
native plugin directory cannot draw a live progress line without a modal
overlay; that would be worse for usability).

### 2.4 Row order

The shared rooms follow the web rail order exactly:

| # | Kodi root | Web rail |
|---|---|---|
| 1 | Latest | Latest |
| 2 | Tape Packs | Tape Packs |
| 3 | Pirate Radio | Pirate Radio |
| 4 | Mixes & Shows | Mixes & Shows |
| 5 | Live Radio | Live Radio |
| 6 | Favourites | Favourites |
| — | (Favourites → Downloads) | Downloads |

Kodi adds three non-rail doors at the end (Search, Surprise, About) and the
Rave Screen entry at the top; Downloads stays a child of Favourites in Kodi
because that hub is the native "saved" surface and adding an eleventh root card
would reflow Estuary's 4×n grid for one duplicate. No route or URL changed.

### 2.5 Focus ring — honest limit

Native directory focus is **skin-owned**. An add-on ListItem cannot draw a
focus plate, ring or bar in Estuary's views; the only motion/emphasis the add-on
owns is *what changes* on focus (its fanart and its art panel). We therefore
did not fake a focus ring with a texture that would sit under every row. The
focus furniture that *is* ours — the Rave Screen bar/plate/cyan twin and the
web `:focus-visible` ring — is the same acid-on-ink language.

### 2.6 WindowXML wrapper for Favourites / Downloads / Search — decision

**Not shipped.** A wrapper would replace Kodi's native directory, and with it:

- the context menus (`Play all`, `Shuffle`, `Download`, `Delete download`,
  `Add/Remove favourite`) that are part of the current UX;
- Kodi's queue/playlist hand-off and the `IsPlayable` contract on every track;
- the search keyboard (`xbmcgui.Dialog().input`) and its IME on Shield/Android;
- sort/scroll behaviour and the skin's own view modes, on every skin.

The Rave Screen is the one place where a full-window browse is worth that
trade (it has its own controller and proven D-pad path). Favourites, Downloads
and Search stay native, now with the same row semantics and status lines.
The reliable middle ground is shipping a *read-only* screen for a subset
later, not replacing these directories.

---

## 3. Rave Screen

The 3.9.48 screen is already at the design geometry; this pass only corrected
the voice:

- Home row labels are **sentence case** (`Latest`, `Toronto Rave Mixtape
  Archive`, `JungleTapes.com`, `RaveTapePacks.com`, `Live Radio`, `Spinning
  Surprise`). The hero title still uppercases for display only, so the row and
  the poster no longer shout the same string twice.
- The focus plate (474×40), acid bar (6×34), magenta plate shadow, cyan label
  twin, separator, hero 640×360, footer plate and Surprise burst/ring/head
  remain exactly as the design map; no control was moved.
- Textures were re-checked: all 35 `special://` texture references resolve, and
  only `font10/12/13` are used. No missing texture, no TTF.

Target renders (design mockups, not device captures):
[home](look-overhaul/after/rave-screen-home.jpg) ·
[Spinning Surprise](look-overhaul/after/rave-screen-surprise.jpg).

---

## 4. Web parity

Tokens are unchanged where the spec pins them (`--ink #07070b`,
`--paper #f2eee3`, `--muted`, `--acid`, `--magenta`, `--cyan`). The pass adds
the missing print grid and the focus/status language:

- **Grid:** `--space-1/2/3/4/6/8/12` (4/8/12/16/24/32/48) and `--row-h: 48px`;
  rows use the 48 px art slot and 8×12 padding.
- **Rail:** active row is a 4 px acid inset slab with a hard 3 px magenta (dark)
  or ink (light) offset — the Rave Screen focus bar, not a soft glow.
- **Rows:** hover/focus gets the same 4 px acid bar; `row-fact` renders a
  duration/count in mono at the 16-character Label2 budget.
- **Status:** `.empty` is a dashed printed plate with a `STANDBY` kicker;
  `.state` gets a 4 px acid (or magenta for errors) left rule.
- **Focus:** one `--focus-ring` token; acid on ink, ink on paper.
- **Light/dark:** the light theme overrides every new element (rail shadow,
  row bar, fact, empty/error plate, focus ring) so the paper mode is still
  intentional rather than an afterthought.
- **Unchanged:** the inline embed dock markup/JS, the single-audio policy, the
  service worker/PWA manifest and the offline cache. The dock keeps its own
  light/dark rules; the only shared change is the focus ring token.

Before/after (real Chromium captures, 1.6.51 fixtures):

| View | Before | After |
|---|---|---|
| Latest, dark 1280 | [before](look-overhaul/web/before/latest-dark.jpg) | [after](look-overhaul/web/after/latest-dark.jpg) |
| Latest, light 1280 | [before](look-overhaul/web/before/latest-light.jpg) | [after](look-overhaul/web/after/latest-light.jpg) |
| Phone, dark | [before](look-overhaul/web/before/phone-dark.jpg) | [after](look-overhaul/web/after/phone-dark.jpg) |
| Embed dock | [before](look-overhaul/web/before/embed-dock.jpg) | [after](look-overhaul/web/after/embed-dock.jpg) |
| Tape Packs, light | [before](look-overhaul/web/before/tape-packs-light.jpg) | [after](look-overhaul/web/after/tape-packs-light.jpg) |

---

## 5. Native before/after boards

Rendered from the add-on's **real ListItems** through the `test/stubs` Kodi
shim, using the 3.9.36 Estuary geometry renderer in
`docs/look-dev/tools/make-look-shots.py`. These are approximations, not device
captures: fonts are Arial/Courier/Impact stand-ins and the focus zoom is not
shown. `before/` is the pristine `integration/3.9.48` worktree; `after/` is this
branch; both were captured with the same tool and fixtures.

| Screen | Before | After |
|---|---|---|
| Root (Estuary IconWall) | [before](look-overhaul/before/native-root.jpg) | [after](look-overhaul/after/native-root.jpg) |
| Tape Packs hub | [before](look-overhaul/before/native-packs.jpg) | [after](look-overhaul/after/native-packs.jpg) |
| Pack tracks (WideList + panel) | [before](look-overhaul/before/native-tracks.jpg) | [after](look-overhaul/after/native-tracks.jpg) |
| About & Sources (Label2 facts) | [before](look-overhaul/before/native-about.jpg) | [after](look-overhaul/after/native-about.jpg) |
| Latest, no sources (status row) | [before](look-overhaul/before/native-empty.jpg) | [after](look-overhaul/after/native-empty.jpg) |

What visibly changes in the tracks board: the row icons become cassette
stickers instead of 180 px service thumbnails, the background stops stretching
a square cover and uses the 16:9 brand fanart, and the right column prints the
real durations. The empty board goes from a blank directory to a retryable
`STANDBY` row.

Regenerate:

```sh
# before (pristine base worktree)
LOOK_REPO=../raveplayer-worktrees/integration-3.9.48 \
LOOK_OUT=$PWD/docs/look-overhaul/before \
python3 docs/look-overhaul/tools/make-native-shots.py

# after (this branch)
LOOK_REPO=$PWD LOOK_OUT=$PWD/docs/look-overhaul/after \
python3 docs/look-overhaul/tools/make-native-shots.py
```

---

## 6. Assets

- **Reuse, not redesign:** the screen uses the accepted design asset set in
  `script.raveplayer.ui/resources/art/rave-screen/`. The native list uses the
  existing 256² sticker family. No new external art direction.
- **No fonts:** display type stays baked into PNGs; live type is the skin's
  sans. No `@font-face`, no TTF in either repo.
- **Missing textures:** zero. A test walks every `special://` texture in the
  Rave Screen XML and every literal art filename in `resources/lib`; both sets
  resolve. The web API/rail art references resolve too.
- **Size optimisation:** 50 web stickers over 256 px were resampled to 256²
  with Lanczos (rail renders at 22 px, row art at 48 px, player at 54 px):
  **17.0 MB → 7.8 MB (−10.7 MB, −62 %)**. Identity assets (`icon.png` 512,
  `icon-180.png`) were not touched. A PIL re-encode audit of the remaining
  PNG/JPEGs found no further lossless gain (they are already palette/optimised
  or are the 1920×1080 QA beds the design spec deliberately keeps).

---

## 7. Tests

Kodi (`python3 -m unittest discover -s test`): **663 passed**.

- New `test/test_look_overhaul.py`: token hex parity with the design spec,
  root-vs-web order, facts/plots on every root and hub row, tape/radio/cover
  art semantics, 16:9 fanart, About facts, seven status-line routes, XML
  texture existence, stock-font-only, focus furniture, sentence-case labels.
- Updated `test/test_playlist.py`, `test/test_routes.py`,
  `test/test_rave_screen.py` for the intended art/status/label changes.

Web (`pytest test`): **507 passed** (500 baseline + 7 new).

- New `test/test_look_overhaul.py`: space/row/focus tokens, rail focus bar,
  48 px row + hover bar, mono fact with `textContent`, printed STANDBY/error
  plates, light-theme overrides, no external font.
- `pytest test_e2e` (Chromium): **36 passed** — including the embed dock at
  1280 and 390, single-audio checks, PWA/offline, and the dark/light/p hone
  screenshot flows. Screenshots above are written by that suite.

---

## 8. Files touched

**Kodi** (`raveplayer`, branch `feat/look-overhaul`)

- `resources/lib/look.py` (new) — tokens, RP codes, status tags.
- `resources/lib/ui.py` — art slots, Label2/plot, `status_item`.
- `resources/lib/routes.py` — tape/radio icons, covers, 16:9 fanart, About
  facts, status rows (latest/archive/search/downloads/favourites/pack/radio).
- `script.raveplayer.ui/raveui/data.py` — sentence-case rows.
- `test/test_look_overhaul.py` (new); `test/test_routes.py`,
  `test/test_playlist.py`, `test/test_rave_screen.py` updated.
- `docs/LOOK-OVERHAUL.md`; `docs/look-overhaul/` (boards + renderer).

**Web** (`Rave Player`, branch `feat/look-overhaul`)

- `static/app.css` — grid/focus tokens, rail bar, row fact/bar, status plates,
  light-theme parity.
- `static/app.js` — `row-fact` (duration/fact, 16 chars, `textContent`).
- `static/art/*.png` — 50 stickers resampled to 256² (identity icons kept).
- `test/test_look_overhaul.py` (new); `docs/LOOK-OVERHAUL.md`;
  `docs/look-overhaul/web/` (before/after).

---

## 9. What this pass deliberately did not do

- No parser, route, URL, cache TTL, prebuffer or playback change.
- No deploy, no version bump, no repo zip rebuild.
- No new font, logo, wordmark or glyph.
- No WindowXML replacement of Favourites/Downloads/Search (see §2.6).
- No claim of device capture: the native boards are Estuary-geometry renders
  and the web boards are Chromium; the Shield QA checklist in
  `docs/QA-KODI.md` still applies.

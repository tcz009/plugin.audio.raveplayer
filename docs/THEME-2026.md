# Rave Player — Kodi theme 2026

**Status:** implemented on branch `theme/3.9.16` (off `main @ b0a515a`, add-on
3.9.16); the Toronto source sticker (`RP-20`) was added in **3.9.31** without
changing the system. **Direction from the owner:** brutalist, modern
streaming-app energy; **bling what exists, don't redesign it.** The logo,
wordmark and identity are untouched. This is a Kodi-surface pass only — no skin
fork.

This document is the token/visual spec, the asset map, and the honest list of
what a Kodi add-on can and cannot control on that surface.

---

## 1. What changed (and what did not)

### Changed
- **20 sticker icons** in `resources/art/` at Kodi size **256×256 PNG** — the
  2026 treatment of the existing glyph language: bright spot-colour tile,
  black ink glyph, hard misregistration, halftone screen, crop marks,
  scanlines, sticker code.
- **18 fanarts** in `resources/art/` at **1280×720 JPG** — one per root
  destination (9), one per hub screen (4) and one per key source (5).
- **Root menu rows now carry their own icon + fanart**, and the four hubs pass
  a hub fanart to every row, so a skin that shows the focused item's fanart
  gives each destination its own room (code: `resources/lib/routes.py`).
- **Fixed three real art bugs** found while mapping the surface:
  `pirate_source.png` was referenced five times but **never existed** (Pirate
  Radio Archives had no icon); root rows for *Favourites* and *About & Sources*
  both used `about.png`; *Surprise Me* and *Tape Packs* both used
  `tapepacks.png`.
- New `docs/theme-2026/` before/after menu renders + captured ListItem JSON.
- Tests: 334 → **344** (`test/test_theme_art.py`).

### Not changed (identity guardrails)
- `icon.png` and `fanart.jpg` at the add-on root — the wordmark identity. Not
  regenerated, not edited.
- Palette, glyph vocabulary, "The Last Transmission" concept, the smiley/play
  mark, copy, menu structure, routing and every `mode=`/`key=` deep link.
- No skin files, no skin fork, no Kodi settings forced on users.

---

## 2. Tokens

### 2.1 Colour

| Token | Hex | Use in this pack |
|---|---|---|
| ink | `#07070b` | glyphs, plates, background wash |
| ink-2 | `#0b0b11` | fanart base, footer |
| paper | `#f2eee3` | fanart display type, icon frame, light tiles |
| muted | `#a8a399` | secondary fanart text, hints |
| acid | `#e8ff00` | Latest, Curated Gems, pirate/flag, Moxser, focus rule |
| magenta | `#ff2d8f` | Surprise, Mixes, Favourites, jungle, GetDarker |
| cyan | `#22e6ff` | Tape Packs, Live Radio, house, Toronto, emphasis |
| orange | `#ff6a1a` | Hardcore, Hardscore (energy sources only) |

Icons are **one spot colour per tile plus ink** — the screen-print rule from
`ARTWORK.md`. A tile is never multi-colour: the second signal colour appears
only as the misregistration plate (see 2.3).

### 2.2 Type

| Role | Face | Notes |
|---|---|---|
| Display | **Impact** | fanart words, sticker codes. Condensed, caps, tight tracking. |
| UI (Kodi renders it) | skin font — we cannot choose it | labels must survive any skin's sans |
| Mono/catalogue | system mono (fanart only) | sublines, code tags, `RP-01`… |

The add-on **cannot set the skin's fonts** (see §5). Impact only appears inside
our artwork. Labels are plain text; keep them short and skin-agnostic.

### 2.3 Icon grid (256×256 PNG)

```
┌──────────────────────────────┐  256 px square, opaque
│ ⌐                         ¬  │  crop marks: ink 3 px, inset 14, length 22
│   ┌────────────────────┐     │  inner frame: ink 1 px @ 70 alpha, inset 5
│   │                    │     │
│   │      GLYPH         │     │  glyph: ink, ~62 % of tile, centred
│   │      (ink)         │     │
│   │                    │     │
│   └────────────────────┘     │
│ RP-01                  ▂▄▆  │  mono code bottom-left; 3-bar signal bottom-right
└──────────────────────────────┘
```

- **Tile** = one spot colour, gentle vertical tint (`+5 % paper` top →
  `−14 % ink` bottom), halftone dot screen (spacing 7, alpha 30), 45° hatch
  (alpha 10), scanlines (period 7, alpha 12).
- **Misregistration** = the glyph alpha duplicated once, shifted **−5,−5 px**
  and coloured with the tile's partner signal (acid↔magenta, cyan↔magenta,
  orange↔acid, paper↔magenta/cyan). This is the 2026 "print pass" that gives
  the tile its energy.
- **Glyph** = the real mark, solid ink, knocked-out details in the tile colour.
- **Code tag** `RP-01…RP-20` for catalogue flavour, never required to be read.
- **Do:** keep one idea per tile, max 2 shapes, generous ink mass.
- **Don't:** put text in the icon (Kodi already draws the label), use a second
  spot colour, add a logo/wordmark, use thin hairlines that vanish at 64 px.

**Legibility target:** the glyph must read at **64×64** in a list row. Check via
`python3 scripts/make-art.py` then the `resources/art/preview.jpg` sheet.

### 2.4 Fanart grid (1280×720 JPG)

```
┌──────────────────────────────────────────────────────────┐ 1280×720, q92
│ hazard  ┌─ dark for Kodi list panel (left 46 %) ─┐        │
│ strip   │  (keep quiet: no type here)             │  ●sun  │
│ (left)  │                                         │  glyph │
│         │                                         │  mark  │
│         │        ← word starts at x = 50 % →     │        │
│         └─────────────────────────────────────────┘        │
│  RP · THEME 2026                            01            │  index
└──────────────────────────────────────────────────────────┘
```

- **Left 46 % stays dark and quiet** — that is where Kodi (Estuary, etc.)
  draws the list panel; type placed there is covered.
- Display word starts at **x = 50 %**, baseline **y = 43 %**, Impact, paper,
  with a **12 px down-right accent misregistration**. Auto-fitted to the safe
  width.
- Subline in tracked mono below the word, with a short accent rule.
- Oversized section-glyph silhouette behind the type at ~46 alpha (identity
  without repetition).
- Accent "sun" radial, halftone screen, hazard strip on the far-left edge,
  crop marks, scanlines, 4-level grain.
- **No wordmark/logo in fanart.** The wordmark only lives in the untouched
  root `fanart.jpg` / `icon.png`.

### 2.5 Motion / texture

There is no motion layer: Kodi skins own transitions. Texture is static print:
halftone dots, 45° hatch, scanlines, grain, hard misregistration. Do not add
blur, glow, glass or gradient "premium" finishes — the language is screen-print,
not glassmorphism.

---

## 3. Surface map

### 3.1 Nine root rows

| # | Root row | Icon (256) | Fanart (1280×720) | Accent | Glyph |
|---|---|---|---|---|---|
| 1 | Latest | `rave.png` | `fanart-latest.jpg` | acid | smiley / play-wink |
| 2 | Surprise Me | `surprise.png` | `fanart-surprise.jpg` | magenta | die |
| 3 | Tape Packs | `tapepacks.png` | `fanart-tapepacks.jpg` | cyan | cassette |
| 4 | Mixes & Shows | `mixes.png` | `fanart-mixes.jpg` | magenta | headphones |
| 5 | Live Radio | `radio.png` | `fanart-live.jpg` | cyan | transmitter |
| 6 | Curated Gems | `curated.png` | `fanart-curated.jpg` | acid | gem |
| 7 | Favourites | `favourites.png` | `fanart-favourites.jpg` | magenta | heart / play cut |
| 8 | Search the Archive | `search.png` | `fanart-search.jpg` | paper | magnifier |
| 9 | About & Sources | `about.png` | `fanart-about.jpg` | paper | info |

### 3.2 Four hub screens (fanart applied to every row in the hub)

| Hub | Fanart | Rows use |
|---|---|---|
| Tape Packs | `fanart-hub-packs.jpg` | shared hub fanart |
| Mixes & Shows | `fanart-hub-shows.jpg` | shared hub fanart, sources override |
| Live Radio | `fanart-hub-live.jpg` | shared hub fanart |
| Curated Gems | `fanart-hub-curated.jpg` | shared hub fanart, sources override |

### 3.3 Key sources (own icon + fanart)

| Source | Icon | Fanart | Accent |
|---|---|---|---|
| Moxser | `moxser.png` | `fanart-moxser.jpg` | acid |
| Hardscore | `hardscore.png` | `fanart-hardscore.jpg` | orange |
| GetDarker | `getdarker.png` | `fanart-getdarker.jpg` | magenta |
| Pirate Radio Archives | `pirate-archive.png` | `fanart-pirate-archive.jpg` | acid |
| Toronto Rave Mixtape Archive | `toronto.png` | `fanart-toronto.jpg` | cyan |

Hub-row icons are the existing section stickers, updated to the 2026 treatment:
`rave`, `jungle`, `hardcore`, `house`, `garage`, `pirate`, `tapepacks`, `radio`,
`djez` (Classic Pack Series filters), `search`, `about`.

### 3.4 Full icon list (20 files)

`rave` `surprise` `tapepacks` `mixes` `radio` `curated` `favourites` `search`
`about` `jungle` `hardcore` `house` `garage` `pirate` `djez` `moxser`
`hardscore` `getdarker` `pirate-archive` `toronto`

### 3.5 Full fanart list (18 files)

`fanart-latest` `fanart-surprise` `fanart-tapepacks` `fanart-mixes`
`fanart-live` `fanart-curated` `fanart-favourites` `fanart-search`
`fanart-about` `fanart-hub-packs` `fanart-hub-shows` `fanart-hub-live`
`fanart-hub-curated` `fanart-moxser` `fanart-hardscore` `fanart-getdarker`
`fanart-pirate-archive` `fanart-toronto`

---

## 4. Labels, copy and spacing (what we can actually set)

- **Label length:** aim ≤ 24 characters. Kodi truncates based on skin width;
  assume ~30 characters at 1080p in Estuary.
- **Case:** sentence case or clear short caps; Kodi/skins may capitalise, so
  never rely on case for meaning.
- **Separators:** ` · ` and `›` are safe in all fonts. Avoid emoji (font
  coverage is skin/OS-dependent) and avoid leading/trailing spaces.
- **Secondary line:** goes in the info tag; in music views Kodi reads
  `comment` (the 3.9.6 lesson), not `plot`. Keep ≤ 80 characters.
- **Colour emphasis in rows:** only Kodi markup (`[COLOR acid]…[/COLOR]`,
  `[B]`, `[I]`, `[U]`, `[LIGHT]`, `[CAPITALIZE]`, `[LOWERCASE]`,
  `[UPPERCASE]`, `[CR]`) — and only if the skin palette has the colour name.
  Never use markup in the InfoTag title (the OSD would show raw tags); the
  add-on already strips it for media titles.
- **Spacing:** there is no per-row padding control. Spacing is the skin's.
  Keep rows list-like: icon + label + short plot; no banners/posters in
  directory rows.
- **Ordering:** menu order is the journey order (Latest → About); it is
  data/code, not skin-dependent.

---

## 5. What the add-on can and cannot control in Kodi

This is the important boundary for a theme pass. The add-on is a **plugin
directory**: it supplies ListItems and artwork; the skin draws them.

### 5.1 Can control (plugin API)

| Surface | Mechanism | Status here |
|---|---|---|
| Per-row icon / thumb / poster | `ListItem.setArt({"icon","thumb","poster","fanart",…})` | ✅ icons 256², fanart per row |
| Per-row fanart | same `setArt` — shown only if the skin shows focused-item fanart | ✅ root + hubs + sources |
| Label text + safe markup | `ListItem(label=…)`, markup subset above | ✅ labels untouched, short |
| Info tags | `setInfo("music", {title, plot, comment, artist, album, duration, mediatype})` | plot/comment used |
| Playable semantics | `setProperty("IsPlayable"/"IsInternetStream")` | unchanged |
| Directory content type | `xbmcplugin.setContent("files"/"songs")` | unchanged |
| End marker | non-playable terminator row | unchanged |
| Context menu | `addContextMenuItems` | unchanged |
| Sort methods | `xbmcplugin.addSortMethod` (not currently used) | — |
| Notification text/icon | `xbmc.executebuiltin("Notification(…,icon)")` | uses add-on icon |
| Add-on browser icon/fanart | `addon.xml` + root `icon.png`/`fanart.jpg` | **identity, untouched** |
| Folder structure, row order, copy | Python | unchanged |

### 5.2 Cannot control (skin owns it)

| Surface | Why |
|---|---|
| Skin XML, layout, row height, list view type | add-on cannot ship skin changes; **no skin fork** |
| Font family, size, weight, letter-spacing of labels | skin font settings only; markup gives crude emphasis |
| Highlight/focus colour, focus animation, sounds | skin palette and animations |
| Whether fanart is shown at all, its crop, zoom, blur, brightness | skin setting; some skins ignore fanart in directory views |
| Icon vs thumb choice per view | skin decides which art type to draw |
| Exact icon display size (we supply 256²; skin scales) | skin/scale settings |
| Background colour of the directory panel | skin |
| Number of visible rows, pagination chrome | skin + window size |
| Positions of add-on name/breadcrumb | skin |
| Kodi OSD/player chrome, seek bar, playlist view | skin; add-on only supplies metadata |
| Emoji/inline images in labels | Kodi label renderer/skin font |
| Animations/transitions between menu screens | skin |

**Practical consequence:** "modern streaming-app energy" has to be carried by
**artwork + labels + information hierarchy**, not by layout. That is exactly
what this pass does: bolder tiles, per-row fanart, distinct glyphs, short
labels. It never pretends to control the skin.

### 5.3 Skin guidance (recommended settings, not a fork)

For the intended look, use a skin that shows focused-item fanart in list views
and recommend:

- **Estuary** (default): *Settings → Interface → Skin → Show fanart* = on;
  use **List** or **InfoWall** for the plugin directory; keep **Show media
  info** off in the list so rows stay compact.
- **Nimbus / Arctic Fuse**: keep "Fanart" enabled for add-on windows and use a
  list view (not poster-only wall) for plugin directories.
- Do **not** edit skin files or ask users to install a modified skin. If a
  skin cannot show fanart in directory views, the icons and labels still carry
  the theme — the pack is designed to work without fanart.

### 5.4 Kodi texture cache note

Kodi caches artwork by path. This pass **replaces** several existing filenames
(`rave.png`, `tapepacks.png`, …) with new content at the same path. After
updating the add-on, Kodi may briefly serve the cached old bitmap. Release
notes/README should mention: **restart Kodi** (or refresh the add-on artwork
cache) once after the 3.9.16 update. All *new* fanarts use new paths, so they
are unaffected.

---

## 6. Implementation and reproduction

Artwork is generated from code (Pillow is build-time only):

```sh
python3 scripts/make-art.py            # 20 icons + 18 fanarts + preview sheet
python3 scripts/make-art.py --sheet docs/theme-2026/icon-sheet.jpg
python3 scripts/make-toronto-art.py    # Toronto icon/fanart + 64/128/256 proof
```

Menu screenshots are rendered from the add-on's real ListItem output through the
Kodi stubs (no device needed):

```sh
python3 scripts/make-theme-shots.py --label before   # current tree
python3 scripts/make-theme-shots.py --label after    # after the theme pass
```

Each run writes `root-<label>.png`, `hubs-<label>.png` and
`menu-<label>.json` under `docs/theme-2026/`. The renderer approximates
Estuary's list view at 1920×1080 (row height, focus rule, footer); the **data
and artwork are the add-on's real output**. It is a review rendering, not a
device capture.

### Before / after

| File | What it shows |
|---|---|
| `docs/theme-2026/root-before.png` | 3.9.15 root: duplicate icons, no per-row fanart |
| `docs/theme-2026/root-after.png` | 3.9.16 root: 9 distinct tiles + per-row fanart |
| `docs/theme-2026/hubs-before.png` | 4 hubs, default fanart |
| `docs/theme-2026/hubs-after.png` | 4 hubs with hub fanart |
| `docs/theme-2026/menu-before.json` | captured ListItems, 3.9.15 |
| `docs/theme-2026/menu-after.json` | captured ListItems, 3.9.16 |

---

## 7. QA checklist for 3.9.16

- [x] 344 offline tests pass (`python3 -m unittest discover -s test`).
- [x] `test/test_theme_art.py` asserts: every art reference exists, all icons
      are 256×256, all fanarts 1280×720, 9 distinct root icons/fanarts, hub and
      source fanarts wired, all fanart assets used, wordmark assets untouched.
- [x] No dangling `pirate_source.png` reference; Pirate Radio Archives has art.
- [x] `scripts/build.sh` / `scripts/build-repo.sh` produce the 3.9.16 zip and
      repository (see §8).
- [ ] **Device smoke test** (Kodi 20–22 on the Shield): open root, check all
      nine rows and four hubs; confirm no blank/missing art; restart once to
      clear stale texture-cache entries for replaced filenames. *(Needs a
      device session — out of scope for the code/asset branch.)*
- [ ] Owner sign-off on the stickers at TV distance (icons are designed to read
      at 64 px; the 4K TV magnifies any halftone shimmer).

### Known limits / caveats

1. These are **menu renders**, not Kodi captures: no device was available in
   this pass. Text metrics and row heights approximate Estuary.
2. Fanart is only visible if the skin shows focused-item fanart; the theme has
   a complete icon fallback.
3. Icons are 256² (Kodi recommendation). Kodi may scale them larger on 4K
   skins; the halftone is coarse enough to survive, but check on the TV.
4. The root `icon.png` / `fanart.jpg` wordmark assets were intentionally not
   regenerated. Any future wordmark change is an identity change, not a theme
   change.
5. The web app keeps its own 512² art (`../Rave Player/static/art`); this pass
   does not touch it. The glyph language is shared, the treatment is Kodi's.
6. No new sources, no new claims, no copy changes, no routing changes beyond
   artwork wiring and the missing-art fix.

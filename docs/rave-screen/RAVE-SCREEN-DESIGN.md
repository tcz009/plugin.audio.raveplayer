> **Snapshot note (look overhaul, 3.9.48):** this is the design reference kept
> with the branch. The delivered textures live in
> [`script.raveplayer.ui/resources/art/rave-screen/`](../../script.raveplayer.ui/resources/art/rave-screen/);
> the one-page board, mockups and generator stay with the design archive and are
> linked here by name only. No code or asset was changed by copying this spec.

# Rave Screen — design spec

**Status:** design deliverable for the WindowXML build. No add-on code, skin
XML, `resources/` file or test was changed by this pass. Everything is under
`docs/rave-screen/`.

**Base:** Kodi 20–22 · 1280×720 control space · Estuary-independent · stock
skin only. The 1920×1080 renders are a true ×1.5 of the same grid, not a
resample.

![Rave Screen — one-page preview](preview-one-page.png)

*One-page board: [`preview-one-page.png`](preview-one-page.png). Screen mockups:
[`mockups/`](mockups/). Control map:
[`WINDOWXML-CONTROL-MAP.md`](WINDOWXML-CONTROL-MAP.md).*

---

## 1. The idea

A **printed pirate-TV guide you can drive with a remote**.

The accepted Direction C2 artwork already carries the language: ink and paper,
one acid / magenta / cyan spot per surface, Impact display, mono codes, hard
sticker shadows, halftone, scanlines, drips and deliberate misregistration.
The Rave Screen does not invent a second language. It gives that artwork a
**room**: a full-screen window where the focused room's fanart is the poster,
the nine root rows are the index, and the bottom strip is the transmission.

Three things make it feel like Rave Player instead of a generic Kodi list:

1. **The hero is the room.** The focused row's own 1280×720 fanart fills a
   640×360 poster window, with its sticker reproduced at 140 px inside the dark
   left panel the fanart was designed to leave quiet.
2. **The list is an index, not a card wall.** Nine 48 px rows, a big acid focus
   bar, a hard magenta plate shadow, and a Label2 fact in the right column.
3. **The footer is a broadcast strip.** ON AIR, the real track, a static
   waveform, a 3 px progress line, and the `B BACK` keycap — never a generic
   Kodi player bar.

**Identity guardrail:** the logo/mark is untouched. The header mark is the
existing `icon.png` at 48 px; the Surprise head is the same file, rotated only
(the existing spinner frames are already produced that way). No new smiley, no
new wordmark, no new glyph vocabulary.

---

## 2. Hard constraints (and how the design answers them)

| Constraint | Consequence in this design |
|---|---|
| Custom `WindowXML`, 1280×720, Estuary-independent | One 720p control space. No `<include>` and no skin palette dependency. All colours are explicit `0xAARRGGBB`; all geometry is fixed. |
| Stock skin | Only `font13`, `font12` and `font10`. No `font14`, no skin-specific font names. |
| No external fonts | Display/Mono type is **rasterised into PNG labels**. Live text is the skin's sans. No TTF is bundled or loaded. |
| Kodi add-ons cannot load TTF fonts into a window | The live UI accepts the skin font; the Impact voice lives in baked labels and the accepted fanarts. This is the same split as `THEME-2026.md` §2.2. |
| Logo/mark untouched | Header + Surprise use `icon.png` as-is. Head frames are rotations only. |
| Fanart is 1280×720, left 46 % quiet | Hero is exactly 640×360 (0.5×) — no crop, and the left 46 % stays the text/side-art panel. |
| TV overscan | All live type is inside the 5 % safe frame **64 / 36** at 720p (96 / 54 at 1080p). Only art bleeds. |
| No blur / glow / glass | Hard offset shadows, halftone, scanlines, grain, crop marks, misregistration. Nothing soft. |

---

## 3. Layout system

### 3.1 Canvas and safe area

| Region | 1280×720 | 1920×1080 (×1.5) |
|---|---|---|
| Canvas | `0,0 1280×720` | `0,0 1920×1080` |
| **5 % TV safe** | `64,36 1152×648` | `96,54 1728×972` |
| Preferred margin | `80,48 1120×624` | `120,72 1680×936` |
| Header | `64,36 1152×76` | `96,54 1728×114` |
| Row list | `64,148 480×432` | `96,222 720×648` |
| Gutter | `32` px (`544 → 576`) | `48` px (`816 → 864`) |
| Hero | `576,148 640×360` | `864,222 960×540` |
| Hero caption | `576,512 640×96` | `864,768 960×144` |
| Now-playing footer | `64,620 1152×64` | `96,930 1728×96` |

- All coordinates are top-left origin in the 720p control space.
- The 1080 column is a reference for QA and 4K skins. **The XML uses the 720
  column only**; Kodi scales the window.
- Art can bleed into the margin. Type, keycaps and focus furniture may not.
- Bottom of the safe frame is `684`; the footer plate ends exactly there.

### 3.2 Vertical rhythm

```
36    safe top
36    header top
112   header rule
148   content top (40 px gap below rule)
148   list row 01
...
580   list row 09 ends (9 × 48 = 432)
512   caption starts (hero ends 508)
608   caption ends
620   footer plate starts (12 px gap)
684   footer plate ends / safe bottom
```

`48` is the row unit; `8` is the micro unit; `12` is the caption/footer gap.
The header is `76` high, the footer `64`; the list is exactly nine rows so the
root never scrolls.

### 3.3 Horizontal rhythm

```
64 ─ 480 list ─ 32 gutter ─ 640 hero ─ 64 ─ 1216
│    index/icon/label/fact/chevron    │
```

- List width is **480**; row controls use `6 / 38 / 86 / 336 / 444` inside it.
- Hero width is **640**; the fanart is 1280×720 at exactly 0.5×.
- The right edge of every text control lands on `1216` (safe right).

### 3.4 Grid drawings

- [`mockups/grid-1280x720.png`](mockups/grid-1280x720.png)
- [`mockups/grid-1920x1080.png`](mockups/grid-1920x1080.png)

---

## 4. Home row list

### 4.1 Row anatomy (480×48)

```
x=0    6   38        86                        336        444 474 480
│shadow │bar│ icon 36 │ label (246)            │ fact 104  │ › │   │
│      └───┴──────────┴────────────────────────┴───────────┴───┘   │
│                       focus plate 474×40 at y=3                  │
└──────────────────────── separator at y=47 ───────────────────────┘
```

| Part | 720p box | Notes |
|---|---|---|
| Index | `6,0 24×48` | `rp_index` (`01`…`09`), font10, muted; acid on focus |
| Icon | `38,6 36×36` | `ListItem.Icon`, from the accepted 256² sticker set |
| Label | `86,0 246×48` | `ListItem.Label`, font12, paper; bold on focus |
| Label2 fact | `336,0 104×48` | `ListItem.Label2`, font10, right, muted; acid on focus |
| Chevron | `444,0 24×48` | `›`, font13, acid; focused row only |
| Separator | `0,47 480×1` | `row-separator-480x1.png`, unfocused rows |
| Focus plate | `0,3 474×40` | `focus-plate-474x40.png` |
| Plate shadow | `6,7 474×40` | `focus-plate-shadow-474x40.png` |
| Focus bar | `0,6 6×34` | `focus-bar-6x34.png` |

The focus bar is **not** the skin's focus rectangle. It is a 6 px acid slab with
a 2 px magenta misregistration edge, sitting at the safe-left edge of the row.
The plate shadow is offset `+6/+4`, not blurred. The label gets a 2 px cyan
misregistration twin at `x+2, y+2`; the fact turns acid; the icon gets a hard
magenta shadow at `+2/+2`.

### 4.2 The nine rows (real 3.9.44 root data)

| # | Label | Label2 fact | RP code | Icon | Hero fanart |
|---|---|---|---|---|---|
| 01 | Latest | `newest` | RP-01 | `rave.png` | `fanart-latest.jpg` |
| 02 | Tape Packs | `1990–2004` | RP-03 | `tapepacks.png` | `fanart-tapepacks.jpg` |
| 03 | Pirate Radio | `1990s` | RP-19 | `pirate-radio.png` | `fanart-curated.jpg` |
| 04 | Mixes & Shows | `podcasts` | RP-27 | `mixes.png` | `fanart-mixes.jpg` |
| 05 | Live Radio | `live` | RP-31 | `radio.png` | `fanart-live.jpg` |
| 06 | Favourites | `saved` | RP-12 | `favourites.png` | `fanart-favourites.jpg` |
| 07 | Search the Archive | `archive.org` | RP-44 | `search.png` | `fanart-search.jpg` |
| 08 | Surprise Me | `random` | RP-02 | `surprise.png` | `fanart-surprise.jpg` |
| 09 | About & Sources | `3.9.44` | RP-99 | `about.png` | `fanart-about.jpg` |

Facts are the real `ListItem.setLabel2` values from `routes.root()`. The About
fact is the add-on version and must stay dynamic. The RP codes are cosmetic
(print furniture), set per item as `rp_code`; they are not routing keys.

### 4.3 Label rules

- Label ≤ 24 characters; current root max is 18 (`Search the Archive`).
- Label2 is capped by `ui.MAX_LABEL2_CHARS = 16`; **do not** put titles there.
- No markup in Label2; the row already carries the fact as a plain string.
- Sentence case. Do not rely on case for meaning; the hero uppercases only for
  display.
- The list is a `list` control, not a skin `panel`. A row is 48 px; if a future
  menu needs > 9 rows, page it (or shrink to 44) rather than adding a
  skin-dependent scrollbar.

### 4.4 Focus and input

- Up/Down moves the list; the hero crossfades with `fadetime 220`.
- Left/Right are trapped on the list (no horizontal focus target).
- OK opens the focused row. Back closes the screen.
- The focus animation is a 160 ms slide-in + 120 ms fade; see the control map.
- A 4× layer detail is at
  [`mockups/detail-focus-row-4x.png`](mockups/detail-focus-row-4x.png).

---

## 5. Hero art area

The hero is the row's existing fanart, not new art.

| Layer | 720p box | Asset | Notes |
|---|---|---|---|
| Shadow | `588,160 640×360` | `hero-shadow-640x360.png` | Solid magenta, `+12/+12`, cyan bottom sliver |
| Fanart | `576,148 640×360` | `ListItem.Art(fanart)` | `stretch`, `fadetime 220`; exactly 16:9 |
| Scrim | `576,148 640×360` | `hero-scrim-640x360.png` | Ink 118 → 0 over the left 62 % |
| Sticker shadow | `608,204 140×140` | `hero-sticker-shadow-140x140.png` | Hard `+8/+8` |
| Sticker | `600,196 140×140` | `ListItem.Icon` | The same 256² sticker at 140 px |
| Frame | `576,148 640×360` | `hero-frame-640x360.png` | Keyline, crop marks, code notch, drips |
| RP sticker | `596,164 50×35` | `sticker-rp.png` | Paper sticker, magenta shadow |
| RP code | `662,170 120×24` | `rp_code` | Font10 acid; print furniture |
| Kicker | `600,354 140×20` | `label-on-the-screen.png` | Baked Impact, acid + magenta |

### 5.1 Caption

| Line | Box | Binding | Type |
|---|---|---|---|
| Title (cyan twin) | `579,514 640×36` | `ListItem.Label`, uppercase | font13 bold, cyan |
| Title | `576,512 640×36` | `ListItem.Label`, uppercase | font13 bold, paper |
| Meta | `576,548 640×22` | `Label2 · rp_code` | font10, acid |
| Plot | `576,572 640×36` | `ListItem.Plot` | font10, muted, max 2 lines |

The title is the only place the live UI is uppercased; the row keeps its
sentence case. The cyan twin is decorative misregistration, not a second title.

### 5.2 Fallback and codes

- If a row has no fanart, use
  [`assets/hero-fallback-640x360.jpg`](assets/hero-fallback-640x360.jpg)
  (`NO SIGNAL / RP / STANDBY`). The root rows all have fanart; this is for hubs
  and future directories.
- Codes are assigned per item. Recommended root codes are in §4.2. Hubs can
  reuse the parent's code or leave `rp_code` blank; the layout holds.

---

## 6. Footer / now-playing strip

The footer is `1152×64` at `64,620`. It is always present; only its state
changes.

### 6.1 States

| State | Left | Middle | Right |
|---|---|---|---|
| **Idle** (`Player.Title` empty) | `rave.png` 36², `NOTHING PLAYING`, `PICK A ROOM · PRESS OK` | Dimmed waveform, no progress | `OK OPEN`, `B BACK` |
| **Playing** (track / tape) | `ON AIR` sticker, `NOW PLAYING` Impact label, title, artist · album | `12:04` / `43:57`, waveform, 3 px progress | `OK OPEN`, `B BACK` |
| **Live radio** | `ON AIR` sticker, `LIVE` (`live` fact), title, station | No total/progress if duration is empty; waveform remains | `OK OPEN`, `B BACK` |

### 6.2 Geometry

| Part | 720p box | Asset / binding | Type |
|---|---|---|---|
| Plate | `64,620 1152×64` | `footer-plate-1152x64.png` | — |
| ON AIR | `76,630 67×29` | `sticker-on-air.png` | visible when playing |
| Kicker | `156,624 118×18` | `label-now-playing.png` | visible when media |
| Title | `156,636 350×28` | `Player.Title` | font12 bold paper |
| Meta | `156,660 350×20` | `Player.Artist · Player.Album` | font10 muted |
| Elapsed | `550,622 60×18` | `Player.Time` | font10 acid |
| Total | `830,622 60×18` | `Player.Duration` | font10 muted, right |
| Waveform | `550,646 340×28` | `np-wave-340x28.png` | static texture |
| Progress | `550,676 340×3` | `progress` + `<info>progress</info>` | acid fill |
| Idle icon | `76,634 36×36` | `rave.png` | visible when idle |
| Idle kicker | `156,630 300×20` | `NOTHING PLAYING` | font10 muted |
| Idle title | `156,650 350×28` | `PICK A ROOM · PRESS OK` | font12 bold |
| OK key | `944,632 40×32` | `keycap-ok.png` | — |
| OK label | `992,640 60×20` | `OPEN` | font10 muted |
| B key | `1066,632 32×32` | `keycap-b.png` | — |
| B label | `1106,640 60×20` | `BACK` | font10 bold |

The footer uses Kodi's own `Player.*` info labels and `<info>progress</info>`,
so it updates without a Python timer. If the coder wants the richer
`nowplaying` metadata (`Vinylgroover · Dreamscape XII · 26 Aug 1994`), set
`Window.Property(rp_now_*)` and bind the same controls to those properties.
The layout does not change.

### 6.3 Rules

- The meta line is a **single line**; artists/albums clip at 350 px. Do not wrap
  into the footer's bottom edge.
- For live radio, `Player.Duration` may be empty/zero; hide total and progress
  when `String.IsEmpty(Player.Duration)`, keep the waveform as texture.
- `ON AIR` means *playing*, not *paused*; use `Player.Playing` for the sticker
  and `!String.IsEmpty(Player.Title)` for the title/now-playing group.
- The footer is not a button. Back is a remote action and a printed keycap.

---

## 7. Surprise mode

Surprise is a **second full-screen window** (`id 14003`), not an in-list state.
That keeps the existing, proven `SurpriseReveal` frame loop: 10 pre-rendered
head frames at 10 fps, 36° per frame, minimum 1.2 s, Back cancels.

### 7.1 Composition

| Layer | 720p box | Asset | Notes |
|---|---|---|---|
| Burst | `0,0 1280×720` | `surprise-burst-1280x720.jpg` | 30 beams, halftone, scanlines, bottom veil |
| Ring | `320,-28 640×640` | `surprise-ring-640x640.png` | Acid/magenta/cyan broken arcs |
| Head | `384,36 512×512` | `head-512-01.png` … `09` | Rotated only; Python cycles |
| Caption plate | `320,516 640×168` | `surprise-caption-plate-640x168.png` | Torn top edge, ink fill |
| Title | `430,536 420×72` | `label-surprise-me.png` | Impact 415×69, magenta shadow |
| Sub | `491,614 290×16` | `label-spinning-the-rack.png` | Tracked mono, paper |
| Code | `500,632 280×20` | `RANDOM PACK · RP-02` | font10 acid, centred |
| Cancel button | `560,648 220×38` | `button-focus-220x38.png` | Focus outline; `Action(Back)` |
| B key | `590,652 32×32` | `keycap-b.png` | — |
| CANCEL | `632,652 120×32` | `CANCEL` | font12 bold |
| Top mark | `64,36 36×36` | `icon.png` | Untouched |
| Top label | `110,44 300×20` | `RAVE SCREEN / SURPRISE` | font10 muted |
| Top code | `1100,44 116×20` | `RP-02` | font10 acid, right |

### 7.2 Motion

| Element | Motion | Implementation |
|---|---|---|
| Head | 10 fps, 36°/frame, 1.2 s minimum | Python `setImage(head-512-XX.png)`; existing `SurpriseReveal` loop |
| Ring | Static | Baked; no rotation (avoids jitter) |
| Burst | Static | Baked; the beams are already directional |
| Optional burst pulse | 100 → 104 % zoom, 1.2 s, reversible | Optional XML animation; do not ship if it stutters |
| Cancel | Focus plate only | Stock button focus textures |
| Close | Immediate | `finally: close()` before the random pick |

### 7.3 Cancel

- Back/Stop sets the existing `_rave_cancelled = True`; the route closes the
  reveal, skips the random pick and ends the directory.
- The focusable CANCEL button sends `Action(Back)`; it is the explicit
  affordance for a remote with no obvious Back label.
- The 256 px frames are the low-density fallback; 512 px is the default at
  720p/1080p.

---

## 8. Back and cancel affordance

| Screen | Affordance | Action |
|---|---|---|
| Home | Footer `B BACK` keycap + label (static) | Python `onAction`: `ACTION_NAV_BACK` 92, `ACTION_PREVIOUS_MENU` 10, `ACTION_PARENT_DIR` 9 → `close()` |
| Surprise | Focusable `B CANCEL` button + keycap | `Action(Back)` → Python `onAction` sets `_rave_cancelled` and closes |
| Any | Remote Back | Same as above; never leaves a half-open window |

The window does not install a keymap and does not override global Back. It
handles the action in `onAction`, which is the stock, skin-independent path.

---

## 9. Tokens

### 9.1 Colour

| Token | Hex | Kodi ARGB | Use |
|---|---|---|---|
| ink | `#07070b` | `0xFF07070B` | type shadow, plates, background |
| ink-2 | `#0b0b11` | `0xFF0B0B11` | footer/plate fill |
| paper | `#f2eee3` | `0xFFF2EEE3` | primary type |
| muted | `#a8a399` | `0xFFA8A399` | facts, meta, micro |
| acid | `#e8ff00` | `0xFFE8FF00` | focus bar, facts, emphasis |
| magenta | `#ff2d8f` | `0xFFFF2D8F` | shadows, Surprise, ON AIR |
| cyan | `#22e6ff` | `0xFF22E6FF` | misregistration, focus twin |
| orange | `#ff6a1a` | `0xFFFF6A1A` | not used on the screen (energy sources only) |

Do not add a second spot colour to a surface. A surface is ink + paper + one
signal; the second signal appears only as a misregistration or a sticker
shadow.

### 9.2 Type

| Role | Face | Where |
|---|---|---|
| Display | **Impact** | Baked labels, fanarts, stickers, Surprise title. Never a live label. |
| UI | skin `font13` / `font12` / `font10` | Wordmark, hero title, rows, footer, hints |
| Mono | **Courier New Bold** (build-time) | Baked code/kicker/sub labels only |

No TTF ships. The generator rasterises Impact/Courier New from the build
machine; the PNGs are the source of truth. If the generator runs on a machine
without those fonts, it falls back to Pillow's default and the output must be
reviewed before shipping — do not redistribute a font file.

### 9.3 Texture

- Halftone dots: coarse, visible at TV distance; no fine 1 px screens.
- Scanlines: 6 px period, low alpha; never over live type.
- Shadows: hard offset, one colour; no blur, glow, glass or gradient sheen.
- Misregistration: 2–5 px offset in one of cyan/magenta/acid; visible, not
  decorative noise.
- Crop marks, registration ticks and `RP` codes are print furniture; they may
  bleed, but never carry information.

---

## 10. Assets

All delivered under [`assets/`](assets/) with a machine-readable
[`manifest.json`](assets/manifest.json). Filenames are kebab-case.

| Group | Files | Size | Use |
|---|---|---|---|
| Beds | `screen-bed-1280x720.jpg`, `screen-bed-1920x1080.jpg` | 1280×720 / 1920×1080 | Ink wash, halftone sun, hazard edge, crop marks |
| Texture | `noise-overlay-1280x720.png` | 1280×720 | Grain + scanlines above the bed |
| Hero | `hero-frame-640x360.png`, `hero-shadow-640x360.png`, `hero-scrim-640x360.png`, `hero-sticker-shadow-140x140.png`, `hero-fallback-640x360.jpg` | 640×360 / 140² | Poster furniture |
| Focus | `focus-plate-474x40.png`, `focus-plate-shadow-474x40.png`, `focus-bar-6x34.png`, `row-separator-480x1.png`, `icon-shadow-36x36.png` | — | Row states |
| Header | `mark-shadow-48x48.png`, `rule-acid-1152x2.png`, `rule-magenta-1152x2.png`, `label-the-rave-screen.png` | — | Brand block |
| Footer | `footer-plate-1152x64.png`, `sticker-on-air.png`, `label-now-playing.png`, `np-wave-340x28.png`, `progress-track-340x3.png`, `progress-fill-2x3.png`, `keycap-b.png`, `keycap-ok.png` | — | Now-playing strip |
| Stickers | `sticker-rp.png`, `sticker-focus.png`, `sticker-on-air.png` | 50×35 / 87×40 / 67×29 | Print labels |
| Baked labels | `label-on-the-screen.png`, `label-now-playing.png`, `label-surprise-me.png`, `label-spinning-the-rack.png`, `label-the-rave-screen.png`, `label-rp-2026.png` | 89–415 px wide | Impact/mono display |
| Surprise | `surprise-burst-1280x720.jpg`, `surprise-burst-1920x1080.jpg`, `surprise-burst-512.png`, `surprise-burst-256.png`, `surprise-ring-640x640.png`, `surprise-caption-plate-640x168.png` | — | Burst, badge, ring, caption band |
| Frames | `head-512-00.png`…`09`, `head-256-00.png`…`09` | 512² / 256² | Rotation frames, derived from `icon.png` |
| Surprise button | `button-focus-220x38.png`, `button-nofocus-220x38.png` | 220×38 | Focus ring for CANCEL |

**Total:** 59 files, ~3.5 MB.

### 10.1 Sizes that matter

- Hero fanart is always **640×360** in the window; the source is 1280×720.
- Focus plate is **474×40** inside a 480×48 row; the 6 px bar is separate.
- Surprise head is **512×512**; the 256² frames are the fallback.
- Baked label PNGs are placed at **native aspect**; do not stretch type.

### 10.2 Regenerate

```sh
python3 docs/rave-screen/make-rave-screen.py
python3 docs/rave-screen/make-rave-screen.py --check
```

The generator writes only into `docs/rave-screen/`. It uses Pillow + numpy at
build time; neither is a runtime dependency.

---

## 11. QA checklist

### Layout
- [ ] All live type is inside `64,36 → 1216,684` at 720p.
- [ ] Header rule sits at `112–116`; no type touches it.
- [ ] Nine rows fit exactly; row 09 ends at `580`.
- [ ] Hero is exactly 16:9; no fanart crop or letterbox.
- [ ] Caption ends at `608`; footer starts at `620`; no collision.
- [ ] Footer's last text baseline is above `684`.

### State
- [ ] Focus: acid bar, plate shadow, cyan twin, acid fact, chevron.
- [ ] Unfocus: separator, muted fact, no shadow.
- [ ] Hero crossfade on focus change; no flash of missing art.
- [ ] Footer idle, playing and live states all legible.
- [ ] ON AIR only while playing; paused still shows the track.
- [ ] Surprise: 10 fps, 36°/frame, 1.2 s min; Back cancels.
- [ ] Back closes home; Back cancels Surprise; no half-open window.

### Brand
- [ ] Header mark is `icon.png`, unmodified.
- [ ] Surprise head is a rotation of `icon.png`, not a redraw.
- [ ] No new glyph vocabulary; only the accepted stickers/fanarts.
- [ ] No external font file in the add-on.

### Device
- [ ] Shield/Kodi 22: 720p and 1080p.
- [ ] TV overscan: no clipped type at 5 %.
- [ ] Texture cache: restart once after replacing a filename.
- [ ] A skin without `font12`/`font10` still opens the window (degraded
      hierarchy, no crash).

---

## 12. Honest limits

1. **No device capture.** The mockups are generated from the same geometry and
   real artwork, but they are not Kodi screenshots. Font metrics are Arial
   approximations of the skin's sans; the skin's real font will shift baselines
   by a few pixels. The control boxes are generously sized so it cannot break.
2. **Kodi font sizes are skin-owned.** The design uses `font13/12/10`; a skin
   that redefines them will change the optical hierarchy. Control heights are
   set for Estuary's 30/25/23 px at 1080p.
3. **Custom-window scaling.** The XML is 720p. Kodi scales it; a 4K skin may
   show the halftone more coarsely. The bed and assets are authored at 1280
   (and 1920 for the bed/burst) so they survive.
4. **`Player.*` metadata is only as good as the InfoTag.** The 3.9.44 pass sets
   artist/album/year/genre on tracks; live streams may have empty duration.
   The footer degrades by hiding the total/progress, not by inventing values.
5. **No skin fork, no forced settings.** If a skin ignores custom-window
   textures or fonts, the window still loads; it just looks less like this
   spec. The fallback path is the existing directory views.

---

## 13. File map

| File | What it is |
|---|---|
| [`RAVE-SCREEN-DESIGN.md`](RAVE-SCREEN-DESIGN.md) | This spec |
| [`WINDOWXML-CONTROL-MAP.md`](WINDOWXML-CONTROL-MAP.md) | IDs, coordinates, fonts, colours, animations, XML skeleton |
| [`preview-one-page.png`](preview-one-page.png) | One-page review board |
| [`mockups/home-row-view-1280x720.png`](mockups/home-row-view-1280x720.png) | Home, focus 01, idle bar |
| [`mockups/focused-item-1280x720.png`](mockups/focused-item-1280x720.png) | Focus 02, plate + hero |
| [`mockups/surprise-spin-1280x720.png`](mockups/surprise-spin-1280x720.png) | Surprise modal state |
| [`mockups/now-playing-bar-1280x720.png`](mockups/now-playing-bar-1280x720.png) | Focus 05, playing bar |
| [`mockups/*-1920x1080.png`](mockups/) | True ×1.5 proofs |
| [`mockups/grid-1280x720.png`](mockups/grid-1280x720.png) | Layout grid |
| [`mockups/detail-focus-row-4x.png`](mockups/detail-focus-row-4x.png) | Focus layer detail |
| [`assets/`](assets/) | 59 PNG/JPG assets + manifest |
| [`make-rave-screen.py`](make-rave-screen.py) | Deterministic generator |

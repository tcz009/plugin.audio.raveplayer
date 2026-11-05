# Rave Screen — WindowXML control map

**Window IDs:** `14002` home / row screen · `14003` Surprise spin
**Control space:** 1280×720 (`<coordinates><system>1</system>`), Kodi 20–22
**Companion:** [`RAVE-SCREEN-DESIGN.md`](RAVE-SCREEN-DESIGN.md)

This map is the build sheet. Every rectangle is `posx,posy width×height` in
**720p control space**; the 1080 proof is exactly ×1.5. If a number here and a
mockup disagree, this file wins.

---

## 0. Before you wire

### 0.1 Asset root

Copy `docs/rave-screen/assets/*` to:

```
plugin.audio.raveplayer/resources/art/rave-screen/
```

Use **absolute** texture paths in the XML:

```
special://home/addons/plugin.audio.raveplayer/resources/art/rave-screen/<file>
```

Do **not** rely on relative `rave-screen/<file>` lookups. Kodi's WindowXML
fallback looks in the current skin's media first; a skin with a same-named
texture can win, and the add-on's fallback media path is not a guaranteed
texture root. Absolute add-on paths also make the texture cache key stable.
The same rule applies to the list-layout textures.

### 0.2 Reserved IDs

Kodi's `WindowXML` window-list lives on **control IDs 50–59**. The row list is
**id 50**; `self.addItems()` populates it and the hero binds through
`Container(50)`. Do not move the list to 500 — it will render but stay empty.

Reserved/avoid: `3`, `4`, `5`, `12`, `50–59` (except 50). The Surprise window
uses no window list.

### 0.3 Fonts and colours

Only `font13`, `font12`, `font10` (skin-owned). No `font14`, no TTF.

| Name | ARGB |
|---|---|
| ink | `0xFF07070B` |
| ink-2 | `0xFF0B0B11` |
| paper | `0xFFF2EEE3` |
| muted | `0xFFA8A399` |
| acid | `0xFFE8FF00` |
| magenta | `0xFFFF2D8F` |
| cyan | `0xFF22E6FF` |

All label controls get `<shadowcolor>0xFF07070B</shadowcolor>` where the text
sits on art. Type is never placed on the bleed; see the safe frame.

---

## 1. Home window — id 14002

`raveplayer-screen.xml` · `type="window"` · `defaultcontrol 50`

### 1.1 Background and header

| ID | Type | 720p rect | Texture / binding | Font | Colour | Notes |
|---|---|---|---|---|---|---|
| 100 | image | `0,0 1280×720` | `screen-bed-1280x720.jpg` | — | — | `stretch`; full bleed |
| 101 | image | `0,0 1280×720` | `noise-overlay-1280x720.png` | — | — | `stretch`; above 100, below all UI |
| 110 | image | `70,46 48×48` | `mark-shadow-48x48.png` | — | — | Hard `+6/+6` mark shadow |
| 111 | image | `64,40 48×48` | `icon.png` (add-on root) | — | — | **Untouched**; `keep` |
| 112 | label | `124,40 360×34` | `[B]RAVE PLAYER[/B]` | `font13` | paper | bold; left/center |
| 113 | image | `124,74 102×13` | `label-the-rave-screen.png` | — | — | Baked Impact, native size |
| 114 | label | `1000,40 216×28` | `$INFO[System.Time]` | `font12` | acid | right/center |
| 115 | label | `1000,72 216×24` | `$INFO[Container(50).NumItems] ROOMS · STANDBY` | `font10` | muted | right; visible when no media |
| 116 | label | `1000,72 216×24` | `$INFO[Container(50).NumItems] ROOMS · ON AIR` | `font10` | muted | right; visible with media |
| 117 | image | `64,112 1152×2` | `rule-acid-1152x2.png` | — | — | acid rule |
| 118 | image | `66,114 1152×2` | `rule-magenta-1152x2.png` | — | — | `colordiffuse 0x88FFFFFF` |

`115` / `116` are two labels, not one with conditional text. Conditions:

```xml
<visible>String.IsEmpty(Player.Title)</visible>   <!-- 115 -->
<visible>!String.IsEmpty(Player.Title)</visible>  <!-- 116 -->
```

### 1.2 Hero and caption

| ID | Type | 720p rect | Texture / binding | Font | Colour | Notes |
|---|---|---|---|---|---|---|
| 200 | image | `588,160 640×360` | `hero-shadow-640x360.png` | — | — | `+12/+12` |
| 201 | image | `576,148 640×360` | `$INFO[Container(50).ListItem.Art(fanart)]` | — | — | `stretch`; `fadetime 220` |
| 202 | image | `576,148 640×360` | `hero-scrim-640x360.png` | — | — | left 62 % ink |
| 203 | image | `608,204 140×140` | `hero-sticker-shadow-140x140.png` | — | — | Hard `+8/+8` |
| 204 | image | `600,196 140×140` | `$INFO[Container(50).ListItem.Icon]` | — | — | `keep` |
| 205 | image | `576,148 640×360` | `hero-frame-640x360.png` | — | — | keyline + crop marks + notch |
| 206 | image | `596,164 50×35` | `sticker-rp.png` | — | — | native 50×35 |
| 207 | label | `662,170 120×24` | `$INFO[Container(50).ListItem.Property(rp_code)]` | `font10` | acid | left/center |
| 208 | image | `600,354 140×20` | `label-on-the-screen.png` | — | — | baked Impact, native 140×20 |
| 209 | label | `579,514 640×36` | title twin (same text) | `font13` | cyan | misregistration; draw before 210 |
| 210 | label | `576,512 640×36` | `[B][UPPERCASE]$INFO[Container(50).ListItem.Label][/UPPERCASE][/B]` | `font13` | paper | bold; left/center |
| 211 | label | `576,548 640×22` | `$INFO[Container(50).ListItem.Label2]  ·  $INFO[Container(50).ListItem.Property(rp_code)]` | `font10` | acid | left/center |
| 212 | label | `576,572 640×36` | `$INFO[Container(50).ListItem.Plot]` | `font10` | muted | `wrapmultiline true`; max 2 lines |

**Hero fallback:** if a `ListItem` has no fanart, set its `fanart` art to
`hero-fallback-640x360.jpg` in Python before adding it. Do not leave 201 blank.

**Title twin:** the cyan label uses the same binding. In XML it is a separate
control, not a `shadowcolor`, so it can sit `+3/+2` and animate separately.

### 1.3 Row list — id 50

| Property | Value |
|---|---|
| Control | `type="list" id="50"` |
| Rect | `64,148 480×432` |
| Layout | `itemlayout` / `focusedlayout`, `height="48" width="480"` |
| Focus trap | `onup 50`, `ondown 50`, `onleft 50`, `onright 50` |
| Scroll | `<scrolltime>180</scrolltime>` |
| Populate | `self.addItems([...])` in `onInit` |
| Default | `defaultcontrol 50` |

#### 1.3.1 Unfocused `itemlayout` (480×48)

| Part | Type | Rect | Binding / texture | Font | Colour |
|---|---|---|---|---|---|
| Index | label | `6,0 24×48` | `$INFO[ListItem.Property(rp_index)]` | `font10` | muted |
| Icon | image | `38,6 36×36` | `$INFO[ListItem.Icon]` | — | — |
| Label | label | `86,0 246×48` | `$INFO[ListItem.Label]` | `font12` | paper |
| Fact | label | `336,0 104×48` | `$INFO[ListItem.Label2]` | `font10` | muted |
| Separator | image | `0,47 480×1` | `row-separator-480x1.png` | — | — |

All labels: `<aligny>center</aligny>`. Fact is `<align>right</align>`. Index is
`<align>center</align>`.

#### 1.3.2 Focused `focusedlayout` (480×48)

| Part | Type | Rect | Binding / texture | Font | Colour |
|---|---|---|---|---|---|
| Plate shadow | image | `6,7 474×40` | `focus-plate-shadow-474x40.png` | — | — |
| Plate | image | `0,3 474×40` | `focus-plate-474x40.png` | — | — |
| Focus bar | image | `0,6 6×34` | `focus-bar-6x34.png` | — | — |
| Icon shadow | image | `40,8 36×36` | `icon-shadow-36x36.png` | — | — |
| Icon | image | `38,6 36×36` | `$INFO[ListItem.Icon]` | — | — |
| Index | label | `6,0 24×48` | `$INFO[ListItem.Property(rp_index)]` | `font10` | acid |
| Label twin | label | `88,2 246×48` | `$INFO[ListItem.Label]` | `font12` bold | cyan |
| Label | label | `86,0 246×48` | `$INFO[ListItem.Label]` | `font12` bold | paper |
| Fact | label | `336,0 104×48` | `$INFO[ListItem.Label2]` | `font10` | acid |
| Chevron | label | `444,0 24×48` | `›` | `font13` | acid |

Draw order in the focused layout: shadow → plate → bar → icon shadow → icon →
twin → label → fact → chevron. The chevron is `<align>center</align>`,
`<aligny>center</aligny>`.

### 1.4 Footer

| ID | Type | 720p rect | Texture / binding | Font | Colour | Visibility |
|---|---|---|---|---|---|---|
| 600 | image | `64,620 1152×64` | `footer-plate-1152x64.png` | — | — | always |
| 601 | image | `76,630 67×29` | `sticker-on-air.png` | — | — | `Player.Playing` |
| 602 | image | `156,624 118×18` | `label-now-playing.png` | — | — | media |
| 603 | label | `156,636 350×28` | `$INFO[Player.Title]` | `font12` | paper bold | media |
| 604 | label | `156,660 350×20` | `$INFO[Player.Artist]  ·  $INFO[Player.Album]` | `font10` | muted | media |
| 605 | label | `550,622 60×18` | `$INFO[Player.Time]` | `font10` | acid | media |
| 606 | label | `830,622 60×18` | `$INFO[Player.Duration]` | `font10` | muted | duration |
| 607 | image | `550,646 340×28` | `np-wave-340x28.png` | — | — | media |
| 608 | progress | `550,676 340×3` | `<info>progress</info>` | — | acid | duration |
| 609 | image | `76,634 36×36` | `rave.png` | — | — | idle |
| 610 | label | `156,630 300×20` | `NOTHING PLAYING` | `font10` | muted | idle |
| 611 | label | `156,650 350×28` | `PICK A ROOM · PRESS OK` | `font12` | paper bold | idle |
| 612 | image | `944,632 40×32` | `keycap-ok.png` | — | — | always |
| 613 | label | `992,640 60×20` | `OPEN` | `font10` | muted | always |
| 614 | image | `1066,632 32×32` | `keycap-b.png` | — | — | always |
| 615 | label | `1106,640 60×20` | `BACK` | `font10` | paper bold | always |

`media` = `!String.IsEmpty(Player.Title)`.
`idle` = `String.IsEmpty(Player.Title)`.
`duration` = `!String.IsEmpty(Player.Duration)`; this is what hides the
total/progress for live radio.

**Progress textures:**

```xml
<control type="progress" id="608">
  <posx>550</posx><posy>676</posy><width>340</width><height>3</height>
  <info>progress</info>
  <texturebg>…/progress-track-340x3.png</texturebg>
  <texturemid>…/progress-fill-2x3.png</texturemid>
</control>
```

If a skin's progress control ignores `texturemid`, the acid fill may fall back
to the skin's bar. The time labels still carry the state.

**Richer metadata option:** set `Window.Property(rp_now_title)`,
`rp_now_meta`, `rp_now_elapsed`, `rp_now_total`, `rp_now_percent` from the
add-on's `nowplaying` data and bind 603–606/608 to those properties instead.
The layout is unchanged. `Player.*` is the zero-timer default.

---

## 2. Bindings and item properties

### 2.1 Hero / list bindings

| Control | Binding |
|---|---|
| Hero art | `$INFO[Container(50).ListItem.Art(fanart)]` |
| Hero sticker | `$INFO[Container(50).ListItem.Icon]` |
| Hero code | `$INFO[Container(50).ListItem.Property(rp_code)]` |
| Hero title | `$INFO[Container(50).ListItem.Label]` |
| Hero fact | `$INFO[Container(50).ListItem.Label2]` |
| Hero plot | `$INFO[Container(50).ListItem.Plot]` |
| Row index | `$INFO[ListItem.Property(rp_index)]` |
| Row icon | `$INFO[ListItem.Icon]` |
| Row label | `$INFO[ListItem.Label]` |
| Row fact | `$INFO[ListItem.Label2]` |
| Room count | `$INFO[Container(50).NumItems]` |
| Clock | `$INFO[System.Time]` |

### 2.2 Properties to set per `ListItem`

```python
li.setProperty("rp_index", "%02d" % (i + 1))   # "01"…"09"
li.setProperty("rp_code", code)                # "RP-01"…"RP-99"; may be ""
li.setArt({"icon": icon, "fanart": fanart})
li.setLabel2(fact)                             # ui.fact(), ≤16 chars
li.setInfo("video", {"plot": plot})            # Estuary reads video plot
```

The screen must work if `rp_code` is empty (hubs): the hero code label is
blank, the meta line shows the fact and a dangling `·`. Guard it in Python by
setting the meta property to `fact` alone when code is empty, or accept the
separator as print furniture.

### 2.3 Optional window properties

| Property | Values | Use |
|---|---|---|
| `rp_live` | `"true"` / `"false"` | Force live state (hide total/progress) if `Player.Duration` is unreliable |
| `rp_now_title` | string | Rich now-playing override |
| `rp_now_meta` | string | Rich artist · venue · date |
| `rp_now_elapsed` | `mm:ss` | Rich elapsed |
| `rp_now_total` | `mm:ss` | Rich total |
| `rp_now_percent` | `0`–`100` | Rich progress |

Bind only one source per control. Do not mix `Player.Title` and
`rp_now_title` in the same label.

---

## 3. Animation map

| Element | Animation | Where | Notes |
|---|---|---|---|
| Focus plate | `slide` `-8,0 → 0,0`, 160 ms + `fade` 0→100, 120 ms | focusedlayout, controls 200/201 | Hard snap, no ease |
| Focus bar | `fade` 0→100, 120 ms | focusedlayout | The acid bar arrives with the plate |
| Label twin | `slide` `-2,0 → 0,0`, 150 ms | focusedlayout, twin | Cyan offset settles last |
| Hero art | `<fadetime>220</fadetime>` | image 201 | Crossfade when focus changes |
| List scroll | `<scrolltime>180</scrolltime>` | list 50 | Nine rows fit; this is future-proofing |
| Surprise head | 10 fps frame swap | Python | 36°/frame; `SurpriseReveal` loop |
| Surprise ring/burst | static | — | No rotation; avoids shimmer |
| Optional burst pulse | `zoom 100 → 104`, 1.2 s, `loop="true"` `reversible="true"` | image 100 (Surprise) | Do not ship if it stutters; static is approved |

Recommended XML:

```xml
<animation effect="slide" start="-8,0" end="0,0" time="160">Focus</animation>
<animation effect="fade" start="0" end="100" time="120">Focus</animation>
```

Do not animate the background bed, the footer plate or the labels' colours.
The screen is a print object; motion belongs to focus and the Surprise head.

---

## 4. Surprise window — id 14003

`raveplayer-surprise.xml` · `type="window"` · `defaultcontrol 107`

| ID | Type | 720p rect | Texture / binding | Font | Colour | Notes |
|---|---|---|---|---|---|---|
| 100 | image | `0,0 1280×720` | `surprise-burst-1280x720.jpg` | — | — | `stretch` |
| 101 | image | `320,-28 640×640` | `surprise-ring-640x640.png` | — | — | `keep`; `colordiffuse 0xE6FFFFFF` |
| 102 | image | `384,36 512×512` | `head-512-XX.png` | — | — | Python frame swap; `keep` |
| 103 | image | `320,516 640×168` | `surprise-caption-plate-640x168.png` | — | — | `stretch`; above head |
| 104 | image | `430,536 420×72` | `label-surprise-me.png` | — | — | native 415×69; `keep` |
| 105 | image | `491,614 290×16` | `label-spinning-the-rack.png` | — | — | native 285×14; `keep` |
| 106 | label | `500,632 280×20` | `RANDOM PACK · RP-02` | `font10` | acid | centre |
| 107 | button | `560,648 220×38` | `button-focus-220x38.png` / `button-nofocus-220x38.png` | `font12` | — | blank label; `Action(Back)`; default |
| 108 | image | `590,652 32×32` | `keycap-b.png` | — | — | — |
| 109 | label | `632,652 120×32` | `CANCEL` | `font12` | paper bold | centre |
| 110 | image | `64,36 36×36` | `icon.png` | — | — | untouched |
| 111 | label | `110,44 300×20` | `RAVE SCREEN / SURPRISE` | `font10` | muted | — |
| 112 | label | `1100,44 116×20` | `RP-02` | `font10` | acid | right |
| 113 | image | `0,0 1280×720` | `noise-overlay-1280x720.png` | — | — | optional top texture |

**Draw order:** burst → ring → head → caption plate → title → sub → code →
button → keycap → CANCEL → top mark/labels → noise.

**Button:** the blank-label button is the focus target; the keycap/label are
drawn on top of it. If your Kodi build will not focus a blank label, put
`<label>B   CANCEL</label>` on the button and remove 108/109. Both are
acceptable; the focus ring is the important part.

**Frame contract:** Python swaps only control 102. 10 frames, 512², names
`head-512-00.png` … `head-512-09.png`; 256² fallback. Frame index =
`int(elapsed * 10) % 10`; angle = `-36° × index`. Do not rotate a live image
control; the frames already carry the rotation.

**Existing `SurpriseReveal` mapping:** the current class uses 99 (bg), 100
(head), 101 (title), 102 (sub), 103 (code), 104 (hint). If you keep that code,
either keep the old IDs in the new XML or update the constants:

| `SurpriseReveal` constant | New control |
|---|---|
| background | 100 |
| head | 102 |
| title | 104 (image; drop `setLabel`) |
| subtitle | 105 (image; drop `setLabel`) |
| code | 106 |
| hint | 109 (`CANCEL`) |

Do not call `setLabel` on 104/105; they are baked images. The code label 106
and the cancel label 109 remain settable.

---

## 5. Lifecycle, Back and OK

### 5.1 Home

```python
class RaveScreen(xbmcgui.WindowXML):
    def onInit(self):
        items = [...]                 # xbmcgui.ListItem, same menu data
        self.addItems(items)          # populates control 50
        # optional: set static images through kodi.ADDON_PATH

    def onAction(self, action):
        if action.getId() in (9, 10, 92):   # PARENT_DIR, PREVIOUS_MENU, NAV_BACK
            self.close()

    def onClick(self, control_id):
        if control_id == 50:
            index = self.getCurrentListPosition()
            # route the focused row; close before opening the next screen
```

- Open with `show()` and keep the calling route alive until the window closes.
  If you need a blocking call, derive from `xbmcgui.WindowXMLDialog` and use
  `doModal()`; the geometry and controls are identical.
- Do not make the Surprise overlay modal; it is `show()` + a timed frame loop
  by design.
- Close the screen **before** `setResolvedUrl` / `Player.play` if the row is a
  playable item.

### 5.2 Surprise

- `SurpriseReveal.show()` as today; `finally: close()` before the random pick.
- `onAction` sets `_rave_cancelled = True` and closes on 9/10/92.
- Button 107 sends `Action(Back)`; the same handler catches it.
- The 1.2 s minimum is the existing `SURPRISE_DURATION`; do not shorten it.

### 5.3 Focus order

- Home: only control 50 is focusable; the footer keycaps are graphics.
- Surprise: only control 107 is focusable. Up/Down/Left/Right may be no-ops;
  Back and OK both cancel.
- No custom keymap. No global action override.

---

## 6. Reference XML skeleton

This is the structural reference, not a complete copy of every label (the
tables above are the source of truth). Replace `R/` with
`special://home/addons/plugin.audio.raveplayer/resources/art/rave-screen/`.
The list is **id 50**.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<window type="window" id="14002">
  <coordinates>
    <system>1</system>
    <posx>0</posx>
    <posy>0</posy>
  </coordinates>
  <controls>

    <!-- background -->
    <control type="image" id="100">
      <posx>0</posx><posy>0</posy><width>1280</width><height>720</height>
      <texture>R/screen-bed-1280x720.jpg</texture>
      <aspectratio>stretch</aspectratio>
    </control>
    <control type="image" id="101">
      <posx>0</posx><posy>0</posy><width>1280</width><height>720</height>
      <texture>R/noise-overlay-1280x720.png</texture>
      <aspectratio>stretch</aspectratio>
    </control>

    <!-- header -->
    <control type="image" id="110">
      <posx>70</posx><posy>46</posy><width>48</width><height>48</height>
      <texture>R/mark-shadow-48x48.png</texture>
    </control>
    <control type="image" id="111">
      <posx>64</posx><posy>40</posy><width>48</width><height>48</height>
      <texture>special://home/addons/plugin.audio.raveplayer/icon.png</texture>
      <aspectratio>keep</aspectratio>
    </control>
    <control type="label" id="112">
      <posx>124</posx><posy>40</posy><width>360</width><height>34</height>
      <label>[B]RAVE PLAYER[/B]</label>
      <font>font13</font>
      <textcolor>0xFFF2EEE3</textcolor>
      <aligny>center</aligny>
    </control>
    <control type="image" id="113">
      <posx>124</posx><posy>74</posy><width>110</width><height>16</height>
      <texture>R/label-the-rave-screen.png</texture>
      <aspectratio>keep</aspectratio>
    </control>
    <control type="label" id="114">
      <posx>1000</posx><posy>40</posy><width>216</width><height>28</height>
      <label>$INFO[System.Time]</label>
      <font>font12</font>
      <textcolor>0xFFE8FF00</textcolor>
      <align>right</align><aligny>center</aligny>
    </control>
    <control type="label" id="115">
      <posx>1000</posx><posy>72</posy><width>216</width><height>24</height>
      <label>[B]$INFO[Container(50).NumItems][/B] ROOMS · STANDBY</label>
      <font>font10</font>
      <textcolor>0xFFA8A399</textcolor>
      <align>right</align><aligny>center</aligny>
      <visible>String.IsEmpty(Player.Title)</visible>
    </control>
    <control type="label" id="116">
      <posx>1000</posx><posy>72</posy><width>216</width><height>24</height>
      <label>[B]$INFO[Container(50).NumItems][/B] ROOMS · ON AIR</label>
      <font>font10</font>
      <textcolor>0xFFA8A399</textcolor>
      <align>right</align><aligny>center</aligny>
      <visible>!String.IsEmpty(Player.Title)</visible>
    </control>
    <control type="image" id="117">
      <posx>64</posx><posy>112</posy><width>1152</width><height>2</height>
      <texture>R/rule-acid-1152x2.png</texture>
    </control>
    <control type="image" id="118">
      <posx>66</posx><posy>114</posy><width>1152</width><height>2</height>
      <texture>R/rule-magenta-1152x2.png</texture>
      <colordiffuse>0x88FFFFFF</colordiffuse>
    </control>

    <!-- hero -->
    <control type="image" id="200">
      <posx>588</posx><posy>160</posy><width>640</width><height>360</height>
      <texture>R/hero-shadow-640x360.png</texture>
    </control>
    <control type="image" id="201">
      <posx>576</posx><posy>148</posy><width>640</width><height>360</height>
      <texture>$INFO[Container(50).ListItem.Art(fanart)]</texture>
      <aspectratio>stretch</aspectratio>
      <fadetime>220</fadetime>
    </control>
    <control type="image" id="202">
      <posx>576</posx><posy>148</posy><width>640</width><height>360</height>
      <texture>R/hero-scrim-640x360.png</texture>
    </control>
    <control type="image" id="203">
      <posx>608</posx><posy>204</posy><width>140</width><height>140</height>
      <texture>R/hero-sticker-shadow-140x140.png</texture>
    </control>
    <control type="image" id="204">
      <posx>600</posx><posy>196</posy><width>140</width><height>140</height>
      <texture>$INFO[Container(50).ListItem.Icon]</texture>
      <aspectratio>keep</aspectratio>
    </control>
    <control type="image" id="205">
      <posx>576</posx><posy>148</posy><width>640</width><height>360</height>
      <texture>R/hero-frame-640x360.png</texture>
    </control>
    <control type="image" id="206">
      <posx>596</posx><posy>164</posy><width>50</width><height>35</height>
      <texture>R/sticker-rp.png</texture>
      <aspectratio>keep</aspectratio>
    </control>
    <control type="label" id="207">
      <posx>662</posx><posy>170</posy><width>120</width><height>24</height>
      <label>$INFO[Container(50).ListItem.Property(rp_code)]</label>
      <font>font10</font>
      <textcolor>0xFFE8FF00</textcolor>
      <aligny>center</aligny>
    </control>
    <control type="image" id="208">
      <posx>600</posx><posy>354</posy><width>140</width><height>20</height>
      <texture>R/label-on-the-screen.png</texture>
      <aspectratio>keep</aspectratio>
    </control>

    <!-- hero caption -->
    <control type="label" id="209">
      <posx>579</posx><posy>514</posy><width>640</width><height>36</height>
      <label>[B][UPPERCASE]$INFO[Container(50).ListItem.Label][/UPPERCASE][/B]</label>
      <font>font13</font>
      <textcolor>0xFF22E6FF</textcolor>
      <aligny>center</aligny>
    </control>
    <control type="label" id="210">
      <posx>576</posx><posy>512</posy><width>640</width><height>36</height>
      <label>[B][UPPERCASE]$INFO[Container(50).ListItem.Label][/UPPERCASE][/B]</label>
      <font>font13</font>
      <textcolor>0xFFF2EEE3</textcolor>
      <aligny>center</aligny>
    </control>
    <control type="label" id="211">
      <posx>576</posx><posy>548</posy><width>640</width><height>22</height>
      <label>$INFO[Container(50).ListItem.Label2]  ·  $INFO[Container(50).ListItem.Property(rp_code)]</label>
      <font>font10</font>
      <textcolor>0xFFE8FF00</textcolor>
      <aligny>center</aligny>
    </control>
    <control type="label" id="212">
      <posx>576</posx><posy>572</posy><width>640</width><height>36</height>
      <label>$INFO[Container(50).ListItem.Plot]</label>
      <font>font10</font>
      <textcolor>0xFFA8A399</textcolor>
      <wrapmultiline>true</wrapmultiline>
    </control>

    <!-- the row list: MUST be id 50 for WindowXML window lists -->
    <control type="list" id="50">
      <posx>64</posx><posy>148</posy><width>480</width><height>432</height>
      <onup>50</onup><ondown>50</ondown>
      <onleft>50</onleft><onright>50</onright>
      <scrolltime>180</scrolltime>

      <itemlayout height="48" width="480">
        <control type="label">
          <posx>6</posx><posy>0</posy><width>24</width><height>48</height>
          <label>$INFO[ListItem.Property(rp_index)]</label>
          <font>font10</font><textcolor>0xFFA8A399</textcolor>
          <align>center</align><aligny>center</aligny>
        </control>
        <control type="image">
          <posx>38</posx><posy>6</posy><width>36</width><height>36</height>
          <texture>$INFO[ListItem.Icon]</texture>
          <aspectratio>keep</aspectratio>
        </control>
        <control type="label">
          <posx>86</posx><posy>0</posy><width>246</width><height>48</height>
          <label>$INFO[ListItem.Label]</label>
          <font>font12</font><textcolor>0xFFF2EEE3</textcolor>
          <aligny>center</aligny>
        </control>
        <control type="label">
          <posx>336</posx><posy>0</posy><width>104</width><height>48</height>
          <label>$INFO[ListItem.Label2]</label>
          <font>font10</font><textcolor>0xFFA8A399</textcolor>
          <align>right</align><aligny>center</aligny>
        </control>
        <control type="image">
          <posx>0</posx><posy>47</posy><width>480</width><height>1</height>
          <texture>R/row-separator-480x1.png</texture>
        </control>
      </itemlayout>

      <focusedlayout height="48" width="480">
        <control type="image">
          <posx>6</posx><posy>7</posy><width>474</width><height>40</height>
          <texture>R/focus-plate-shadow-474x40.png</texture>
          <animation effect="slide" start="-8,0" end="0,0" time="160">Focus</animation>
          <animation effect="fade" start="0" end="100" time="120">Focus</animation>
        </control>
        <control type="image">
          <posx>0</posx><posy>3</posy><width>474</width><height>40</height>
          <texture>R/focus-plate-474x40.png</texture>
        </control>
        <control type="image">
          <posx>0</posx><posy>6</posy><width>6</width><height>34</height>
          <texture>R/focus-bar-6x34.png</texture>
          <animation effect="fade" start="0" end="100" time="120">Focus</animation>
        </control>
        <control type="image">
          <posx>40</posx><posy>8</posy><width>36</width><height>36</height>
          <texture>R/icon-shadow-36x36.png</texture>
        </control>
        <control type="image">
          <posx>38</posx><posy>6</posy><width>36</width><height>36</height>
          <texture>$INFO[ListItem.Icon]</texture>
          <aspectratio>keep</aspectratio>
        </control>
        <control type="label">
          <posx>6</posx><posy>0</posy><width>24</width><height>48</height>
          <label>$INFO[ListItem.Property(rp_index)]</label>
          <font>font10</font><textcolor>0xFFE8FF00</textcolor>
          <align>center</align><aligny>center</aligny>
        </control>
        <control type="label">
          <posx>88</posx><posy>2</posy><width>246</width><height>48</height>
          <label>[B]$INFO[ListItem.Label][/B]</label>
          <font>font12</font><textcolor>0xFF22E6FF</textcolor>
          <aligny>center</aligny>
          <animation effect="slide" start="-2,0" end="0,0" time="150">Focus</animation>
        </control>
        <control type="label">
          <posx>86</posx><posy>0</posy><width>246</width><height>48</height>
          <label>[B]$INFO[ListItem.Label][/B]</label>
          <font>font12</font><textcolor>0xFFF2EEE3</textcolor>
          <aligny>center</aligny>
        </control>
        <control type="label">
          <posx>336</posx><posy>0</posy><width>104</width><height>48</height>
          <label>$INFO[ListItem.Label2]</label>
          <font>font10</font><textcolor>0xFFE8FF00</textcolor>
          <align>right</align><aligny>center</aligny>
        </control>
        <control type="label">
          <posx>444</posx><posy>0</posy><width>24</width><height>48</height>
          <label>›</label>
          <font>font13</font><textcolor>0xFFE8FF00</textcolor>
          <align>center</align><aligny>center</aligny>
        </control>
      </focusedlayout>
    </control>

    <!-- footer plate + states (one state shown; mirror the table for the rest) -->
    <control type="image" id="600">
      <posx>64</posx><posy>620</posy><width>1152</width><height>64</height>
      <texture>R/footer-plate-1152x64.png</texture>
    </control>
    <control type="image" id="601">
      <posx>76</posx><posy>630</posy><width>67</width><height>29</height>
      <texture>R/sticker-on-air.png</texture>
      <aspectratio>keep</aspectratio>
      <visible>Player.Playing</visible>
    </control>
    <control type="label" id="603">
      <posx>156</posx><posy>636</posy><width>350</width><height>28</height>
      <label>$INFO[Player.Title]</label>
      <font>font12</font><textcolor>0xFFF2EEE3</textcolor>
      <aligny>center</aligny>
      <visible>!String.IsEmpty(Player.Title)</visible>
    </control>
    <control type="label" id="605">
      <posx>550</posx><posy>622</posy><width>60</width><height>18</height>
      <label>$INFO[Player.Time]</label>
      <font>font10</font><textcolor>0xFFE8FF00</textcolor>
      <aligny>center</aligny>
      <visible>!String.IsEmpty(Player.Duration)</visible>
    </control>
    <control type="progress" id="608">
      <posx>550</posx><posy>676</posy><width>340</width><height>3</height>
      <info>progress</info>
      <texturebg>R/progress-track-340x3.png</texturebg>
      <texturemid>R/progress-fill-2x3.png</texturemid>
      <visible>!String.IsEmpty(Player.Duration)</visible>
    </control>

  </controls>
  <defaultcontrol>50</defaultcontrol>
</window>
```

---

## 7. Kodi notes that will bite

1. **`Container(50)`, not `Container(500)`.** The WindowXML window list is
   id 50–59. A 500 list can draw if you populate it manually, but
   `addItems()` / `getCurrentListPosition()` bind to the window list.
2. **Textures are absolute.** Relative paths resolve through skin media and can
   pick up a same-named skin file. Unique names help; absolute paths settle it.
3. **Fonts are skin-owned.** The window cannot load a TTF. `font13/12/10` are
   the contract; if a skin redefines them, adjust control heights, not the art.
4. **`[B]`, `[UPPERCASE]`, `[COLOR]` are skin markup.** Do not put markup in
   `ListItem.Label`/`Label2`; the hero adds display markup around the label.
5. **`Player.Playing` is false when paused.** Use `!String.IsEmpty(Player.Title)`
   for the now-playing group and `Player.Playing` only for the ON AIR sticker.
6. **`Player.Duration` is empty on many live streams.** Hide total/progress,
   keep the waveform; never show `00:00`.
7. **`Action(Back)`** on button 107 is routed to `onAction`. Handle IDs
   `9, 10, 92`; call `close()` once.
8. **Do not make the Surprise overlay modal.** It is `show()` + a timed frame
   loop and must close before the random pick.
9. **Texture cache** is keyed by path. Replacing a file with the same name can
   serve the old bitmap until Kodi restarts; that is why the release note says
   “restart once”.
10. **720p vs 1080p.** The XML is 720p. Do not add a 1080 variant of every
    coordinate; Kodi scales. The 1920 assets exist because the bed/burst benefit
    from native pixels on a 4K UI, not because the window is authored at 1080.

---

## 8. Smoke test for the coder

1. Open 14002. The list shows nine rows, focus on 01, hero is `fanart-latest`.
2. Move Down: hero crossfades, row 02 gets plate/bar/twin/fact/chevron.
3. Press OK on 02: the route opens; no leftover window.
4. Press Back from 14002: window closes, Kodi UI returns.
5. Start a tape, reopen 14002: footer shows ON AIR, title/time/wave/progress;
   header says ON AIR.
6. Pause: ON AIR sticker hides, track/title remains.
7. Start live radio: total/progress hide, waveform/title remain.
8. Open 14003: head spins at 10 fps, Back cancels, random pick is skipped.
9. Open 14003 and press OK on the CANCEL button: same cancel path.
10. Restart Kodi once after installing new texture names; verify no stale art.

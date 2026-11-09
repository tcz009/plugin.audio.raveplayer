# Rave Screen — `script.raveplayer.ui`

Full-screen Kodi window for Rave Player, version 3.9.56 (it requires
`plugin.audio.raveplayer` 3.9.56).

This is a **script add-on**, not an overlay. It owns one
`xbmcgui.WindowXML` window at 1280×720 and reads the
`plugin.audio.raveplayer` data modules read-only.

## Install

Install both zips from the Rave Player repository:

- `plugin.audio.raveplayer-3.9.56.zip`
- `script.raveplayer.ui-3.9.56.zip`

Then open **Rave Player → Rave Player** (the first root row, the app launcher;
or Add-ons → Programs → Rave Screen). Back closes the window and returns you
to Kodi.

## Controls

| Input | Action |
|---|---|
| D-pad ↑ / ↓ | Move through the row list (Kodi handles scroll/focus) |
| OK | Open a source, open a pack/show, or play a track |
| Back | Pop one level; Back at home closes the window |
| OK on **SPINNING SURPRISE** | One random pack + track, ≥1.2 s spin, playback |

See `../docs/RAVE-SCREEN.md` in the source repository for the architecture,
Kodi 22 risk notes and the device test checklist.

## Splash visibility

The 14 Spinning Surprise controls (700-713) are shown by a window-property
condition, not by XML defaults:

```xml
<visible>String.IsEqual(Window.Property(rp_splash),1)</visible>
```

`KodiView.set_spinner_visible()` sets `rp_splash=1` before calling
`setVisible(True)` on the controls, and clears it when the reveal ends. Do not
replace this with a literal `<visible>false</visible>`: Kodi re-evaluates that
condition every frame and it silently overrides `setVisible()`, leaving the
splash invisible on Kodi 22 even though the Python log says it is visible.
See [`../docs/RAVE-SCREEN-SPLASH-FIX.md`](../docs/RAVE-SCREEN-SPLASH-FIX.md).

# Rave Screen — `script.raveplayer.ui`

Full-screen Kodi window for Rave Player, version 3.9.47.

This is a **script add-on**, not an overlay. It owns one
`xbmcgui.WindowXML` window at 1280×720 and reads the
`plugin.audio.raveplayer` data modules read-only.

## Install

Install both zips from the Rave Player repository:

- `plugin.audio.raveplayer-3.9.47.zip`
- `script.raveplayer.ui-3.9.47.zip`

Then open **Rave Player → Rave Screen** (the first root row). Back closes the
window and returns you to Kodi.

## Controls

| Input | Action |
|---|---|
| D-pad ↑ / ↓ | Move through the row list (Kodi handles scroll/focus) |
| OK | Open a source, open a pack/show, or play a track |
| Back | Pop one level; Back at home closes the window |
| OK on **SPINNING SURPRISE** | One random pack + track, ≥1.2 s spin, playback |

See `../docs/RAVE-SCREEN.md` in the source repository for the architecture,
Kodi 22 risk notes and the device test checklist.

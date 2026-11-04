# look-dev — mockups for the 2026 look & feel audit

Dev-only. Nothing in this directory ships in the add-on. The audit itself is
[`../LOOK-AND-FEEL-2026.md`](../LOOK-AND-FEEL-2026.md).

```sh
python3 docs/look-dev/tools/make-look-shots.py
```

## What is here

| Path | What it is |
|---|---|
| `board-before-after.png` | One-page board: root, tracks, downloads — before vs proposed |
| `current/` | What Kodi draws today, from real ListItem output |
| `proposed/` | The same data with a proposed change applied; `-clean.png` has no callouts, the other has numbered annotations |
| `capture.json` | Every captured ListItem (label, art, info, context) the renders were made from |
| `assets/cover-dreamscape12-front.jpg` | Real archive.org pack front, 1699×2485 (the sharp alternative to the 180 px thumbnail) |
| `assets/cover-dreamscape14.jpg` | The 180 px `services/img` thumbnail the add-on uses today |
| `tools/make-look-shots.py` | The renderer: dispatches the plugin through `test/stubs`, draws Estuary geometry with Pillow |
| `tools/fixtures/archive-packs.json` | Real archive.org data captured 2026-11-03, so the renderer runs offline |

## Screens

`current/` and `proposed/`:

| File | Screen | Estuary view modelled |
|---|---|---|
| `root.png` | Nine-door root menu | 52 IconWall |
| `packs.png` | Tape Packs hub | 52 IconWall |
| `tracks.png` | Dreamscape XII track list (15 real tracks) | 55 WideList, `songs` layout |
| `downloads.png` | Favourites → Downloads (sample index) | 52 IconWall (current) / 55 WideList (proposed) |
| `about.png` | About & Sources | 52 IconWall |
| `empty.png` | Failed load | 52 IconWall |
| `context.png` / `context-menu.png` | Context menu | Kodi's DialogContextMenu |
| `now-playing-overlay.png` | Bold idea: WindowXML tape deck | — |
| `focus-transition.png` | Bold idea: focus → fanart, three frames | 52 IconWall |

## Fidelity

Labels, plots, art paths, durations and context entries are the add-on's real
output. Layout numbers come from the Estuary master skin XML (`MyPrograms.xml`,
`View_52_IconWall.xml`, `View_55_WideList.xml`, `Constants_1080.xml`,
`Variables.xml`, `colors/defaults.xml`). Fonts are Arial for Estuary's Roboto,
and focus transitions/dim levels are approximated — it is a review rendering,
not a device capture.

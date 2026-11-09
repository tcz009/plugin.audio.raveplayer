# Rave Player 3.9.61 — full classic-menu parity in the screen

Patch over **3.9.60** (`4248678`) on branch `feat/3.9.61-parity`. Plugin and
Rave Player are both **3.9.61**; resolver stays **1.1.0**. This is a code-only
release: no device run, no ADB, no Shield change, no push and no tag.

## Why

3.9.60 made the full-screen app the add-on's front door, but the screen was
missing several destinations that still existed in the classic directory:
Classic Pack Series, By Rave/Venue/Promoter, By Year, Every Pack, a Pirate
Radio hub, Live Radio genre doors, and any in-app route back to the classic
UI. The 2014 line-up's Mikus Musik and Demodulated Mixtapes had also been
dropped from both surfaces.

## What is new

- **Tape Packs hub** (new home room) → Toronto, JungleTapes, RaveTapePacks,
  Classic Pack Series, By Rave, By Year, Every Pack. The three literal
  cassette sources keep their existing rooms.
- **Pirate Radio hub** (new home room) → Hardscore, Pirate Radio Archives,
  Kool FM Sets.
- **Archive-backed children**: classic filter series (including the filter's
  live door), rave catalogue entries (Archive packs plus a Mixcloud hand-off
  when the add-on is installed), year queries, and the Every Pack query.
- **Live Radio genre doors** → Hardcore, Jungle, Drum & Bass, House, UK Garage,
  Dubstep & Grime, each a playable station list from radio-browser.
- **About → Classic lists** launches `mode=classic_root` in the Programs
  window, so the original directory UI remains reachable from the screen.
- **Mikus Musik / Demodulated Mixtapes** restored in both the classic Mixes &
  Shows menu and the screen, backed by the new
  `resources/lib/legacyblog.py` RSS reader. Mikus posts play through the Kodi
  Mixcloud add-on; Demodulated posts expose their direct preview MP3.
- Home is now **13 rooms**. No existing room, row, key, art, fact, code or
  Back behaviour was removed.

## Shared taxonomy

The screen does not fork the classic data. `routes.py` now exposes public
`classic_filters`, `classic_raves`, `classic_radio_sections`,
`classic_archive_sections` and `classic_years` helpers, and the screen reads
those through the plugin bridge. `filters.json`, `rave-catalog.json`,
`RADIO_SECTIONS` and `ARCHIVE_SECTIONS` remain the single sources of truth.

## Parity contract

[`docs/PARITY-3.9.61.md`](PARITY-3.9.61.md) is the reviewed destination matrix.
`test/test_parity_3_9_61.py` enforces it:

- every page mode in `routes.HANDLERS` must be either in the matrix, a known
  playback/context action, a root helper, or the explicit `mixcloud_account`
  orphan list;
- every matrix destination must be reachable by walking the real screen data
  (home rooms, Tape Packs tree, Pirate tree, Mixes sources, Live rows and the
  About action);
- no classic mode may be silently added without a screen action.

## Tests and artifacts

New/updated tests: `test/test_parity_3_9_61.py`, `test/test_legacyblog.py`,
new screen/live/About action tests, and updated route/live/menu expectations.
The full offline suite (`python3 -m unittest discover -s test`) ran twice:
**1206 tests, OK** in both runs.

Release path:

```sh
./scripts/build.sh
./scripts/build-repo.sh
./scripts/check-repo-artifacts.sh
```

`dist/` and the versioned `repo/` zips were rebuilt from this tree.

SHA-256 (identical in `dist/` and `repo/`):

```
9552e05c7cf4ac17a9313d25dbbe155306c1b6d79f199065c9afad1da3d3b29a  plugin.audio.raveplayer-3.9.61.zip
20f860a64f6579696de64b029dd42916dd222606d9912e6b77a2b096751e19a4  script.raveplayer.ui-3.9.61.zip
a4f66ed8266b43d1c427b4d52a20fcecc2d4f99c122cf5ceefc011db1296013d  script.module.raveresolver-1.1.0.zip
c58243ca7dba70e83e2080be929be647613e6801167cafcad2ae72cd8dcb95ab  repo/addons.xml
8649f5ddf1f3492eac97bcebc325d8b017b2c4398fdfbe9aead89b1aced30d59  repo/addons.xml.md5
```

## Known limits

- Mikus posts mostly embed Mixcloud; without the official Kodi Mixcloud add-on
  the post row still lists but shows no in-Kodi media (the same policy as
  GetDarker).
- Demodulated's old full-download ZIP links are not queued; only the direct
  preview MP3 in the feed is offered.
- `mixcloud_account` remains registered-but-orphaned (no menu emits it); the
  parity test lists it explicitly so it cannot be mistaken for a destination.

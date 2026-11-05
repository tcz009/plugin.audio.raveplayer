# App integration — one implementation per concern (3.9.51)

**Branch:** `feat/app-integration` (from `feat/fullscreen-app-3.9.51`)
**Add-ons:** `plugin.audio.raveplayer` 3.9.51 · `script.raveplayer.ui` 3.9.50
**Status:** integrated offline; full suite green 2×. Not deployed to the Shield
(no push/deploy in this pass).

This pass replaced the shell's duplicates with the finished screen modules.
The shell (`window.py` + `controller.py`) is now an adapter and navigation
stack; each room's data, paging, actions and states have exactly one owner.

## Ownership map

| Concern | One owner | Shell responsibility |
|---|---|---|
| Search, Favourites, Downloads, About | `raveui/screens/library.py` (`LibraryScreens`, `Screen`, `Row`) | in-window keyboard, route string, paint, Back stack |
| Live Radio rows/state/actions | `raveui/screens/live.py` (`LiveRadio`, live `Row` dict) | click routing, pirate door, footer paint |
| Footer / now playing | `raveui/nowplaying.py` (`Footer`) | `KodiView.set_footer`, ~1 Hz `controller.tick()` |
| Spinning Surprise pick | `raveui/surprise_pick.py` (`SurprisePicker`, `pick_and_handoff`, `PlayOnce`) | splash animation, one handoff, new-gesture guard reset |
| Latest / Toronto / JungleTapes / RaveTapePacks / Mixes / root | `raveui/data.py` | unchanged shell rooms |
| Audio | `raveui/playback.py` | unchanged single playback policy |

## Removed from the shell

`raveui/data.py` no longer has:

- `_live_entries()`, `_live_genre_children()`, `_station_entry()` — Live Radio
  now comes from `LiveRadio.rows()` (3 stations + pirate door);
- `_favourite_rows()`, `_download_rows()`, `about_rows()` — the library module
  builds these rooms;
- `search()`, `_search_archive()`, `_search_jungletapes()`, `_search_live()`,
  `_search_favourites()`, `_match_score()`, `_archive_pack_entry()`;
- `random_pick()` and `last_surprise_reason` — one bounded policy now lives in
  `surprise_pick.py`.

`raveui/controller.py` no longer has keyboard scope cycling or any per-room
search/favourites/downloads/about/live/surprise data logic. `RaveData.room()`
raises for the module-owned rooms, so a regression cannot silently bring the
duplicate path back.

## One row normalisation

`RaveScreenController._adopt_row()` is the only boundary conversion:

- a library `Row` (dataclass with `payload`) becomes a `library_room`,
  `library_track` or `library_action` shell row, keeping `payload`/`action`;
- a live `Row` (dict with `action`) becomes a `station`/`section` shell row with
  the dict action preserved;
- a shell `Entry` passes through unchanged.

Room payloads still map onto the shell's existing routes:

| Library `mode` | Shell route |
|---|---|
| `archive_item` | `Entry(kind="pack", source="latest")` |
| `legacy_pack` / `legacy_post` | `pack` / `rtp_post` on RaveTapePacks |
| `legacy_jt_show` | `JungleTapes` show |
| `dnb_play` | DNB Radio show |
| `handoff` | `handoff.target()` → external `plugin://` path |

## Footer

`nowplaying.Footer` is the only footer state. `KodiView.set_footer()` paints
`rp_now_*` properties and the ON AIR sticker; the XML binds 601–608, 610, 611
and 616 to those properties. `controller.tick()` (called from `open_screen`'s
100 ms loop, throttled to ~1 Hz) refreshes elapsed/duration/progress and
pause state. Live hides duration/progress even when Kodi reports a total.

## Surprise

- One `SurprisePicker` per controller, cache shared with `RaveData` and seeded
  by the single Latest load (`RaveData.surprise_cache`).
- 2–3 bounded backend attempts (default 3, backoff 0.35 s / 0.8 s), cache-first.
- `pick_and_handoff` trips the shared `PlayOnce` guard **before** the reveal's
  handoff; the guard resets only in `_start_surprise()` (a new gesture).
- A cancelled pick paints no failure; exhaustion paints one `NO PACK FOUND`
  plate with the module's message.

## Tests

- `test/test_app_integration.py` — routing, row normalisation, idle/playing/
  paused/live footer, Surprise one-policy/one-play/cache, Back stack.
- `test/test_rave_screen.py` — shell tests updated; obsolete shell
  search/favourites/downloads/about/live/random-pick tests deleted and
  replaced with delegation assertions.
- `test/test_screens_library.py`, `test_screens_live.py`,
  `test_nowplaying_footer.py`, `test_surprise_pick.py` remain the module
  contracts (153 tests).
- `python3 -m unittest discover -s test -p 'test_*.py'` → **921 tests, OK**
  (run twice before committing).

## Residual duplication (deliberate)

- Add/remove-favourite on **non-library shell rows** (a pack/track in Latest,
  Toronto, JungleTapes, RaveTapePacks, Mixes) still uses
  `RaveData.favourite_payload()`/`add_favourite()`/`remove_favourite()`.
  The Favourites *room* reads through `LibraryScreens`; both call the plugin's
  one `favourites` module. This write-side mapping is the remaining overlap.
- The active download queue (`downloadqueue.py`) is separate from the
  Downloads *room* (`LibraryScreens.downloads`): one is a worker/progress
  concern, the other a saved-file list.
- Home row facts for Favourites/Downloads are static labels ("saved"/"offline")
  so `data.home_rows()` no longer reads the favourites/downloads stores.

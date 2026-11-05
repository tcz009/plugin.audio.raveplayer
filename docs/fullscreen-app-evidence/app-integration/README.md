# App-integration device evidence (Shield / Kodi 22)

**Date:** 5 Nov 2026 · **Device:** NVIDIA Shield TV (`192.168.1.189:5555`,
foster_e, Android 11) · **Kodi:** 22.0-BETA1 (21.90.801)
**Installed pair:** `plugin.audio.raveplayer` 3.9.51 + `script.raveplayer.ui`
3.9.50 · **Kodi webserver:** 8080 (restored; `services.webserver=true`)

These are 1280×720 JPEG reductions of 3840×2160 `adb exec-out screencap`
frames taken while exercising the integrated shell. The `raveui/controller.py`,
`raveui/data.py`, `raveui/window.py` and skin XML on the device at capture time
hash-matched this worktree, so the frames show the integrated code paths.

**No deploy was issued from this session.** No `adb push`, `adb install`, Kodi
add-on install or repository publish was run; the pair above was already
installed. Kodi was restarted between some captures to clear stale script
windows; audio was stopped and Kodi was left on **Home** at the end.

| File | State | Notes |
|---|---|---|
| `01-home.jpg` | Rave Screen home, 11 rooms | Integrated shell; Favourites/Downloads facts are the new static `saved`/`offline`; idle footer follows Latest |
| `02-search-keyboard.jpg` | In-window Search keyboard | 9 keys, **no SCOPE row** (one Archive scope owned by `screens/library.py`); subtitle says “search now to run” |
| `03-search-results.jpg` | Search results for “AMEN” | Header `AMEN · 3 packs` is the `LibraryScreens.search` subtitle; a pack-load plate overlays this frame |
| `04-favourites.jpg` | Favourites | `LibraryScreens.favourites`: `FAVOURITES`, `1 saved`, module `Row` facts (`Archive.org`) |
| `05-downloads.jpg` | Downloads | `LibraryScreens.downloads`: `7 files · 232.3 MB`, local-play rows |
| `06-about.jpg` | About & Sources | `LibraryScreens.about`: 19 rows, `Rave Player 3.9.51 · GPL-3.0-or-later`, links + every source |
| `07-live-radio.jpg` | Live Radio | `LiveRadio.rows()`: exactly 3 stations + Pirate door (the old 6 genre doors are gone) |
| `08-live-on-air.jpg` | Live Radio ON AIR | Kool FM playing; footer `ON AIR`, live hides duration/elapsed/progress |
| `09-back-audio-continues.jpg` | Back from Live | Returns to home, restores focus, audio keeps playing (header `11 ROOMS · ON AIR`, footer `ON AIR Rinse FM`) |
| `10-now-playing-footer.jpg` | Now-playing footer | Downloaded file: elapsed `0:02`, total `27:24`, progress fill. **Caveat:** this frame came from a stale stacked script window whose meta line still rendered the old `Player.Artist · Player.Album`; the model-driven title/time/duration are correct. |
| `11-surprise-splash-baseline.jpg` | **Baseline** Spinning Surprise splash | Pre-integration 3.9.50 capture (copied from the parent evidence set); not proof of the new picker |
| `12-surprise-playing-baseline.jpg` | **Baseline** Surprise playback | As above |

## What was not captured cleanly

- **Surprise splash + play on the new policy.** The device accumulated several
  script windows across launches; `Addons.ExecuteAddon` sometimes loaded a
  window from the stack instead of a fresh home, and the splash (≈1.2 s) was
  missed. The one-policy behaviour is covered by
  `test/test_surprise_pick.py` plus `test/test_app_integration.py`
  (`three bounded attempts → exactly one playback`, guard reset only on a new
  gesture, cache seeded from Latest).
- **Search empty** was not reached cleanly; the library module's empty state
  (retry row, “No matching packs”) is asserted in
  `test_screens_library.py` and `test/test_app_integration.py`.
- `10-now-playing-footer.jpg` shows the stale meta-line artefact described
  above; `KodiView.set_footer` and the model properties are covered by
  `test_nowplaying_footer.py` and the window-adapter tests.

## Reproduce (read-only)

```sh
ADB="$PWD/shield-tools/platform-tools/adb -s 192.168.1.189:5555"
HOME="$PWD/shield-tools/adbhome" ANDROID_USER_HOME="$PWD/shield-tools/adbhome" \
  $ADB exec-out screencap -p > frame.png
curl -s -u kodi:bobhope0 -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"Addons.ExecuteAddon",
       "params":{"addonid":"script.raveplayer.ui","wait":false}}' \
  http://192.168.1.189:8080/jsonrpc
```

Final state: `Player.GetActivePlayers` → `[]`, `GUI.GetProperties.currentwindow`
→ `Home` (10000), `services.webserverport` → `8080`.

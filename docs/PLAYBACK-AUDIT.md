# Playback audit (3.9.22)

Triggered by the Shield incident on 2026-11-01 where audio appeared to move
between tracks while the owner was not in the add-on.

## Evidence

- Android logcat from the Shield (read-only, Kodi already disabled) shows
  repeated ADB shell input injection between 20:27 and 20:29:
  `uid=2000(shell) /apex/.../adbd`, `InputManager: Input event injection from
  pid 3684 uid 1000`, and `handleComboKeys` for DPAD keys 19/20/21/22/23.
- Music stream creation follows those injected key events
  (`APM_AudioPolicyManager`/`AudioFlinger`, 20:27:02–20:29:05).
- The Kodi log only retains the post-restart window from 20:31; it shows two
  Rave Player `CPythonInvoker` entries and `PAPlayer::PrepareStream - Ready`
  but no add-on error/traceback. The earlier 20:27–29 Kodi log was rotated.
- The independent QA run drove the Shield by ADB key events; this is external
  input, not an add-on autonomous action.

## Static audit

Playback can only start in these code paths:

| Path | Trigger |
|---|---|
| `routes.play()` → `xbmcplugin.setResolvedUrl(True)` | explicit `mode=play` list item / RunPlugin |
| `routes._play_tracks()` → `PlayList.clear/add` + `Player().play()` | explicit `play_all` context action only |
| `routes.dnb_play()` → `routes.play()` | explicit `mode=dnb_play` list item / favourite |

`play_all` is emitted only from the Archive pack context menu (`_pack_context`)
and the track “Play all from here” context menu; it is never called by a
directory route. `_latest_live_rows`, `fav_list` `kind=stream`, `downloads_menu`
local items and `about` only construct ListItems. `download_start`,
`download_delete`, `fav_add`, `fav_remove` and the spinner never call playback.
There is no `PlayMedia`, `executebuiltin("PlayMedia")`, auto-advance, end-of-list
auto-start or download-completion play call.

Latest retains its non-playable `End of list` terminator and `files` content
type; dead DNB rows are still dropped before rendering.

## Fix

`_fail_playback()` previously called `xbmc.Player().stop()` when a resolve
failed. That could interrupt unrelated user playback if a programmatic/deep
link invoked `mode=play` with an invalid URL. It now only notifies and calls
`setResolvedUrl(False)`; it never stops, clears or starts playback.

## Regression test

`test/test_playback_audit.py`:
- dispatches root, all four hubs, Latest/on-air, archive item, favourites
  `kind=stream`, Downloads, About and other directory pages with
  `PlayList`/`Player`/`setResolvedUrl` mocked, asserting none are called;
- asserts explicit `play` still calls `setResolvedUrl(True)` and explicit
  `play_all` still starts the playlist;
- asserts a failed resolve does not stop user playback.

Full suite: **409 tests OK** (403 before this audit; 6 new playback-audit
tests).

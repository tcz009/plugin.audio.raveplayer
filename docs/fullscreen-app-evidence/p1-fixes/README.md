# P1 fixes — device acceptance (Shield / Kodi 22)

**Date:** 5 Nov 2026 · **Device:** NVIDIA Shield TV (`192.168.1.189:5555`,
foster_e, Android 11) · **Kodi:** 22.0-BETA1 (21.90.801)
**Installed:** `plugin.audio.raveplayer` 3.9.51 + `script.raveplayer.ui` 3.9.50
**Webserver:** JSON-RPC on 8080 (`kodi` / local credential), ADB over Ethernet.

The installed `raveui/controller.py`, `window.py`, `downloadqueue.py`,
`tasks.py`, `downloadworker.py`, `screens/library.py`, `screens/live.py` and
`resources/lib/http.py` were SHA-1-compared to this worktree after the run; all
matched. Screenshots are 1280×720 reductions of `adb exec-out screencap`
frames.

| # | File | Scenario | Observed |
|---|---|---|---|
| 0 | `00-home.jpg` | App home after a clean launch | 11 rooms, Latest focused, one window |
| 1 | `01-back-during-load-plate.jpg` | Cold Latest load still painting `PLEASE WAIT` | Plate is real; the load was still in flight |
| 2 | `02-back-during-load-home.jpg` | Back pressed during that load | Kodi Home (`10000`); window closed, one close, invoker gone |
| 3 | `03-surprise-timeout-no-play.jpg` | Spinning Surprise with Archive blackholed | `PICK TIMED OUT`; `Player.GetActivePlayers` `[]`; footer `NOTHING PLAYING` |
| 4 | `04-live-on-air.jpg` | Kool FM playing | Row `ON AIR`; footer `ON AIR / Kool FM`; live hides duration |
| 5 | `05-double-launch-one-window.jpg` | Two `Addons.ExecuteAddon` calls | One screen; log `second launch refused; a screen is already open.` |
| 6 | `06-live-stop-clears-on-air.jpg` | Remote Stop while live | Row back to `LIVE`, footer `STANDBY`, status `Stopped.`, player `[]` |
| 7 | `07-live-then-normal-track.jpg` | Live then a downloaded track | Footer is the normal track with elapsed/total; no stale Kool FM state |
| 8 | `08-favourites-dnb-platform.jpg` | Saved DNB + platform favourites | Three saved rows, including DNB and YouTube hand-off |
| 9 | `09-handoff-favourite-opens-content.jpg` | OK on the platform favourite | YouTube add-on opened the content; footer shows its title |
| 10 | `10-dnb-favourite-opens-content.jpg` | OK on the saved DNB show | Resolved stream plays in Kodi; footer shows the DNB title and duration |
| 11 | `11-downloads-active-progress.jpg` | 167 MB Archive download active | Downloads header `1 active · 8 files`; row `3%` (percent comes from the owner process) |
| 12 | `12-downloads-cancel.jpg` | OK on the active row | Row `cancelling`; store becomes `cancelled`; sidecar cancel flag drains; transfer stops |

## Method notes

`Back during load` was measured with cold caches (plugin cache deleted, Kodi
restarted) and JSON-RPC `GUI.GetProperties`: after Back the current window was
`10000` within ~0.1 s (one run: Back at +0.87 s after OK, Home at +0.96 s).
The screenshot above was captured while the plate was still up in the same
cold-load state.

`Surprise timeout` used a temporary fault injection in the **installed plugin
only**: `resources/lib/http.py` slept for 60 s on `archive.org` requests, so
the screen's 45 s `ThreadTaskRunner` timeout fired. The original `http.py` was
pushed back immediately afterwards and its SHA-1 matched this worktree. The
screen itself was not modified for the test. `Player.GetActivePlayers` was
`[]` at the timeout and still `[]` 10 s later; the footer never changed.

`Double launch` fired two `Addons.ExecuteAddon` calls ~300 ms apart. The log
showed exactly one `home rows=11` line and one
`second launch refused; a screen is already open.` line. The marker file
`userdata/addon_data/script.raveplayer.ui/screen-instance.lock` is created and
removed by `open_screen()`.

`Downloads cancel` was exercised through the real Downloads room. The active
row's percent came from the headless owner's store; pressing OK wrote the
cancel sidecar that the transfer worker polls before each chunk. The row
turned `cancelling`, then the store (`download-queue.json`) became
`cancelled`, and the worker lock drained.

## Cleanup

The temporary favourites rows used for the DNB/YouTube checks were removed and
the device's original `favourites.json` restored. The test queue files
(`download-queue.json*`) and the partial transfer were removed; the app was
left closed on Kodi Home and the player stopped. No deploy, tag or push was
performed from the device session.

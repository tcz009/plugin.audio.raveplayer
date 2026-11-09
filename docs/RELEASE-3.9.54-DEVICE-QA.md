# Rave Player 3.9.54 — full device verification (release gate)

**Date:** 9 Nov 2026 · **Device:** Nvidia Shield `192.168.1.189:5555` · **Kodi:** 22.0-BETA1
(`20260621-77395cf42e`, Piers) · **Skin:** Estuary · **JSON-RPC:** `:8080` (`kodi`)

**Build under test:** plugin `3.9.54` / screen `3.9.54` / resolver module `1.1.0`
(`raveplayer-worktrees/release-3.9.54`, commit `1510875` "3.9.54: resolver wiring + speed pass",
`check-repo-artifacts.sh` clean).

**Verdict: SHIP** — no release blockers. Three P2 defects and four P3 defects are recorded
below; none loses data, breaks playback, or blocks the normal user path. The owner-approved
Resolver settings are configured on the device and survive a Kodi restart.

Shield system settings, CEC, power, display and sleep were **not** touched. Kodi was
force-stopped exactly once (settings-persistence reboot) and is left on Kodi Home with
playback stopped. **No TV/CEC/display anomaly was observed** at any point (no input switch,
no standby, no resolution change); the TV stayed on the Shield input throughout.

---

## 1. Install identity — PASS

`Addons.GetAddonDetails`:

| add-on | version | enabled | path |
|---|---|---|---|
| `plugin.audio.raveplayer` | **3.9.54** | yes | `…/.kodi/addons/plugin.audio.raveplayer/` |
| `script.raveplayer.ui` | **3.9.54** | yes | `…/.kodi/addons/script.raveplayer.ui/` |
| `script.module.raveresolver` | **1.1.0** | yes (see below) | `…/.kodi/addons/script.module.raveresolver/` |
| `repository.raveplayer` | 1.0.0 | yes | `…/.kodi/addons/repository.raveplayer/` |

* The plugin declares `script.module.raveresolver >= 1.1.0`; the screen declares
  `plugin.audio.raveplayer >= 3.9.54`.
* **Resolver module was found disabled** (`enabled:false`) although installed at 1.1.0. It was
  enabled with `Addons.SetAddonEnabled` before testing. A disabled dependency would have made
  every Mediafire/Drive/Mega path fail at import. This is an install-state fix, not a code change.
* **Repo artifacts:** `scripts/check-repo-artifacts.sh` → *"repo/ artifacts are current and
  committed for plugin 3.9.54, screen 3.9.54, resolver 1.1.0"*; `repo/addons.xml.md5` matches
  `addons.xml` (`1cb691a4…fd6`).
* **Device == repo payload:** every non-`__pycache__` file in the three installed add-ons was
  hashed on-device (`sha256sum`) and compared with the extracted repo zips:
  plugin **144/144**, screen **105/105**, resolver **21/21** files identical. Only runtime
  `__pycache__/*.pyc` files differ (expected; Kodi compiles on first run).
* **No conflicting 3.9.5x directories:** `addons/` contains exactly one directory per rave
  add-on. There are no `*.old`, `*-3.9.5x` or backup copies. `addons/packages/` still holds an
  old `plugin.audio.raveplayer-3.9.28.zip` (installer cache, not an active add-on); harmless.
* Evidence: `qa-3.9.54/evidence/{zip,device}-<addon>.sha256`, `diff-*.txt`.

---

## 2. Settings changed (owner-approved resolver setup) — PASS

Set through **Kodi's own add-on Settings UI** (Add-ons ▸ Music add-ons ▸ Rave Player ▸ Settings
▸ *Resolver (Mediafire / Drive / Podomatic / Mega)*), **not** by editing `settings.xml`. No
backup was required because the file was never written by hand; Kodi serialised the values on
OK. The pre-change file had no `resolver_*` keys at all.

| setting | value | notes |
|---|---|---|
| `resolver_service_url` | `http://192.168.1.179:8097` | LAN base; service `/api/health` reachable |
| `resolver_service_token` | 64-hex token from `.git-auth/resolver_token` | masked in UI as `********`; Kodi stores text settings in plain text in `settings.xml` — file is in the private Kodi profile, not logged |
| `resolver_service_cookie` | *(blank)* | Bearer wins |
| `resolver_enable_mega` | `true` | |

Kodi also added `default="true"` attributes to three untouched settings when it rewrote the file
(`results_per_page`, `rtp_egress_fallback`, `rtp_egress_hosts`); **their values are unchanged**
(50 / true / `ravetapepacks.com`). All pre-existing settings were preserved:
`episode_limit=60`, `radio_limit=100`, `hide_empty_feeds=true`, `spinner_overlay=true`,
`spinner_tuning=false`, `surprise_animate=false`, `rtp_egress_proxy=192.168.1.142:8888`.

**Persistence after Kodi restart:** force-stop + relaunch, then read back:
URL, token, Mega=true and every legacy setting still present; resolver module still enabled;
add-on versions unchanged. Screens: `13-resolver-settings.png`, `18-mega-on.png`,
`70-relaunch.png`. File snapshot: `qa-3.9.54/logs/settings-before-reboot.xml`.

Note: `CAddonSettings … failed to parse old setting definition for "results_per_page" of type
"select"` appears in the log. It is **pre-existing** (18 occurrences in `kodi.old.log` from
earlier builds, before this pass) and not caused by the settings save.

---

## 3. App walkthrough — PASS (2 P2 visual defects)

Launched with `Addons.ExecuteAddon(script.raveplayer.ui)` from Kodi Home. Home painted
**11 rooms**; footer `NOTHING PLAYING`; no freeze, no relaunch loop, no zombie process. Back from
Home returned to Kodi Home and ended the script (`CPythonInvoker` exit), and a fresh launch
immediately after Back worked.

| room / action | result | evidence |
|---|---|---|
| First paint | 11 rows, 539–640 ms | `70-relaunch.png`, log |
| Latest | 100 items, `Page 1 of 2`, `SAVED LIST · up to date` | `21-latest.png` |
| Latest page 2 | `NEXT PAGE ▸` row → `Page 2 of 2`, 118 ms | `22-latest-end.png`, `23-latest-page2.png` |
| Back from page 2 | returns to page 1, focus on Next Page | `24-back-page1.png` |
| Toronto hub | 4 genres | `25-toronto-hub.png` |
| Toronto genre | Jungle & Hardcore, 678 items, `Page 1 of 14` | `26-toronto-genre.png` |
| JungleTapes | 310 shows / 7 pages; show opens 1 track | `27-jungletapes.png`, `28-jungle-show.png` |
| RaveTapePacks hub | 5 index rows | `29-rtp-hub.png` |
| RTP By Event index | 50 categories | `30-rtp-index.png` |
| RTP category | 3 packs | `31-rtp-category.png` |
| RTP post | 16 DJ tracks | `32-rtp-post.png` |
| Live Radio | 4 stations | `35-live-radio.png` |
| Search | in-window keyboard, query `JUNGLE` → 65 packs, 2 pages | `36`–`41` |
| Favourites | 1 saved item (Brockie – Kool FM 94.5) | `44-favourites2.png` |
| Downloads | 7 files → 13 files as downloads completed | `45`, `71`, `74`, `78` |
| About | plugin 3.9.54, screen 3.9.54, Kodi 22.0-BETA1, 19 rows | `49-about.png` |
| Back → Kodi Home | `back-home 81 / 71 / 41 ms` | `50-kodi-home-back.png`, `82-final-home.png` |

**P2-1 — Downloads room shows the Favourites hero.** Entering Downloads twice (fresh and cached)
displays the *FAVOURITES / SAVED PACKS AND SHOWS* hero while the list and counts are correct.
Reproduced at `45-downloads.png` and `46-downloads-reenter.png`.

**P2-2 — stale "now playing" chrome after an external stop.** After `Player.Stop` via JSON-RPC the
footer cleared within ~4 s but the status line kept `Playing 678 tracks — 187-…` and, on the RTP
post, `Now playing: Andy C` remained until the next navigation (`52`, `53`, `55`, `56`). In-app
Stop via the row context is the normal path and was not observed to leave this state.

**P3-1 — `NEXT PAGE` row hero shows `NO SIGNAL`.** Cosmetic; the row still works (`22-latest-end.png`).

---

## 4. Playback — PASS

All playback was started through the plugin's real `mode=play` route (the screen hands off to
the same route). `Player.GetItem.file` shows the **resolved** media URL, which is direct proof
that the resolver ran on the device.

| source | resolved URL / player file | HTTP | progress | evidence |
|---|---|---|---|---|
| Toronto direct | `https://www.torontoravemixtapearchive.com/…/187- Live at Syrous…mp3` | **206**, `audio/mpeg`, `bytes 0-32767/29266048` | 6 s of 40:38, speed 1 | log `play …`, `71`? (log) |
| RTP direct | loopback bridge `http://127.0.0.1:37085/<b64 ravetapepacks url>`; upstream via egress proxy | **206**, `audio/mpeg`, `bytes 0-32767/45395968` | 7 s of 46:49 | log `play https://www.ravetapepacks.com/…Andy_C.mp3` |
| Mediafire (EZ Garage) | `https://download1346.mediafire.com/…/72aswcrx4hlw2sh/DJ+EZ%40LaCosaNostra.mp3` | **206**, `audio/mpeg`, `bytes 0-32767/140191841` | 12 s → 17 s of 58:24 | `Player.GetItem`; log decoder `mp3float` |
| Google Drive (Mikus) | `https://drive.usercontent.google.com/download?id=1tHRu…&export=download&confirm=t&uuid=…` | **206**, `audio/mpeg` | 10 s of 54:53 | `Player.GetItem`; resolver cache file |
| Mega (PNG fixture) | `http://192.168.1.179:8097/api/mega/stream?e=…&t=…` | **206**, 32 768 B, decrypted bytes start `89 50 4e 47 0d 0a 1a 0a` (PNG) | player rejects PNG (`Could not find audio stream`) — expected | Kodi log line + direct `Range` fetch |

* Mediafire and Drive both **played through the resolver**, not a raw page URL. Header suffix
  (`|Header=…`) is applied by `kodi_url()`; Kodi's reported `file` is the signed URL.
* The Drive resolution is also visible in the device resolver cache:
  `temp/raveresolver/drive:v1:1tHRu…json` (`expires`, signed `drive.usercontent` URL).
* **Mega is proven end-to-end**: the player received the signed `/api/mega/stream` URL (extracted
  verbatim from the Kodi error line), and that URL returns 206 with decrypted PNG magic. This is
  the fallback the task allows when no audio Mega link is available.
* **Play-all / shuffle offsets:** Toronto › Jungle › context ▸ Play all → playlist **678** items,
  current position 0, `queue 678 shuffle=False`. Next/previous: position 0→1 (`AC Slater…`)→0.
  Shuffle all → `queue 678 shuffle=True`, randomized order (first item changed to
  `Dj_Ruckus…`), 678 items. Stop cleared playback; playlist retained.
* **Live radio:** Kool FM (`https://admin.stream.rinse.fm/proxy/kool/stream|noshout=true`) played,
  23 s elapsed, no total duration (live). Rinse/Centreforce/Pirate are the other three rows.
  **DejaVu FM and OSA Radio are not present in the Kodi plugin's live data** (they are web
  `/api/live` stations; `grep` over `resources/lib` finds no reference), so that web-regression
  item is **N/A on this device** rather than FAIL.
* **Silent RTP failure unchanged:** a dead `ravetapepacks.com` URL ended with no notification,
  no dialog and no spinner; only `CCurlFile … code 502` and `Kodi is not playing any media file`
  in the log (`59-rtp-silent-fail.png`). RTP silence behaviour preserved.

---

## 5. Downloads — PASS (cancel PARTIAL)

Downloads are written to `special://userdata/downloads/raveplayer/`, checked for size,
Content-Type and free space before starting, then written to a `.part` and renamed on exact
Content-Length.

| test | result | evidence |
|---|---|---|
| Direct (Toronto track from screen context ▸ Download) | **complete**, `187-…-31a814c1.mp3`, 29 266 048 B, valid MPEG sync | `74-downloads.png`; file listing |
| Resolved Mediafire (EZ Garage) | **complete**, `ez-garage-device-qa-…mp3`, **140 191 841 B** = Content-Length, header `ff fb e0 00`, metadata `source="Rave Resolver"` | `65-download-yes.png`; `downloads.json` |
| Resolved Drive (Mikus) | **complete**, `mikus-drive-device-qa-…mp3`, **134 083 154 B** = Content-Range total, header `ID3`, `source="Rave Resolver"` | `66`; `downloads.json` |
| Plan/confirm dialog | shows title, **133.7 MB** size and **4.9 GB** free before download | `63-download-confirm.png` |
| Failure path (RTP via bridge) | marked **failed / "incomplete response"** at 4 %, 1 851 392 / 45 395 968 B; **not** added to `downloads.json` | `71`/`74` rows, `download-queue.json` |
| Cancel | **PARTIAL** — context ▸ *Cancel download* sets `cancel:true`, status `cancelling` in `download-queue.json`; the already-completed duplicate file was not deleted. A plugin-invoked download (spinner overlay) has no cancel control and Back does not stop it; that attempt ran to completion. | `75-cancel-context.png`, `76-cancelled.png` |
| Integrity / truncation | no truncated file was indexed as a download; failed attempt stays `.part` and is surfaced as failed | above |

**P2-3 — cancel semantics.** The screen queue exposes Cancel and records the request, but a
download that has already completed under the same key is not removed, and a second queued row
can remain `queued`/`cancelling` after the file completed. Plugin-triggered downloads (the JSON‑RPC
path used here) show a spinner overlay with no Cancel and ignore Back.

**P3-2 — stale `.part` files** from earlier builds remain in the folder
(`damon-wild-…mp3.part` 17.5 MB, `dj-clue-…mp3.part` 51.2 MB, dated 1/5 Nov). They are not shown
as downloads; housekeeping only.

**P3-3 — duplicate queue row / page indicator on RTP categories** (`total=0` in the data makes
the header read `1/0` for category pages). Cosmetic.

---

## 6. Regressions — PASS except noted

| item | result |
|---|---|
| Favourites | PASS — existing item listed and playable context intact (`44`) |
| Live radio | PASS for Kodi's four stations (Kool FM played); DejaVu/OSA N/A (web-only) |
| Handoff items (screen → plugin) | PASS — RTP track handed off to the loopback bridge and played (`Player.GetItem` bridge URL) |
| No popups | PASS on app paths. The one popup seen (`No PVR add-on enabled`) was caused by the test harness sending raw `adb input text` keys into Kodi's global keymap while the in-window keyboard was focused — not an app dialog (`37-search-typed.png`). Download confirm/progress dialogs are expected. |
| Silent RTP failure | PASS — see §4 |
| Settings persisted after Kodi reboot (not device) | PASS — see §2 |
| Reboot / relaunch | PASS after restart. **P2-4:** an unclean screen exit leaves `addon_data/script.raveplayer.ui/screen-instance.lock` containing **Kodi's own PID** (scripts run in-process), so `_pid_alive()` is always true and the 10-minute `INSTANCE_LOCK_TTL` is the only recovery. Reproduced once (`second launch refused; a screen is already open`) after a plugin modal closed the screen; a Kodi restart cleared it and normal Back→relaunch worked repeatedly. |

---

## 7. Timings (Shield, Kodi 22 beta, 50 rows/page)

Baseline "before" is the 3.9.51/3.9.50 column of `docs/PERF-3.9.52.md`; 3.9.52 "after" is shown
for context. Values are `[script.raveplayer.ui]` INFO lines (script-internal, excludes event
dispatch), warm paint cache unless stated.

| path | 3.9.51 before | 3.9.52 | **3.9.54** |
|---|---|---|---|
| App launch → first paint | 1.19–1.33 s external (not instrumented) | 556–629 ms | **539, 561, 605, 640 ms** (4 launches) |
| Latest open (warm) | ~0.4–0.6 s typical | 91–126 ms | **42 ms** |
| Toronto hub (warm) | 467 ms external | 51 ms | **26 / 17 / 32 ms** |
| Toronto genre (warm) | 4.27 s (first) | 85 ms | **84 ms** warm; 2 019 ms X-Static first |
| Back → Kodi Home | 12×200 ms loop, worst 2.4 s | 28–79 ms | **81 / 71 / 41 ms** |

Other observed 3.9.54 lines: RTP hub 42 ms, By Event index 43 ms, category 125 ms (3 rows),
post 77 ms, JungleTapes first 220 ms, search 6 s (network, 65 hits), Downloads 13 ms cached /
42 ms refreshed, Live 27 ms cached (first 8 s window).

The only sample above the 3.9.52 Back range is 81 ms (one of three), still 30× better than the
3.9.51 loop and within the 28–79 ms + noise band.

---

## 8. Rollback — PASS

Zips exist and are valid (addon.xml present, correct ids):

| build | file | size |
|---|---|---|
| plugin 3.9.51 | `raveplayer-worktrees/resolver-client/dist/plugin.audio.raveplayer-3.9.51.zip` | 9 089 839 B |
| screen 3.9.51 | `raveplayer-worktrees/kodi-perf/dist/script.raveplayer.ui-3.9.51.zip` | 5 426 814 B |
| plugin 3.9.50 | `raveplayer-worktrees/integration-3.9.49/dist/plugin.audio.raveplayer-3.9.50.zip` | 9 088 325 B |
| screen 3.9.50 | `raveplayer-worktrees/resolver-module/dist/script.raveplayer.ui-3.9.50.zip` | 5 416 334 B |

Rollback = install 3.9.51 plugin + 3.9.51 screen (or the 3.9.50 pair), restart Kodi. The resolver
module can stay installed and enabled — 3.9.51 does not import it. Resolver settings are inert on
3.9.51 and can be cleared with *Defaults* in Configure. Paint cache is version-keyed and can be
ignored. No data migration, no settings schema change.

---

## 9. Verdict

**SHIP.**

* Install identity exact and device payload hash-identical to the repo zips.
* All eleven rooms open, page 2 works, Back returns to Kodi Home in 41–81 ms, no freeze or
  relaunch loop on the normal path.
* Direct, Mediafire, Drive playback all produce 206 + advancing playback; Mega reaches the
  signed `/api/mega/stream` URL and that URL returns 206 with decrypted PNG bytes.
* Direct and resolved downloads complete at the exact Content-Length with valid audio headers;
  failures are not indexed as downloads.
* Resolver settings are set through the UI and persist across a Kodi restart.
* Rollback artifacts are present.

**Non-blocking defects (fix in 3.9.55):** Downloads hero shows Favourites (P2-1); stale
now-playing status after external stop (P2-2); cancel semantics for completed/duplicate and
plugin-path downloads (P2-3); 10-minute single-instance lock after an unclean screen exit (P2-4).
No data loss, no crash, no blocker.

**Blockers: none.**

---

## 10. Evidence index

`qa-3.9.54/`

* `shots/00-initial.png … 82-final-home.png` — chronological device captures (3840×2160).
  Key: `13` resolver settings, `18` Mega on, `21` Latest, `23` Latest page 2, `25/26` Toronto,
  `27/28` JungleTapes, `29`–`32` RTP, `35` Live, `36`–`41` Search, `44` Favourites, `45/46/71/74/78`
  Downloads, `49` About, `50/82` Kodi Home, `63` download confirm, `75` cancel context.
* `logs/kodi-session1.log`, `logs/kodi-session2.log` — full Kodi logs for the pass.
* `logs/settings-before-reboot.xml` — settings after the UI edit, before the persistence reboot.
* `evidence/*-<addon>.sha256`, `evidence/diff-*.txt` — device vs repo payload hashes.
* `rpc.sh` — JSON-RPC helper used for every query.

Shield final state: Kodi Home (`82-final-home.png`), `Player.GetActivePlayers` = `[]`, no
playback, no Kodi modal open. No Shield system/CEC/power change was made.

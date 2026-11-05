# Rave Screen 3.9.47 / 3.9.48

**Date:** 5 Nov 2026 · **Version:** 3.9.48 (screen visual pass) · **Branch:** `integration/3.9.48`
**Status:** implemented; 3.9.48 splash paint verified on the Shield (Kodi 22),
full offline suite green; **not pushed, tagged or deployed**.

> Sections 1-9 describe the 3.9.47 implementation. Section 10 is the 3.9.48
> visual-parity pass over the same behaviour, including the device-verified
> Spinning Surprise splash fix. See
> [`RAVE-SCREEN-SPLASH-FIX.md`](RAVE-SCREEN-SPLASH-FIX.md) for the root cause
> and screenshot evidence.

This is the replacement for the plugin-list overlay approach: **a real add-on
window, not a dialog painted on top of the plugin directory**. Kodi owns the
window, so there is no plugin-list renderer to freeze, no overlay that Kodi 22
can refuse to draw, and Back follows normal Kodi window-stack behaviour.

---

## 1. What ships

| Add-on | Role | Version |
|---|---|---|
| `plugin.audio.raveplayer` | Normal plugin lists, data providers, root **Rave Screen** row and fallback | 3.9.48 |
| `script.raveplayer.ui` | Full-screen Rave Screen `WindowXML` owner | 3.9.48 |
| `repository.raveplayer` | Repository catalogue, now three add-ons | 1.0.0 |

The script add-on declares `plugin.audio.raveplayer` as a dependency and imports
its data modules read-only. The plugin does **not** depend on the script, so the
normal lists still install and work on their own; the root row checks
`System.HasAddon(script.raveplayer.ui)` and shows one notification if it is
missing.

### Files

```
script.raveplayer.ui/
├── addon.xml                          # xbmc.python.script, xbmc.python 3.0.0
├── default.py                         # entry point; imports raveui.window
├── raveui/
│   ├── window.py                      # WindowXML adapter + open_screen keepalive
│   ├── controller.py                  # view state, Back stack, single-pick surprise
│   ├── data.py                        # six home rows + lazy source loaders
│   ├── pluginbridge.py                # read-only import alias for plugin resources/lib
│   ├── animation.py                   # >=1.2 s reveal-worker head spin
│   ├── playback.py                    # one-item PlayList -> Player().play
│   └── tasks.py                       # bounded worker-thread data loads
├── resources/skins/Default/720p/script-raveplayer-ui.xml
├── resources/skins/Default/media/     # focus plate + static backdrop
└── resources/art/spinner/             # 10 bundled head frames (512 px)
```

Plugin changes: `resources/lib/routes.py` (`MENU_ART["screen"]`, root row,
`rave_screen`, `HANDLERS["screen"]`), `addon.xml`, `changelog.txt`,
`resources/art/screen.png`, `resources/art/fanart-screen.jpg`,
`scripts/build.sh`, `scripts/build-repo.sh`, `scripts/check-repo-artifacts.sh`,
`.github/workflows/build.yml`.

**Art:** the 2026 screen-bed, surprise burst, 512 px rotation frames, footer
plate and surprise ring come from the parallel design specialist's
`docs/rave-screen/assets` snapshot. `scripts/make-screen-art.py` still generates
the root `screen.png` / `fanart-screen.jpg` and fallback hero as placeholders;
the parallel specialist owns the final sticker/hero. The generator refuses to
overwrite existing art by default (`--force` to regenerate placeholders, which
would replace the integrated design snapshot).

---

## 2. Window, focus and Back

- `<window type="window" id="15047">` at 1280×720, skin XML loaded from the
  script add-on's `resources/skins/Default/720p/`.
- Layout: full-bleed backdrop; large hero art on the right; wordmark, view
  title and subtitle on the left; a vertical `list` (id 50) under them; status
  and now-playing lines at the bottom.
- The list is the `defaultcontrol`. Kodi handles D-pad motion and scrolling;
  `onAction` forwards non-Back actions to the base window and refreshes the
  hero for the selected row. Back (`ACTION_NAV_BACK` / `ACTION_PREVIOUS_MENU`)
  pops one view; at home it closes the window.
- Skin animations:
  - window/hero fade and slide on `WindowOpen`;
  - list and focused-row label `Focus` zoom;
  - spinner backdrop `Visible` fade.
  The controller does not animate focus itself, so a remote burst cannot build
  a Python animation queue.
- `show()` is non-modal; `open_screen()` keeps the script alive with
  `xbmc.Monitor().abortRequested()` + `xbmc.sleep(100)` until the window marks
  itself closed. Closing is idempotent.

### View stack

```
home
  ├── Latest            → packs            → tracks → playback
  ├── Toronto           → genres           → tracks → playback
  ├── JungleTapes       → shows            → tracks → playback
  ├── RaveTapePacks     → packs            → tracks → playback
  ├── Live Radio        → stations         → playback
  └── SPINNING SURPRISE → single pick      → animation → playback
```

Back pops exactly one level while browsing. At home it closes the window; after
a playback hand-off Back closes from any depth (the footer says “exit”). If a
load is in flight it closes immediately and the late worker result is ignored.
There is no "close then reopen" path and no auto-advance folder behind the
window.

---

## 3. Data contract (read-only)

`pluginbridge.py` locates the installed plugin with
`xbmcaddon.Addon("plugin.audio.raveplayer")`, then installs the plugin tree as
the private package `raveplayer_plugin` and imports:

```
raveplayer_plugin.resources.lib.{archive,http,kodi,latest,legacy,radio,toronto,ui}
```

The alias means the plugin's relative imports work without colliding with the
script add-on's own packages. Only public read helpers are called:

| Row | Calls | Level 2 |
|---|---|---|
| Latest | `latest.recent_packs(rows=20)` | `archive.audio_files(id)` |
| Toronto | `toronto.genres()` | `toronto.tracks(genre)` |
| JungleTapes | `legacy.jungle_shows()` | `legacy.jungle_tracks(key)` |
| RaveTapePacks | `legacy.packs()` | `legacy.pack(key)`, `legacy.playable(url)` |
| Live Radio | `radio.curated()` for the three known live stations | direct `radio.stream_url()` |
| Surprise | `latest.random_pack()` then `archive.audio_files(id)` | one `random.choice` |

No settings, cache, favourites, downloads or plugin directories are written.
URLs pass through the plugin's `http.safe_stream_url`; invalid scraper URLs are
skipped rather than handed to Kodi. Artwork is a local plugin path or a public
`http(s)` Archive thumbnail.

**No network on window open.** The home screen is six static rows. Every source
load and the surprise pick runs through `ThreadTaskRunner` with a 15 s hard cap
while the GUI shows "Loading…"; the worker cannot freeze focus forever. The
worker result is discarded if the window closed first.

---

## 4. Spinning Surprise — exactly once

Sequence:

1. OK on **SPINNING SURPRISE** → the callback sets `_busy` and paints the
   splash. Visibility is bound to `Window.Property(rp_splash)`: the adapter
   sets the property to `1` and then calls `setVisible(True)` on controls
   700-713. Never use a literal `<visible>false</visible>` here — Kodi
   re-evaluates it every frame and it overrides `setVisible()`.
2. `data.random_pick()` runs once on a bounded worker:
   - `latest.random_pack()` once;
   - `archive.audio_files(identifier)` once;
   - `random.choice` over playable tracks once.
3. `SpinnerAnimator` runs on the reveal worker for **at least 1.2 s**:
   - `setImage(frame)` on control 702 (the 512 px head inside the splash);
   - `xbmc.sleep(frame_ms)`, with the Kodi GUI thread repainting independently;
   - 10 fps, frame index `int(elapsed*10) % 10`;
   - cancellation/dead control stops without playback.
4. The controller clears `rp_splash`, hides the controls and calls
   `PlaybackService.play(track)` once: builds a one-item
   `xbmc.PlayList(xbmc.PLAYLIST_MUSIC)`, adds the stream, calls
   `xbmc.Player().play(playlist)`.
5. The window sets **`Now playing: <track> — <pack>`**, notifies once, and
   stays open.
6. Any further OK while `_handed_off` is true only updates the status line
   (“Already playing — press Back to exit”); it never picks, animates or plays
   again. Back closes the window from any depth once `_handed_off` is set.

Failure paths are fail-soft and terminal for that attempt: no pick → status, no
animation, no playback; animation failure → status, no playback; playback
exception → clear `_handed_off`, status, no half-playing state. Back while
busy closes the window immediately.

> `setResolvedUrl` is not used: a script add-on has no plugin handle. Kodi's
> public `PlayList` + `Player().play` path is the hand-off. The plugin's own
> `mode=play` resolver is untouched for the normal lists.

---

## 5. Kodi 19–22 compatibility

- The script manifest requires `xbmc.python **3.0.0**` (Kodi 19 Matrix), and
  uses only APIs present since Python 3 / Kodi 19: `WindowXML`, `ControlList`,
  `PlayList`, `Player`, `Monitor`, `xbmcgui.ListItem`, `setArt/setInfo`.
- Runtime code is parsed with the Python 3.9 grammar in tests. Kodi 22 ships a
  newer Python, so 3.9 is the conservative floor, not a ceiling.
- **Dependency caveat:** the current `plugin.audio.raveplayer` 3.9.48 manifest
  still requires `xbmc.python 3.0.1` (Kodi 20+). Kodi will therefore install
  the script+plugin pair on Kodi 20–22 only. The script code is Kodi-19
  compatible, but running it on Matrix would also need the plugin requirement
  lowered — untested and not changed here because the project has no Matrix
  device. This is called out rather than claiming an untested combination.

---

## 6. Kodi 22 risk register

| Risk | Why it matters on Kodi 22 | Mitigation / status |
|---|---|---|
| `WindowXML` custom-window internals | Kodi 22 changed renderer/skin paths in past releases; a custom add-on XML is not exercised by the default skin | Uses only long-standing `WindowXML` + list controls; XML validated in tests; **device run required** |
| Splash visibility condition | A literal `<visible>false</visible>` is re-evaluated every GUI frame and silently overrides `Control.setVisible(True)`, so the reveal never paints | 700-713 bind to `Window.Property(rp_splash)`; the adapter writes the property before the controls; tests forbid literal `false`; **device-verified 4/4** (3 primary runs + rebuilt-zip smoke; see `RAVE-SCREEN-SPLASH-FIX.md`) |
| Reveal worker + control updates | `setImage` runs on the reveal worker while the Kodi GUI renders; a dead or closed control must not raise or leak | Hard 1.2 s minimum, 10 fps; bounded pick timeout; `cancelled` poll and fail-soft `setImage`; no animation queue; **device video shows the head rotating** |
| `show()` non-modal + script keepalive | If Kodi changes `show()` semantics, the script could exit and take the window with it | `open_screen` polls `window.closed` / `Monitor.abortRequested` with `xbmc.sleep(100)`; no busy-spin |
| Player hand-off from a script | Kodi may pause/stop audio when the launching script exits, or show no OSD because the custom window is on top | Window stays open after `Player().play`; Back is the explicit exit; device checklist tests audio, OSD and a second selection |
| Focus/list rendering + skin assets | Skin media paths or focus animations can differ between skins/versions | Media lives in this add-on's own `resources/skins/Default/media`; no skin fork; only built-in fonts and colours |
| Missing script add-on | Root row would otherwise be a dead item | `System.HasAddon` check + notification; normal root list is rebuilt |
| Plugin dependency version | A future plugin bump can leave the script on an older API (or uninstalled) | Dependency is pinned to 3.9.48; bridge imports under a private alias and fails with one status line, not a traceback |
| Kodi 19 dependency floor | See §5: script is 3.0.0, plugin is 3.0.1 | Documented; no Matrix claim until a device test |
| Network source slowness | Archive/radio sites can hang | Worker thread + 15 s timeout + status line; window stays usable/closeable |
| Overlay regression | A future change could reintroduce a dialog over the plugin list | There is no `Dialog`/overlay in the script; docs and tests assert `WindowXML` ownership. The old plugin Surprise Me overlay (`spinner.SurpriseReveal`) remains only on the legacy plugin route and is untouched by the new screen |

---

## 7. Device test checklist (Kodi 22, Shield)

Run after installing **both** 3.9.48 zips. Record Kodi build, skin and log file.

### Install and entry

- [ ] Install `plugin.audio.raveplayer-3.9.48.zip`, then
      `script.raveplayer.ui-3.9.48.zip` (or both from the repository).
- [ ] Settings → Add-ons → My add-ons shows **Rave Screen 3.9.48** enabled.
- [ ] Rave Player root shows **Rave Screen** as row 1, with the screen sticker
      and fanart; the other nine rows are unchanged.
- [ ] Select it: plugin directory closes, full-screen window opens (no plugin
      list visible behind it).
- [ ] Kodi log has no `script.raveplayer.ui` traceback and no unknown-control
      errors (`Non-Existent Control`, `Unknown animation`, `invalid texture`).

### Window and focus

- [ ] Backdrop is opaque and the hero art changes as the row selection moves.
- [ ] D-pad ↑/↓ moves the list; focus plate and focused label animate/scale
      smoothly; hold-to-repeat does not stutter or lose focus.
- [ ] OK opens Latest; rows show pack titles and facts.
- [ ] Back pops Latest → home; Back at home returns to the Rave Player root
      (or Kodi home, depending on launch point) with no black frame and no
      overlay left behind.
- [ ] Reopen the screen 3×; no leaked window, no doubled input and no growing
      memory in the log.

### Sources

- [ ] Latest → pack → track list loads; Back restores the pack list; no
      repeated network load.
- [ ] Toronto → genre → track list loads; play one track; audio starts.
- [ ] JungleTapes → show → track list loads; play one track.
- [ ] RaveTapePacks → pack → track list loads; play one; RTP `Referer` suffix
      is preserved (audio does not 403).
- [ ] Live Radio → Kool/Rinse/Centreforce plays; a station list failure shows a
      status line and leaves the window usable.
- [ ] Every source: Back during "Loading…" closes cleanly; the late worker does
      not reopen or mutate the window.

### Spinning Surprise

- [ ] Select **SPINNING SURPRISE**, press OK once: spinner panel appears, head
      advances for at least 1.2 s, then audio starts.
- [ ] Now-playing line reads exactly `Now playing: <track> — <pack>`.
- [ ] The spinner panel disappears; no second pick, no second `Player().play`,
      no folder auto-advance.
- [ ] Press OK repeatedly during/after playback: status changes, but the same
      track is not restarted.
- [ ] Back closes the window; audio continues (or stops as Kodi's audio policy
      dictates) with no add-on crash.
- [ ] Repeat Surprise 5×: each run picks once, animates ≥1.2 s, plays once;
      no accumulating playlist entries (`PlayList` length is 1).

### Failure paths

- [ ] Uninstall/disable `script.raveplayer.ui`: root row remains, selection
      shows one notification, normal lists work.
- [ ] Disable networking and open a source: status line explains, Back exits,
      no freeze.
- [ ] Force a bad stream (or block the host): no repeated playback; error status
      is shown; window can be closed.
- [ ] `Monitor.abortRequested` / Kodi quit while the window is open: script
      exits cleanly.

### Regression

- [ ] Normal root/hub/track lists still behave exactly as 3.9.44 (Label2,
      plots, playback, favourites, downloads).
- [ ] Download spinner (opt-in overlay) is unaffected.
- [ ] No new autoplay on any directory route; the new root row only launches the
      script when selected.

---

## 8. Tests and artefacts

```sh
python3 -m unittest discover -s test      # green
python3 -m unittest test.test_rave_screen -v   # green
./scripts/build.sh                        # both zips in dist/
./scripts/build-repo.sh                   # repo/addons.xml + both zips
./scripts/check-repo-artifacts.sh         # must print "current and committed"
```

New coverage in `test/test_rave_screen.py`:

- window class/manifest/skin XML, 720p window id, `<animation>`, skin media;
- controller start/home, focus → hero, section load, Back pop/exit;
- Back while loading closes exactly once;
- surprise single pick, one animation, one playback, no replay on repeated OK;
- no-pick, pick-exception and animation-failure paths (no playback, spinner
  hidden, busy flag cleared);
- ≥1.2 s animation timing, frame cycling, cancellation and dead-control
  fail-soft;
- playback hand-off builds a one-item playlist and calls `Player().play`;
- plugin root row, `mode=screen` launcher, missing-script fallback;
- Python 3.9 parse of every script source;
- committed repo catalogue and zip contents.

**Artifacts:** `dist/plugin.audio.raveplayer-3.9.48.zip`,
`dist/script.raveplayer.ui-3.9.48.zip`,
`repo/plugin.audio.raveplayer/plugin.audio.raveplayer-3.9.48.zip`,
`repo/script.raveplayer.ui/script.raveplayer.ui-3.9.48.zip`,
regenerated `repo/addons.xml` + `.md5`. `dist/` is gitignored; `repo/` is
committed.

**Rollback:** reinstall the previous 3.9.44 zips (and remove/uninstall
`script.raveplayer.ui` if a clean plugin-only state is wanted); no data
migration, settings or cache schema changed. `git revert` the Rave Screen
commits on the branch.

---

## 9. Known limitations (deliberate)

- Source browsing is shallow: Latest reaches tracks directly; Toronto and
  JungleTapes go genre/show → tracks; RaveTapePacks goes pack → tracks. There
  is no search, favourites, downloads, pagination or context menu in the custom
  window — those remain in the normal plugin lists.
- The screen is audio-first; it does not attempt video, visualisations or OSD
  layout.
- The root sticker/fanart and fallback hero remain placeholders; the
  screen-bed/spinner/footer art is the parallel specialist's current snapshot
  and may be replaced by their final pass.
- The Spinning Surprise splash and its 1.2 s head spin are device-verified on
  the Shield/Kodi 22; the rest of the section 7 and section 10 checklist has
  not been re-run end-to-end since the 3.9.48 visual pass.

---

## 10. 3.9.48 visual parity pass

`script.raveplayer.ui` 3.9.48 rebuilds the window to the design specialist's
`docs/rave-screen/WINDOWXML-CONTROL-MAP.md` (plugin version stays 3.9.48;
behaviour is unchanged).

### What changed

- The 59 design assets were copied to
  `script.raveplayer.ui/resources/art/rave-screen/`; the untouched Rave Player
  `icon.png` is bundled beside them as `mark.png`. Every static texture is an
  absolute `special://home/addons/script.raveplayer.ui/...` path.
- `script-raveplayer-ui.xml` is now the control map: 1280x720 bed + grain,
  header mark/wordmark/baked subtitle, acid/magenta rules, clock and room
  count, 640x360 hero poster (shadow, fanart, scrim, 140px sticker, RP
  sticker/code, frame, baked kicker), cyan/paper title twins, meta and plot,
  48px rows with plate/shadow/bar/icon-shadow/twin/fact/chevron, and the
  1152x64 footer with ON AIR, NOW PLAYING, `Player.*` metadata, waveform,
  progress and keycaps. The list remains **control 50** with
  `defaultcontrol 50`; the XML has no focus-id override.
- Rows now carry `rp_index`, `rp_code`, `rp_meta` and `rp_fact` item
  properties, `Label2` facts (duration/count/source, <= 16 chars), `fanart`
  art for the hero binding and a video plot for the hero caption.
- The footer shows the selected row while idle and `Player.*` while playing;
  `Player.Duration` hides the total and progress on live radio.
- Spinning Surprise is restyled as a full-window state of the same window:
  burst, ring, 512px head frames (Python swaps only control 702), caption
  plate, baked SURPRISE ME / SPINNING THE RACK labels, RP-02 code line and
  B CANCEL. The single-pick guard, >= 1.2 s animation, one playback handoff
  and fail-fast launcher are unchanged.
- New offline tests parse the XML and assert control 50/defaultcontrol 50/no
  focus override, that every referenced texture exists, the 720p bands and
  64/36 safe margins for live type, the focus/hero/footer bindings, the
  bundled asset set and the row facts.

### Deviations from the design map (deliberate)

- The window keeps the script add-on's established id `15047` (Kodi assigns
  the runtime id); the map's `14002/14003` are plugin-window ids.
- One window, not two: the Surprise state lives on 700-713 above the home
  controls, so the proven `show()` + keepalive launcher does not change.
- A header breadcrumb (119/120) shows the current section, which the map does
  not define; it is right-aligned inside the safe frame and uses font12/10.
- The idle footer's main line is the focused row (the map's static
  "PICK A ROOM - PRESS OK" is replaced by the selected row + fact); the
  right-hand keycaps still say OPEN/BACK.
- The FOCUS sticker is placed above the row list at 64,118 (58x27) rather
  than omitted, so all three print stickers are present.
- Home still has the six 3.9.47 source rows (Latest, Toronto, JungleTapes,
  RaveTapePacks, Live, Surprise), not the web/map's nine root rows: adding
  favourites/search/about routing to the script window is a behaviour change,
  out of scope for a visual pass. Rows are rendered with the new anatomy.

### Device test checklist (in addition to section 7)

- [ ] Install plugin 3.9.48 + script 3.9.48; restart Kodi once so the texture
      cache picks up the new absolute paths.
- [ ] Open Rave Screen: bed/halftone/grain, mark, wordmark, baked subtitle,
      rules, clock and ROOMS count are visible; no texture is missing or
      borrowed from the skin.
- [ ] Home list: six rows with index, 36px sticker, label, right-hand fact;
      focused row has the acid bar, magenta plate shadow, cyan twin, acid
      fact and chevron; D-pad repeat stays smooth.
- [ ] Focus movement crossfades the hero fanart; hero sticker, RP code,
      title (cyan twin), meta and plot follow the row.
- [ ] Footer idle: mark, NOTHING PLAYING, selected row label and fact,
      OPEN/BACK keycaps.
- [ ] Play a tape: ON AIR sticker appears, NOW PLAYING label, Player title /
      artist / album, elapsed/total, waveform, 3px progress; header says
      ON AIR. Pause: ON AIR hides, title remains.
- [ ] Play live radio: total and progress hide; waveform and title remain.
- [x] Surprise: burst/ring/head are full-window, head spins >= 1.2 s, caption
      and CANCEL render, one pick, one playback, Back exits; B CANCEL is the
      printed affordance. **Device-verified 5 Nov 2026, 4/4 runs (3 primary + rebuilt-zip smoke).**
- [ ] 720p and 1080p UI: no live type clipped at 64/36; overscan margins hold;
      hero is 16:9 with no crop.
- [ ] Skin without font12/font10 still opens the window (degraded hierarchy,
      no crash); Kodi log has no unknown-control or invalid-texture errors.
- [ ] Run the full suite and `./scripts/check-repo-artifacts.sh`; the
      committed `repo/` must match the 3.9.48 zips.

### Splash paint fix (device-verified)

The first 3.9.48 build put a literal `<visible>false</visible>` on every
splash control (700-713). Kodi 22 treats that as a visibility *condition*,
re-evaluates it on every GUI frame and re-hides the control immediately after
`Control.setVisible(True)` — so Python logged `visible=True controls=14` while
the splash never painted. The fix binds 700-713 to
`String.IsEqual(Window.Property(rp_splash),1)`, and
`KodiView.set_spinner_visible()` sets `rp_splash=1`/`0` before touching the
controls. The 1.2 s spin and single-play behaviour are unchanged.

Verified on the Shield with four JSON-RPC-driven Surprise runs (the last on the rebuilt zip) and
`adb exec-out screencap`: the splash painted every time, the head rotated
during the reveal, and playback started once immediately after the hide.
Root cause, log timestamps and before/after frames:
[`RAVE-SCREEN-SPLASH-FIX.md`](RAVE-SCREEN-SPLASH-FIX.md) and
[`rave-screen-evidence/`](rave-screen-evidence/).

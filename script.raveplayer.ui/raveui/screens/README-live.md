# Live Radio + footer + Surprise reliability — integration notes

**Branch:** `feat/screens-live` · **Worktree:** `raveplayer-worktrees/screens-live`
**Base:** `22cbf4d` (3.9.50) · **Status:** new modules only; not integrated, not
built, not deployed.

This branch adds three pure-Python pieces for the full-screen Rave app
(Rave Screen 02 look). It deliberately does **not** edit `window.py`,
`controller.py`, `data.py`, `playback.py`, `pluginbridge.py` or any skin XML:
the lead integrates the calls below into the parallel shell
(`feat/fullscreen-app-3.9.51`).

| File | Purpose |
|---|---|
| `script.raveplayer.ui/raveui/screens/live.py` | Live Radio rows, station state, play/stop, now-playing metadata |
| `script.raveplayer.ui/raveui/nowplaying.py` | Footer model: STANDBY / playing / paused / live, progress maths, Kodi-shaped input |
| `script.raveplayer.ui/raveui/surprise_pick.py` | Bounded retry + cache-first Surprise pick, single-play gate, plugin wiring |
| `script.raveplayer.ui/raveui/screens/__init__.py` | Package exports |
| `test/test_screens_live.py` | 26 offline tests |
| `test/test_nowplaying_footer.py` | 19 offline tests |
| `test/test_surprise_pick.py` | 33 offline tests |

No new art, no new skin XML, no settings, no network call on import, and no
`xbmc`/`xbmcgui` import in any of the three modules. They can be unit-tested
on a laptop and imported by the window adapter.

---

## 1. Row protocol

`live.rows()` returns `Row` objects. A `Row` **is** a `dict` with exactly the
six fields the full-screen list uses, plus attribute access:

```python
{
    "title":  "Kool FM",           # display label
    "fact":   "ON AIR",           # Label2, <= 16 chars
    "art":    "/…/resources/art/kool.png",  # resolved path, or "" / bare name
    "code":   "RP-32",            # print furniture, never a routing key
    "kind":   "station",          # "station" | "section"
    "action": {"type": "stop", "station": "kool"},
}
```

Both styles work:

```python
row = live.rows()[0]
row["title"] == row.title
json.dumps(row)                 # serialisable
```

`kind` is `station` for the three playable rows and `section` for the Pirate
Radio door. `action["type"]` is:

| type | meaning | fields |
|---|---|---|
| `play` | start/resume this station | `station`, `url`, `title`, `live=True` |
| `stop` | stop this station | `station` |
| `open` | controller opens another room | `source="pirate"`, `target="pirate"` |

The visual fact flips automatically: `LIVE` → `ON AIR` when playing,
`PAUSED` when paused, `PIRATE` on the door. Live rows never carry a duration,
elapsed time or progress value.

If the integrated `library.py` uses a dataclass rather than a mapping, convert
once at the boundary; the field names above are the contract:

```python
Row = library.Row
rows = [Row(**{f: r[f] for f in live.ROW_FIELDS}) for r in live.rows()]
```

---

## 2. Live Radio screen

```python
from raveui.screens.live import LiveRadio

# data.modules is the pluginbridge namespace already held by RaveData.
# data.root is the plugin path used to resolve resources/art/kool.png etc.
live_screen = LiveRadio(
    modules=data.modules,
    playback=self.playback,                 # raveui.playback.PlaybackService
    stopper=lambda: xbmc.Player().stop(),   # injected: the pure layer has no xbmc
    art_root=data.root,
    now_playing=self._read_icy_title,       # optional callable(token) -> str|dict
)
```

### API

| Call | Behaviour |
|---|---|
| `rows()` | 3 station rows + Pirate Radio, in fixed order |
| `play(token)` | builds a `LiveTrack` and calls `playback.play()` **once**; replaying the current station returns `False` without a call |
| `stop()` | calls `stopper()` once; clears ON AIR only after it succeeds |
| `toggle(token)` | stop if that station is on air, else play |
| `perform(action)` | dispatch a row action (`play`/`stop`); `open` is the controller's |
| `set_paused(bool)` | reflects a player pause/resume without another play call |
| `state(token)` | `StationState` (`mode`, `on_air`, `no duration/progress`) |
| `now_playing(token)` | live metadata dict; always `has_duration=False`, `has_progress=False` |
| `footer()` | `nowplaying.Footer` for this screen |
| `status` | last human-readable status line |

Station URLs come from `radio.curated(token)` → `radio.stream_url()` and pass
through `http.safe_stream_url()` when available. Built-in canonical URLs are a
fallback only, so the row set still renders if the plugin is missing. The
module intentionally does **not** add a radio-browser search: three 8-second
mirror timeouts can outlive the whole load, and three known playable stations
beat a dead row.

### Integration points

1. **Room load** (`data.py` / `controller.py`): replace `_live_entries()` with
   `live_screen.rows()`, title `LIVE RADIO`, subtitle
   `Kool FM · Rinse FM · Centreforce · pirate`.
2. **Click dispatch** in `controller.on_click()`:

```python
action = row.get("action") if isinstance(row, dict) else getattr(row, "action", None)
if action and action.get("type") in ("play", "stop"):
    self.live_screen.perform(action)
    self.view.set_status(self.live_screen.status)
    self.view.set_footer(self.live_screen.footer())
    return True
if action and action.get("type") == "open" and action.get("source") == "pirate":
    return self._open_room("pirate")
```

3. **Playback contract**: `LiveTrack` has `title`, `pack="Live radio"`, `url`,
   `art`, `live=True`; it works with the existing
   `PlaybackService.play(track)` unchanged.
4. **Pause/resume**: if the shell observes `Player.Paused` / speed `0`, call
   `live_screen.set_paused(True/False)`; do not call `play()` again to resume.
5. **Stopper**: the controller may keep `xbmc` out of its own file by passing a
   callable from the window adapter, exactly as `open_screen()` does today.

### Current shell note

`feat/fullscreen-app-3.9.51` already has its own `_live_entries()` and a
4-attempt `data.random_pick()`. That work is compatible, but do not run two
retry policies: either keep the shell implementation or delegate to these
modules. If the shell's `Entry` shape stays, map fields once:

```python
Entry(key=action.get("station", row["title"]), label=row["title"],
      subtitle="Live radio · no duration", art=row["art"], kind=row["kind"],
      source="live", target=action.get("url", ""), fact=row["fact"],
      code=row["code"], plot="Live radio · ON AIR while playing")
```

---

## 3. Footer / now-playing model

```python
from raveui import nowplaying

footer = nowplaying.standby(room="Kool FM", fact="LIVE")
footer = nowplaying.playing("Tape 1 - Brockie", artist="Brockie",
                            album="Dreamscape 19", duration=2637, elapsed=1204)
footer = nowplaying.playing("Kool FM", artist="DJ Hype", live=True)
footer = nowplaying.from_player(player_snapshot, live=False)
```

### States

| mode | ON AIR | kicker | duration / progress |
|---|---|---|---|
| `idle` | no | `STANDBY` | hidden; title `NOTHING PLAYING`, meta is the focused room or `PICK A ROOM · PRESS OK` |
| `playing` | yes | `NOW PLAYING` | shown when `duration > 0`; progress clamped 0..1 |
| `paused` | **no** | `PAUSED` | kept; title/meta kept |
| `live` | yes | `ON AIR` | **always hidden**, even if Kodi reports a duration |

`ON AIR` means *playing*, not paused. `media_live` survives a pause, so
`resume(paused_live)` returns to `live`, not to a normal track.

### Painting

`Footer.properties()` returns `rp_now_*` strings ready for
`Window.setProperty()`:

```
rp_now_mode, rp_now_on_air, rp_now_kicker, rp_now_title, rp_now_meta,
rp_now_elapsed, rp_now_duration, rp_now_progress, rp_now_show_duration,
rp_now_show_progress, rp_now_room, rp_now_fact, rp_now_media_live
```

Exact adapter method for `KodiView` (the lead owns the file; this is the
contract):

```python
def set_footer(self, footer):
    for key, value in footer.properties().items():
        self.window.setProperty(key, value)
    self._label(CONTROL_NOW_KICKER, footer.kicker)   # 602
    self._label(CONTROL_NOW_TITLE, footer.title)     # 603
    self._label(CONTROL_NOW_META, footer.meta)       # 604
    self._visible(CONTROL_ON_AIR, footer.on_air)     # 601
    self.set_now_playing(footer.status_line())       # existing rp_now fallback
```

Existing control IDs map cleanly: `CONTROL_FOOTER=600`, `CONTROL_ON_AIR=601`,
`CONTROL_NOW_KICKER=602`, `CONTROL_NOW_TITLE=603`, `CONTROL_NOW_META=604`,
`CONTROL_STATUS=30`. Add elapsed/duration/progress controls for the new layout
and bind their visibility to `Window.Property(rp_now_show_duration)` /
`rp_now_show_progress`; do not bind a live stream's progress to
`Player.Progress`, which keeps advancing.

`from_player()` accepts Kodi-shaped values:

```python
{"title": …, "artist": … or [...], "album": …,
 "time": {"hours": 0, "minutes": 20, "seconds": 4},
 "totaltime": {"hours": 0, "minutes": 43, "seconds": 57},
 "percentage": 45.7, "speed": 1, "playing": True, "is_live": False}
```

It does **not** guess live from a missing duration; a duration-less tape just
hides the total honestly. Pass `live=True` for station rows.

---

## 4. Surprise pick reliability

The Shield symptom was a single `latest.random_pack()` call (two Archive
searches) returning empty/failing once, which the UI reported as "No random
pack found". The replacement policy is deliberately small and bounded:

1. **Cache first.** Packs already seen by the Latest/screen load are free.
   `PackCache` is bounded (48), thread-safe, dedupes by identifier, and avoids
   the last 8 successful picks when it has another candidate.
2. **2–3 backend attempts.** Default 3, clamped to 2..3. Short backoff
   `0.35 s`, `0.8 s` (1.15 s total worst case), injected sleep for tests.
3. **Retry every failure kind.** Exception, `None`, malformed/no-identifier
   pack, and — when a resolver is supplied — a pack with no playable audio.
4. **Clear failure only after exhaustion.** `PickResult.message` is the UI
   line; `last_error` carries the diagnostic. A cancel returns
   `cancelled=True` and must not paint a failure.
5. **Never double-play.** `PlayOnce` trips *before* the callback, so a retry,
   exception, re-entrant OK, or second handoff cannot start audio twice.

### Wiring

```python
from raveui.surprise_pick import PackCache, from_plugin, pick_and_handoff

self.surprise_cache = PackCache()
self.surprise_picker = from_plugin(data.modules, cache=self.surprise_cache)
# equivalent to:
#   pick=modules.latest.random_pack
#   resolve=make_resolver(modules.archive, safe_url=modules.http.safe_stream_url)

# when Latest/screen rows load, seed the cache:
self.surprise_cache.remember_latest(recent_pack_dicts)
```

### Controller replacement

```python
result = self.surprise_picker.pick_once()      # one bounded series, never raises
if self._closed:
    return False
if not result:
    self.view.set_status(result.message)       # clear line, after exhaustion
    return False
# … existing SpinnerAnimator (>= 1.2 s) …
return self._handoff(result.track)             # existing single-shot handoff
```

`result.track` is a `PickedTrack`: it is a dict and also has `.title`, `.pack`
(the pack title), `.url`, `.art`, `.live=False`, so the existing
`PlaybackService.play(track)` works unchanged. If the controller prefers the
combined helper:

```python
result = pick_and_handoff(
    self.surprise_picker,
    self._handoff,                 # called at most once per guard
    on_result=lambda r: self.view.set_status(r.message if not r else ""))
```

`pick_and_handoff` uses the picker's shared guard by default. Call
`self.surprise_picker.guard.reset()` when the user starts a **new** Surprise
gesture (after a completed or failed one), never on a retry.

### Note on the current shell

`RaveData.random_pick()` in `feat/fullscreen-app-3.9.51` now has its own
4-attempt loop plus recent-packs fallback. That covers the same symptom, but
the two policies must not stack. Recommended: replace the body with
`surprise_pick.from_plugin(self.modules).pick_once()` or call the picker from
the controller. The module adds the cache-first path and the single-play gate;
the shell loop does not.

---

## 5. Tests

Offline, no Kodi, no network:

```bash
cd raveplayer-worktrees/screens-live
python3 -m unittest test.test_screens_live test.test_nowplaying_footer \
    test.test_surprise_pick -v
python3 -m unittest discover -s test -p 'test_*.py'   # full suite
```

Results on this branch:

- new modules: **78 tests OK** (26 live + 19 footer + 33 surprise)
- full repository suite: **803 tests OK** (no regressions)

Coverage highlights: row field contract, plugin URL fallback and unsafe URL
rejection, art resolution, ON AIR/PAUSED/stop/switch transitions, no double
play, live hides duration/progress, paused clears ON AIR but keeps metadata,
`from_player` time-dict conversion, cache-first and recent avoidance, retry
counts and backoff values, unplayable-pack retry, exhaustion messages,
cancellation, identifier sanitation and the one-shot handoff gate.

---

## 6. Device verification (no deploy)

Read-only checks against the Shield on 2026-11-05 (the new modules are **not**
installed on it; this verifies the backend and the environment, not the new
code path):

| Check | Result |
|---|---|
| ADB | `192.168.1.189:5555` `SHIELD_Android_TV` (`foster_e`), online |
| Kodi | `22.0-BETA1`, revision `20260621-77395cf42e` |
| `script.raveplayer.ui` | 3.9.49, installed + enabled (older than this branch) |
| `plugin.audio.raveplayer` | 3.9.50, installed + enabled |
| Player | idle (`Player.GetActivePlayers` → `[]`) |
| Live backend | `Files.GetDirectory` on `mode=station_live` for kool/rinse/centreforce returned one playable row each with correct station names and `GB · AAC+/MP3 · kbps` metadata |
| Kodi log | no `No random pack found` in the current `kodi.log` at sample time (it may have rotated; absence is not disproof) |

The host-side `adb forward tcp:9090` path was intermittent (accepted then
timed out), so the JSON-RPC checks above were run **on-device**:

```bash
adb shell 'printf %s "<json>\n" | toybox nc -w 30 127.0.0.1 9090'
```

Because no deploy was allowed, the new Live rows, footer and picker have not
been exercised inside the installed 3.9.49 shell. Offline tests are the
verification for those; the exact integration points above are what the lead
must wire. A device pass after integration should check:

- Live Radio → Kool/Rinse/Centreforce row becomes `ON AIR`, footer hides total
  and progress, Back after handoff closes.
- Pause hides ON AIR while the title stays.
- Surprise on the Shield: first press plays; a forced empty first pick still
  results in one pick series and exactly one stream; a real three-attempt
  failure shows one clear status, not three notifications.
- No "No random pack found" on a single transient Archive response.

---

## 7. Limits / deliberately out of scope

- No station search in Live; only the curated three + pirate door.
- No ICY fetch inside the module; `now_playing=` is an injected probe. The
  shell can keep using `Player.*` or pass a probe from its existing metadata
  helper.
- Art filenames are looked up under `<root>/resources/art`; missing files keep
  the bare name so the view can resolve/fallback. The module never invents art.
- No settings, no downloads, no background threads. The retry policy is
  synchronous and bounded so it always runs inside the controller's existing
  worker task.
- No edits to `window.py`, `controller.py`, `data.py` or the main XML.

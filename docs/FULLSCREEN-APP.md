# Full-screen Rave Player app (3.9.51)

**Branch:** `feat/app-integration` (from `feat/fullscreen-app-3.9.51`)
**Add-ons:** `plugin.audio.raveplayer` **3.9.51**, `script.raveplayer.ui` **3.9.50**
**Device:** NVIDIA Shield TV, Android 11, Kodi `22.0-BETA1 (21.90.801)`, Estuary 4.1.0
**Status:** implemented, full offline suite green (2×), installed on the Shield.
Device evidence is listed in §10.

The Rave Player is now the **primary app**, not a demo home screen.
`script.raveplayer.ui` owns the full-screen `WindowXML` and all navigation;
`plugin.audio.raveplayer` is the data and playback backend it drives. The
plugin's normal directory lists are deliberately kept as **Classic lists** —
the documented fallback when the script or window is unavailable.

---

## 1. Entry points

| Entry | Behaviour |
|---|---|
| Plugin root | Two rows: **Rave Player** (program row, launches the app) and **Classic lists** (folder). The app row is first/default. |
| `plugin://plugin.audio.raveplayer/?mode=screen` | Same app launch; a legacy saved favourite still works. |
| `script.raveplayer.ui` directly (Add-ons → Programs) | Same app. |
| Classic lists | `mode=classic_root` shows the pre-3.9.51 root rows unchanged (Latest, Tape Packs, Pirate Radio, Mixes & Shows, Live Radio, Favourites, Search, Surprise Me, About). |

The root row is still a non-folder program item, so Kodi does not open a
directory window for it (no `DialogBusy` race). The app is one window; Back
follows normal Kodi window-stack behaviour.

---

## 2. Architecture

```
script.raveplayer.ui/
├── default.py                 # script entry point
├── raveui/
│   ├── window.py              # one WindowXML, all controls, input adapter
│   ├── controller.py          # view stack, paging, keyboard, context, states
│   ├── data.py                # shell rooms + Page/Entry/Track model
│   ├── screens/
│   │   ├── library.py         # Search/Favourites/Downloads/About (one impl)
│   │   └── live.py            # Live Radio rows/state (one impl)
│   ├── nowplaying.py          # Footer model for idle/playing/paused/live
│   ├── surprise_pick.py       # cache-first pick policy + single-play gate
│   ├── pluginbridge.py        # imports the plugin tree read-only under an alias
│   ├── downloadqueue.py       # worker + progress rows via the plugin's downloads
│   ├── playback.py            # the single audio policy
│   ├── animation.py           # the >=1.2 s Spinning Surprise reveal
│   └── tasks.py               # bounded worker loads
└── resources/skins/Default/720p/script-raveplayer-ui.xml
```

### One window, many states

The app does not create a second window or a modal dialog. Everything is a
state of the same 1280×720 `WindowXML`:

| State | Controls | What the user sees |
|---|---|---|
| Home / list | bed, header, hero, list 50, footer | the 02 design unchanged |
| In-window keyboard | list 50 + header/status | letter/digit rows, SPACE/DELETE/CLEAR, SEARCH NOW, CANCEL |
| Context menu | list 50 + header/status | Play all, Shuffle all, Download, Favourite, rows per page, Stop, Refresh |
| Loading | plate 720-727 (`rp_plate=1`, `rp_plate_head=1`) | dimmed screen, spinning head, PLEASE WAIT, detail |
| STANDBY / ERROR | plate 720-727 (`rp_plate=1`, `rp_plate_head=0`) | STANDBY/ERROR, reason, OK retry / BACK |
| Spinning Surprise | controls 700-713 (`rp_splash=1`) | the existing full-window reveal |

All conditional visibility is **window-property bound**, never a literal
`<visible>false</visible>`. Kodi re-evaluates a visibility condition every
frame; a constant false silently overrides `Control.setVisible(True)` (the
3.9.48 splash bug, see `RAVE-SCREEN-SPLASH-FIX.md`). The plate uses
`rp_plate`, `rp_plate_head`; the splash uses `rp_splash`; live playback uses
`rp_live` to hide duration/progress.

### View stack

```
home
 ├── Latest           → pack        → tracks          → playback
 ├── Toronto          → genre       → tracks          → playback
 ├── JungleTapes      → 310 shows (paged) → show → tapes → playback
 ├── RaveTapePacks    → Event/DJ/MC/Year index → categories → pack/post
 │                     → tracks → playback
 ├── Live Radio       → three curated stations (play/stop) + pirate door
 ├── Mixes & Shows    → DNBRADIO / podcasts / Moxser / Hardscore /
 │                     GetDarker / Pirate Radio → lists → playback
 ├── Search           → in-window keyboard → library.Search (scoped, paged)
 ├── Favourites       → library.Favourites (play / open / remove)
 ├── Downloads        → library.Downloads (play / remove)
 ├── About            → library.About (versions, licence, links, policy)
 └── Spinning Surprise → one bounded pick series → reveal → one playback
```

Each frame stores its target, page, rows and selected index. Back pops one
level and restores the exact page **and** focus (not row 1). Back at home
closes the window. Back while a plate is up clears the plate; Back while a
load is in flight closes and the late worker result is ignored.

### Paging (25 / 50 / 100)

`RaveData` returns a `Page(rows, total, page, pages, rows_per_page, has_next,
cursor)` for the shell-owned rooms. `raveui.screens.library` returns a `Screen`
with the same paging fields for Search/Favourites/Downloads/About.
RaveTapePacks category/all pages use the source's own page/cursor. The controller adds explicit **PREVIOUS / NEXT**
rows, shows `Page n of m · N items` in the header, and a `P1/7` indicator in
the footer. Long-press OK → *Rows per page* cycles 25/50/100 and reloads near
the same position.

RaveTapePacks' WordPress archives expose a next-link cursor; `Page.cursor`
carries it and the screen never invents a page past the source's next link.

---

## 3. In-window search

No Kodi `Dialog().input`/keyboard. `Search` opens a keyboard made of the same
48 px sticker rows:

```
A B C D E F G H I      ← left/right moves the selected letter
J K L M N O P Q R
S T U V W X Y Z
0 1 2 3 4 5 6 7 8 9
SPACE / DELETE / CLEAR / SEARCH NOW / CANCEL
```

- Up/down is native list movement; left/right is handled by the controller
  (`on_horizontal`) so the same list stays focused.
- The selected letter is marked with `«X»` (not `[X]`, which Kodi would parse
  as label markup).
- One scope, owned by the library module: **Tape packs** (Internet Archive,
  relevance order). The shell keyboard only collects the query; scope cycling
  was removed so there is one search implementation.
- Results are paged by `LibraryScreens.search`, always scoped to
  `collection:ravetapes AND mediatype:audio` and sorted by the Archive's
  relevance. Empty results are the module's retry row, not a shell state.
- Back from results restores the keyboard with the query and selected row
  intact; Back again returns to the previous room.

---

## 4. In-window context menu

Long-press OK (or the remote's context-menu/info key) opens an actions list in
the same window. Nothing is modal and nothing is drawn over a plugin list.

| Row type | Actions |
|---|---|
| folder (pack/genre/show/RTP/feed/source) | Open, Play all, Shuffle all, Favourite, Rows per page, Stop, Refresh |
| track | Play, Play all, Shuffle all, Download (approved source only), Favourite, Rows, Stop, Refresh |
| live station | Play / stop (module state), Favourite, Refresh |
| saved row | Remove favourite |
| active download | Cancel download |
| completed download | Play, Delete download |

`Play all`/`Shuffle` queue the shell-owned room's **whole collection** (the
complete pack/show/genre/post/feed) in one `PlayList`; the library rooms
(Search/Favourites/Downloads) queue the visible page, as their in-window action
copy says. The plugin's `mode=play` URL is used per track, so RTP
egress/bridge and live reconnect stay the plugin's business.

---

## 5. States and failure rules

- **Loading** paints before the worker starts; the controller advances the
  small head from the task runner's poll on the GUI thread, so the plate stays
  animated during a slow Archive fetch without touching a control from a
  worker thread. The Surprise worker gets a per-run token poll that is inert
  from any non-GUI thread and after cancel/timeout/close, so an abandoned
  picker can never call `Control.setImage` (P1-2/P2-5b).
- **Empty** is a quiet STANDBY plate: “Nothing in \<room\> right now. The
  source may be blocked or offline.” No notification, no dialog.
- **Error/timeout** is an ERROR plate with the concrete reason and
  `OK retry · BACK back`. Retry reruns the same target/page.
- **Back during load**: Back closes the window once instead of returning
  `False` behind a loading plate, stops the animation, sets both cancel events,
  and the runner's `cancelled` predicate drops the late result. Device
  measurement (cold cache): Back → Kodi Home in ~0.1 s.
- **Playback failure** is a status line (“Could not start playback — see the
  log”) and a quiet stop; there is no RTP warning/notification. The plugin's
  own RTP path already suppresses those.
- **Surprise failure** (no pack, exception, missing art, failed reveal) hides
  the splash and paints an error plate with retry; it never starts a
  half-playing state.
- The activation guard from 3.9.49/3.9.50 remains: `open_screen()` waits for
  an active modal, verifies `onInit` ran, and fails fast with one notification
  instead of looping forever on a refused `show()`.

### The focus fix found on device

Kodi focuses `defaultcontrol=50` **before** `onInit` finishes. The controller
binds the 11 rows during `onInit` (it imports the plugin and reads
favourites/downloads), so the initial focus attempt failed
(`Control 50 … asked to focus, but it can't`) and the painted window received
no key events while the previous window kept them. `window.py` now calls
`self.setFocusId(CONTROL_LIST)` **after** `controller.start()` has added the
rows. Device evidence: root list moves immediately on D-pad, every room opens.

---

## 6. Audio policy (one owner)

**Kodi's player owns audio.** There is no second player, no watchdog and no
auto-advance.

| Action | Path |
|---|---|
| Single track / station | one-item `PlayList` → plugin `mode=play` URL (live adds `live=1&station=<token>`; the token, not the “Live radio” album label, is what reconnect re-resolves) |
| Play all / Shuffle | one `PlayList` of N plugin `mode=play` URLs |
| Downloaded file | direct local path (no network policy applies) |
| Platform hand-off (GetDarker/Mixcloud) | the official add-on's `plugin://` path |
| Explicit Stop | remote Stop / context **Stop playback** → `Player().stop()` |
| Leaving the window | **audio continues**; Kodi home/Classic lists stay usable |
| Live stop / normal track | the next `tick()` reconciles the live latch with Kodi; ON AIR clears, duration returns for the normal item |

That last row is the deliberate “sane behaviour”: the app is a shell, not a
player owner. Back does not silently kill a set. The footer says
`Back leaves audio playing`; the context menu and the remote Stop key are the
explicit stop. Live playback sets `rp_live=1`, so time/total/progress are
hidden and the ON AIR sticker stays.

---

## 7. Backend changes (`plugin.audio.raveplayer` 3.9.51)

- **Root is the app launcher**: `root()` has two rows; `classic_root()` holds
  the old lists. `HANDLERS["classic_root"]` added.
- **`latest.random_pack()` keeps its bounded retry** for Classic plugin routes
  (three fresh Archive pages, identifier-bearing docs only). The screen's
  Surprise picker is the single retry owner for the app: it tries a cached pack
  first, then at most **three single plugin picks** via
  `latest.random_pack_once()` with short backoff. One press therefore makes at
  most 3 × (count + page) = **6 `archive.search` calls**, not the 18 from a
  nested 3 × 3 policy. Cancel between attempts stops immediately.
- **Favourites accept `legacy_post`** (RaveTapePacks post id), matching the
  kind the plugin's own context menu already wrote. The screen uses it for
  RTP posts; `fav_list` already rendered it.
- No change to the data scrapers, play resolver, RTP egress or bridge.

The screen imports the plugin's public modules under the private alias
`raveplayer_plugin`; favourites/downloads writes go through the plugin's own
profile paths and locks. The screen does not write settings or cache keys.

---

## 8. Deliberately left native (Classic lists)

These stay in `plugin.audio.raveplayer`'s directory UI and are reachable from
**Classic lists**:

- archive.org full search (the screen's search is scoped to the curated rave
  collection, not the whole Archive);
- the older hub taxonomies (Classic Pack Series, By Rave/Venue, By Year,
  Pirate Radio, Media feeds, DNBRADIO, GetDarker, Moxser, Hardscore) as
  directories;
- per-source legacy settings, cache maintenance and the download folder
  settings UI;
- Kodi's own OSD/player controls, subtitles, audio settings and codec info;
- Kodi's virtual keyboard for arbitrary text outside the app (the app's
  search keyboard is its own, in-window).

The app is audio-first and 1280×720/720p control space; it uses only
`font13`/`font12`/`font10`, and no skin fork or TTF.

---

## 9. Tests and artifacts

```sh
python3 -m unittest discover -s test        # 959 tests, OK (run 2×)
./scripts/build.sh                          # dist zips 3.9.51 / 3.9.50
./scripts/build-repo.sh                     # repo/ catalogue + zips
./scripts/check-repo-artifacts.sh           # after committing repo/
```

Coverage added/updated in `test/test_rave_screen.py`:

- room/data model (13 rooms since 3.9.61, all source adapters, favourites/downloads/about);
- paging (local slice, server page, cursor, previous/next rows, Back focus);
- in-window keyboard: typing, submit, results, Back restore;
- context actions: play all/shuffle, download, favourite, rows-per-page;
- loading/empty/error plates and retry; Back during load; no busy leak;
- Surprise: one pick series, one animation, one handoff, no-pick/exception/
  reveal failure, cancel; the production runner's poll is GUI-only and a
  cancelled worker makes zero `set_plate_head` calls; cache-first three
  attempts make at most six `archive.search` calls;
- position: Refresh and a rows-per-page change keep the focused item and hero
  (including a page-size change across a page boundary);
- playback policy: single item, whole collection, shuffle, local file,
  platform hand-off, live item (station token in the reconnect query), stop;
- live context can save a station to Favourites;
- download queue: progress, plan refusal, worker failure, ineligible source,
  and two concurrent writers keeping every store snapshot valid;
- skin XML: plate/page controls, property binding, live hide, every texture;
- plugin root launcher + Classic lists, manifest versions, repo catalogue.

`docs/RAVE-SCREEN-DIAGNOSIS.md`, `RAVE-SCREEN-SPLASH-FIX.md` and the 3.9.49
inside still explain the Kodi 22 modal/activation and splash-visibility traps;
this app keeps both fixes.

---

## 10. Device verification (Shield / Kodi 22)

**Evidence:** [`docs/fullscreen-app-evidence/`](fullscreen-app-evidence/README.md)
contains 20 downsized 4K frames, the machine-readable QA manifest and the QA
checks report. The independent harness ran against the installed pair
`plugin.audio.raveplayer 3.9.51` + `script.raveplayer.ui 3.9.50`.

### What passed on the device

- Add-on pair enabled, versions and dependency satisfied (plugin 3.9.51 ≥ 3.9.51).
- Home: 13 rooms discovered since 3.9.61, first room focused, Surprise row present.
- Rooms: Latest, Toronto, JungleTapes (310 shows, Page 1 of 7), Live Radio,
  RaveTapePacks, Favourites, Downloads, About captured; room lists render with
  rows, hero, focus plate and footer.
- Back stack: room → tracks → show list → home → closed.
- Spinning Surprise: full-window splash painted, then **one** playback
  (`Player.GetActivePlayers` internal audio, item label = surprise track);
  screenshot `12-surprise-splash.jpg` / `13-surprise-playing.jpg`.
- Now-playing footer: ON AIR, title, elapsed/total, waveform and progress.
- Plugin Classic lists: root launcher + Classic lists, Archive page 1/last,
  JungleTapes show, RTP index/category/pack/tracks, RTP play-all using plugin
  `mode=play` routes.
- No traceback, no non-existent control, no media-open failure.

### Focus bug found and fixed on device

Kodi focuses `defaultcontrol=50` **before** `onInit` finishes. The controller
binds the 11 rows during `onInit` (it imports the plugin and reads
favourites/downloads), so the initial focus attempt failed
(`Control 50 … asked to focus, but it can't`) and the painted window received no
key events while the previous window kept them. `window.py` now calls
`self.setFocusId(CONTROL_LIST)` **after** `controller.start()` has added the
rows. After the fix, the first D-pad Down moved Latest → Toronto and the hero
updated; before it, the same key went to the underlying window and relaunched
the plugin root.

### QA result and known harness mismatches

`qa-checks.md`: **40 pass / 9 fail / 1 warn**. None of the failures is an app
crash or a traceback. They are:

- `list.root` expects the pre-3.9.51 10-row root; the new root is deliberately
  the 2-row app launcher + Classic lists.
- `states.keyboard` / `list.search` expect Kodi's virtual keyboard; search is
  deliberately an in-window keyboard (no `Dialog().input`).
- `screen.rooms_open` flags Mixes (captured across a Kodi restart) and Search
  (Search opens the keyboard, not child rows).
- `screen.modal_refusal` recovered into the window instead of refusing; because
  the window activated, the guard's failure log line is absent
  (`logs.modal_guard`).
- `list.downloads` counts one extra non-local row; `playlist.jt_play_all`
  queued the single track that show actually has.
- `run.harness_errors` records a 401 caused by the concurrent credential change
  during the run.

### P1 fix pass (5 Nov 2026)

The six P1s from the adversarial review were finished and re-verified on the
same Shield/Kodi pair. Evidence, timings and the exact fault injection used for
the Surprise timeout are in
[`fullscreen-app-evidence/p1-fixes/README.md`](fullscreen-app-evidence/p1-fixes/README.md):

| P1 | Device result |
|---|---|
| Back during load | closed to Home in ~0.1 s from a real cold `PLEASE WAIT` plate |
| Surprise timeout | `PICK TIMED OUT`, player `[]` at timeout and 10 s later |
| Live ON AIR | Stop clears ON AIR; a normal track replaces the station with elapsed/total |
| DNB / hand-off favourites | DNB resolves and plays; YouTube favourite opens and plays in its add-on |
| Downloads | active row shows percent; OK cancels; the headless owner persists the queue across the window |
| Double launch | one screen; the second launch logs "second launch refused" |

### Device caveat / cleanup

A second local process (the QA harness in `raveplayer-worktrees/qa-harness`) was
driving Kodi through JSON-RPC during the same window, so some screenshots carry
Kodi's debug-info overlay. For the final build the overlay was turned off, the
web server was restored to 8080 / `kodi:bobhope0`, and Kodi was left on Home.
The app's own final-build frames (`final-root`, `final-search-keys`) are in the
same evidence folder without the overlay.

## 11. Known limitations

- The screen's Archive search is scoped to the curated rave collection; the
  full-Archive search remains a Classic list.
- RaveTapePacks category/all pages report a cursor page count, not a total
  (the source does not expose a count for those routes). The header shows
  `Page n · more`; previous/next rows are authoritative.
- GetDarker rows are platform hand-offs; if the Mixcloud add-on is not
  installed the source list is empty (the plugin's own route does the same).
- Downloads show the live queue (active percent, cancel) when the room is
  rendered. The row is not repainted every percentage point while the user
  stays in another room; reopen the room for a fresh snapshot. The headless
  `script.raveplayer.ui downloads` owner keeps a transfer alive after Back and
  a window close. The window and that owner share `download-queue.json`; every
  save uses a per-writer unique temp file plus a writer lock and an atomic
  rename, so concurrent saves cannot leave a partial/corrupt snapshot (last
  complete snapshot wins).
- The app is audio-first: no video, visualisation or subtitle UI.
- The 02 art still uses the placeholder root sticker/hero generator; the
  screen-bed/spinner/footer art is the design snapshot.
- The app requires plugin 3.9.51 (script 3.9.50 depends on it). Install the
  pair together; Kodi 22 still runs an enabled script with an unmet
  dependency, but the screen route/data contract is not guaranteed.

# Library screens — protocol and wiring notes

**Branch:** `feat/screens-library` (worktree
`raveplayer-worktrees/screens-library`, base commit `22cbf4d`).
**Scope:** new modules only. No edit to `window.py`, `controller.py`, the
`windowing` layer, the main XML or `raveui/data.py`; the lead integrates.

This package adds four rooms to the full-screen Rave UI:

| Room | Route | RP code | Data source |
|---|---|---|---|
| Search | `search` | `RP-33` | scoped Internet Archive advanced search |
| Favourites | `favourites` | `RP-34` | plugin `favourites.json` |
| Downloads | `downloads` | `RP-35` | plugin `downloads.json` + files |
| About & Sources | `about` | `RP-36` | add-on metadata + static credits |

They use the same language as the Rave Screen 02 look: `title` / `subtitle`
header, a list of `label` + 16-character `fact` + icon + fanart + mono `code`,
and the same print-furniture codes (`RP-xx`) as `look.RP_CODES`. There is no
second visual language to learn or reskin.

**Files**

```
script.raveplayer.ui/raveui/screens/__init__.py          # public re-exports
script.raveplayer.ui/raveui/screens/library.py           # protocol + adapter
script.raveplayer.ui/raveui/screens/README-library.md    # this file
test/test_screens_library.py                             # 74 offline tests
```

> **Package merge note:** `raveui/screens/` is shared with the live-radio
> stream (`screens/live.py`, `feat/screens-live`). Both modules add names to
> `screens/__init__.py`; keep both re-export lists when integrating. The two
> `Row` shapes are compatible for the window adapter (`label`/`title`,
> `art`/`hero`, `fact`, `code`); this module additionally carries `payload`.

No Kodi import at module level and no network call in this package. The backend
is lazily loaded through `raveui.pluginbridge`, exactly like `raveui.data`; a
test or the shell can inject a fake backend.

---

## 1. The five-minute integration

```python
from raveui.screens.library import (
    LibraryScreens, KIND_ROOM, KIND_TRACK, ACTION_PLAY_ALL, ACTION_SHUFFLE,
    ACTION_DOWNLOAD, ACTION_FAVOURITE, ACTION_REMOVE, ACTION_RETRY,
    ROUTE_SEARCH,
)

# once, when the library overlay is created
self.library = LibraryScreens(playback=self.playback)

# paint immediately without blocking the GUI thread
self._paint(self.library.loading(ROUTE_SEARCH, query=query, page=page))

# run the handler on the existing worker runner
screen = self._task_runner.run(lambda: self.library.search(query, page))
self._paint(screen)
```

`Row` deliberately exposes the same attributes the current WindowXML adapter
already reads (`label`, `fact`, `art`, `hero`, `code`, `subtitle`, `plot`), so
`view.set_rows(list(screen.rows))` renders library rows with **no window.py
edit at all**. Only the title/subtitle/status need wiring:

```python
def _paint(self, screen):
    self.view.set_title(screen.title)
    self.view.set_subtitle(screen.subtitle)
    self.view.set_rows(list(screen.rows))
    self.view.set_status(screen.page_label or
                         ("Loading…" if screen.state == "loading" else ""))
```

Click dispatch is one small `if` in the shell:

```python
def _on_click(self, screen, row):
    if row.kind == KIND_ROOM:
        return self._open_room(row.payload)          # see §4
    if row.kind == KIND_TRACK:
        return self.library.play(row)                # validated, then hand-off
    action = row.payload.get("action")
    if action == "play":
        return self.library.play(row)
    if action == ACTION_PLAY_ALL:
        return self.library.play_all(screen)
    if action == ACTION_SHUFFLE:
        return self.library.shuffle(screen)
    if action == ACTION_DOWNLOAD:
        return self._run_worker(self.library.download, row, progress=...)
    if action == ACTION_FAVOURITE:
        return self.library.favourite(row)
    if action == ACTION_REMOVE:
        return self.library.remove(row)
    if action == ACTION_RETRY:
        return self._run_worker(self.library.retry, row)
    if action == "open":                             # About links only
        return self._open_url(row.payload.get("url"))
```

Back is two lines:

```python
parent = self.library.back(self._screen)
if parent is None:
    self._leave_library()          # return to the Rave Screen home
else:
    self._paint(parent)            # search results -> idle Search
```

Paging is explicit: `self.library.search(query, screen.page + 1)` (or
`favourites`/`downloads`). `screen.page_label` is the ready-made
`"Page 2 of 3 · 120 favourites"` line; `screen.has_next` / `has_previous`
guard the key handling. Do not page through `back()`.

---

## 2. Protocol

### `Screen`

| Field | Type | Meaning |
|---|---|---|
| `route` | str | `search`, `favourites`, `downloads` or `about` |
| `title` | str | Screen header (`SEARCH`, `FAVOURITES`, `DOWNLOADS`, `ABOUT`) |
| `subtitle` | str | One line of context, already shortened |
| `rows` | tuple[Row] | Content rows; empty for a loading/idle screen |
| `state` | str | `ready`, `empty`, `loading` or `error` |
| `page` / `pages` | int | 1-based current page and page count |
| `total` | int | Items in the whole list (server total for search) |
| `page_size` | int | Always one of 25 / 50 / 100 (alias: `rows_per_page`) |
| `query` | str | The cleaned search term, or `""` |
| `error` | str | Human-readable error (`state == "error"`), <= 200 chars |
| `noun` | str | Word used by `page_label` (`packs`, `favourites`, …) |
| `code` | str | Room's RP code, e.g. `RP-33` |

Convenience properties: `is_ready`, `is_empty`, `has_error`, `has_previous`,
`has_next`, `page_label`, `retry_row`.

### `Row`

| Field | Type | Meaning |
|---|---|---|
| `label` | str | Primary title (alias: `title`, for the live-screen shape) |
| `kind` | str | `room`, `track` or `action` |
| `fact` | str | Label2, already capped at **16 chars** |
| `icon` | str | Sticker / Archive thumbnail URL (alias: `art`) |
| `fanart` | str | 1280×720 hero (alias: `hero`, falls back to `icon`) |
| `code` | str | Mono print furniture, `RP-xx`; not a routing key |
| `payload` | dict | Action metadata — treat as read-only |
| `subtitle` | str | Existing Entry-style subtitle fallback |
| `plot` | str | Existing Entry-style description fallback |

### Page sizes

The shell reads the **plugin's** `results_per_page` setting through the
backend. Anything outside 25/50/100 snaps to the nearest allowed size
(`normalise_page_size`); a missing/broken setting becomes 50. Constructor
`page_size=` overrides it for tests or a shell preference. Search pages are
server-side and an out-of-range page is clamped to the last real page (one
retry request, no empty screen for a stale bookmark).

### States, retry, Back

| State | Rows | Shell action |
|---|---|---|
| `loading` | none | Paint the same header + a loading footer, then run the worker |
| `ready` | content | Render normally |
| `empty` | one retry row | Show the subtitle; OK on the row re-runs the room |
| `error` | one `Retry` row | Show `screen.error`; OK on the row re-runs the room |

`empty`/`error` rows are ordinary `kind="action"` rows with
`payload={"action": "retry", "route": …, "query": …, "page": …}`; call
`screens.retry(row)` (a `Screen` or a route string also works). The one
exception is an *idle* Search screen (`query == ""`): it has no rows and never
touches the backend — the shell owns the keyboard/search input.

Back semantics:

* Search **results** → idle Search (`query` cleared, no request).
* Idle Search, Favourites, Downloads, About → `None`, meaning "leave the
  library overlay and show the Rave Screen home". `None` does **not** mean
  close Kodi.

---

## 3. Handlers

| Method | Returns | Notes |
|---|---|---|
| `search(query, page=1)` | `Screen` | Always scoped; blank query returns idle Search, no request |
| `favourites(page=1)` | `Screen` | Saved packs/shows/stations/streams/newest first |
| `downloads(page=1)` | `Screen` | Existing copies + missing entries (kept so they can be removed) |
| `about()` | `Screen` | Versions, licence, links and every source |
| `play(row)` | `ActionResult` | Validates URL, then hands a `PlayItem` to `PlaybackService`; without a player returns the intent |
| `play_all(screen)` | `ActionResult` | Queues the playable rows on that page; result carries `tracks` |
| `shuffle(screen)` | `ActionResult` | `play_all(..., shuffle=True)` with the injected RNG |
| `download(row, progress=None, cancelled=None)` | `ActionResult` | Plans, then downloads; blocking — run on a worker |
| `favourite(row)` | `ActionResult` | Adds/refreshes the row's source entry |
| `remove(row)` | `ActionResult` | Removes a favourite or deletes a download, whichever the row is |
| `retry(target)` | `Screen` | Accepts a `Screen`, retry `Row`, payload dict or route string |
| `loading(route, query="", page=1)` | `Screen` | Ready-to-paint `loading` state |
| `back(screen)` | `Screen | None` | See above |
| `progress(url="")` | dict / list | Last download progress; `url` selects one |
| `page_size()` / `scope()` | int / str | Effective page size / Archive scope |

### `ActionResult`

`ok`, `action`, `message` (footer/notification ready), `payload`, `track`
(`play`), `tracks` (tuple, `play_all`/`shuffle`), `refresh` (route to reload,
`favourites` or `downloads`). A failed action is still a normal return
(`ok=False`), never an exception.

### Actions on rows

| Row | `payload` keys |
|---|---|
| Search pack (`room`) | `room="pack"`, `mode="archive_item"`, `identifier`, `source="Archive.org"`, `favourite_kind="pack"`, `target`, `title` |
| Favourite room rows | plus `favourite_key`, and the mode from §4 |
| Playable track (`track`) | `action="play"`, `url`, `title`, `album`, `art`, `live`, `local`, `source`, `favourite_kind="stream"`, `target` |
| Downloaded track (`track`) | as above with `local=true`, `download_key`, plus the file `path` in `url` |
| Stale favourite / missing file (`action`) | `action="remove"`, `favourite_key` **or** `download_key`, `target`, `title` |
| Retry (`action`) | `action="retry"`, `route`, `query`, `page` |
| About link (`action`) | `action="open"`, `url` (an optional extension; ignore it if the shell has no browser) |

The seven required actions are `play`, `play_all`, `shuffle`, `download`,
`favourite`, `remove`, `retry`. `open` is the only extra and only appears on
About rows. Rows are content only: there are no synthetic "Next page" rows, so
`total`/`page` stay truthful; the shell draws its own pager.

---

## 4. Room payloads the lead must map

Search rows and favourite rows are `room` rows; the library does not own the
pack/show detail screens. The payloads mirror the plugin route names:

| `mode` | Extra payload | Plugin route / target |
|---|---|---|
| `archive_item` | `identifier` | `?mode=archive_item&id=<identifier>` |
| `legacy_pack` | `pack` | `?mode=legacy_pack&pack=<pack>` |
| `legacy_post` | `post` | `?mode=legacy_post&post=<post>` |
| `legacy_jt_show` | `key` | `?mode=legacy_jt_show&key=<key>` |
| `dnb_play` | `id` | `?mode=dnb_play&id=<id>` |
| `handoff` | `platform`, `target` | platform add-on hand-off (`handoff.target`) |

`room` is a friendly name (`pack`, `platform`, `track`) for the shell's own
stack; `mode` is the stable routing key. Search results are packs, not tracks,
which is why they are rooms: the shell opens the pack and reuses the existing
track list.

---

## 5. Backend contract

`LibraryScreens(backend=...)` accepts any duck-typed object. `PluginBackend`
is the default and reads the installed plugin through
`pluginbridge.load_plugin()`; it also accepts an injected `modules` namespace
for tests. It imports `favourites`, `downloads` and `handoff` lazily through
`pluginbridge.PLUGIN_ALIAS` (the bridge's fixed module list does not include
them, and this package must not edit the bridge).

| Method | Default implementation | Used by |
|---|---|---|
| `scope()` | `latest.RAVE_COLLECTION` | search |
| `page_size()` | `kodi.setting_int("results_per_page", 50)` | all lists |
| `search(query, page, rows)` | `archive.search(..., rows=rows)` | search |
| `archive_thumb(identifier)` | `archive.thumb` | search art |
| `art(name)` | plugin `resources/art/<name>` (script `rave-screen` fallback) | all rows |
| `favourites()` / `favourite_key` / `has` / `add` / `remove` | `favourites.*` | favourites, actions |
| `downloads()` / `download_plan` / `download` / `download_delete` | `downloads.*` | downloads, actions |
| `playable_url(url)` | `http.safe_stream_url` | play validation |
| `platform_kind(url)` | `handoff.platform_kind` | favourite streams |
| `about()` | add-on versions + `ABOUT_LINKS` / `ABOUT_SOURCES` | about |

No method here fetches a URL itself: the plugin's `archive`, `downloads` and
`http` modules do the network work. The UI only maps results into rows.
`download()` forwards `progress(done, total)` and also records the last values
for `screens.progress(url)`, so the shell can poll from the GUI thread while
the worker blocks. A download is refused before the network when the plugin's
`downloads.plan` says it is ineligible, too large or out of space.

---

## 6. Tests

```bash
python3 -m unittest test.test_screens_library -v
```

74 tests, all offline, using the existing `test/stubs` Kodi stubs:

* 25/50/100 page sizes, backend snapshot, clamping, page labels;
* scoped search (`collection:ravetapes AND mediatype:audio`), blank query,
  empty results + retry, backend error + recovery, control-character cleaning;
* favourites pagination across 120 entries, pack/show/station/platform/stale
  mapping, add/remove actions and failures;
* downloads list, missing files, local playback, plan refusal, progress
  forwarding, failure reasons and progress copies;
* About versions/licence/links/sources, dict payloads, error state;
* play/play_all/shuffle intents, player hand-off, shuffle determinism, retry
  dispatch, Back semantics, loading state, import-light AST guard;
* the plugin backend delegated method-by-method and the extra-module import
  path through `raveplayer_plugin.resources.lib.*`;
* a library `Row` renders through the existing `KodiView.set_rows` unchanged.

Full suite remains green: `python3 -m unittest discover -s test` → 799 tests.

---

## 7. Known limits / follow-ups for the lead

* `play_all`/`shuffle` queue the **current page** of the screen handed to it.
  That is deliberate for a page-aware shell; if Play All should span every
  page of Favourites/Downloads, call it with a temporary all-rows screen
  (`Screen(..., rows=all_rows)`) or extend the handler with a list argument.
* There are no synthetic pagination rows. The shell owns the page keys and can
  use `page_label`, `has_next` and `has_previous`.
* In-flight downloads are exposed through `progress(url)`, not as extra rows;
  a download appears in `downloads()` only after the plugin writes its index.
* Favourites are loaded and saved by the plugin, so the shell must repaint the
  room from `ActionResult.refresh` after add/remove.
* `action="open"` on About rows is advisory; if the shell cannot open a URL it
  can render the row as information. The URL is plain data and is never
  fetched here.

# Look and feel 3.9.44 — implementation note

**Date:** 4 Nov 2026 · **Version:** 3.9.44 · **Branch:** `look-feel/3.9.44`
**Scope:** the first three recommendations of
[`LOOK-AND-FEEL-2026.md`](LOOK-AND-FEEL-2026.md) — Label2 facts, visible
descriptions, track InfoTags — plus removal of the tracked `* 2.*` duplicate
artifacts that broke `test_naming`. Display-only: no routing, content-type,
artwork or playback changes. **Nothing pushed, tagged or deployed; the Shield
check is still pending.**

## 1. Label2 on every row it helps

`ui.add_item()` now calls `ListItem.setLabel2()` with a plain, single-line fact
of **at most 16 characters** (`ui.MAX_LABEL2_CHARS`). The label itself is
unchanged, so the breadcrumb, the info dialog and the OSD keep working.

`ui.fact()` strips Kodi markup, collapses whitespace and clips an over-long
value with `…`. Three formatters feed it:

| Helper | Output | Used for |
|---|---|---|
| `ui.duration_fact()` | `43:57`, `1:02:03` | track and episode rows |
| `ui.count_fact()` | `1,204` | counts where a bare number is readable |
| `ui.size_date_fact()` | `48.0 MB · 31 Oct` (exactly 16) | downloads |
| `ui.short_date()` | `31 Oct` | dates in a fact, ISO only |

Facts shipped per screen:

| Screen | Label2 |
|---|---|
| Root | `newest`, `1990–2004`, `1990s`, `podcasts`, `live`, `saved`, `archive.org`, `random`, current version |
| Tape Packs hub | `2,600+`, `106 shows`, `1992–2004`, `14 series`, `33 raves`, `1987–now`, `archive.org` |
| Mixes & Shows hub | `5 feeds`, `archive`, `dubstep/grime`, `old skool` |
| Live Radio hub | `live` / `stations` |
| RaveTapePacks hub | `events`, `DJs`, `MCs`, `1992–2004`, `all` |
| Favourites | saved/download source, `offline`, `add-on`, `live` |
| Archive results | parsed event/venue (e.g. `Dreamscape`) |
| Archive tracks | duration (`43:57`); year/venue for sources without durations |
| Podcast episodes / Latest | duration |
| Downloads | size · date; `31 Oct` or `missing` for a missing file |
| Pirate Radio recordings | year |
| Moxser mix | compact date |
| Toronto / live stations | genre is already the album/plot; `live` for stations |

Skins that do not draw Label2 (Estuary's IconWall label plate renders
`ListItem.Label` only) simply ignore it. List view 55 and the right-hand column
gain the fact.

## 2. The description is now a field Estuary reads

Estuary's info/poster panels read `ListItem.Plot`, which Kodi resolves from the
**video** InfoTag (`VideoGUIInfo.cpp`, `case LISTITEM_PLOT`). Kodi 22 rejects
the music `plot` key, so the add-on's copy in the music `comment` field was
correct API hygiene but invisible in Estuary.

`kodi.video_info(plot)` returns the minimal tag `{"plot": ...}` — no title, no
media type — and `ui.add_item()` sets it on any directory ListItem that has a
plot (`menu_item`, `info_item`, `track_item`, `end_marker` all route through
it). The music tag still carries `comment`, and on Kodi 20–21 also `plot`, so
the music dialog, the OSD and the old skin paths are unchanged.

| Kodi | Music tag | Video tag | Estuary plot |
|---|---|---|---|
| 22 (Piers) | `comment` only | `plot` | visible |
| 20–21 (Nexus/Omega) | `comment` **and** `plot` | `plot` | visible |

The plot is display text only. `play()` build its own resolved ListItem and is
**not** touched, so a dual tag can never reach playback. Both paths are covered
by `test/test_look_feel.py::VisiblePlotTests` (patched `kodi.KODI_MAJOR` 22 and
21) and by `AboutPlotTests` against the real About route.

## 3. Track InfoTags are no longer discarded

`archive_item` and the "Play all" playlist builder now set:

| Field | Before | After | Source |
|---|---|---|---|
| `artist` | not set | `details["artist"]` | `nowplaying.parse` |
| `album` | `identifier.replace("-", " ")` | `archive.item_title(id)` (real title) | already fetched |
| `year` | not set | int year from `details["date"]` | new `nowplaying.year()` |
| `genre` | not set | display genre from the item's Archive `subject` tags (or an explicit genre word in the title) | new `archive._genre()` |
| `tracknumber` | not set | index + 1 (original order, even when shuffled) | loop index |
| `duration` | seconds | unchanged | Archive |

Unknown values stay unset: the add-on does not guess a DJ, year or genre; a title only contributes a genre when it names one ("Jungle", "Drum & Bass", …). The
same fields go on the "Play all"/"Shuffle pack" playlist, so the Estuary song
panel (`Track / Artist / Album / Year / Genre / Duration`) and the OSD get real
values instead of a slug album and three blanks. `nowplaying` was not changed
beyond the new `year()` accessor.

Related rows also gained tags where the data already existed: Toronto genre
rows carry their genre, Pirate Radio recordings their year, and Moxser its
date.

## 4. Duplicate artifacts removed

The `repo: publish 3.9.43` commit had accidentally tracked **70** `* 2.*`
copies (theme docs/PNGs, `resources/art/* 2.png`, fixture and test copies,
`scripts/make-rollout-art 2.py`). They failed `test_naming`'s kebab-case and
no-duplicate guards and inflated the walk. All 70 were byte-identical to their
originals except an older `test_naming 2.py`, which was removed too.

## Not in this build

The audit's remaining items are deliberately untouched: card art at 1.23:1 and
full-size pack covers (§4.4), `setContent("songs")` on Downloads (§4.5),
actionable empty states (§4.6), About regrouped into eight doors (§4.7),
context-menu reordering (§4.8), terminators/`+` in titles and `addSortMethod`.

## Files

| File | Change |
|---|---|
| `resources/lib/ui.py` | `MAX_LABEL2_CHARS`, `fact`/`duration_fact`/`count_fact`/`short_date`/`size_date_fact`, `setLabel2` in `add_item`, video plot, track tag parameters |
| `resources/lib/kodi.py` | `video_info()` — minimal video InfoTag |
| `resources/lib/nowplaying.py` | `year(details)` accessor |
| `resources/lib/archive.py` | `_genre()` + genre on each track dict |
| `resources/lib/routes.py` | facts on root/hubs/favourites/downloads/tracks; real album, artist, year, genre, tracknumber on archive rows and the playlist |
| `test/stubs/xbmcgui.py`, `test/stubs/xbmcplugin.py` | record `label2` |
| `test/test_look_feel.py` | 21 new tests |
| `addon.xml`, `changelog.txt`, `README.md`, `docs/QA-KODI.md` | version/docs |
| 70 `* 2.*` files | deleted |

## Verification

```sh
python3 -m unittest discover -s test     # Ran 542 tests ... OK (was 521)
python3 -m unittest test.test_look_feel -v
python3 test/run.py root                 # inspect label2/plot in the stub
```

`test_look_feel.py` covers: the 16-character budget and markup stripping,
duration/count/date formatting, root and pack-hub facts, track duration,
download `size · date`, archive venue, Kodi 22 vs legacy plot placement, the
About plot, `artist/album/year/genre/tracknumber` on archive rows and the
playlist (including original track numbers under shuffle), and Archive
subject → genre mapping.

## Shield checklist (pending)

1. Root/hubs: move across the cards and open view 55 — does the right-hand
   column show `1990–2004` / `106 shows` / `14 series`?
2. Tape pack track list: durations in the right column.
3. Tape pack info panel: `Artist`, `Album` (real title), `Year`, `Genre`,
   `Track` filled; OSD shows the artist while a tape plays.
4. About & Sources: descriptions visible while browsing (not only in the info
   dialog); Downloads copy visible.
5. Play a tape: no change to playback, playlist or OSD crash; the music dialog
   still shows the full plot.
6. Kodi 20/21 fallback only if a device becomes available — the video tag is
   additive there, and the legacy music `plot` is still set.

## Artifacts

`repo/` regenerated for 3.9.44 with `scripts/build-repo.sh` and committed on the
branch (required for auto-updates). No push, tag or device install was done.

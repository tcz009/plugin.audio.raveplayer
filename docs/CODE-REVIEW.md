# Independent code review — brief

**Project:** Rave Player — Kodi audio add-on (`plugin.audio.raveplayer`)
**Version under review:** 3.9.22 (branch `hardening/3.9.22`; 3.9.21 is `main`)
**Reviewer target:** the runtime code and tests in this repo; please ignore `dist/`, `repo/`, `stage/`, `__pycache__/` and generated artwork.

## What it is

A Kodi plugin that browses and streams oldskool rave tape packs, podcasts and live pirate radio from public sources (Internet Archive, radio-browser.info, RSS feeds, DNBRADIO). No content is hosted or redistributed; everything is streamed from third parties.

- Python 3, `xbmc.python` 3.0.1, targets Kodi 20 (Nexus) – 22 (Piers); Kodi 22 ships Python 3.14.
- Roughly 2,000 lines of runtime Python in `resources/lib/` plus `default.py`.
- Tests: `test/`, run with `python3 -m unittest discover -s test` (409 tests, all offline; stubs in `test/stubs/`).

## Layout

| Path | Purpose |
|---|---|
| `default.py` | entry point → `routes.dispatch(sys.argv)` |
| `resources/lib/routes.py` | menu routes + dispatch table (largest file) |
| `resources/lib/http.py` | urllib fetch with timeouts, retries, disk cache |
| `resources/lib/cache.py` | on-disk JSON/text cache with TTL |
| `resources/lib/archive.py` | archive.org search, item metadata, audio file resolution |
| `resources/lib/radio.py` | live stations via radio-browser.info + curated stations |
| `resources/lib/feeds.py` | RSS/Atom podcasts |
| `resources/lib/dnbradio.py`, `legacy.py`, `nowplaying.py` | additional sources / metadata |
| `resources/lib/latest.py` | merged “Latest” view |
| `resources/lib/moxser.py`, `hardscore.py`, `getdarker.py`, `mixcloud.py`, `pirate.py`, `handoff.py` | 3.9.14 sources: Moxser sitemap/MP3, Hardscore RSS/pages, GetDarker RSS, curated Mixcloud, curated pirate data |
| `resources/lib/favourites.py`, `nowplaying.py`, `kodi.py`, `ui.py` | Kodi integration |
| `resources/*.json` | data: feeds, filters, rave catalogue, pirate-radio |
| `test/` | offline unit tests + stubs |

## How to run

```sh
python3 -m unittest discover -s test          # 409 tests, no network
python3 test/run.py latest                    # live smoke test (network)
python3 test/run.py filter_live key=kool      # curated Kool live route
```

No third-party dependencies; stdlib only.

## Changes since the last review / recent work

- **Latest cascade fix:** directory now ends as content `files`; DNB streams resolved concurrently at build time (3 s timeout, failures dropped); failed playback clears the playlist and stops instead of auto-advancing; visible non-playable “End of list” row.
- **Live radio:** curated streams for Kool London and Rinse FM (both via `admin.stream.rinse.fm`); radio-browser name results are filtered to real matches. `resources/filters.json` gained a `rinse` entry (16 total).
- **Archive playback:** audio URLs now use the item’s own storage node (`d1`/`server`/`d2` + `dir`) instead of `archive.org/download/`, which sometimes redirects to a node returning HTTP 500.

## Known trade-offs and areas worth scrutiny

- **Network I/O on the UI thread.** Kodi plugin routes are synchronous. The runtime caps a whole invocation at a 20 s network budget (plus per-request/read deadlines), so a slow source degrades to a partial directory with a notification; first-open latency up to that budget is still real.
- **archive.org URL construction.** Identifiers/filenames are validated and quoted, storage nodes are restricted to `archive.org`, and playback URLs pass the same public-host guard; check for any new metadata shape that bypasses it.
- **Cache key safety.** `cache.py` hashes URL+headers into filenames; header values are JSON-encoded into the key (injective), entries age out and are capped; review migration/cleanup behaviour.
- **Timeouts/retries.** Centralised in `http.py`; check that every source has a bounded timeout and that failures degrade to an empty list, not a crash.
- **Kodi 22 warnings (known, accepted).** `setInfo("music", {"plot": …})` logs “Unknown Music Info Key” on Kodi 22; the value is kept for backwards compatibility but `comment` is the supported field. Removing it would break older consumers, so it is documented rather than changed.
- **Mixcloud/YouTube need their official Kodi add-ons (known).** Kodi cannot embed Mixcloud's widget or play its HLS streams; this add-on hands off to `plugin.audio.mixcloud` / `plugin.video.youtube` and hides the row when an add-on is missing. No browser/OS intent is used. SoundCloud is not part of the Kodi build (web-version-only credit).
- **Third-party page headers (known).** Hardscore's WordPress "Bad Behavior" filter 403s a bare urllib UA; the adapter sends a browser UA + RSS Accept header. Moxser is rate-limited to one request/second and caches for 6 h.
- **DNS in the play route (known residual).** The public-host guard resolves the stream host synchronously (per-route memoised); a pathological resolver could delay one play attempt. The guard is required for the private-IP protection.
- **`repo/` artefacts** are generated by `scripts/build-repo.sh` and are not rebuilt on every code commit; the CI check `scripts/check-repo-artifacts.sh` expects them current. This is packaging, not runtime.
- **No secrets in the repo.** Any API keys are environment/local only; there should be none committed.

## Questions for the reviewer

1. Are there blocking calls or unbounded loops that could freeze Kodi?
2. Is the archive URL/identifier handling safe against malformed or hostile metadata?
3. Is the cache safe (key collisions, unbounded growth, concurrent writes)?
4. Are failure paths consistent — notify + empty list, never a traceback to Kodi?
5. Any Python 3.9–3.14 compatibility traps (Kodi 22 ships 3.14)?
6. Security: any SSRF-ish behaviour from user-supplied identifiers/URLs? Any injection into Kodi labels/InfoTags?

Findings can be returned as a file or pasted notes; we will triage every item.

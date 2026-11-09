# Web-only sources — 3.9.67

The NAS web app keeps five sources server-side (scraping is not practical on a
Kodi device). 3.9.67 adds them to **Classic lists** and to the **full-screen
app** without adding a top-level room to the app's ten-room home.

This release is code/docs only. No device, ADB, push or tag was used.

## Configuration

The plugin's existing Resolver section supplies both values:

| Setting | Use |
|---|---|
| `resolver_service_url` | e.g. `http://192.168.1.179:8097`; bare `host:port` is accepted and gets `http://`. |
| `resolver_service_token` | Sent as `Authorization: Bearer <token>` on every web JSON request. |

No new resolver provider is required. Web rows that are relative paths are
played as the absolute URL on that configured origin; the NAS proxies/resolves
the Mediafire URL behind `/stream`.

## API contract used

```
GET /api/20bensons
GET /api/ukraves
GET /api/ezgarage
GET /api/live
GET /api/podcast/dejavu-fm
```

Each list returns `items` (or `rows`) of:

```json
{"label": "...", "sub": "...", "play": "...", "art": "...",
 "fav": {}, "download": {}, "fact": "..."}
```

* `play` may be absolute (20bensons, Podomatic podcast enclosures, live radio)
  or a web-relative path (EZ Garage, UK Raves `/stream`); relative paths are
  resolved against the base.
* `art` may also be relative, e.g. `/static/art/20bensons.png`.
* Pagination is read from `total` + `pager` (`page/pages/total/per_page/next`)
  or from `next`; a bare `?page=N` query is honoured. Lists are displayed at
  the server's 40-row page size.
* Rows without a playable `play`, and YouTube/SoundCloud/Mixcloud/etc. platform
  pages, are never emitted as playable Kodi items.
* `download` is used only where the existing download allowlist supports it
  (DejaVu's Podomatic episodes → `Rave Resolver`); other web rows do not grow
  the download surface.

## Classic routes

| Mode | Purpose |
|---|---|
| `web_list&source=20bensons|ukraves|ezgarage|dejavu` | Paged web source list; rows are playable. |
| `web_live&token=dejavu|osa` | One DejaVu FM / OSA Radio live row. |
| `web_play&url=…` | Direct playback: absolute public stream, or a path on the configured web origin. No resolver step. |

Menu additions:

* **Tape Packs**: 20bensons.com, UK Raves Downloads, EZ Garage Sets.
* **Mixes & Shows**: DejaVu FM Archive.
* **Live Radio**: DejaVu FM, OSA Radio (from `/api/live`, canonical streams as
  the offline fallback).

## Full-screen app

The existing ten top-level rooms are unchanged. New hub rows use the normal
`Entry`/`Page` path:

* Tape Packs → 20bensons.com / UK Raves Downloads / EZ Garage Sets
  (`kind="web_list"`, paged child handler).
* Mixes & Shows → DejaVu FM Archive (`kind="web_feed"`, paged 40, downloadable
  episodes).
* Live Radio → DejaVu FM and OSA Radio before the Pirate Radio door; the
  `raveui.screens.live` module reads `/api/live` through the plugin helper and
  keeps the canonical streams as fallback.

Web tracks carry `Track.path` set to the resolved absolute URL, so
`PlaybackService` hands the URL straight to Kodi instead of wrapping it in a
`plugin://` resolve (which would re-run the public/resolver path and could
route Podomatic through the resolver).

## Client hardening (`resources/lib/webapi.py`)

* urllib only, no Kodi import; opener injectable for tests.
* 10 s default timeout, 1 MiB default body cap (declared length checked too).
* No automatic redirects; at most two same-origin hops.
* Token sent only after the origin check.
* Base URL normalisation rejects credentials, query strings, fragments and
  non-http(s) schemes.
* Absolute `play` URLs from a web row must still be public; only paths on the
  configured web origin may be private/LAN.
* 60 s in-memory cache (bounded, cleared by tests), failures are never cached.

## Tests

```sh
python3 -m unittest test.test_webapi test.test_web_routes
python3 -m unittest discover -s test
```

`test_webapi.py` covers base normalisation, bearer header/page query, relative
play/art, external-row rejection, pagination shapes, cache behaviour, byte
caps, off-host redirect refusal and same-origin redirects. `test_web_routes.py`
covers the three classic routes, retry plates, direct URL validation and the
`/api/live` preference/fallback. Screen coverage lives in
`test/test_rave_screen.py` (web doors, DejaVu downloadability, live rows).

## Rollout dependency

The web team is adding GET scope for these endpoints to the resolver service
token. Until that scope is deployed, list rooms may show a retryable empty
plate (401/403); Live Radio still shows and plays the canonical DejaVu FM / OSA
Radio streams. No Kodi change is needed when the scope lands.

# Kodi Resolver integration

Status: **module only — plugin routes are not wired in this branch.**

`script.module.raveresolver` 1.0.0 is an installable Kodi module add-on that
packages the resolver SDK in `resources/lib/resolver/`. The plugin
`plugin.audio.raveplayer` still plays URLs exactly as before. The integration
pass below is deliberately left to the Lead so the Kodi-all-at-once change is
one reviewable step.

## Why this shape

- Direct, Mediafire and Google Drive resolve **in-process on the Shield**.
  Those are the common Rave sources, and they must keep working when the NAS is
  off.
- Mega and Podomatic page links use a native adapter when one is supplied;
  otherwise they call the optional NAS `POST /api/resolve` endpoint.
- The service is a fallback, never the primary path for direct/Mediafire/Drive.
- The module is additive: a separate add-on zip, its own settings, its own
  cache directory, no changes to `resources/lib/routes.py` yet.

## 1. Dependency manifest

Add one line to `plugin.audio.raveplayer/addon.xml`:

```xml
<addon id="plugin.audio.raveplayer" ... version="3.9.52">
    <requires>
        <import addon="xbmc.python" version="3.0.1"/>
        <import addon="script.module.raveresolver" version="1.0.0"/>
    </requires>
    ...
</addon>
```

Kodi installs the module first and puts
`script.module.raveresolver/resources/lib` on `sys.path`. The package imports as
`resolver`:

```python
from resolver import Resolver, ResolveError
```

The module's own manifest requires `xbmc.python 3.0.0` (Kodi 20+), so it does
not raise the plugin's minimum Kodi version.

## 2. Resolution contract

```python
resolver = Resolver()                      # reads script.module.raveresolver settings
result = resolver.resolve(url)             # Resolution or ResolveError subclass

result.url          # directly playable http(s) URL
result.provider     # direct | mediafire | drive | podomatic | mega | service
result.source       # in-process | service
result.expires_at   # epoch seconds, or None
result.headers      # extra headers the media request may need
result.kodi_url()   # URL + Kodi |Header=... suffix when headers exist
```

Selection helpers:

- `resolver.provider_for(url)` — provider name or `""`.
- `resolver.needs_resolution(url)` — True only for **known** provider page
  links. It is False for direct audio and for unknown hosts, so live-radio and
  third-party streams are not accidentally routed through the resolver.
- `resolver.resolve(url, use_service=False)` — in-process only, for diagnosis.
- `resolver.resolve_url(url)` — string, or `""` on failure.

Typed failures all carry `.code` and `.fallback`: `InvalidURL`, `BlockedURL`,
`HostNotAllowed`, `UnsupportedURL`, `AdapterNotReady`, `NotFound`,
`ProviderError`, `ProviderTimeout`, `RateLimited`, `ServiceAuthError`,
`ServiceError`, `ServiceProtocolError`.

## 3. `routes.play()` integration

Add a small lazy helper near the other `_lazy()` modules in
`resources/lib/routes.py`. Keeping the import lazy means a missing module
surfaces only when playback needs it, not while the plugin root is loading.

```python
_RESOLVER = None


def _resolver():
    global _RESOLVER
    if _RESOLVER is None:
        from resolver import Resolver
        _RESOLVER = Resolver()
    return _RESOLVER


def _resolve_stream(value):
    """Turn a provider page into a playable URL; direct audio passes through."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        resolver = _resolver()
        if not resolver.needs_resolution(text):
            return _playable_url(text)
        result = resolver.resolve(text)
        return _playable_url(result.kodi_url())
    except Exception as exc:  # resolver failures must not kill the route
        kodi.log("resolver: %s" % exc, level=30)
        return ""
```

Then in `play()` replace the current one-line stream resolution:

```python
# before
stream = _playable_url(params.get("url", ""))

# after
stream = _resolve_stream(params.get("url", ""))
```

The existing failure block already handles an empty stream with the
"private, loopback or unresolved host" notification. Do **not** log the raw
`params["url"]`: signed provider URLs are credentials.

## 4. `_play_tracks()` integration

`_play_tracks()` is shared by `play_all` and `play_all_collection`, so one loop
change covers both. Replace the per-track guard:

```python
# before
for index, track in selected:
    url = _playable_url(track.get("url", ""))
    if not url:
        dropped += 1
        kodi.log("play_all: skipping non-public track URL for %r"
                 % track.get("title"), level=30)
        continue

# after
for index, track in selected:
    url = _resolve_stream(track.get("url", ""))
    if not url:
        dropped += 1
        kodi.log("play_all: skipping unresolvable track URL for %r"
                 % track.get("title"), level=30)
        continue
```

`_resolve_stream()` calls `_playable_url()` again on the resolved URL, so the
existing public-host guard remains the last check before a URL enters the
playlist. `kodi.notify("Skipped N tracks…")` already reports the drops.

## 5. Downloads integration

`_download_context()` currently offers Download only for
`downloads.eligible(url, source, check_host=False)`. A Mediafire/Drive page is
not a direct file, so it is not eligible. Two additive changes:

1. Extend the downloads allowlist in `resources/lib/downloads.py`:

```python
ALLOWED_SOURCES = {
    # ... existing sources ...
    "Rave Resolver": (
        "mediafire.com",
        "drive.google.com",
        "drive.usercontent.google.com",
        "podomatic.com",
        "mega.nz",
    ),
}
```

`downloads._source_host_ok()` already matches subdomains, so
`download*.mediafire.com` passes. Keep the existing 500 MiB/2 GiB and
content-type guards.

2. Resolve before planning in `download_start()`:

```python
def download_start(handle, params):
    raw = params.get("url", "")
    title = params.get("title", "Rave Player download")
    source = params.get("source", "")
    try:
        resolution = _resolver().resolve(raw)
    except Exception as exc:
        kodi.log("resolver: %s" % exc, level=30)
        kodi.notify("That download could not be resolved.")
        return
    if resolution.provider != "direct":
        source = "Rave Resolver"
    # kodi_url() carries any Referer/User-Agent suffix into
    # downloads.plan() -> http.probe_media() and downloads.download() ->
    # http.open_media().
    plan = downloads.plan(resolution.kodi_url(), title, source)
    ...
```

Offer the context item for resolvable pages too:

```python
def _download_context(url, title, source):
    resolvable = _resolver().needs_resolution(url)
    if not (downloads.eligible(url, source, check_host=False) or resolvable):
        return []
    ...
```

Keep the existing `Downloads` index semantics: store the resolved URL (with
the header suffix), not the page URL, or a later replay would resolve again.

## 6. NAS service contract

Configure `resolver_service_url` and `resolver_service_token` in the Rave
Resolver add-on settings. The client sends:

```http
POST http://nas:8080/api/resolve
Authorization: Bearer <resolver_service_token>
Content-Type: application/json

{"url": "https://mega.nz/file/abc123#key", "provider": "mega"}
```

It accepts:

```json
{
  "url": "https://gfs123.userstorage.mega.co.nz/abc",
  "provider": "mega",
  "expires_at": 1760000000,
  "headers": {"Referer": "https://mega.nz/"}
}
```

`expires_in` (seconds) and a `{"result": {...}}` wrapper are also accepted.
The returned URL must be public http(s); private/loopback results are rejected.
The service URL itself may be a LAN name (`http://nas:8080`,
`http://nas.local:8080`) because it is operator-configured, not user input.

## 7. Settings

| Setting | Default | Notes |
| --- | --- | --- |
| `resolver_service_url` | empty | blank disables the fallback |
| `resolver_service_token` | empty | Bearer token; masked, never logged |
| `resolver_enable_mega` | false | off means Mega is rejected locally |
| `resolver_http_timeout` | 20 s | provider page/probe |
| `resolver_service_timeout` | 25 s | NAS fallback |
| `resolver_cache_dir` | empty | blank = `special://temp/raveresolver` |
| `resolver_cache_ttl` | 7200 s | signed-URL cache; 0 disables |

## 8. Security and logging

- Loopback/private/link-local/metadata addresses are rejected before any
  connection; normal hostnames are resolved and every answer must be public.
- Redirects are validated hop by hop (max 5).
- The service token is only sent as a Bearer header. It is not in a URL, a
  cache key, a log line or `Resolution.headers`.
- `resolver.log` strips query strings and registered secrets. Do not add
  `kodi.log(url)` calls in the integration.
- The cache stores signed provider URLs (needed for replay). It lives under
  the Kodi temp/profile area and uses SHA-256 file names.

## 9. Rollout checklist (Lead, tonight)

1. Merge/cherry-pick this module branch or install the module zip.
2. Add the `<import addon="script.module.raveresolver" version="1.0.0"/>` line.
3. Apply the `routes.play()` and `_play_tracks()` edits above.
4. Apply the downloads allowlist + `download_start()` edits.
5. Add the download context item for resolvable pages.
6. Run `python3 -m unittest discover -s test -v` (offline; no network).
7. Build and install the zips from `repo/`: `repository.raveplayer`,
   `script.module.raveresolver`, `plugin.audio.raveplayer` (dependencies
   resolve automatically) and `script.raveplayer.ui` as before.
8. Device-test direct Archive, Mediafire, Drive, live radio and Downloads;
   verify `kodi.log` has no token or signed URL.
9. Only then bump `addon.xml`/`changelog.txt` and regenerate `repo/`.

## 10. Tests

The module is covered by the plugin's existing offline suite:

```sh
python3 -m unittest discover -s test -v
```

New files:

- `test/test_resolver_module.py` — manifest/settings/policy/cache/log and a
  no-socket assertion.
- `test/test_resolver_adapters.py` — adapter selection, direct/Mediafire/Drive
  parsing and caching, Podomatic seam.
- `test/test_resolver_mega.py` — Mega URL parsing and adapter seam.
- `test/test_resolver_service.py` — service contract, fallback, auth errors and
  token redaction.

All HTTP and DNS is injected; no test opens a network connection.

## 11. Files in this change

```
script.module.raveresolver/
  addon.xml
  changelog.txt
  README.md
  resources/settings.xml
  resources/lib/resolver/
    __init__.py base.py policy.py http.py cache.py settings.py log.py
    direct.py mediafire.py drive.py podomatic.py mega.py service.py manager.py
docs/KODI-RESOLVER.md
test/test_resolver_*.py
scripts/build.sh scripts/build-repo.sh scripts/check-repo-artifacts.sh
repo/  (regenerated catalogue + module zip)
```

No plugin route file is modified in this branch.

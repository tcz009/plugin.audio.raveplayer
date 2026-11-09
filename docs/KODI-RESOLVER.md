# Kodi Resolver integration

Status: **module only — plugin routes are not wired in this branch.**

`script.module.raveresolver` 1.1.0 is an installable Kodi module add-on that
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
        <import addon="script.module.raveresolver" version="1.1.0"/>
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

For a Mega result from the web service, `result.url` is the signed
`/api/mega/stream?...` URL, `result.headers` is empty (the URL is
self-authenticating) and `result.expires_at` is the token's `e`. Non-Mega
service results keep the payload's headers and expiry.

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

## 6. NAS service contract (web 1.6.64 and later)

Configure `resolver_service_url` with the web resolver **base**. LAN,
Tailscale and reverse-proxy forms are all supported; a trailing `/` is
ignored:

```text
http://192.168.1.179:8097           LAN
http://rave-nas.tail1234.ts.net:8097 Tailscale
https://rave.example/resolver       reverse-proxy prefix
```

The client sends:

```http
POST <base>/api/resolve
Accept: application/json
Content-Type: application/json

{"url": "https://mega.nz/file/abc123#key", "provider": "mega"}
```

### 6.1 Auth: exactly one mode

| Configured | Header sent |
| --- | --- |
| `resolver_service_token` | `Authorization: Bearer <resolver_service_token>` |
| only `resolver_service_cookie` | `Cookie: raveplayer_session=<signed value>` |
| neither | no auth header (web answers `401` → `ServiceAuthError`) |

Bearer wins when both are set. The service base is operator-configured, so it
may be a LAN name (`http://nas:8080`, `http://nas.local:8080`) or a Tailscale
name. That is the only place private addresses are allowed.

#### Web-side requirement: `RAVEWEB_RESOLVER_TOKEN`

Web 1.6.64 accepts only the browser session cookie. For Kodi to authenticate
without a browser, the web must add an optional machine-to-machine token:

- environment variable `RAVEWEB_RESOLVER_TOKEN` (32+ random bytes; treat it as
  a password and rotate by restarting the container);
- accept `Authorization: Bearer <token>` on `POST /api/resolve` and,
  optionally, `/api/mega/sign`;
- compare with `hmac.compare_digest`; when the variable is unset, reject every
  bearer (fail closed);
- scope the token to those resolver endpoints only — it is **not** a general
  `/api/*` session and must not unlock downloads, admin or settings;
- never log the token or the `Authorization` header;
- keep `/api/mega/stream` token-free: the signed HMAC query is the credential.

Cookie mode is the temporary compatibility path. Copy
`raveplayer_session=<value>` from a logged-in browser (DevTools → Application
→ Cookies) into `resolver_service_cookie`, or paste just the value. The cookie
is a bearer credential with the same access as that browser session; it
expires with the session (or the remember-me window) and must be replaced when
it does.

### 6.2 Response

Web 1.6.64 returns:

```json
{
  "ok": true,
  "url": "https://gfs123.userstorage.mega.co.nz/dl/...",
  "headers": {"Referer": "https://mega.nz/"},
  "expires": 1760000000,
  "source": "mega",
  "host": "gfs123.userstorage.mega.co.nz",
  "stream": "/api/mega/stream?u=https%3A%2F%2Fmega.nz%2Ffile%2Fabc123%23key&e=1780000000&t=..."
}
```

| Field | Meaning |
| --- | --- |
| `url` | Direct media URL for non-Mega. For Mega this is **AES-CTR ciphertext** and the client never returns it. |
| `source` | Adapter id: `direct`, `mediafire`, `drive`, `podomatic`, `mega`. |
| `expires` | Unix epoch seconds for `url` (for Mega, the short-lived storage URL). |
| `stream` | Relative signed path, present for Mega. The playable expiry is its `e` query parameter. |
| `headers` | Extra request headers for the direct URL. Ignored for Mega (the signed stream is self-authenticating). |
| `host` | Resolved URL host, for diagnostics only. |

Older shapes remain accepted: `provider` instead of `source`,
`expires_at` (epoch or ISO-8601) or `expires_in` instead of `expires`, and a
`{"result": {...}}` / `{"data": {...}}` wrapper. Non-Mega results must be
public http(s) URLs; private/loopback results raise `ServiceProtocolError`.

### 6.3 Mega selection — never ciphertext

When the payload's `source` (or legacy `provider`) is `mega`:

1. If `stream` is a non-empty **relative** path, the result is
   `base + stream` (query preserved), `provider = "mega"`,
   `headers = {}`, and `expires_at` is the stream token's `e` (falling back
   to the payload expiry).
2. If `stream` is missing, empty, absolute, protocol-relative, contains
   control characters, or exceeds 8 KiB, the resolve raises
   `ServiceProtocolError`.

`url` is never used as a fallback for Mega: it is encrypted bytes, not audio,
and it is a short-lived storage capability. Tests assert this explicitly.

### 6.4 Absolute stream URL

`stream` is root-relative. The client appends it to the configured base and
preserves the signed query byte-for-byte:

| `resolver_service_url` | Returned playable URL |
| --- | --- |
| `http://192.168.1.179:8097` | `http://192.168.1.179:8097/api/mega/stream?...` |
| `http://rave-nas.tail1234.ts.net:8097` | `http://rave-nas.tail1234.ts.net:8097/api/mega/stream?...` |
| `http://192.168.1.179:8097/` | same (no double slash) |
| `https://rave.example/resolver` | `https://rave.example/resolver/api/mega/stream?...` |
| `http://nas:8080/api/resolve` | `http://nas:8080/api/mega/stream?...` |

The constructed URL is validated syntax-only under `allow_private=True`: the
base is operator-configured, and the web may be on the LAN or a Tailscale
address. A service-supplied absolute host is never followed.

### 6.5 Player behaviour: Range, HEAD and headers

Kodi (or any player) requests the returned stream URL **directly**:

- Do not append `Authorization`, `Cookie`, the service token, or a
  `|Header=...` suffix to a Mega stream URL. The HMAC is in `?t=`, and extra
  headers can break the token/proxy contract. For Mega the module returns an
  empty header mapping, so `Resolution.kodi_url()` is the plain URL.
- `Range`/`HEAD` are handled end-to-end by the web `/api/mega/stream` proxy;
  Kodi's normal `Range` seek behaviour returns `206`. The module never proxies
  media bytes and never mints a second token.
- Do not log, copy or display a signed stream URL: it contains the MEGA file
  key and a reusable HMAC token until `e`. Re-resolve when `result.is_expired()`
  is true or the web answers `401/403`.
- Keep the service URL and credentials out of playlist/`kodi.log` output.

## 7. Settings

| Setting | Default | Notes |
| --- | --- | --- |
| `resolver_service_url` | empty | web base (LAN/Tailscale/reverse-proxy prefix); blank disables the fallback |
| `resolver_service_token` | empty | `Authorization: Bearer`; masked, never logged; preferred |
| `resolver_service_cookie` | empty | web session cookie for web builds without a service token; masked, never logged |
| `resolver_enable_mega` | false | off means Mega is rejected locally |
| `resolver_http_timeout` | 20 s | provider page/probe |
| `resolver_service_timeout` | 25 s | NAS fallback |
| `resolver_cache_dir` | empty | blank = `special://temp/raveresolver` |
| `resolver_cache_ttl` | 7200 s | signed-URL cache; 0 disables |

## 8. Security and logging

- Loopback/private/link-local/metadata addresses are rejected before any
  connection; normal hostnames are resolved and every answer must be public.
  The one exception is the operator-configured service base (including the
  absolute Mega stream URL built from it).
- Redirects are validated hop by hop (max 5).
- The service token is sent only as a Bearer header; the session cookie only
  as a `Cookie` header, and only when no token is configured. Neither is in a
  URL, a cache key, a log line or `Resolution.headers`.
- `resolver.log` strips query strings and registered secrets (both the token
  and the cookie). Do not add `kodi.log(url)` calls in the integration.
- For Mega, service-supplied response `headers` are dropped: the signed URL
  authenticates itself, and a stray `Authorization`/`Cookie` would be both
  unnecessary and potentially breaking.
- The cache stores signed provider URLs (needed for replay). It lives under
  the Kodi temp/profile area and uses SHA-256 file names.

## 9. Rollout checklist (Lead, tonight)

1. Merge/cherry-pick this module branch or install the 1.1.0 module zip.
2. Add the `<import addon="script.module.raveresolver" version="1.1.0"/>` line.
3. Apply the `routes.play()` and `_play_tracks()` edits above.
4. Apply the downloads allowlist + `download_start()` edits.
5. Add the download context item for resolvable pages.
6. Configure `resolver_service_url` and **one** auth mode. For web 1.6.64 use
   `resolver_service_cookie`; once `RAVEWEB_RESOLVER_TOKEN` is deployed use
   `resolver_service_token` instead.
7. Run `python3 -m unittest discover -s test -v` (offline; no network).
8. Build and install the zips from `repo/`: `repository.raveplayer`,
   `script.module.raveresolver`, `plugin.audio.raveplayer` (dependencies
   resolve automatically) and `script.raveplayer.ui` as before.
9. Device-test direct Archive, Mediafire, Drive, live radio, Downloads and one
   Mega file (seek forward/backward); verify `kodi.log` has no token, cookie
   or signed URL.
10. Only then bump `addon.xml`/`changelog.txt` and regenerate `repo/`.

## 10. Tests

The module is covered by the plugin's existing offline suite:

```sh
python3 -m unittest discover -s test -v
```

Relevant files:

- `test/test_resolver_module.py` — manifest/settings/policy/cache/log and a
  no-socket assertion.
- `test/test_resolver_adapters.py` — adapter selection, direct/Mediafire/Drive
  parsing and caching, Podomatic seam.
- `test/test_resolver_mega.py` — Mega URL parsing and adapter seam.
- `test/test_resolver_service.py` — service contract, fallback, auth errors and
  token redaction.
- `test/test_resolver_stream.py` — new/old payload parsing, Mega `stream`
  selection (LAN, Tailscale, trailing slash, reverse-proxy prefix), Bearer vs
  cookie, and the no-ciphertext-fallback failures.

All HTTP and DNS is injected; no test opens a network connection.

## 11. Files in this change

```
script.module.raveresolver/
  addon.xml (1.1.0)
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

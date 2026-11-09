# Rave Resolver (`script.module.raveresolver`)

Shared resolver SDK for **Rave Player** on Kodi 20 (Nexus) through Kodi 22
(Piers). It turns provider page links into directly playable audio URLs.

The plugin requires this module (1.1.1 in 3.9.73) and calls it from
`routes.play()`, `_play_tracks()` and downloads; see `docs/KODI-RESOLVER.md`
in the plugin repo.

## What runs where

| Provider | In-process | Needs NAS | Notes |
| --- | --- | --- | --- |
| Direct audio | yes | no | Host allowlist + public-address check; no network request |
| Mediafire | yes | no | Extracts the signed `download*.mediafire.com` URL |
| Google Drive | yes | no | Handles the >100 MB virus-scan confirm form |
| Podomatic | direct CDN files only | page links | Page scraper lands in the web build |
| Mega | URL parsing + adapter seam | signed stream | Web returns `/api/mega/stream?...`; the raw `url` is ciphertext and is never played |
| Anything else | no | optional | Service fallback when configured |

The NAS `POST /api/resolve` endpoint is a **fallback**, never the primary path
for direct, Mediafire or Drive.

## Install

Install the module zip (`script.module.raveresolver-1.1.1.zip`) from the Rave
Player repository, or add it as a dependency of `plugin.audio.raveplayer`:

```xml
<requires>
    <import addon="xbmc.python" version="3.0.1"/>
    <import addon="script.module.raveresolver" version="1.1.1"/>
</requires>
```

Kodi then puts `script.module.raveresolver/resources/lib` on `sys.path`, so the
package imports as `resolver`:

```python
from resolver import Resolver, ResolveError
```

## API

```python
resolver = Resolver()
result = resolver.resolve("https://www.mediafire.com/file/abc123/set.mp3")
result.url          # direct signed URL
result.provider     # direct | mediafire | drive | podomatic | mega | service
result.source       # in-process | service
result.kodi_url()   # URL with Kodi |Header=... suffix when needed
result.expires_at   # epoch seconds, or None
```

A Mega result from the service is the playable signed stream URL
(`<base>/api/mega/stream?...`), never the AES-CTR ciphertext. Its
`expires_at` is the signed token's `e`, and its `headers` mapping is empty:
Kodi must request the URL directly without appending `Authorization`/`Cookie`.

- `resolver.needs_resolution(url)` — False for ordinary direct audio, True for
  provider pages and unknown links.
- `resolver.provider_for(url)` — provider name or `""`.
- `resolver.resolve(url, use_service=False)` — in-process only (diagnostics).
- `resolver.resolve_url(url)` — string, or `""` on failure.
- `resolver.available_providers()` — adapters plus `service` when configured.

Failures are typed: `InvalidURL`, `BlockedURL`, `HostNotAllowed`,
`UnsupportedURL`, `AdapterNotReady`, `NotFound`, `ProviderError`,
`ProviderTimeout`, `RateLimited`, `ServiceAuthError`, `ServiceError`,
`ServiceProtocolError`. Every one carries `code` and `fallback`.

## Settings (Kodi add-on settings)

| Setting | Default | Meaning |
| --- | --- | --- |
| `resolver_service_url` | empty | Web base URL, e.g. `http://nas:8080` or a Tailscale name |
| `resolver_service_token` | empty | Bearer token (`RAVEWEB_RESOLVER_TOKEN` contract); masked, never logged |
| `resolver_service_cookie` | empty | `raveplayer_session=...` cookie for web builds without a service token; masked, never logged |
| `resolver_enable_mega` | false | Allow Mega links (native adapter or service) |
| `resolver_http_timeout` | 20 s | Provider page/probe timeout |
| `resolver_service_timeout` | 25 s | NAS fallback timeout |
| `resolver_cache_dir` | empty | Blank = `special://temp/raveresolver` |
| `resolver_cache_ttl` | 7200 s | Signed-URL cache lifetime; 0 disables |

The service URL may be a LAN host (including `.local`); media URLs may not.
That asymmetry is intentional: the service is operator-configured, media URLs
come from third parties.

## Security model

- http(s) only; no userinfo, control characters, non-standard scheme or
  malformed port.
- Loopback, link-local, private, multicast, reserved, unspecified and
  local-only names (`.local`, `.lan`, `.internal`, `.home.arpa`, `.test`,
  `.invalid`, `.onion`) are refused before a connection.
- Normal hostnames are resolved and **every** A/AAAA answer must be public.
- Redirects are followed manually (max 5) and every hop is re-validated.
- A service result must be a public http(s) URL; it cannot point Kodi at the
  LAN. A private/loopback URL is never sent to the service either.
- Only one service auth mode is used: `Authorization: Bearer ...` when a
  token is set, otherwise `Cookie: raveplayer_session=...` when a session
  cookie is configured. Neither is in the URL, the cache, a log line or a
  `Resolution.headers` mapping.
- Non-Mega service results must be public http(s) URLs. A Mega stream URL is
  built from the operator-configured service base (LAN/Tailscale allowed) and
  the service-supplied relative `stream` path; an absolute stream path or a
  missing `stream` is refused. The ciphertext `url` is never played.
- Logs contain scheme + host at most; signed URLs and query strings are
  stripped by `resolver.log`.

## Tests

The module's tests live in the plugin repo's existing offline suite:

```sh
python3 -m unittest discover -s test -v
```

They run with the Kodi stubs in `test/stubs`, injected fake HTTP clients and
injected DNS resolvers. No test opens a socket, and that is asserted.

## Build

From the plugin repo root:

```sh
./scripts/build.sh        # dist/plugin..., dist/script.raveplayer.ui..., dist/script.module.raveresolver...
./scripts/build-repo.sh   # repo/addons.xml, repo/script.module.raveresolver/*.zip
```

`scripts/check-repo-artifacts.sh` verifies the module zip is tracked and
`repo/addons.xml` is current.

## Version history

See `changelog.txt`. Version 1.0.0 was the first Kodi-installable module.
Version 1.1.1 is the 3.9.73 hardening release: typed service error codes,
cached-expiry clamps, 80/443-only media ports, default no-redirect HTTP, DNS
checks for absolute web results, `pdcn.co`/`mega.io`/`drive.usercontent` host
parity, bare `host:port` service bases, bounded cache/negative state and
sanitised headers.  Version 1.1.0 added the web 1.6.64 service contract:
`source`/`expires`/`stream`
parsing, the absolute Mega stream URL, and Bearer-or-cookie auth. The plugin
routes are intentionally unchanged until the integration pass.

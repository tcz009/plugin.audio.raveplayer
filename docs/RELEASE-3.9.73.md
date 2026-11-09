# Rave Player 3.9.73 — resolver hardening

Offline, code/docs only. No device, ADB, push, tag or deploy. Worktree
`raveplayer-worktrees/kodi-resolver-hardening`, branch
`feat/3.9.73-resolver`, base `3c499dd` (v3.9.72).

Versions: **plugin 3.9.73**, **screen 3.9.73**, **resolver module 1.1.1**
(`plugin.audio.raveplayer` now requires `script.module.raveresolver 1.1.1`).

## What changed

### P1 correctness and security

1. **Typed `/api/resolve` errors.** `ServiceClient` now reads the web's JSON
   `code` and maps it (and the HTTP status as a fallback) onto the module's
   typed failures: `not_found` → `NotFound`, `rate_limited` → `RateLimited`
   with a bounded `Retry-After` (numeric or HTTP-date, capped 120 s),
   `timeout` → `ProviderTimeout`, `upstream` → `ProviderError`, `blocked` →
   `BlockedURL`, `invalid` → `InvalidURL`, `unsupported`/`unknown` →
   `UnsupportedURL`, `unauthorized`/401/403 → `ServiceAuthError`.  A 3xx from
   the service is refused (`ServiceProtocolError`); the client follows no
   redirects.  Error bodies are never copied into an exception string.
2. **Cached expiry.** Mediafire and Drive cache records are re-checked against
   their own `expires_at` on read and the cache TTL is clamped to it, so a 2 h
   entry cannot serve an expired signed URL.  The Mediafire negative cache is
   now the web's 15 s (was 5 min), pruned and capped at 128 entries.
3. **Ports.** Media/provider/Mega URLs are limited to ports 80 and 443; a
   `:22`, `:8080`, etc. URL is rejected before a request.  The one exception is
   the operator-configured resolver service base, which keeps any port so a
   LAN `http://nas:8080` still works.
4. **Redirects.** `HttpClient` no longer follows redirects by default; callers
   opt in.  Drive opts in to at most 3 hops, each re-checked against the
   Google host allowlist and DNS policy.  Mediafire maps every 3xx to
   `ProviderError`.  The service client explicitly follows none and refuses an
   off-origin redirect.
5. **SSRF.** `/api/resolve` absolute results keep the real DNS public-host
   check (any loopback/private/link-local/metadata answer → protocol error).
   In-process adapter results are re-validated for scheme, port and
   private/local literal hosts.  At play time, `web_play()` now passes every
   absolute (non-same-origin) web row through a new shared
   `http.is_public_http_url_dns()`; the same-origin EZ Garage / UK Raves proxy
   base remains exempt because that service does the resolving.
6. **Host recognition.** `pdcn.co` is a Podomatic host and `/e/...` wrapper
   links are canonicalised locally to their `*.podomatic.com/enclosure/...`
   target.  `mega.io` is a Mega host (parsed/normalised to `mega.nz`).
   `drive.usercontent.google.com` is no longer a Drive *page*: its signed
   download URLs stay on the direct path while the host remains in the Drive
   result allowlist.  Single-label and `.localdomain` hostnames are refused.
7. **Service base.** Bare `host:port` / `host` is accepted (`http://`
   assumed), matching `webapi.normalise_base`.  A bad setting no longer
   disables all resolution: construction logs once, leaves `service=None`, and
   Mediafire/Drive/Podomatic/direct stay usable.  The plugin retries a
   non-import construction failure instead of caching a permanent failure.
   Private LAN/Tailscale bases are still allowed, but link-local
   (169.254/16, fe80::/10, metadata IPv6) and cloud-metadata hostnames are
   refused because the request carries the Bearer token.

### P2

- Bounded cache: 512 in-memory entries, 512 files / 64 MiB on disk (oldest
  pruned), `0600` files, and `Cache.clear()` deletes only its own 64-hex
  hashed entries.
- Bounded Mediafire negative state (above).
- `MegaLink.as_dict()` returns kind/handle/has-key only — no fragment key and
  no URL (which embeds the key).  Equality still compares the private fields.
- Header sanitising: 24 headers / 8 KiB, printable values, no
  credentials/framing/`Content-Type`, applied to service results and to every
  in-process adapter result before Kodi sees it.

## Tests

```sh
python3 -m unittest discover -s test        # full suite, twice
python3 -m unittest test.test_resolver_module test.test_resolver_service \
  test.test_resolver_adapters test.test_resolver_mega test.test_resolver_wiring \
  test.test_web_routes test.test_http
```

All tests are offline (Kodi stubs, fake DNS, fake HTTP).  New coverage:
error-code/`Retry-After` mapping, 200-with-`ok:false`, service 3xx, DNS-private
service result, non-80/443 results, cache expiry/negative/bounds/`0600`/clear,
redirect default-off + cap + off-allowlist refusal, adapter result/header
validation, pdcn/mega.io/drive.usercontent classification, `MegaLink.as_dict`,
bare service base, metadata/link-local service base, and `web_play` absolute
rows with a fake resolver (public plays, private DNS refused).

## Residual (not in this phase)

- Full-screen app `Track.path` writes still bypass the new play-time DNS guard
  when a web row is handed straight to the player; `web_play` is covered but
  the app's own absolute-row path is a separate follow-up.
- No per-registrable-domain rate limiter in Kodi (web has a bounded token
  bucket); Mediafire retains its 1.2 s courtesy gap and 429 backoff.
- No service-result cache / cross-adapter single-flight (web has both).
- Drive/MEGA 429 typing is unchanged (neither side types Drive 429).
- No device validation; playback/ADB checks are a separate release step.

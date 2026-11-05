# RaveTapePacks egress + playback bridge — 3.9.43

## Egress

Only `ravetapepacks.com` / `www.ravetapepacks.com` are sent through the
homelab VPN HTTP CONNECT proxy. Every other provider stays direct. The setting
is **General → RaveTapePacks egress proxy** (`rtp_egress_proxy`). The shipped
default is **blank** (direct); a public build must never carry a developer's
private LAN address. Set it on the network that needs the VPN route, e.g.:

```
<proxy-host>:8888
```

It accepts `host:port` or `http://host:port`; an empty value means direct. The
`RTP_EGRESS_PROXY` environment variable overrides it (operator/diagnostic use).
`RTP_EGRESS_HOSTS` overrides the RTP host list; `RTP_EGRESS_FALLBACK=0` disables
the one-shot direct fallback. A dead proxy/failed RTP fetch logs at debug and
falls back direct; RTP browsing/metadata/downloads all use this path.
SSRF validation is unchanged: every URL and redirect hop is checked against the
public http(s) guard.

## Playback bridge

Kodi’s player cannot use urllib’s proxy, so RTP play starts a temporary
`127.0.0.1` HTTP bridge. 3.9.50 also routes JungleTapes MP3s through it: Kodi's
libcurl fetch of that host stalls on the Shield (`CFileCache::Open failed`,
0 % cache) while the add-on's Python fetch of the same URL works.

- random per-process token in the path; no unauthenticated/open proxy;
- only `is_bridge_host()` targets are accepted (RTP egress hosts plus
  `jungletapes.com`; every other host → 403);
- loopback-only bind, bounded per-request timeout, Range/Referer/headers
  forwarded, redirects followed then the final host re-checked (non-allowlisted
  → 502);
- Kodi receives `http://127.0.0.1:<random-port>/<token>/<encoded target>`;
- the plugin stays alive until playback stops, then closes the bridge in a
  `finally`. If the bridge cannot start, play falls back to the direct URL.
- RTP play/browse failures are quiet: no notification/dialog/banner; debug log
  only.

## Tests

`test/test_rtp_egress.py` (proxy selection/headers/fallback/SSRF),
`test/test_rtp_bridge.py` (token rejection, non-RTP rejection, Range/headers,
redirect-away refusal), `test/test_rtp_bridge_routes.py` (bridge used for RTP and JungleTapes,
wait-before-close, fallback-direct, quiet RTP failures). Full suite **705 tests
OK** for 3.9.50.

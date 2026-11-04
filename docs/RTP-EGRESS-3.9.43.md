# RaveTapePacks egress + playback bridge — 3.9.43

## Egress

Only `ravetapepacks.com` / `www.ravetapepacks.com` are sent through the
homelab VPN HTTP CONNECT proxy. Every other provider stays direct. The setting
is **General → RaveTapePacks egress proxy** (`rtp_egress_proxy`), default:

```
192.168.1.142:8888
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
`127.0.0.1` HTTP bridge:

- random per-process token in the path; no unauthenticated/open proxy;
- only `is_egress_host()` targets are accepted (non-RTP → 403);
- loopback-only bind, bounded per-request timeout, Range/Referer/headers
  forwarded, redirects followed then the final host re-checked (non-RTP → 502);
- Kodi receives `http://127.0.0.1:<random-port>/<token>/<encoded target>`;
- the plugin stays alive until playback stops, then closes the bridge in a
  `finally`. If the bridge cannot start, play falls back to the direct URL.
- RTP play/browse failures are quiet: no notification/dialog/banner; debug log
  only.

## Tests

`test/test_rtp_egress.py` (proxy selection/headers/fallback/SSRF),
`test/test_rtp_bridge.py` (token rejection, non-RTP rejection, Range/headers,
redirect-away refusal), `test/test_rtp_bridge_routes.py` (bridge used for RTP,
wait-before-close, fallback-direct, quiet RTP failures). Full suite **521 tests
OK**.

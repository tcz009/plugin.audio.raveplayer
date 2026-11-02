# 3.9.27 — keep the fixed live title by disabling Kodi Shoutcast re-open

Research detail: `../docs/ICY-METADATA-OPTIONS.md` (workspace report; Kodi 22
`ShoutcastFile.cpp` / `CurlFile.cpp`). Short version: Kodi's audio file layer
detects the Rinse proxy via `icy-name`/`icy-br`, re-opens it as Shoutcast, opts
into `Icy-MetaData: 1` and replaces the current music tag with `StreamTitle`.

## Fix

Only the **play-time** URL carries the supported per-item protocol option:

- `resources/lib/live.py` `playback_url(stream)` → `stream + "|noshout=true"`
  (idempotent, lowercase `true`; invalid URLs return `""`).
- `resources/lib/routes.py` applies it to every one of the six direct-URL
  playlist entries and to the direct `setResolvedUrl` fallback.
- Stored/config/favourite/deep-link/radio-browser URLs are untouched.
- The finite six-entry reconnect, fixed labels/art and non-live playback are
  unchanged.

Kodi strips protocol options before the request, so the server never sees
`noshout`; this only suppresses the shoutcast re-open and the ICY tag update.
Worst-case maintenance risk is the option being removed in a future Kodi: the
placeholder would return, with no other playback change.

## Tests

`test/test_live.py` asserts every playlist and fallback path ends with
`|noshout=true`, idempotency, invalid URLs, stored curated URLs clean, plus the
existing finite/cap/Stop/no-M3U/direct-fallback coverage. No device test by the
agent; owner will verify Title stays "Kool FM" and the log no longer says
"File is a shoutcast stream. Re-opening".

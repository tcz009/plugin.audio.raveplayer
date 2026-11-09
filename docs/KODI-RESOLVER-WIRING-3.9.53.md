# Kodi resolver wiring — 3.9.53

Status: **shipped in the plugin** (code only; no device test, no push, no tag).
Branch `feat/resolver-integration-3.9.53`, based on `1c0b9da` (3.9.51), with
`feat/resolver-client` (`98bb517`, resolver module 1.1.0) merged fast-forward.

This is the integration pass that `docs/KODI-RESOLVER.md` left to the Lead.
That document remains the SDK/module and NAS-service contract; this one records
what the plugin now does with it.

## 1. What changed

| Area | Change |
| --- | --- |
| Manifest | `plugin.audio.raveplayer` is 3.9.53 and requires `script.module.raveresolver` 1.1.0. `script.raveplayer.ui` is 3.9.53 and requires plugin 3.9.53 (no screen code change). |
| `routes.play()` | Resolves a known provider page once, then plays the result (headers via Kodi `|Header=`; Mega via the absolute signed stream URL, no headers). |
| `_play_tracks()` | Provider pages are queued as `mode=play` plugin URLs, never raw. Resolution happens lazily per track, so play-all keeps its offsets and never spends the route budget resolving a whole collection. |
| Downloads | Mediafire/Drive/Podomatic results are planned/downloaded from their direct URL; Mega downloads use the signed `/api/mega/stream` endpoint. The 500 MiB/2 GiB, free-space and audio Content-Type checks are unchanged. |
| Settings | Four resolver settings in the plugin's Configure dialog (the module's own settings remain for other consumers). |
| Settings/selection | Provider classification in directory code is a local host check: no resolver import, no cache construction, no network on a list render. |
| Repo | `repo/addons.xml(.md5)` plus four add-ons: plugin, screen, resolver module, repository. |
| CI | `build.yml` and `check-repo-artifacts.sh` now fail if the plugin does not require the module version that ships in `repo/`. |

## 2. Selection and resolution

`routes._provider_for()` recognises exactly the four page providers the SDK
ships:

- Mediafire (`mediafire.com`)
- Google Drive (`drive.google.com`, `docs.google.com`,
  `drive.usercontent.google.com`)
- Podomatic (`podomatic.com`)
- Mega (`mega.nz`, `mega.co.nz`)

Everything else — Archive audio, live radio, JungleTapes/RTP, unknown hosts —
keeps the pre-3.9.53 direct path. This is deliberate: `resolver.needs_resolution`
would require importing the module and building its cache for every row, and
unknown/live streams must not be sent to a resolver.

`routes._resolve_stream()`:

1. Empty / direct / unknown → `_playable_url()` (the existing public-host and
   DNS guard).
2. Known page → `resolver.resolve()` exactly once for that playback.
3. Non-Mega result → `_playable_url(result.kodi_url())`. `kodi_url()` appends
   `|Header=value&...` with percent-encoded names/values.
4. Mega result from the web service → the absolute signed stream URL only.
   `result.url` is the signed URL; `result.headers` is empty. No `|Header=`
   suffix, no Authorization/Cookie, no ciphertext fallback.
5. Any failure → log provider + exception class only, return `""`; the existing
   failure path resolves a failed item quietly (and RTP stays silent).

### Mega URL guard

`_is_service_stream()` accepts the signed URL only when:

- it is http(s), has no userinfo, no `|` and no fragment;
- its scheme and netloc equal the configured `resolver_service_url` base;
- its path is exactly `<prefix>/api/mega/stream` (the prefix is preserved for a
  reverse-proxy base such as `https://rave.example/resolver`).

The service base is operator-configured and normally LAN/Tailscale, so this
one URL intentionally bypasses the public-host guard. A compromised or
misconfigured service cannot point playback or a download at another private
host. The signed query is kept byte-for-byte.

## 3. Playback

`routes.play()`:

- `is_rtp` is still derived from the incoming URL, so RTP silence is unchanged.
- `is_bridge = http.is_bridge_host(stream)` is derived from the **resolved**
  media URL, so a resolver result that needs the loopback bridge still gets it.
- The provider page is resolved once; `setResolvedUrl` receives the resolved
  path. Direct streams take the old path unchanged.

`_play_tracks()` (shared by `play_all` and `play_all_collection`):

- Each track is classified locally; every provider page is validated as a
  public page and then queued as
  `plugin://...?mode=play&url=...&label=...&thumb=...&fanart=...`.
- Kodi calls `mode=play` when that track starts, which resolves it there. A
  2,640-track play-all therefore does zero resolver work up front.
- The page URL and any Mega ciphertext never enter the playlist.
- `start` remains an absolute index into the full collection and track numbers
  keep their absolute value; shuffle is unchanged.
- Bridge hosts (RTP/JungleTapes) keep the same per-track wrapper.

The resolver's own two-hour signed-URL cache bounds repeated resolution when the
user replays tracks.

## 4. Downloads

`_download_context()` now also offers Download when the URL is a known provider
page. `routes.download_start()`:

1. Resolves the page once.
2. Non-Mega: plans/downloads `result.kodi_url()` (direct URL + `|Header=`).
3. Mega service result: plans/downloads the signed stream URL, with
   `allow_private=True` for exactly the configured service host.
4. Sets `source="Rave Resolver"`, so the existing download index and allowlist
   stay authoritative.

`downloads.py`:

- `ALLOWED_SOURCES["Rave Resolver"]` covers the four provider hosts. Subdomains
  match, so `download239.mediafire.com` passes.
- `eligible(resolved=True)` drops the filename-extension requirement (Drive
  download URLs and the signed Mega endpoint have none) but keeps the source
  host allowlist and the public-host guard. `extra_hosts` is the exact
  operator-configured service host for the signed Mega endpoint.
- `plan()` probes with the same `allow_private` decision, still requires a
  positive size ≤ 500 MiB, an audio Content-Type, the 2 GiB total allowance and
  256 MiB free. The probe's Content-Type chooses `.m4a` vs `.mp3` when the URL
  has no extension.
- `download()` keeps the atomic temp+rename, exact Content-Length check and
  metadata index; it passes `allow_private` through to `http.open_media`.
- `http.open_media`/`probe_media` gain `allow_private=False`; when true they
  require http(s) with no userinfo and confine redirects to the same origin.
  Nothing else can reach this path: `download_start()` only sets it after
  `_is_service_stream()` succeeds.

Existing Archive/Moxser/Hardscore/Pirate/RTP/Toronto download behaviour and
allowlists are unchanged.

## 5. Settings

Plugin → Configure → **Resolver (Mediafire / Drive / Podomatic / Mega)**:

| Setting | Default | Notes |
| --- | --- | --- |
| `resolver_service_url` | blank | Web resolver base, e.g. `http://192.168.1.179:8097`, a Tailscale name, or `https://rave.example/resolver`. Blank = in-process only (Mediafire/Drive still work; Mega/Podomatic pages need a service). |
| `resolver_service_token` | blank | `Authorization: Bearer`; masked; preferred. Web `RAVEWEB_RESOLVER_TOKEN`. |
| `resolver_service_cookie` | blank | `raveplayer_session=...` or a bare value; masked; temporary cookie mode for web builds without the token. Bearer wins if both are set. |
| `resolver_enable_mega` | false | Mega is rejected locally when off. |

The module's `resources/settings.xml` still documents the same ids plus
timeouts/cache for standalone use. The plugin passes its own add-on object to
`resolver.settings.Settings`, so plugin settings win and appear in the normal
Configure dialog. Tokens, cookies and signed URLs are never logged.

## 6. Tests

New `test/test_resolver_wiring.py` covers:

- direct/unknown pass-through without a resolver import;
- provider selection for all four pages;
- header suffix construction (Mediafire Referer);
- Drive/Podomatic direct results;
- Mega signed stream: absolute URL, reverse-proxy prefix, headerless;
- ciphertext refusal, foreign-host refusal, wrong-path refusal;
- quiet failures (class-only log, failed resolve);
- `play()` resolved path and Mega LAN URL;
- play-all provider pages queued as `mode=play` (raw page/ciphertext never
  enqueued), absolute offsets, bridge host still wrapped;
- download predicate/plan/download route for resolver sources, including
  `allow_private` and the exact extra host;
- plugin↔module manifest dependency and the four plugin settings.

Run:

```sh
python3 -m unittest discover -s test           # full suite, twice
python3 -m unittest test.test_resolver_wiring -v
```

The suite is offline (DNS/HTTP/resolver injected).

## 7. Build and repo

```sh
./scripts/build.sh
./scripts/build-repo.sh
./scripts/check-repo-artifacts.sh
```

`build-repo.sh` regenerates `repo/` with four add-ons
(`plugin.audio.raveplayer`, `script.raveplayer.ui`,
`script.module.raveresolver`, `repository.raveplayer`) and the catalogue
`addons.xml`/`addons.xml.md5`. `check-repo-artifacts.sh` now also asserts the
plugin's module dependency matches the module manifest.

## 8. Combining with `perf/3.9.52`

The perf branch and this branch both touch `resources/lib/routes.py` in the
playback area, so expect conflicts in `play()` / `_play_tracks()` (and possibly
`downloads.py`/`settings.xml`). Do not merge generated `repo/` zips by hand.

Recommended order (perf reviewed first):

```sh
# on the perf branch / its integration branch
git merge --no-ff feat/resolver-integration-3.9.53
# resolve source conflicts:
#   - keep perf's cache/stale-cache/back behaviour verbatim;
#   - keep this branch's provider classification, _resolve_stream() and the
#     per-track provider wrapper in _play_tracks();
#   - keep the resolver settings + addon.xml dependency.
./scripts/build-repo.sh
./scripts/check-repo-artifacts.sh
python3 -m unittest discover -s test           # twice
```

If perf lands first on `main`, instead rebase this branch onto the new main and
re-run the same build/tests. Either way the final combined version must be a
single new version number (3.9.54 if perf ships as 3.9.52/3.9.53), and `repo/`
must be regenerated after the merge — never keep either branch's committed
zips.

Potential semantic overlaps to check in review:

- perf may change `_playable_url`/cache behaviour; `_resolve_stream` must still
  call it for non-Mega results and for the final Mega native URL.
- perf may rework playlist construction; provider pages must remain `mode=play`
  wrappers, not resolved eagerly and not raw.
- perf may touch `downloads.py` size/probe paths; `allow_private` must stay
  confined to the signed Mega endpoint.

## 9. Out of scope / limitations

- No Shield/device run in this change (code and offline tests only).
- No push, tag or release.
- Mega still needs a reachable resolver service with a valid Bearer token or
  session cookie; the in-process adapter has no bundled AES client.
- A signed Mega download must finish before its token expires; re-resolve to
  start a fresh download if the web answers 401/403.
- Cookie auth is a compatibility mode and expires with the browser session.

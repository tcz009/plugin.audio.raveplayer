# Independent advisor review — Rave Player 3.9.54

**Review type:** independent, read-only. No device interaction, no code
changes, no deploy, no push, no tag.
**Repo:** `raveplayer-worktrees/release-3.9.54`, branch `release/3.9.54`.
**Basis commit:** `647abc9` (`3.9.54: release notes, doc alignment and
regenerated repo artifacts`), whose code is identical to `1510875`
(`3.9.54: resolver wiring + speed pass`). The release-docs/artifact commit
landed while this review was running; the review was re-checked against it.
`647abc9` only updates README/PUBLISHING/release notes, regenerates `repo/`
zips, and removes the stray `special:/temp/…m3u`; no `.py` changed.
**Base:** `1c0b9da` (3.9.51). **Merged branches:** `perf/3.9.52`
(`a421955`), `feat/resolver-integration-3.9.53` (`f4aeb3f`), resolver module
`1.1.0` (`98bb517`).
**Method:** static review of the full diff, controller/window/data/
paintcache/tasks/pluginbridge reading, resolver module reading, targeted
Python reproductions of two SWR defects with the repo's own test doubles, the
full test suite, artifact/zip inspection, manifest/md5 checks, and inspection
of the two device screenshots.

---

## Verdict

**SHIP** for 3.9.54.

- **No P0 and no P1 code blockers were found.** The performance pass is
  device-verified for the paths it claims (Home/Latest, Back, lazy import) and
  its changes are additive. Existing playback/download paths keep their
  previous behaviour: provider classification is host-based and no shipped
  content source emits a Mediafire/Drive/Podomatic/Mega page URL, so the new
  resolver code is effectively dormant for normal browsing.
- **The resolver half is code-only, not device-verified.** Ship it as a
  dormant/default-off capability, not as a verified feature. The release note
  already says this; keep that wording.
- **The P2 items below should be fixed in 3.9.55** (several are cheap). If the
  owner wants the headline SWR promise to be literally true on every room
  before tagging, fix P2-1/P2-2/P2-4 first; none of them can lose data or
  break playback.
- **If the release is advertised as "provider playback/downloads verified",**
  the gate changes to **NO SHIP** on evidence grounds (there is no provider
  content in the shipped catalogue and no device play test). That is a
  claims/evidence decision, not a code defect.

---

## Ranked findings

### P0 — none

No crash, data-loss, credential-exposure or payment/security defect was found
in the changed code. The paint cache is versioned and atomic, resolver
failures are quiet and fail closed, and the Mega signed-URL guard is
exact-origin.

### P1 — none that I would block the release on

The closest candidates are recorded as P2 with their probability/impact. They
are transient/UI-level or latent behind a future adapter; none is
deterministic on the shipped paths.

### P2 — should fix (ranked by user/release impact)

1. **P2-1 — Live Radio SWR signature is structurally always different, so
   every Live refresh repaints and `SAVED LIST · up to date` never appears.**
   `_live_signature()` (`script.raveplayer.ui/raveui/controller.py:52-61`)
   tries `dict(row)` on the controller's `_EntryLike` rows, which raises
   `TypeError`, then falls back to `str(row)`. That string contains the object
   address, so two identical live rows hash differently. Reproduced with the
   repo's classes: two identical `_EntryLike` rows produce different
   signatures. Impact: `_apply_refreshed_live`
   (`controller.py:1341-1363`) always takes the changed branch, clears the
   status line and repaints; the Live Radio part of the perf claim ("repaint
   only when rows changed") is false. Fix the signature to use stable fields
   (`key/label/target/fact/...` or the encoded row), add an unchanged-refresh
   test.

2. **P2-2 — a library room whose refresh returns empty/error leaves
   `UPDATING · showing saved list` on screen indefinitely.**
   `_apply_refreshed_screen()` (`controller.py:1318-1339`) returns when
   `screen.is_ready` is false without setting any status. Reproduced with an
   empty `Screen`: the status stayed `UPDATING · showing saved list` while the
   stale rows remained. This is the likely path when the last favourite is
   removed or a source returns an empty/error screen. It is not an exception,
   so `_poll_refresh`'s error branch does not cover it. Fix: set
   `PAINT_EMPTY`/`PAINT_OFFLINE` (or clear) and decide whether stale rows
   should stay; add a test.

3. **P2-3 — removing a favourite or deleting/cancelling a download paints the
   stale row again (brief resurrection).** `_reload_current()` /
   `_reload_library()` go through `_load_target`/`_run_library`, which paint
   the cached screen first and refresh second
   (`controller.py:1491-1515`, `1607-1627`, `2787-2817`). After a successful
   remove/delete, the removed row is back on screen until the background
   refresh completes (up to the 45 s timeout on a slow source). Fix: invalidate
   the affected cache entry before reload (add `PaintCache.delete(kind, target,
   page, rows)` / a `use_cache=False` flag) or clear the affected screen cache.

4. **P2-4 — cache/page refresh can move focus to the nav row or the wrong row
   on page 2+.** `_apply_refreshed_page()` computes
   `_current_index()` (which includes the `PREVIOUS PAGE` nav row on page 2+),
   then clamps to `len(page_obj.rows) - 1`
   (`controller.py:1295-1317`). If a refreshed page shrinks, the clamp can
   select the nav row; at the end of a full page the comparison is off by one.
   The same class of mismatch exists in `_apply_refreshed_screen`'s
   `_select_index(index)` after `_paint_library_screen`. Fix by restoring the
   absolute content offset (`_content_offset()`/`_restore_offset()`) as
   `_reload_current` already does, or by computing the nav offset explicitly.

5. **P2-5 — cache key/value can disagree on the page number when a source
   clamps an out-of-range page, which then makes the refresh matcher drop the
   result.** `_store_page(target, page, page_obj)` stores under the requested
   `page` but the value can carry a clamped `page_obj.page`
   (`controller.py:1148-1158`). On the next open, `_apply_page` sets
   `self._page` from the value, while `_start_refresh`'s `matches` predicate
   requires `self._page == page` (`controller.py:1389-1394`), so the refresh
   is discarded. This is reachable from a stale `NEXT PAGE` row after the
   source loses a page. Fix: store the page actually painted, or match on the
   target/navigation token rather than the integer.

6. **P2-6 — lazy import has an unsynchronised first-load race.**
   `pluginbridge.load_plugin()` (`script.raveplayer.ui/raveui/pluginbridge.py:
   170-197`) checks/repairs/installs the alias and `_CACHE` without the
   `_IMPORT_LOCK` that `_PluginNamespace._module` uses. The new idle prefetch
   thread (`controller.py:1086-1118`) can call `data.modules` at the same
   moment the GUI opens a room; both can run `_install_alias`/`_clear_alias`,
   producing duplicate package/module objects or a transient
   `PluginUnavailable` (empty plate, retryable). Probability is small (2 s
   prefetch window, import window of a few ms) but it is a new concurrency path
   introduced by this release. Fix: wrap the body of `load_plugin` in
   `_IMPORT_LOCK` (or a dedicated load lock).

7. **P2-7 — provider page URLs that already carry a Kodi `|Header=` suffix
   fail to resolve.** `_resolve_stream()` (`resources/lib/routes.py:2779-2810`)
   passes the raw value to the resolver. `MediafireAdapter.clean_page_url`
   then treats `|Referer=…` as part of the page path and fetches a 404;
   reproduced with the repo's `FakeResolver`: plain URL resolves, same URL
   with `|Referer=…` returns `""` and calls the resolver with the suffix.
   Current sources do not emit provider pages, so this is latent; strip the
   suffix before provider resolution and re-attach only the resolved result's
   headers.

8. **P2-8 — a resolved non-Mega URL containing `|` can smuggle Kodi protocol
   options/headers.** `Resolution.kodi_url()`
   (`script.module.raveresolver/resources/lib/resolver/base.py:166-188`)
   appends `|Header=…` but never rejects a `|` already present in
   `self.url`; `policy.check_url` permits `|` in the path/query. Kodi parses
   the first `|` as the option boundary, so a service- or provider-supplied URL
   such as `https://cdn.example/a.mp3|Cookie=…` would become media URL
   `https://cdn.example/a.mp3` plus a Kodi option. The service is
   operator-configured and its auth headers are filtered, so this is
   hardening rather than a demonstrated credential leak, but the resolver
   contract should reject `|` (and control characters) in resolved URLs before
   building a Kodi path. Same check belongs in `_resolve_stream` for the
   non-Mega result.

9. **P2-9 — the "no ciphertext fallback" rule is enforced for
   `source == "service"` but not for a future in-process Mega adapter or a
   service that labels its answer differently.** `_resolve_stream` sends any
   Mega result whose `source != "service"` through `_playable_url`
   (`routes.py:2800-2809`). `mega.py`'s native seam returns a "signed CDN URL"
   (`mega.py:129-149`), which in Mega's protocol is still AES-CTR ciphertext;
   the wiring test explicitly accepts that URL
   (`test/test_resolver_wiring.py::test_native_mega_result_still_uses_the_public_guard`).
   No native adapter is bundled in 1.1.0, so this is latent, but the test
   encodes the unsafe behaviour. Also, `ServiceClient._source_name` trusts a
   service's `source` field (`service.py:303-309`); a response with
   `source: "service"` and a ciphertext `url` (no `stream`) would bypass
   `_mega_resolution`'s fail-closed branch. Fix: for a requested `provider ==
   "mega"`, require `stream` regardless of the echoed source, reject
   `*.userstorage.mega.co.nz`/ciphertext hosts in `_resolve_stream`, and change
   the native test to assert a playable/decrypted URL, not merely a public one.

10. **P2-10 — resolver downloads assume HEAD works and a narrow CDN
    allowlist.** `downloads.plan` relies on `http.probe_media`'s HEAD-only
    probe (`downloads.py:302-330`, `http.py:946-1000`); there is no
    Range-GET fallback unlike the Drive adapter itself. Mediafire signed
    links, Podomatic CDNs and the signed Mega proxy are untested on device; a
    405/403 HEAD makes the download unavailable even when GET would work.
    `ALLOWED_SOURCES["Rave Resolver"]` (`downloads.py:46-50`) also only lists
    `mediafire.com`, Google hosts, `podomatic.com`, `mega.nz/.co.nz`; a
    service-resolved Podomatic file on another CDN host would play but not
    download. Add a HEAD→Range-GET fallback (or make the probe use the same
    Range request as Drive) and either widen the resolver source to the exact
    resolved host or document the restriction.

11. **P2-11 — the screen cannot download resolver results; only the plugin
    Classic lists can.** `PluginBackend.download_plan` calls
    `downloads.plan(url, title, source)` with no resolver
    (`script.raveplayer.ui/raveui/screens/library.py:582-586`,
    `1007-1070`), and `RaveData.start_download` passes the raw track URL
    (`data.py:1070-1085`). Provider page rows are therefore not offered as
    downloadable in the primary UI (their `downloadable` flag is false), while
    the plugin's `_download_context` does offer them and
    `download_start` resolves (`routes.py:2039-2055`, `2461-2505`). This is
    inconsistent rather than unsafe; add resolver resolution to the screen
    queue or explicitly document the screen/Classic split.

12. **P2-12 — an invalid `resolver_service_url` disables even in-process
    Mediafire/Drive.** `ServiceClient.from_settings` constructs
    `endpoint()` in `Resolver.__init__`; a malformed URL raises before any
    adapter is built, so `routes._resolver()` catches, sets
    `_RESOLVER_IMPORT_FAILED`, and provider pages fail (the log says the module
    is unavailable). `routes.py:2701-2717`. Fix: treat an invalid service URL
    as "service off" (log once, build in-process adapters) rather than
    poisoning the whole resolver. Related: the resolver module's own
    `resources/settings.xml` duplicates the four plugin settings, but the
    wiring binds `Settings(addon=kodi.ADDON)` to the **plugin**
    (`routes.py:2713`, `settings.py:33-48`), so module-side settings are
    ignored; either remove the duplication or make the effective source
    explicit.

13. **P2-13 — the resolver is not reachable from any shipped content source,
    so its end-to-end path is unverified.** A repo-wide scan found provider
    hosts only in `resources/lib/routes.py`, `resources/lib/downloads.py`,
    `resources/settings.xml` and the resolver tests — not in `latest.py`,
    `legacy.py`, `feeds.py`, `toronto.py`, `moxser.py`, `hardscore.py`,
    `dnbradio.py`, `pirate.py` or `archive.py`. `legacy._music_url` restricts
    RTP references to `/music/<pack>/<file>.mp3` on RaveTapePacks
    (`legacy.py:143-190`); feed enclosures are passed through as direct URLs
    (`feeds.py:101-140`). A provider page is therefore reachable only via a
    saved favourite/deep link or a future source. Do not present provider
    playback/downloads as a working catalogue feature in the release notes;
    add a real source (or a device fixture) before claiming it. This also means
    the new code cannot regress existing browsing, which lowers the ship risk.

14. **P2-14 — the perf table contains comparisons that do not support their
    labels.** `docs/PERF-3.9.52.md` is credible in direction and has two real
    screenshots, but: "Plugin Latest fallback 729 ms warm → median 787 ms (no
    regression)" is a 58 ms regression by the table's own numbers; "RTP
    category page 469–2524 ms (plugin route) → 153 ms first" compares a plugin
    route against a screen-room paint; the external app-launch after range
    (0.99–1.57 s) overlaps the before range (1.19–1.33 s), so only the internal
    first-paint number is a clear win; "Live Radio 52 ms warm / 6.3 s first"
    is a 6.3 s **GUI-blocking** first open; and the cache/prune disk work and
    the new resolver cold path are not in the table. State these as directional
    owner measurements, not as a complete before/after benchmark.

15. **P2-15 — Instant Back reduced retries from 12 to 2; the no-relaunch edge
    is now less covered.** `RaveScreenWindow.close()` fires
    `ActivateWindow(Home)` once, polls 200 ms, retries once for 300 ms, then
    closes regardless (`window.py:582-650`). The old loop kept retrying for up
    to 2.4 s specifically because Kodi can refuse the activation while a modal
    is up; the new path is faster and device-measured at 28–79 ms, but if both
    attempts are refused it closes from under an unknown window and the plugin
    launcher can relaunch. The tests only mock `getCurrentWindowId` and
    `executebuiltin` (`test_rave_screen.py:2718-2745`); they do not exercise a
    real modal/relaunch. Consider a third bounded attempt (or a modal-aware
    retry) before declaring "one Back" robust, and re-test the modal edge on
    the device.

16. **P2-16 — cache lifecycle has no read-time age check and no byte budget.**
    `PaintCache.load` (`paintcache.py:370-392`) does not inspect the stored
    `ts`; `MAX_AGE_SECONDS` is only applied by `prune`, which runs every 16
    writes (`paintcache.py:435-477`). An untouched entry older than 30 days can
    still paint until some write triggers pruning; 240 entries × up to 4 MiB is
    a theoretical ~960 MiB (realistic pages are much smaller); search queries
    are cached per query and can evict room pages. Add a read-time age check, a
    total-byte cap, and consider not caching search results (or capping distinct
    queries).

17. **P2-17 — the cache is not always fail-soft on the encode side.**
    `_store_page`/`_store_screen` (`controller.py:1148-1184`) call
    `encode_page`/`encode_library_screen` outside a `try`; a malformed `Page`
    (non-numeric `total`, etc.) raises `ValueError` and aborts the room load.
    Reproduced with `Page(total="oops")`. Normal data is well-typed, so this is
    defensive only, but the module's own rule is that the cache must never
    break a load. Wrap the encode call as well as the store.

18. **P2-18 — lazy import repairs the plugin `kodi` context incompletely.**
    `_bind_addon_context` (`pluginbridge.py:92-104`) fixes `ADDON`,
    `ADDON_PATH`, `ADDON_ID/NAME/VERSION`, `ICON`, `FANART`, but not
    `kodi.ROUND_FACE`, which is computed at import from the wrong (`script`)
    add-on path (`resources/lib/kodi.py:19`); `notify(..., icon=ICON)` also
    captures `ICON` as a default argument at definition time
    (`kodi.py:82`). Any plugin data module loaded by the screen that uses those
    gets the screen's art/icon. Cosmetic only, but it undermines the stated
    "bind the add-on context before modules cache constants" guarantee. Set
    `ROUND_FACE` in `_bind_addon_context` and avoid the `ICON` default
    argument.

19. **P2-19 — prefetch is not cancelled by D-pad focus movement.**
    `_prefetch_worker` stops on `_user_active`, but `on_focus` does not set it
    (`controller.py:306-323`), so a user who starts browsing Home with the
    remote after the 2 s grace can have the prefetch fetch Latest/RTP
    concurrently with the room they open. The prefetch checks `_busy`/`_refresh`
    between items, so it is bounded, but an in-flight fetch is not cancellable.
    Set `_user_active` in `on_focus` (or cancel on any action) and consider a
    single in-flight prefetch target.

20. **P2-20 — the resolver service base can be a metadata/loopback address.**
    `resolver.service.endpoint()` accepts any http(s) host
    (`service.py:67-88`) and `ServiceClient` deliberately requests with
    `allow_private=True` (`service.py:176-195`). The setting is
    operator-controlled, but a bad/imported setting could point at
    `169.254.169.254` or loopback. The provider-page policy correctly refuses
    private addresses; the service base is the one deliberate exception.
    Refuse link-local/metadata and consider requiring the operator to opt in to
    non-RFC1918/Tailscale hosts.

21. **P2-21 — resolver URL cache has no pruning.** `resolver/cache.py` has
    `get/put/delete/clear` but no entry cap or age sweep. Expired entries are
    only removed when read; distinct Mediafire/Drive URLs accumulate in
    `special://temp/raveresolver`. Each file is small, but this is unbounded
    over time. Add a periodic prune (count/age) like the plugin's own cache.

### P3 — nits / documentation

- `ImmediateTask` is imported into `controller.py:48` but unused; `_refresh_seq`
  is written but never checked; `RaveData.plugin_version()` is unused.
- The instant-Back changelog says "at most ~200 ms"; the code can wait
  200 ms + 300 ms plus `Dialog.Close`/worker spawn. Say "≤ ~500 ms worst
  case".
- `docs/KODI-RESOLVER.md` still says "no changes to `resources/lib/routes.py`
  yet" and shows the old `Resolver()`/`needs_resolution` snippet; it is
  contradicted by `docs/KODI-RESOLVER-WIRING-3.9.53.md` and the actual code.
  Add a "superseded by 3.9.53" banner or update it.
- `docs/RELEASE-3.9.54.md` says the screen "pins the plugin exactly"; Kodi
  treats `<import version>` as a minimum, not an exact pin. The pair is still
  validated by the repo/CI, so this is wording only.
- `docs/RELEASE-3.9.54.md` §4 discloses that `.git-auth/` contains an SSH key
  and a 64-hex resolver token. It is outside the repo and no value is printed,
  but naming the secret location in a tracked public document is avoidable.
- The screen `README-library.md`/`README-live.md` docs still ship inside the
  screen zip (already noted in the release doc).
- `docs/PERF-3.9.52.md` says old keys are pruned "by age/size"; the code prunes
  by age and entry count, not byte size.
- `script.raveplayer.ui/changelog.txt` keeps the perf items under a
  `3.9.51` heading (the branch's screen version) while the merged release is
  3.9.54; add a short 3.9.54 summary or a "merged from 3.9.51" note.

---

## 1. SWR paint cache — correctness and risk

**What is right**

- Key includes `SCHEMA`, screen version, plugin version, kind, target
  identity, page and rows-per-page (`paintcache.py:36-95`); a version bump
  produces a different key and a guaranteed miss
  (`test_rave_screen.py::PaintCacheDiskTests`).
- `target_key` distinguishes an `Entry` by kind/source/target/key, so the same
  pack in Latest and an RTP category cannot collide (`paintcache.py:77-88`).
- Writes are temp-file + `os.replace` (`paintcache.py:393-412`); corrupt,
  oversized and wrong-schema entries are removed and treated as misses
  (`paintcache.py:370-392`). JSON serialisation errors become a failed write,
  not a room failure.
- Cache hits paint the last page, start a daemon `BackgroundTask`, and apply
  only on the GUI thread in `tick()` (`controller.py:1261-1293`,
  `1952-1961`). Back cancels the refresh without waiting
  (`controller.py:414-423`), and the old task's result is never applied.
- A changed page repaints; an unchanged page only updates the status
  (`controller.py:1295-1339`).
- Empty/error results are not stored (`_store_page` requires rows,
  `_store_screen` requires `is_ready`), so a transient hiccup cannot poison
  the cache.
- Page/folder/search/favourites/downloads/About/live all have cache keys;
  Search keys are normalised query + page.

**What is wrong / risky**

- **Live signature (P2-1)**: confirmed reproducible; defeats change detection
  for the one room that is refreshed on every open.
- **Library non-ready status (P2-2)**: confirmed; stale `UPDATING` line.
- **Destructive action flashback (P2-3)**: stale row returns until refresh.
- **Page/focus mismatch (P2-4/P2-5)**: page-2 nav row and out-of-range page
  clamp; cosmetic/refresh-drop, not corruption.
- **Growth/age (P2-16)**: 240 entries, 30-day prune, no read-time age, no byte
  cap, search entries compete with rooms. The directory is bounded in count,
  so this is a hygiene issue rather than a disk-filling bug in normal use.
- **Malformed page (P2-17)**: encode outside try; defensive gap.
- **Version invalidation**: correct, but old-version entries are only removed
  by prune. That is acceptable: the new key misses, so no stale rows paint.
- **Stale source data**: a source that is permanently empty leaves the last
  page painted with `SOURCE EMPTY · showing saved list`; tapping those rows
  fails. This is a deliberate SWR trade-off but should be documented; the
  release note should not promise "the list always reflects the source".
- **Threading**: all control mutations remain on the GUI thread; the
  `_on_runner_poll` and `_advance_loading_frame` guards keep background
  callers inert (`controller.py:2142-2174`). The only new concurrency is the
  prefetch's plugin-module import (P2-6) and an in-flight refresh continuing
  after Back/away (result discarded). No GUI-violation was found.

**Pagination/folder pages**: each page is cached independently and the nav
rows are rebuilt from `page`/`has_next`; Back restores a frame rather than
re-fetching. The only defects are the focus clamp and the key/page mismatch
above.

**Search/favourites/downloads**: the library cache path is correct in shape,
but it has no tests, and destructive reloads paint stale data first (P2-3).
Downloads progress rows can also be stale for the refresh window; the queue's
own progress path is separate.

## 2. Lazy imports and prefetch

**Lifecycle**: `load_plugin` imports only `plugin.kodi`, binds its add-on
context, then lets `_PluginNamespace._module` lazily import the rest under
`_IMPORT_LOCK` (`pluginbridge.py:131-197`). The namespace is cached per plugin
root. This is the right shape for Kodi (fresh interpreter per call) and for
the screen's resident interpreter.

**Lock**: per-module import is locked; the top-level `load_plugin` is not
(P2-6). The prefetch thread is the new second caller and makes this reachable
at startup.

**Add-on context**: `_bind_addon_context` correctly runs before any data module
can capture `ui.DEFAULT_FANART`, and it repairs the settings/profile add-on
object used by `cache.py`/`favourites.py`. `ROUND_FACE` and `notify`'s default
icon are not repaired (P2-18), but they are art-only.

**Thread cancellation**: the prefetch cancels on click/back/context/plate and
between items; it cannot abort an in-flight network call and does not observe
D-pad focus (P2-19). That is bounded and acceptable for a warm-up, but the
"stops the moment the user acts" claim is slightly stronger than the code.

**Kodi 22 compatibility**: the lazy alias uses `sys.modules`/`ModuleType`,
which is interpreter-level and version-independent; `xbmcvfs.translatePath`,
`xbmc.sleep`, `xbmc.Monitor`, `xbmcgui.getCurrentWindowId` and
`xbmc.getCondVisibility` are all present on the supported 20–22 range. The
resolver/screen code stays Python 3.9-compatible (no `removeprefix`, no match
statements). No K22-specific API was introduced.

**Startup failure modes**: missing/disabled plugin -> `PluginUnavailable`,
Home still paints with script art, rooms become empty/error plates and the
surprise picker fails softly. Missing resolver module -> `_resolver()` returns
`None`, provider pages fail quietly, direct playback/downloads unchanged.
Malformed resolver service URL is the exception (P2-12).

## 3. Instant Back

**Lifecycle**: `close()` sets `_closed`, calls controller `shutdown()`, hands
an active download queue to the headless worker, closes dialogs, activates
Home once, polls 25 ms for up to 200 ms, retries once for 300 ms, then calls
`super().close()` and releases the instance lock in `open_screen`'s `finally`
(`window.py:582-650`, `812-903`). One Back -> one close; a second Back during
close is a no-op (`_closed` guard). The instance marker is PID-checked and
touched while the window lives, so a second launch focuses/refuses rather than
stacking.

**Risks**: the two-attempt Home fallback is the only material behavioural
change versus the 12-attempt loop; a refused activation in a modal/busy GUI is
the edge that the old loop covered. The device measurement (28–79 ms) is
credible for the normal path, but the tests mock the window APIs and do not
prove the modal/relaunch edge (P2-15). No zombie window was evident in the
code; the `_cleanup` distinction for never-initialised windows is preserved.

**Home fallback**: `_current_window_id()` returning `None` (API unavailable)
skips the wait and closes immediately; that is the old fallback behaviour and
is acceptable. The 200/300 ms bounds are documented and now honest except for
the "~200 ms" changelog phrase.

## 4. Resolver wiring

**Verified good**

- `_provider_for` is a local host check; no resolver import or cache on a
  directory render (`routes.py:2730-2747`).
- `play()` resolves exactly once (`_resolve_stream`, `routes.py:2913-2934`);
  direct/unknown URLs keep the old `_playable_url` path.
- Non-Mega results use `Resolution.kodi_url()` with `|Header=`; I checked
  Kodi's `CUrlOptions::AddOptions`, which splits on `&` and then
  `CURL::Decode`s each option key/value, so the module's percent-encoding is
  the correct way to prevent header smuggling
  ([Kodi source](https://github.com/xbmc/xbmc/blob/master/xbmc/utils/UrlOptions.cpp)).
- Mega service results return only the absolute signed URL, with no headers;
  `_is_service_stream` requires http(s), no userinfo, no `|`/fragment, exact
  scheme+netloc and exactly `<prefix>/api/mega/stream`
  (`routes.py:2749-2777`). Tests cover LAN, reverse-proxy prefix, foreign
  host, wrong path, and ciphertext rejection.
- `ServiceClient._mega_resolution` fails closed if `stream` is missing and
  never returns the storage `url` (`service.py:243-261`).
- Play-all wraps provider pages as `mode=play` and leaves direct/bridge hosts
  on their old path; offsets and track numbers are preserved
  (`routes.py:645-710`; tests).
- Downloads resolve before planning, set `source="Rave Resolver"`, use
  `allow_private` only after `_is_service_stream`, and confine private
  redirects to the same origin (`routes.py:2461-2505`, `downloads.py:152-190`,
  `http.py:879-1000`). `plan` keeps the 500 MiB/2 GiB/free-space/Content-Type
  checks and `download` keeps the atomic rename and Content-Length check.
- Settings defaults are blank/off and hidden token/cookie; tests assert the
  manifest dependency and the plugin-side settings.
- Failure logging is provider + exception class; no URL/token/cookie/signed
  stream is logged in the resolver paths I reviewed.

**Findings**: provider header suffix (P2-7), pipe/option injection (P2-8),
native/source ciphertext gap (P2-9), HEAD-only downloads and allowlist
(P2-10), screen/Classic asymmetry (P2-11), invalid service URL (P2-12),
dormant/no source (P2-13), service private base (P2-20), resolver cache
unbounded (P2-21). Also note the tuning spinner's 25 s timeout
(`spinner.py:38-39`) can expire during a 25 s service resolve or a two-probe
Drive resolve, after which `_tuning_aborted` fails the playback even though
the resolve eventually succeeded; a first provider play on a slow service can
therefore fail and only the retry (now cached for Mediafire/Drive) succeed.
That path is unmeasured and should be part of the device check.

## 5. Repo and release hygiene

At `647abc9`:

- `addon.xml` plugin 3.9.54 requires `script.module.raveresolver` 1.1.0;
  screen 3.9.54 requires plugin 3.9.54; module 1.1.0. Changelogs, root README,
  screen README and PUBLISHING all say 3.9.54/1.1.0.
- `repo/addons.xml` has four addons, md5 matches, `check-repo-artifacts.sh`
  passes, and all four zips are tracked. `dist/` and `repo/` copies are
  byte-identical. Zip manifests match filenames; the plugin zip contains
  `_resolve_stream`; no `test/`, `__pycache__`, `.pyc`, `.DS_Store` or scratch
  files are inside.
- The stray `special:/temp/raveplayer-live-7620df74c1b70356.m3u` (a Kool FM
  test playlist accidentally committed in 3.9.24) was removed in `647abc9`;
  `git status` is clean.
- 1128 tests pass locally (23.4 s, Python 3.9.6); CI is Python 3.12. No
  `print()`/`pdb`/`TODO`/`FIXME` debug code in the shipped Python.
- No credential value is tracked. `.git-auth/` is outside the repo; the
  release doc names it (P3 wording issue). No old local IP/ADB path reappeared.
- No tag `v3.9.54`; `origin/main` is still `1c0b9da`; `HEAD` is a fast-forward
  descendant. Release doc explicitly says prepared, not released.

**Gaps**: test coverage for library/live SWR, cache prune/age, destructive
invalidation, prefetch races, Kodi header decoding on a real player, download
HEAD fallbacks and any Mega audio fixture. The release doc already flags the
resolver and mobile/device gaps; add the SWR library/live tests.

## 6. Performance evidence

**Credible in direction**

- Two real Shield screenshots (`docs/perf-3.9.52/home.png`,
  `latest-painted.png`), the second showing the `SAVED LIST · up to date`
  status on Latest with 100 items / page 1 of 2 and 100 rows.
- The lazy-import claim is structurally right: `load_plugin()` imports one
  module instead of twenty; the local harness here (different machine/Python)
  measured ~153 ms first load and 177 ms for the first `latest` import, so the
  absolute Shield numbers are not directly reproducible but the module-count
  and direction are.
- Paint-cache warm opens in the 91–126 ms range for a 50-row page are
  plausible; Back 28–79 ms versus a 12×200 ms loop is a real structural win;
  instant Back is 2 attempts worst case.

**Not credible as a complete benchmark**

- "Plugin Latest fallback 729 ms warm → median 787 ms (no regression)" is a
  regression by the numbers; no statistic or sample is given.
- "RTP category page 469–2524 ms (plugin route) → 153 ms first" compares a
  plugin route to a screen room; the "first" values also mix cached and
  uncached runs across rows.
- App launch external before 1.19–1.33 s vs after 0.99–1.57 s: the ranges
  overlap and the high end is worse; only the script-internal first paint is a
  clear improvement.
- Live Radio's first open remains a 6.3 s synchronous `load_stations` on the
  GUI thread; the cache only helps subsequent opens. That is in the ">1 s"
  list but is a poor first-run experience.
- Plugin search still times out (>90 s); pre-existing, documented, not fixed.
- New cold provider playback/download is not in the table: Mediafire can
  take 25 s + 1.2 s gap, Drive up to two 25 s probes, service 25 s, versus the
  spinner's 25 s timeout. This is a new path, not a regression of an existing
  one, but it is the one most likely to exceed 1 s.
- No bench script/logs are committed for the screen numbers; they are
  owner-reported and should be labelled as such. The screenshots corroborate
  the two headline claims.

**Regression answer:** no measured existing path regressed by more than 1 s.
The only new >1 s path is cold resolver playback/download (by design/unbounded
up to resolver timeout); first Live Radio (6.3 s) and plugin search (>90 s) are
pre-existing. Cache read/write/prune hitches and prefetch contention are
unmeasured; they should be millisecond-scale for a 50-row page.

## 7. Required fixes / recommended actions

**Before the tag (cheap, low risk; not blockers)**

1. P2-1 Live signature: build it from stable fields; add an unchanged-refresh
   test.
2. P2-2 library empty/error status: set a terminal status; add a test.
3. P2-6 `load_plugin` lock: one lock around the body; no behaviour change.
4. P2-8 reject `|`/control characters in resolved non-Mega URLs and in
   `kodi_url`.
5. Re-run `python3 -m unittest discover -s test` and
   `./scripts/check-repo-artifacts.sh`, then rebuild `repo/` if any change
   (zips/hashes change).

**Before/with the release notes**

6. Keep the resolver labelled **code-only, not device-verified**, and add:
   no shipped source emits provider pages; Mega/Podomatic need a configured
   service; provider downloads are untested on device; screen downloads do not
   use the resolver.
7. Fix the P2-14 perf-table claims (787 vs 729, plugin-vs-screen RTP row,
   external launch ranges, Live Radio 6.3 s, new resolver latency).
8. Fix the P3 doc contradictions (`KODI-RESOLVER.md`, "~200 ms", "exact pin",
   `.git-auth` location, age/size pruning, screen changelog heading).

**3.9.55**

9. P2-3 destructive reload invalidation; P2-4/5 offset/page matching;
   P2-10 HEAD→Range fallback and resolver download host handling; P2-11 screen
   downloads; P2-12 invalid-service handling and module-settings cleanup;
   P2-16 cache age/byte cap; P2-17 encode guard; P2-18 ROUND_FACE/notify;
   P2-19 focus cancellation; P2-20 service-base guard; P2-21 resolver cache
   pruning.

## 8. Untested / not verifiable in this review

- **Device playback of any resolver provider** (Mediafire, Drive, Podomatic,
  Mega) and resolver downloads. No device was used; the code is unit-tested
  against fakes only. The release doc itself marks this post-release.
- **Mega audio**: no real fixture; only URL shape, origin guard, no-ciphertext
  and no-header tests. The in-process native adapter is not bundled.
- **Podomatic page resolution** requires the NAS service; no service available
  here.
- **Paint cache on library rooms, Search, Favourites, Downloads and Live
  Radio** on device; only the page cache is covered by SWR tests and only
  Latest/Home are screenshotted.
- **Kodi 20/21**; device is Kodi 22 beta. CI is Python 3.12 but not Kodi.
- **Header decoding on the player**: verified against Kodi's option parser
  source, not on the Shield.
- **Download HEAD behaviour** of Mediafire/Drive/Podomatic/Mega endpoints;
  no network from this review.
- **Instant Back modal/relaunch edge**; tests mock the window id/builtin.
- **Long-duration cache growth** (30 days, 240 entries) and prefetch/prune
  hitches.
- **Plugin fallback lists** (Classic lists) are not row-cached, still pay
  Kodi's Python process start and source fetch; plugin search >90 s remains.
- **Resident UI** is deliberately deferred; first paint is ~0.56–0.63 s
  internal, ~1.0–1.6 s external per the owner's measurements.

## 9. Verification performed

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `647abc9` (code same as `1510875`) |
| Merge completeness | `1510875` contains both parents' changes; no lost resolver/perf hunks |
| Full suite | **1128 tests, OK** in 23.4 s (Python 3.9.6) |
| `scripts/check-repo-artifacts.sh` | pass, dependency 1.1.0 |
| `repo/addons.xml` md5 | `1cb691a4…fd6` matches `repo/addons.xml.md5` |
| Four repo zips | present, tracked, manifests match, no test/bytecode/scratch |
| dist vs repo | byte-identical for plugin/screen/module |
| `repo` hashes | match `docs/RELEASE-3.9.54.md` §4 |
| Tags / remote | no `v3.9.54`; `origin/main` at `1c0b9da`; no push |
| Debug/secret scan | no `print`/`pdb`/`TODO`; no tracked credential values |
| Targeted reproduction | Live signature always differs; empty-screen refresh leaves `UPDATING`; suffixed provider URL fails; `Page(total="oops")` raises in `_store_page` |

---

*This review is read-only. It did not modify code, build artifacts, device
state, git refs or the repository catalogue. The only file written is this
report.*

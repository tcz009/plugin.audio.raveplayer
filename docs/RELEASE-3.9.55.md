# Release 3.9.55 — advisor pre-release fixes

**Status:** release **prepared, not released**. Branch `fix/3.9.55` is local
only; `main`, the tags and the GitHub release are untouched. Nothing was
pushed, deployed or run on a device in this pass.

**Prepared:** 9 November 2026 · **Branch:** `fix/3.9.55`
**Base:** `release/3.9.54` @ `647abc9` (`3.9.54: release notes, doc alignment
and regenerated repo artifacts`).
**Scope:** the five cheap pre-release fixes requested from the 3.9.54 advisor
review (P2-1, P2-2, P2-6, P2-7/P2-8 and P2-15) plus the
version/changelog/artifact updates they require. The review report lives on the
release worktree as `docs/ADVISOR-REVIEW-3.9.54.md`; it is not part of this
branch. No other advisor P2 was attempted.

---

## 1. Versions

| Artifact | Version | Requires / notes |
|---|---|---|
| `plugin.audio.raveplayer` (`addon.xml`) | **3.9.55** | `xbmc.python` 3.0.1, `script.module.raveresolver` 1.1.0 |
| `script.raveplayer.ui` (`script.raveplayer.ui/addon.xml`) | **3.9.55** | `xbmc.python` 3.0.0, `plugin.audio.raveplayer` **3.9.55** |
| `script.module.raveresolver` | **1.1.0** | unchanged code and contract; rebuilt only because `repo/` is regenerated |
| `repository.raveplayer` | 1.0.0 | unchanged |
| `repo/addons.xml` | 3.9.55 / 3.9.55 / 1.1.0 / 1.0.0 | 4 entries; md5 `da29f0ce0bfffe61ff825571bf55bd84` |

The screen's `<import version>` is Kodi's minimum, not an exact pin; the
repository still installs the pair together.

---

## 2. What ships

### P2-1 — Live Radio SWR signature

`_live_signature()` (`script.raveplayer.ui/raveui/controller.py`) no longer
tries `dict()`/`str()` on the controller's `_EntryLike` rows. It builds a
stable tuple from `key`, `label`, `title`, `target`, `subtitle`, `art`, `fact`,
`code`, `kind`, `plot`, `meta` and the action's `type`/`station`/`url`. Equal
rows now produce the same digest, so an unchanged Live refresh shows
`SAVED LIST · up to date` and does not repaint (it still updates the cached
station list before comparing).

Tests: `LiveSignatureTests` (equal `_EntryLike` and dict rows sign equal;
changed fact/label differ) and `LiveRefreshTests` (a cached Live refresh with
identical stations ends in `PAINT_CURRENT`).

### P2-2 — stuck `UPDATING` on an empty/error library refresh

`_apply_refreshed_screen()` now sets a terminal status on every path where the
room is still current: `PAINT_OFFLINE` for an error `Screen`, `PAINT_EMPTY`
for an empty/non-ready one, then returns. The saved rows stay painted
(unchanged SWR trade-off). A ready-but-empty screen was already `PAINT_EMPTY`;
error/empty backgrounds previously returned silently and left
`UPDATING · showing saved list` on screen.

Tests: `test_empty_library_refresh_shows_a_terminal_status` and
`test_error_library_refresh_shows_a_terminal_status` (both seed a ready saved
screen, then refresh to an empty/error screen; the stale row and terminal
status are asserted).

### P2-6 — `load_plugin()` lock

`pluginbridge.load_plugin()` now performs the whole check/repair/install
sequence under `_IMPORT_LOCK`, the same lock `_PluginNamespace._module` uses.
The idle prefetch thread and the GUI opening the first room can no longer run
`_install_alias`/`_clear_alias` concurrently and produce duplicate package
objects or a transient `PluginUnavailable`.

Test: `test_concurrent_load_plugin_calls_install_one_alias` starts one thread
inside a deliberately blocked `_install_alias`, starts a second `load_plugin()`
caller, asserts the alias was installed once, then asserts both callers share
one namespace object.

### P2-7 / P2-8 — pipe/protocol-option hardening

- `_resolve_stream()` (`resources/lib/routes.py`) refuses a provider page that
  already contains `|` (Kodi `|Header=`/protocol options) **before** calling
  the resolver, logging the provider only. Previously the suffix became part
  of the page path and the resolve failed.
- A resolved non-Mega URL containing `|` or a control character is refused;
  the one exception is the exact configured signed Mega `/api/mega/stream`
  URL. `download_start()` applies both rules too, through the shared
  `_has_protocol_options()` / `_resolved_kodi_url()` helpers. The resolver
  module itself stays at 1.1.0: the plugin validates `result.url` before it
  calls `kodi_url()`, so the shipped SDK contract is unchanged.

Tests: `ProtocolOptionTests` (suffixed page never reaches the resolver;
resolved pipe/control URLs refused; exact signed Mega URL still returned) and
`DownloadRouteTests` (page and resolved download URLs refused).

### P2-15 — third Instant Back attempt

`RaveScreenWindow.close()` now tries the Home activation up to three bounded
times (200 ms, 300 ms, 300 ms = 800 ms worst case) instead of two. The loop
stops on the first successful switch, so the normal path is still one
activation and the device-measured 28–79 ms range is unchanged. The extra
attempt covers the modal-transition/launcher-relaunch edge the old 12-attempt
loop guarded.

Tests: `InstantBackTests` assert one activation when Home appears, two when it
appears on the second wait, and three activations with the exact
`[200, 300, 300]` wait sequence when it is refused throughout.

---

## 3. Verification in this pass

```sh
./scripts/build-repo.sh
./scripts/check-repo-artifacts.sh
python3 -m unittest discover -s test      # twice, fresh cache dirs
```

| Check | Result |
|---|---|
| Full suite (run 1) | **1141 tests, OK** |
| Full suite (run 2) | **1141 tests, OK** |
| `check-repo-artifacts.sh` | pass for plugin 3.9.55, screen 3.9.55, resolver 1.1.0 |
| `repo/addons.xml` md5 | `da29f0ce0bfffe61ff825571bf55bd84` |
| Version bump | plugin 3.9.55, screen 3.9.55, screen requires plugin 3.9.55 |
| Advisor fix count | P2-1, P2-2, P2-6, P2-7, P2-8, P2-15 closed |

`dist/` and `repo/` copies are byte-identical after the rebuild. Zip timestamps
change on every build, so a rebuild changes the hashes even with identical
contents; the hashes below describe the committed artifacts.

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `plugin.audio.raveplayer-3.9.55.zip` | 9,096,002 | `000badcc79831be805511f6c5280b111f8de5a8aba1d469360e2dd60632465b8` |
| `script.raveplayer.ui-3.9.55.zip` | 5,428,147 | `dd19dd475c57ba7cf6d339a0ee69e8acd934550e4d80cd2a2eab85b8162189b8` |
| `script.module.raveresolver-1.1.0.zip` | 310,713 | `ae172510369796ec140f4898e1eeb33d76540bc8c14bc0309f4bedfbdef438b0` |
| `repository.raveplayer-1.0.0.zip` | 853,389 | `ac6403b7e49f4357198650e316040a768760f7d3d2623172ea9f248f4a2c739f` |

---

## 4. Advisor P2 status

| Advisor item | 3.9.55 status |
|---|---|
| P2-1 Live Radio signature | **Closed** (stable fields + unchanged-refresh test) |
| P2-2 stuck `UPDATING` | **Closed** (terminal status + empty/error tests) |
| P2-3 destructive reload flashback | Open (deferred to 3.9.56) |
| P2-4 / P2-5 page/focus offset | Open |
| P2-6 `load_plugin` lock | **Closed** (lock + concurrent test) |
| P2-7 provider `|Header=` suffix | **Closed by refusal** (the advisor suggested stripping; this pass refuses the suffixed page before resolving) |
| P2-8 resolved pipe/control injection | **Closed** for non-Mega results in `_resolve_stream`/`download_start`; the exact signed Mega URL is still allowed |
| P2-9 native/source ciphertext gap | Open (latent; no native Mega adapter bundled) |
| P2-10 … P2-14, P2-16 … P2-21 | Open |

---

## 5. Not done / not verified

- No device, Shield, ADB or network run: all changes are unit-tested only.
- No web repo changes; the `Rave Player` web build is untouched.
- No push, tag or GitHub release.
- The Instant Back modal/relaunch edge still needs a real-device re-test when a
  device is next available; the new third attempt only bounds the retry.
- Live Radio/Library SWR remains untested on device; only the offline
  controller tests cover the new terminal-status and signature paths.

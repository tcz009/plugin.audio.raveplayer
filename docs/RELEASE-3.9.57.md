# Rave Player 3.9.57 — cancel/data-integrity patch

Patch over 3.9.56 for the advisor P1 findings.

## Fixes
- **Cancel never deletes another job's completion.** Auto/late cancellation
  deletes only the exact job identity (key). An explicit user cancel may also
  match the completed index row by URL, because the plugin completion key is
  `sha1(url)` while the screen queue key is `parent:md5(url)`; this is what
  makes "cancel removes its completed copy" work without letting duplicate
  auto-cancel delete a finished file.
- **Queued-cancel sidecar lifecycle.** The owner persists a terminal status and
  only then clears the sidecar; the window leaves the sidecar for the owner. A
  queued row cancelled before a worker starts is terminalized by the owner's
  drain step, so `active()` drains and retries are allowed.
- **Screen queue completed-file deletion** now uses the lazy plugin modules
  hook, so a screen cancel removes its own completed index/file.
- Regressions covered by `test/test_cancel_integrity_adversarial.py` (8 tests:
  cross-row completion survival, late finish, explicit user delete, window vs
  owner sidecar, orphaned queued cancel, lazy modules) plus the existing
  queue/screen suites (1174 total).

## Versions
- plugin 3.9.57, screen 3.9.57 (requires plugin 3.9.57), resolver 1.1.0.

## Known limits
- Cancel deletes only its own identity; duplicate rows that finished under a
  different key are intentionally left for an explicit delete.
- Resolver/provider playback remains code-only in the shipped catalogue; Mega
  requires the LAN/Tailscale resolver service and token.
- Plugin fallback lists are not row-cached; resident UI is deferred; first
  Live Radio open remains source-bound.

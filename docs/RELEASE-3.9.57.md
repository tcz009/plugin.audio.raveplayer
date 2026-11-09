# Rave Player 3.9.57 — cancel/data-integrity patch

Patch over 3.9.56 for the advisor P1 findings.

## Fixes
- **Cancel never deletes another job's completion.** Completed downloads are
  deleted by job identity (key) only, never by URL. A cancelled duplicate row
  that shares a URL with a finished row cannot remove that finished file/index.
- **Queued-cancel sidecar lifecycle.** The sidecar is cleared on owner start and
  when a terminal row loads; the inferred cancelled status is persisted, so a
  lost sidecar cannot resurrect the row and a later retry runs cleanly.
- **Screen queue completed-file deletion** now uses the lazy plugin modules
  hook, so a screen cancel removes its own completed index/file.
- Regressions covered by `test/test_cancel_integrity_adversarial.py` plus the
  existing queue/screen suites.

## Versions
- plugin 3.9.57, screen 3.9.57 (requires plugin 3.9.57), resolver 1.1.0.

## Known limits
- Cancel deletes only its own identity; duplicate rows that finished under a
  different key are intentionally left for an explicit delete.
- Resolver/provider playback remains code-only in the shipped catalogue; Mega
  requires the LAN/Tailscale resolver service and token.
- Plugin fallback lists are not row-cached; resident UI is deferred; first
  Live Radio open remains source-bound.

# Round-face fallback — 3.9.48

Kodi's player/Now Playing was showing its generic unknown-eye icon when a
playable track had no cover. The add-on now falls back to the round-face
sticker (`resources/art/icon.png`, derived from the add-on smiley logo) while
keeping genuine cover art.

- `kodi.ROUND_FACE` is the absolute add-on asset path.
- `ui.track_item()` uses it for `icon`/`thumb` only when `thumb` is empty.
- `routes.play()` uses `_safe_art(thumb, kodi.ROUND_FACE)`, so the resolved
  player item gets the same face; DNB/playlist paths use it too.
- RaveTapePacks, Toronto and Moxser track rows without a real flyer/cover pass
  the face instead of a generic/stale source sticker. Genuine HTTP(S) covers
  are unchanged.
- Tests: `test/test_round_face.py` (real art retained, no-art fallback,
  resolution evidence); full suite **524 tests OK**.

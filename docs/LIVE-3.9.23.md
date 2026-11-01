# Live radio reconnect + metadata (3.9.23)

## Kool/Rinse drop

Kodi PAPlayer does not reconnect a dropped internet stream. The Rinse proxy
stream was observed playing for ~5 minutes, then Kodi logged "Kodi is not
playing any media file" and stopped.

`resources/lib/live.py` now builds a **finite local M3U** for the two curated
live URLs (Kool FM, Rinse FM): six `#EXTINF` entries of the same resolved
stream. Kodi uses the M3U as the resolved item; a dropped entry advances to the
next one, while a user Stop stops playback and does not auto-advance. The cap
is six entries; there is no infinite loop. If the M3U cannot be written, the
route falls back to the direct stream (no reconnect) rather than failing.

The M3U filename is a SHA-1 hash of the stream URL under
`special://temp/raveplayer-live-<hash>.m3u`; no user text is used as a path.

## Fixed station metadata

The live rows now carry `live=1` and `station=<name>`; `live.station_name()`
maps Kool/Rinse and rejects the placeholder text. The M3U `#EXTINF` and the
resolved ListItem use fixed:

- title / artist: **Kool FM** or **Rinse FM**
- album: **Live radio**
- art: the live-radio icon/favicon

This keeps the placeholder ICY title from being the primary label where Kodi
honours playlist metadata. A stream-level ICY override is outside the add-on's
control; the fixed label/art is the best the plugin can set.

## Kodi 22 music InfoTag

Kodi 22 logs `Unknown Music Info Key "plot"` for every music `ListItem` that
sets `plot`. `kodi.music_info()` now sets the supported `comment` field and only
adds `plot` on Kodi <22 (compatibility). Applied to menu rows, track rows,
read-only rows, the play resolver and `_play_tracks`.

## Tests

- `test/test_live.py`: station mapping, placeholder rejection, finite M3U,
  route uses the M3U, direct fallback, non-live streams unchanged.
- `test/test_music_info.py`: Kodi 22 omits plot, Kodi 21 keeps it.
- Full suite: **417 tests OK**.

No 10-minute Shield playback was run (Kodi playback safety hold). The
reconnect state is a pure bounded-list implementation; device confirmation of
the six-entry M3U advance remains a QoL check once the owner re-enables Kodi.

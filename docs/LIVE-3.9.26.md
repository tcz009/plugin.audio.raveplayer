# Live reconnect 3.9.26 — finite direct-URL playlist

## Evidence from the Shield (Kodi 22, supervised playback; no input injected)

Observed in the active Kodi log on 2026-11-02:

- `11:12:46` Kool FM direct stream started (`PAPlayer::PrepareStream - Ready`).
- `11:16:08` the HTTP read failed:
  `CCurlFile::CReadState::FillBuffer ... Timeout was reached(28)`,
  `Process ... source read failed with -1!`.
- Kodi then ran its own `Reconnect, (re)try 1`, reopened the AAC decoder and
  reported `PAPlayer::PrepareStream - Ready` again at `11:16:14`.

So the drop is a transport/read failure, not an add-on metadata or URL
resolution failure. Kodi can recover within the current entry, but when it
gives up PAPlayer reports `Kodi is not playing any media file`. The add-on
therefore needs a finite fallback *outside* the single stream entry.

The full 10+ minute capture and final Shield acceptance remain with the owner;
no playback input was injected during this investigation.

## Design

`routes.play()` for a curated live station:

1. Calls `live.reconnect_urls(stream, station, resolver=...)`.
2. The resolver (`_resolve_live_player_url`) re-resolves through
   `radio.curated`/`radio.stream_url` **once per entry**; a failed/empty
   resolve keeps the last known direct URL.
3. Builds `xbmc.PlayList(xbmc.PLAYLIST_MUSIC)` with up to six entries, each
   carrying the fixed Kool FM/Rinse FM title, artist, album and artwork.
4. Starts it with `xbmc.Player().play(playlist)`. No local file, no
   `setResolvedUrl` playlist.

`live.reconnect_urls` is bounded to 6 (hard maximum 12), and the playlist is
finite. Kodi advances only after the current stream fails; a user Stop clears
the playlist and does not advance. There is no watchdog or background loop.
If playlist construction or `Player.play` raises, the route logs and resolves
the direct URL through the proven `setResolvedUrl` path.

## Failure modes / fallback

| Failure | Behaviour |
| --- | --- |
| Current stream read timeout | Kodi native retry, then advances to next direct URL |
| All six URLs fail | playlist ends; Kodi stops (finite, no loop) |
| URL resolver temporarily fails | last known direct URL is reused |
| Playlist construction/play raises | direct `setResolvedUrl` fallback |
| User Stop | playlist stops immediately, no auto-advance |
| Non-live item | unchanged single `setResolvedUrl` |

M3U files were removed in 3.9.25 after the Shield showed PAPlayer rejecting
them through `setResolvedUrl` (`Unable to Init Codec`); 3.9.26 does not use
them.

## Tests

`test/test_live.py` covers identity, six-entry construction, per-entry
re-resolution, cap, invalid stream, Stop, no `.m3u`/playlist-file, and direct
fallback. Full suite: **423 OK**. No device playback by the agent.

# 3.9.28 — live playlist `CCurlFile::Stat` log noise

## Evidence (Kodi 22 on the Shield, owner-supervised playback)

The repeated line is:

```
error <general>: CCurlFile::Stat - <https://admin.stream.rinse.fm/proxy/kool/stream|noshout=true> Failed: Unsupported protocol(1)
```

Observed every ~10–20 s while Kool FM continued playing. Two useful points:

1. The same `CCurlFile::Stat ... Unsupported protocol(1)` line appears in the
   3.9.25/26 log against the **clean** URL (before `|noshout=true` existed), so
   it is not newly caused by the ICY suffix; the suffix only appears in the
   logged URL.
2. The player is not failing: the same log shows the AAC decoder reopening and
   `PAPlayer::PrepareStream - Ready`; the owner reports playback works. This
   is Kodi probing/statting the current item, not an audio failure.

Kodi's file-stat path does not parse URL protocol options (`|noshout=true`) the
way the curl open path does; `noshout` is only honoured by the curl/shoutcast
decision. There is no supported `ListItem` property for it, so putting the
option only on the "URL handed to the player" is not a separate thing for a
playlist — every entry is handed to the player. Removing the suffix from
playlist entries would bring back the ICY `StreamTitle` overwrite.

## Decision

Leave playback untouched. The stat errors are harmless daemon log noise; they
do not stop the playlist, change the fixed title/artist/album/art, or bypass
`|noshout=true`. This is documented rather than worked around because the
available alternatives (InputStream add-on/proxy, `Player.updateInfoTag`
watchdog) are larger behavioural changes with device risk; they are not part of
this polish batch.

If a future Kodi fixes `Stat` option parsing, the noise disappears without an
add-on change. If Kodi drops `noshout`, the fallback is the reactive
`Player.updateInfoTag` plan from the ICY research report.

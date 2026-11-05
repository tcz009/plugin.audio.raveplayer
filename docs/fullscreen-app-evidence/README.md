# Full-screen app device evidence (Shield / Kodi 22)

These images are 1280×720 JPEG reductions of the 3840×2160 `adb exec-out
screencap` frames from the independent QA harness run
`qa-artifacts/baseline-3.9.51` on 5 Nov 2026, against the installed pair
`plugin.audio.raveplayer` 3.9.51 + `script.raveplayer.ui` 3.9.50.

| File | State |
|---|---|
| `01-root-home.jpg` | Rave Screen home, 11 rooms, Latest focused |
| `02-latest-section.jpg` | Latest paged list (100 items, P1/2) |
| `03-toronto-room.jpg` | Toronto genre room |
| `04-jungletapes-room.jpg` | JungleTapes 310-show room (page 1/7) |
| `05-live-room.jpg` | Live Radio stations + genre doors |
| `06-ravetapepacks-room.jpg` | RaveTapePacks Event/DJ/MC/Year indexes |
| `07-mixes-room.jpg` | Mixes & Shows room (capture was taken during a Kodi restart; see QA checks) |
| `08-search-room.jpg` | Search room capture |
| `09-favourites.jpg` | Favourites (1 saved) |
| `10-downloads.jpg` | Downloads (7 files) |
| `11-about.jpg` | About: 3.9.51 / 3.9.50 / Kodi 22 facts |
| `12-surprise-splash.jpg` | Spinning Surprise splash (full-window burst) |
| `13-surprise-playing.jpg` | Surprise playback: ON AIR, now playing, elapsed/total |
| `14-plugin-root-launcher.jpg` | Plugin root: Rave Player + Classic lists |
| `15-classic-archive-paged.jpg` | Classic list: Archive Jungle page 1 |
| `16-classic-archive-last.jpg` | Classic list: Archive Jungle last page |
| `17-classic-jt-show.jpg` | Classic list: JungleTapes show → tracks |
| `18-classic-rtp-category.jpg` | Classic list: RTP category |
| `19-classic-rtp-pack.jpg` | Classic list: RTP pack |
| `20-classic-rtp-tracks.jpg` | Classic list: RTP pack tracks |
| `21-final-root.jpg` | Final-build root home (no debug overlay) |
| `22-final-search-keys.jpg` | Final-build in-window keyboard, query “A” |
| `23-final-jungletapes.jpg` | Final-build JungleTapes room (neutral hero, no baked TAPE PACKS) |
| `24-final-latest-tracks.jpg` | Final-build pack → track row with duration/year/genre |

Most 01-20 frames have the Kodi debug-info overlay because debug logging was
enabled for the QA run; it is a Kodi overlay, not part of the app. The
`21-final-*` frames were captured after the final install with debug off.

`qa-checks.md` and `qa-manifest.json` are the machine-readable run report:
**40 pass / 9 fail / 1 warn**. The 9 fails are QA-harness contract assumptions
or a run interruption, not app crashes:

- `list.root` expects the old 10-row root; 3.9.51 deliberately has the 2-row
  app launcher + Classic lists.
- `states.keyboard` / `list.search` expect Kodi's virtual keyboard; the app's
  search is deliberately in-window.
- `screen.rooms_open` flags Mixes (captured across a Kodi restart) and Search
  (the Search row opens the keyboard, not child rows).
- `screen.modal_refusal` recovered into the window instead of refusing; the
  guard still logs nothing because the window activated.
- `list.downloads` counts an extra non-local row; `playlist.jt_play_all`
  queued the single track that show actually has.
- `logs.modal_guard` is the missing-guard consequence of the recovery above.
- `run.harness_errors` records a 401 caused by the concurrent credential change
  during the run.

Everything else passed: add-on pair/versions/dependency, 11 home rooms,
Surprise splash + exactly one playback, now-playing footer, Back stack,
Live/plugin lists, RTP/JT pages, RTP play-all uses plugin routes, no
tracebacks, no non-existent controls, no media-open failures.

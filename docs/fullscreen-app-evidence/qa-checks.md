# QA full-screen checks — baseline-3.9.51

**40 pass · 9 fail · 1 warn**

| Check | Result | Evidence |
|---|---|---|
| `addon.plugin.audio.raveplayer.enabled` — Add-on enabled | **PASS** | version=3.9.51 enabled=True broken=False |
| `addon.plugin.audio.raveplayer.version` — Add-on version | **PASS** | 3.9.51 |
| `addon.script.raveplayer.ui.enabled` — Add-on enabled | **PASS** | version=3.9.50 enabled=True broken=False |
| `addon.script.raveplayer.ui.version` — Add-on version | **PASS** | 3.9.50 |
| `addon.plugin.expected` — Plugin matches expected version | **PASS** | got 3.9.51 expected 3.9.51 |
| `addon.script.expected` — Rave Screen matches expected version | **PASS** | got 3.9.50 expected 3.9.50 |
| `addon.repository.enabled` — Repository enabled | **PASS** | version=1.0.0 enabled=True |
| `addon.dependency` — Rave Screen dependency satisfied | **PASS** | plugin 3.9.51 >= 3.9.51 |
| `env.kodi` — Kodi version recorded | **PASS** | Kodi 22.0 (beta) |
| `env.device` — Shield model/Android recorded | **PASS** | SHIELD Android TV Android 11 (adb 192.168.1.189:5555) |
| `run.kodi_restarts` — Every state was captured in a clean window | **PASS** | 1 observed restart(s); states across a restart: none |
| `run.harness_errors` — Harness completed without errors | **FAIL** | [{"at": "2026-11-05T16:26:36+0000", "message": "capture screen_room_ravetapepacks failed: Kodi RPC authentication failed (401): ", "traceback": "Traceback (most recent call last):\n  File \"/Users/theyid/Documents/deepseek-harness/default-workspace/raveplayer-worktrees/qa-harness/scripts/qa_fullscreen.py\", line 308, in call\n    with urllib.request.urlopen(\n  File \"/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/urllib/request.py\", line 214, in urlopen\n    return opener.open(url, data, timeout)\n  File \"/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/urllib/request.py\", line 523, in open\n    response = meth(req, response)\n  File \"/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/urllib/request.py\", line 632, in http_response\n    response = self.parent.error(\n  File \"/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/urllib/request.py\", line 561, in error\n    return self._call_chain(*args)\n  File \"/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framew |
| `states.required` — Every required state was captured | **PASS** | all present |
| `states.screenshots` — Screenshots are valid PNGs | **PASS** | checked 43 |
| `states.screen_window` — Screen states use the add-on window | **PASS** | range (13000, 13999); all inside |
| `states.music_window` — Plugin lists use Kodi's Music window | **PASS** | all 10502 |
| `states.keyboard` — Search query shows the virtual keyboard | **FAIL** | window=10502 |
| `states.modal_keyboard` — Modal test held the keyboard open | **PASS** | window=10103 |
| `screen.home_rows` — Home screen exposes its rooms | **PASS** | 11 rooms: Latest, Toronto Rave Mixtape Archive, JungleTapes.com, RaveTapePacks.com, Live Radio, Mixes & Shows, Search, Favourites, Downloads, About, Spinning Surprise |
| `screen.surprise_row` — Spinning Surprise is a home row | **PASS** | surprise_index=10 |
| `screen.home_focus` — Home opens on the first room | **PASS** | focus='Latest' expected='Latest' |
| `screen.rooms_open` — Every room opens into content | **FAIL** | Mixes & Shows: capture window wrong; Mixes & Shows: no child rows (None); Search: no child rows ('Latest') |
| `screen.back_stack` — Back pops one level and closes at home | **PASS** | room opened=True; tracks opened=True; Back returned to show list=True; Back returned home=True; Back at home closed the window=True |
| `screen.surprise` — Surprise shows a splash then plays once | **PASS** | splash=True playing=True item='DJ Czech @ Soundfeer Festival, Rekreační Středisko Věšín, Czech Republic (June 21, 2013)' samples=3  |
| `screen.now_playing` — Now-playing footer is captured with audio | **PASS** | screenshot=True active=True |
| `screen.modal_refusal` — Modal launch fails fast, then recovers | **FAIL** | held=True refused_logged=False recovery_window=13000 midwait=False |
| `list.root` — Root has the public 10-row taxonomy | **FAIL** | labels=['Rave Player', 'Classic lists'] |
| `list.about` — About names the installed version | **PASS** | first='Rave Player 3.9.51 — GPL-3.0' version=3.9.51 |
| `list.radio` — Live Radio lists the stations | **PASS** | 10 rows: ['Kool FM', 'Rinse FM', 'Centreforce 883', 'Hardcore', 'Jungle', 'Drum & Bass'] |
| `list.downloads` — Downloads are local files | **FAIL** | 8 rows, 7 local |
| `list.favourites` — Favourites shows saved rows + Downloads | **PASS** | 2 rows: ['Downloads  [COLOR gray](7)[/COLOR]', 'Brockie - Kool FM 94.5'] |
| `pages.archive_jungle` — Archive Jungle page 1/last headers | **PASS** | header='Page 1 of 2 · 71 items' pages=2 total=71  |
| `pages.jt_index` — JungleTapes index page 1/last headers | **PASS** | header='Page 1 of 7 · 310 shows' pages=7 total=310  |
| `pages.rtp_category` — RaveTapePacks category index page header | **PASS** | single page / no header, 51 rows |
| `list.jt_show` — JungleTapes show lists tracks | **PASS** | 1 rows |
| `list.rtp_index` — RaveTapePacks index is complete | **PASS** | 6 rows |
| `list.rtp_pack` — RaveTapePacks pack list is non-empty | **PASS** | 4 rows |
| `list.rtp_tracks` — RaveTapePacks pack lists tracks | **PASS** | 16 rows |
| `list.search` — Search query, results and empty states | **FAIL** | results=39 empty=1 nonsense query returned 1 rows |
| `urls.listings` — Bridge-host listings use plugin play routes | **PASS** | inspected 17 items; clean |
| `playlist.rtp_play_all` — rtp_play_all queue is plugin routes | **PASS** | count=16 raw=0 bad=0 |
| `playlist.jt_play_all` — jt_play_all queue is plugin routes | **FAIL** | count=1 raw=0 bad=0 |
| `logs.traceback` — No tracebacks or fatal plugin errors | **PASS** | tracebacks=0 fatal=0 |
| `logs.nonexistent_control` — No non-existent control errors | **PASS** | 0 matches |
| `logs.control_errors` — No unexpected control errors | **WARN** | Control 52 in window 10502 has been asked to focus, but it can't; Control 52 in window 10502 has been asked to focus, but it can't; Control 52 in window 10502 has been asked to focus, but it can't |
| `logs.playback` — No media open failures | **PASS** | 0 matches |
| `logs.activation_refused` — Activation refusals only in the modal test | **PASS** | states=['modal_refusal_held', 'modal_refusal_result', 'modal_recovery_midwait'] |
| `logs.modal_guard` — Modal-refusal guard logged its failure | **FAIL** | missing guard line |
| `timing.capture` — Screencap latency recorded | **PASS** | max=63219ms avg=17066ms |
| `timing.states` — Per-state durations recorded | **PASS** | max=70246ms wall=1209.9s |

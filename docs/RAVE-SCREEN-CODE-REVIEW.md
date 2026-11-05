# Rave Screen — Kodi 22 code review

**Reviewed revision:** `feat/rave-screen-3.9.47` @ `0084d18` (the feature plus the
device diagnosis commits)
**Review date:** 5 Nov 2026
**Scope:** `script.raveplayer.ui/**`, the plugin's `mode=screen` route
(`resources/lib/routes.py`), the repository artefacts and the tests.
**No deploy, tag or push was performed.**
**Companion:** [`RAVE-SCREEN-DIAGNOSIS.md`](RAVE-SCREEN-DIAGNOSIS.md) — the
Kodi 22 / SHIELD device run on this branch. This review was written without a
device; it verifies the code against the Kodi source (Matrix, Nexus, Omega,
Piers) and builds on that diagnosis.

**Fix branch:** `fix/rave-screen-review` (6 commits on top of `0084d18`,
600 tests OK). It fixes the clear defects only. The open items in §2 have
patches in §7 but are deliberately **not** committed without a device run.

---

## 1. Verdict

The **window model is fundamentally sound**: one full-screen `WindowXML` owned
by a script add-on, 1280×720, a `ControlList` bound from Python, one control
port and a controller that owns all state. That is the right architecture, and
it removes the legacy plugin-list overlay failure mode. It should not be
replaced by a dialog by default.

The **launcher** was not sound, and the device run found the real P0:
`WindowXML.show()` is refused while any modal dialog is up, silently. The
script then waited forever for a `close()` that could never arrive, producing
an invisible "zombie" invoker and no user-visible error. This review confirms
that mechanism from the Kodi source and adds the missing fail-fast/verification
fix plus a launcher change that removes the common `DialogBusy` race entirely.

Two further P1s would still have broken the release even with the window fixed:

1. **RaveTapePacks playback bypasses the 3.9.43 RTP egress bridge.** The screen
   hands the raw `ravetapepacks.com` URL to Kodi; the plugin's own `mode=play`
   starts a loopback bridge because Kodi's player cannot use the egress proxy
   and the origin firewall drops the home WAN address. Those tracks will fail
   on the device while the rest of the screen works.
2. **Three fonts referenced by the skin XML do not exist in Estuary** on any
   supported Kodi (`font16`, `font20`, `font30`). Kodi silently falls back to
   `font13`, so the type hierarchy collapses — exactly the "controls don't load
   silently" class of bug.

Plus: the `System.HasAddon` check treats a *disabled* add-on as installed (dead
row), `Back` during a load kept the script alive for up to 15 s, the 400-row
JungleTapes list was bound one item at a time with an O(n²) message storm, a
data-load failure left a blank window, and after one play the screen is a
dead end until Back. The first four are fixed on the branch; the last is a
design decision (below).

**Bottom line:** do not ship 3.9.47 as-is. Merge the fix branch, add the RTP
playback fix, decide the `_handed_off` behaviour, and resolve the release
packaging (see D13).

---

## 2. Ranked defects

| # | Severity | Defect | Location (@0084d18) | Status |
|---|---|---|---|---|
| D1 | **P0** | `show()` refused while a modal is up; keepalive waits forever (headless zombie) | `raveui/window.py:261-275` | **fixed** |
| D2 | **P0** | Screen launched through a plugin *folder* → `DialogBusy` race, and Back lands on an empty folder | `routes.py:610-627`, `:577-606` | **fixed** |
| D3 | **P1** | RaveTapePacks playback bypasses the RTP egress/loopback bridge | `raveui/playback.py:30-64`, `raveui/data.py:242-254` | **open** |
| D4 | **P1** | `font20`/`font16`/`font30` do not exist in Estuary → silent `font13` fallback | skin XML `:61,127,171,211` | **fixed** |
| D5 | **P1** | Disabled script add-on passes `System.HasAddon` → dead row, no message | `routes.py:618` | **fixed** |
| D6 | **P2** | Back during a load does not cancel: script lingers up to 15 s after close | `raveui/tasks.py:45-71`, `raveui/controller.py:209-234` | **fixed** |
| D7 | **P2** | Per-row `addItem()` re-sends the whole list (O(n²)); JungleTapes ~400 rows | `raveui/window.py:90-120` | **fixed** |
| D8 | **P2** | Data-load failure leaves a blank window and a live controller | `raveui/window.py:200-214` | **fixed** |
| D9 | **P2** | `_handed_off` locks the screen after one play; no playback-failure detection | `raveui/controller.py:89-95`, `:236-254` | **open** |
| D10 | **P2** | 15 s runner timeout is shorter than the plugin's own 25-30 s fetch timeouts | `raveui/tasks.py:31` | **open** |
| D11 | **P2** | No singleton: a second launch creates a second window/invoker that can also play | `default.py:18-30`, `routes.py:610` | **open** |
| D12 | **P2** | "Repeated songs" attribution is unproven; single-pick guarantee is per process | `raveui/controller.py` | **analysis** |
| D13 | **P2** | Plugin 3.9.48 (parallel branch) has **no** `mode=screen` route: installing it erases the feature | packaging / branch | **open (release blocker)** |
| D14 | P3 | Surprise overlay visible until the deferred `onInit` runs → flash on open | skin XML `:177-226` | **fixed** |
| D15 | P3 | `setFocusId(50)` in `onInit` logs "Control 50 … asked to focus, but it can't" | `raveui/window.py:211-214` | **fixed** |
| D16 | P3 | Home subtitle clipped ("…one rando") | `raveui/controller.py:19` | **fixed** |
| D17 | P3 | `ACTION_PARENT_DIR` (9) not treated as Back | `raveui/window.py:36-39` | **fixed** |
| D18 | P3 | Plugin add-on context bound *after* importing data modules → stale module constants | `raveui/pluginbridge.py:114-137` | **fixed** |
| D19 | P3 | A missing control id fails completely silently | `raveui/window.py:56-60` | **fixed** |
| D20 | P3 | Generic skin-media names (`screen-bg.jpg`, `focus-plate.png`, …) can be shadowed by the active skin's media | skin XML textures | **open (low)** |
| D21 | P3 | Docs/tests overstate correctness (window id, fonts, "GUI-thread" model, "read-only", "pinned") | docs, tests | **partly fixed** |

---

## 3. Findings in detail

### D1 — P0: a refused activation is indistinguishable from a shown window

Reviewed code (`script.raveplayer.ui/raveui/window.py:261-275`):

```python
def open_screen(window_factory=None, monitor_factory=None):
    factory = window_factory or RaveScreenWindow
    window = factory(XML_FILE, ADDON_PATH)
    window.show()                                   # returns nothing on refusal
    monitor = monitor_factory() if monitor_factory else xbmc.Monitor()
    while not getattr(window, "closed", False):     # waits for a close that cannot come
        ...
        xbmc.sleep(100)
```

Kodi facts (verified in the tree):

- `xbmcgui.WindowXML.show()` is **non-blocking**: `Window::show()` sends
  `TMSG_GUI_ACTIVATE_WINDOW` through the application messenger and returns
  (`xbmc/interfaces/legacy/Window.cpp`, `Window::show`).
- `CGUIWindowManager::ActivateWindow` refuses the activation while a modal
  dialog is active and only writes one `info` line
  (`Activate of window '13000' refused because there are active modal
  dialogs`). No exception reaches Python, and the line does not name the
  add-on. The device log in `RAVE-SCREEN-DIAGNOSIS.md` §3 shows exactly this.
- `close()` is the only thing that clears `window.closed`, and a window that
  never activated never receives `onAction`, so the loop is unbreakable except
  by restarting Kodi.
- There is no general way to ask a Python window for its own id: `getId()` on
  the legacy API belongs to `Action`, not `Window` (and the XML `id` is
  ignored, see D21). `xbmcgui.getCurrentWindowId()` returns the *active*
  window id, but a `>= 13000` check could match another script add-on's window.
- The reliable signal is **`onInit`**. A refused activation never sends
  `GUI_MSG_WINDOW_INIT`, so `WindowXML::OnMessage` never invokes `onInit`; the
  device log had no `Window Init (...script-raveplayer-ui.xml)` line and no
  `onInit enter`. `onInit` is a queued callback that runs on the script thread
  inside `xbmc.sleep()` — exactly the call the activation wait is already
  making.

**Fix (applied):** wait for `System.HasActiveModalDialog` to clear, `show()`,
then wait (bounded, 10 s) for the deferred `onInit` callback to set the
window's `initialized` flag. On refusal, log one error and notify, then
return without entering the keepalive. Do **not** call `close()` in that case:
`Window.close()` sends `TMSG_GUI_PREVIOUS_WINDOW` (Kodi's
`CGUIWindowManager::PreviousWindow()`) and would pop the root list the user is
standing on; dropping the reference lets Kodi delete the unused window without
touching the stack. On a successful window, `open_screen()` closes in a
`finally` (idempotent with Back).

`System.HasActiveModalDialog` is a real Kodi info bool (Estuary uses it;
`SYSTEM_HAS_ACTIVE_MODAL_DIALOG` in `xbmc/guilib/guiinfo/GUIControlsGUIInfo.cpp`)
and exists on Matrix through Piers, i.e. the whole 19-22 range.

**Test:** `test_open_screen_waits_for_a_modal_dialog_before_showing`,
`test_open_screen_fails_fast_when_activation_is_refused`.

### D2 — P0: launching through a plugin directory created the modal and the dead end

Reviewed code (`resources/lib/routes.py:610-627`): the root row was added with
`menu_item(..., is_folder=True)` (`ui.py:183`) and `mode=screen` called
`kodi.end_directory()` then `RunScript`. `end_directory()` only finishes the
listing; Kodi still opens the `?mode=screen` directory window, and while it is
loading it owns `DialogBusy`. That is the modal that raced the script's
`show()`. It also means Back from the screen landed on the empty "Rave Screen"
folder (Kodi adds only a `..` row to an empty plugin folder), not the root list.

**Fix (applied):** make the root row a **non-folder plugin item**. Kodi's
`CGUIMediaWindow::OnClick` has an explicit branch for exactly this case:

```cpp
else if (pItem->IsPlugin() && !pItem->GetProperty("isplayable").asBoolean())
  return XFILE::CPluginDirectory::RunScriptWithParams(pItem->GetURL(), resume);
```

`RunScriptWithParams` → `CScriptRunner::ExecuteScript` starts the plugin
asynchronously without waiting and **without a directory window**, so there is
no `DialogBusy` to race and Back returns to the root list. The route now:

- checks `System.AddonIsEnabled(script.raveplayer.ui)` (D5),
- calls `end_directory()` only for a legacy folder/favourite invocation
  (`handle >= 0`; the program-style invocation passes `-1`),
- `RunScript(script.raveplayer.ui)`.

The script-side activation guard (D1) remains as defence for other entry
points (Add-ons → Programs, JSON-RPC `Addons.ExecuteAddon`, a directory
loading behind a skin shortcut).

**Test:** `test_root_has_rave_screen_as_a_non_folder_program_row`,
`test_screen_route_launches_the_script_without_a_directory`,
`test_screen_route_ends_a_legacy_folder_handle`.

### D3 — P1 open: RaveTapePacks playback cannot work through the screen

The plugin's own playback route (`resources/lib/routes.py:2093`) detects
`http.is_egress_host(url)` and starts a loopback bridge:

```python
is_rtp = http.is_egress_host(params.get("url", ""))
...
bridge = rtp_bridge.RTPBridge()
if bridge.start():
    bridged = bridge.url_for(stream)
    ...
bridge.wait_for_playback()        # plugin stays alive while Kodi plays it
```

`docs/RTP-EGRESS-3.9.43.md` explains why: only `ravetapepacks.com` traffic goes
through the homelab HTTP CONNECT proxy, Kodi's player cannot use `urllib`'s
proxy, and the origin firewall drops the home WAN address at TCP level. A raw
`ravetapepacks.com` stream URL handed to `Player().play()` therefore fails
(blackholed connection or 403), however correct the `|Referer=` suffix is.

The screen's `PlaybackService.play` (`raveui/playback.py:30-64`) builds a
one-item music playlist from the raw URL (`:57-60`). `data.py:242-254` applies
`legacy.playable()` (Referer/UA) but never the bridge. So **RaveTapePacks rows
will list and then fail to play** on the device, while the same track plays
from the normal plugin lists. The device checklist in `RAVE-SCREEN.md` asks for
exactly this ("RTP `Referer` suffix is preserved (audio does not 403)") but the
suffix is not the only requirement.

**Recommended fix (open, §7.1):** delegate playback to the plugin's proven
resolver instead of re-implementing it. Build a `plugin://plugin.audio.raveplayer/?mode=play&...`
item and play that; the plugin then applies the RTP bridge, the live reconnect
playlist, pre-buffering and the IsLiveStream flags it already owns. This also
removes D9's duplicate playback model. The alternative is to import
`rtp_bridge` from the plugin and keep the bridge alive for the lifetime of the
screen; that duplicates logic and needs `rtp_bridge` added to
`pluginbridge.MODULE_NAMES`.

**Must be tested after the fix:** RaveTapePacks pack → track plays on the LAN
where the direct origin is blocked; a non-RTP track still plays; a live station
still reconnects.

### D4 — P1: fonts that do not exist in Estuary

The skin XML references `font45` (exists), `font20` (`:61`), `font16`
(`:127`, `:171`) and `font30` (`:211`). Estuary on Kodi 19-22 defines only
`font10`, `font12`, `font13`, `font14`, `font23_narrow`, `font25_narrow`,
`font27`, `font27_narrow`, `font32`, `font37`, `font45`, `font60` and the
`*_title` variants. `font30_title` is not `font30`.

Kodi does not fail: `GUIFontManager::GetFont()` falls back to `font13` for any
unknown name (`xbmc/guilib/GUIFontManager.cpp`, "fall back to font13"), with no
log line. The result is that the wordmark is 45 pt while the view title, the
focused row, the now-playing line and the Surprise caption are all 13 pt — the
whole hierarchy the design asks for is lost, silently. This also contradicts
the design spec (`docs/rave-screen/RAVE-SCREEN-DESIGN.md` §2: "Only font13,
font12 and font10… no font14, no skin-specific font names").

**Fix (applied):** `font20 → font27`, `font16 → font14`, `font30 → font37`
(all defined by Estuary Matrix..Piers), and the font45 wordmark gets a 50 px
box so it is not clipped. A test now asserts every `<font>` name is in the
Estuary set, so a future skin edit cannot reintroduce a silent fallback.

### D5 — P1: `System.HasAddon` is true for a *disabled* add-on

`routes.py:618` used `System.HasAddon(script.raveplayer.ui)`. Estuary itself
uses the two conditions separately:

```xml
<onclick condition="System.AddonIsEnabled(script.globalsearch)">RunScript(script.globalsearch)</onclick>
<onclick condition="System.HasAddon(script.globalsearch) + !System.AddonIsEnabled(script.globalsearch)">EnableAddon(script.globalsearch)</onclick>
<onclick condition="!System.HasAddon(script.globalsearch)">InstallAddon(script.globalsearch)</onclick>
```

So a disabled (or dependency-broken) script add-on passed the old check;
`RunScript` then did nothing and the directory was closed first. On the new
non-folder row there is no directory to close, but the dead row is still
fixed: the route distinguishes installed-but-disabled from not-installed and
gives one notification; it never touches the list.

### D6 — P2: Back during a load did not cancel the poll

`ThreadTaskRunner.run` (`tasks.py:45-71`) polls the worker with `xbmc.sleep(50)`
for up to 15 s. That `xbmc.sleep` **pumps queued Python callbacks** (see
`ModuleXbmc.cpp`: `sleep()` calls `languageHook->MakePendingCalls()` after each
≤100 ms chunk), so Back is delivered re-entrantly while the load is in flight.
But the runner never looked at `window.closed`; `on_back()` closed the window
while the poll loop kept going until the worker finished or the timeout
expired. The diagnosis's `show()`-refusal zombie is a different bug, but this
one has the same shape: a closed window with a live script behind it.

**Fix (applied):** `ThreadTaskRunner(cancelled=...)` (default `None`), checked
before the thread starts and on every poll tick, raising `TaskCancelled`; the
controller treats it as a quiet no-op. `RaveScreenController` passes
`cancelled=lambda: self._closed`.

**Test:** `test_thread_runner_stops_when_the_window_closed`.

### D7 — P2: the list was bound one row at a time

`KodiView.set_rows` called `control.addItem(item)` per row (`window.py:114`).
Kodi's `ControlList::addItem` does not append one item: it re-sends the
**entire** current vector as `GUI_MSG_LABEL_BIND`
(`xbmc/interfaces/legacy/Control.cpp`, `sendLabelBind`). For the 400+ show
JungleTapes list that is 400 queued messages carrying 1, 2, … 400 items, each
one rebuilding list layouts on the GUI thread — an O(n²) storm that can visibly
churn/freeze for seconds. Latest (20 rows) and Live (3) hid the problem.

**Fix (applied):** build all `ListItem`s first and call `control.addItems(items)`
once (one `LABEL_BIND`), with the old per-item path only as a fallback.
`reset()` + `addItems()` + `selectItem(0)` is the correct programmatic list
sequence.

Note: the XML **must not** add `<content>` to the list. With a `<content>`
provider, Kodi ignores `GUI_MSG_LABEL_BIND` for that control
(`CGUIBaseContainer::OnMessage` only binds the vector when `m_listProvider` is
null), so Python's `addItem`/`addItems` would silently do nothing. The current
XML is correct here.

### D8 — P2: a data failure left a blank window

If `RaveData()`/`controller.start()` raised (plugin disabled/broken, corrupt
package), `onInit` caught it and set a status line — on a window with no rows,
no controller, and no way to discover what happened except Back. The top-level
`default.py` guard does not help because nothing escaped.

**Fix (applied):** log, set the status, show one notification and close the
window, so the user is returned to the list instead of being parked in a blank
screen.

### D9 — P2 open: one play ends the screen's usefulness

`on_click` returns `"Already playing — press Back to exit."` whenever
`_handed_off` is true (`controller.py:89-95`); `_handed_off` is only cleared if
`playback.play()` *raises* (`:236-254`). `Player().play()` returns before the
stream has actually started, so:

- a dead URL leaves the UI claiming "Now playing" and refuses every further
  pick until Back;
- after the track finishes, the user cannot pick another track from the screen
  without leaving and re-opening it;
- the "no repeated songs" rule is enforced by making the screen a dead end
  rather than by guarding re-entry.

This is a product decision that the changelog states as deliberate ("a second
OK while playing is a no-op"), so it is reported rather than changed. A small
patch is in §7.2: verify playback after a short grace period and re-arm when it
has stopped, or allow an explicit different-row pick while still refusing a
replay of the same URL.

### D10 — P2 open: the screen's timeout is shorter than the plugin's

`ThreadTaskRunner` defaults to 15 s (`tasks.py:31`). The plugin's own loaders
use `http.fetch(..., timeout=25)` for `legacy.packs()` and `timeout=30` for
`legacy.jungle_shows()` (two requests), and its route budget is 20 s. On a slow
link the screen will announce "Timed out loading …" while the same directory
would eventually load in the normal plugin lists; the abandoned worker keeps
running (and populates the cache) after the status line is gone.

Fix: raise the screen cap to ~30-45 s for explicit user loads, or pass a
per-loader timeout. Back cancels now (D6), so a longer cap costs nothing when
the user gives up.

### D11 — P2 open: no single-instance guard

Kodi happily runs two instances of a script add-on. Double-pressing OK on the
row (or launching from Programs while a screen is already open) creates a
second window and a second controller with its own `_handed_off`; both can
play. This is also the most plausible source of the reported "repeated songs"
(D12). Fix in §7.3.

### D12 — P2: what the "repeated songs" symptom can and cannot be

The diagnosis attributes the repeated songs to the zombie invoker ("the
plugin/UI underneath carries on"). Be careful: a script that never activated a
window never ran `onClick` and therefore never called `PlaybackService.play`.
It cannot itself have started audio. The realistic mechanisms are:

1. **Multiple screen instances** (D11): each has its own `_handed_off`, and
   closing the top window reveals the older one, which can play again.
2. **The legacy "Surprise Me" route** is still present in the plugin and still
   uses the old overlay/`SurpriseReveal` path. If the user selected it (or the
   root row was missing on plugin 3.9.46/3.9.48), that path can play
   independently of the screen.
3. **Kodi's own playlist behaviour**: the screen clears the music playlist and
   adds exactly one item, so Kodi will not auto-advance or repeat; a repeat
   needs a second `Player().play` call.

What is true: the **single-pick guarantee is per process**, not global. There
is no cross-instance lock and no "last played" guard, so "no repeated songs" is
not an architectural property of the add-on. If that guarantee matters across
launches, add a small persistent guard (last URL + timestamp in the plugin
profile, or a `Window(10000)` property) or a singleton (D11).

### D13 — P2 open, release blocker: the 3.9.48 branch has no screen route

`RAVE-SCREEN-DIAGNOSIS.md` §7.1 records that the installed plugin became
**3.9.48** from a parallel branch, and that its `routes.py` has no Rave Screen
row and no `mode=screen` handler (`grep -c "Rave Screen"` = 0). Kodi sees
nothing wrong: the script's dependency is `>= 3.9.47`, which 3.9.48 satisfies,
so the feature is simply invisible. Any 3.9.48 build that does not include the
`feat/rave-screen-3.9.47` route will erase it for users.

Required: merge/cherry-pick the plugin side (`root` row, `MENU_ART["screen"]`,
`rave_screen`, `HANDLERS["screen"]`, `resources/art/screen.png`,
`fanart-screen.jpg`) into the 3.9.48 line, bump both add-ons together, rebuild
the repo zips and re-run `scripts/check-repo-artifacts.sh`. Also note the
dependency is a **minimum**, not a pin (`AddonManager.cpp` uses
`MeetsVersion(dependency.versionMin, dependency.version)`), so the script's
declared `3.9.47` will never block a future incompatible plugin.

### D14-D19 — P3 fixes applied

- **D14 spinner flash:** Kodi renders the window before the script's deferred
  `onInit` callback runs (`onInit` is queued and executed on the script thread
  by `MakePendingCalls`), so the Surprise backdrop/ring/head/caption were
  visible for the first frame(s) of every open. The five spinner controls now
  carry `<visible>false</visible>` in the XML as well as being hidden in
  `onInit`.
- **D15 focus error:** `setFocusId(50)` inside `onInit` runs before the window
  is active and makes Kodi log `Control 50 in window 13000 has been asked to
  focus, but it can't` on every launch. `defaultcontrol=50` already focuses the
  list during window init; the explicit call is removed.
- **D16 subtitle clipping:** `HOME_SUBTITLE` was longer than the 530 px label at
  font13; shortened to `"OK opens a source · SPINNING SURPRISE picks one"`.
- **D17 Back variants:** added `ACTION_PARENT_DIR` (9) to `BACK_ACTIONS`
  alongside 92/10 (the design spec lists 9; some remotes/keymaps send it).
- **D18 bridge bind order:** `pluginbridge.load_plugin()` imported
  `kodi, latest, legacy, radio, toronto, ui, …` and only then patched the
  plugin's `kodi` context. `ui.py` caches `DEFAULT_FANART = kodi.FANART` at
  import time, and the plugin's `kodi.py` computes `ADDON`/`ADDON_PATH` at
  import time with `xbmcaddon.Addon()` — which inside a script add-on is
  *this* add-on. The result: module-level copies kept the script's paths/settings
  (e.g. `ui.DEFAULT_FANART`). Fix: import `kodi` first, bind, then import the
  rest. A regression test asserts `modules.ui.DEFAULT_FANART` is the plugin's
  fanart.
- **D19 silent control miss:** `KodiView._control` swallowed every
  `getControl()` failure, so a wrong id or a control Kodi failed to create gave
  a blank screen with no log. It now logs one error per missing id.

### D20 — P3 open: texture names can be shadowed by a skin

`WindowXML::AllocResources` appends the add-on's
`resources/skins/<defaultSkin>` directory to Kodi's texture search paths, but
the active skin's own path is already there (`ApplicationSkinHandling` calls
`SetMediaDir(skin->Path())` and `CGUITextureManager::GetTexturePath` scans the
list in order, appending `/media/`). So a skin that ships a same-named file
wins over this add-on. The names here are generic — `screen-bg.jpg`,
`focus-plate.png`, `footer-plate.png`, `rule-acid.png`, `surprise-ring.png` —
so a third-party skin could override the look. Stock Estuary has none of these
names, so this is low risk today. Prefer `rave-screen-` prefixed filenames, or
absolute `special://home/addons/script.raveplayer.ui/resources/skins/Default/media/…`
paths as the design spec (§0.1) recommends for exactly this reason.

### D21 — P3: documentation and test-accuracy corrections

The review found these statements to be wrong or misleading; the fix branch
corrects the code but not the prose documents:

- `RAVE-SCREEN.md` §2: `<window type="window" id="15047">` — the `id` attribute
  is **ignored** for add-on windows; Kodi allocates 13000-13099
  (`Window::getNextAvailableWindowId`) and the device log shows 13000. The
  design doc's 14002/14003 map is not what Kodi uses either.
- `RAVE-SCREEN.md` §4: "Back during animation is queued, not destructive" —
  Back is delivered **inside** the animation because `xbmc.sleep` pumps pending
  callbacks; it cancels the reveal and closes the window. That is safe (the
  animator checks `_closed`) but not queued.
- `RAVE-SCREEN.md` §4: "No settings, caches … are written" — the imported
  plugin modules do write the plugin's normal HTTP cache (`cache.py`), because
  `legacy.packs()` caches parsed pages. The screen is read-only with respect to
  *user settings/favourites*, not the cache.
- `RAVE-SCREEN.md` §6: "Dependency is pinned to 3.9.47" — it is a minimum
  (`MeetsVersion(versionMin, version)`).
- `RAVE-SCREEN.md` §6: "reads only built-in fonts" — three referenced fonts do
  not exist in Estuary (fixed).
- `tasks.py` docstring: "Kodi's Python window callbacks run on the GUI thread"
  — callbacks are queued and executed on the script thread by
  `xbmc.sleep`/`waitForAbort`; the GUI thread is not blocked by the animation
  (fixed in the branch).
- Tests: the stub `WindowXML.getControl()` always raised, so no test ever
  checked a control id, a font, a texture or list population; the old
  `test_window_xml…` asserted the ignored `id="15047"`. The new contract tests
  close that gap.

### Design-spec divergence (not a Kodi defect)

`docs/rave-screen/` (currently untracked) describes a richer, different screen:
window ids 14002/14003, a second full-screen window for Surprise, a focusable
CANCEL button, footer bound to `Player.*`/`<info>progress</info>`, control ids
100-212, only font10/12/13, absolute texture paths. The shipped XML is a
simpler single-window variant with ids 10-64 and an in-window surprise panel.
Either the design snapshot or the implementation must be declared
authoritative; shipping both as "the design" is confusing for the next
maintainer. The review's fixes preserve the implemented layout.

---

## 4. The six Kodi-22 questions

### 4.1 Window lifecycle — `WindowXML` vs `WindowXMLDialog`, `show()` vs `doModal()`

- **`WindowXML` + `show()` is the right base for this feature.** The window is
  non-modal, so it does not block Kodi's other windows, and Back can be a
  normal action. `WindowXML` is backed by `CGUIMediaWindow` (with the
  media-window `OnAction` skipped by Kodi's interceptor); the XML only needs
  `<window>` + `<controls>` + `<defaultcontrol>`.
- **`show()` is non-blocking.** It queues `TMSG_GUI_ACTIVATE_WINDOW` and
  returns. The script must stay alive itself — the keepalive loop is
  **required**, not optional — and a refused activation is invisible (D1).
- **The "main thread" rule is subtler than it looks.** Python window callbacks
  (`onInit`, `onClick`, `onAction`, `onFocus`) are queued by Kodi and executed
  on the thread that created the window (this script) the next time it calls
  `xbmc.sleep()`/`Monitor.waitForAbort()` (Kodi's `PythonCallbackHandler` only
  accepts callbacks on the creating thread; `xbmc.sleep` calls
  `MakePendingCalls`). Consequences:
  - `xbmc.sleep()` inside `onClick` does **not** freeze rendering; the GUI
    thread keeps drawing, which is why the 1.2 s spin works.
  - It *does* allow re-entrant callbacks: Back can arrive during the spin and
    cancels it (safe, tested); a second OK is ignored by `_busy`.
  - If the keepalive loop were replaced by a plain `time.sleep()` (or anything
    that does not pump pending calls), **no callbacks would ever fire**.
- **Back** is handled in `onAction` for 92/10/9; `WindowXML` does not
  auto-close on Back (Kodi's Python window `OnBack` is a no-op returning
  `true`), so the app's Back stack is in control. `WindowXMLDialog` would be
  modal and uses a different activation path (`RegisterDialog` +
  `HACK_CUSTOM_ACTION_OPENING`) that is not blocked by an open modal — a
  possible hardening, but it changes Back/stacking semantics and is not needed
  once D1+D2 are fixed.
- **Cleanup:** `Window::dispose()` closes or deletes the window when the Python
  object is destroyed (`open_screen` returns and the caller drops it), so a
  script that exits does not leak the window. The old code did not guarantee
  exit on failure (D1) and had no `finally`; both are fixed. `close()` is
  idempotent and safe to call from `onAction`; the double close in
  `controller.on_back()` + `onAction` is guarded by `_closed`.

### 4.2 Skin XML

- `<window type="window">` vs dialog: the `type` attribute is **not** what
  selects dialog behaviour — do that in Python (`WindowXMLDialog`). For an
  add-on window, Kodi ignores the XML `id` as well (D21).
- `<controls>`/`<defaultcontrol>`: correct. `defaultcontrol=50` matches
  `CONTROL_LIST`, and every `CONTROL_*` constant in `window.py` has a matching
  control (new test). Two decorative controls have no id, which is legal.
- The list has **no `<content>`**, which is correct for a Python-bound list
  (D7 explains why adding one would break `addItems`).
- Fonts: three were undefined in Estuary → silent `font13` (D4, fixed).
- Colours: all explicit `0xAARRGGBB`; no skin palette dependency.
- Textures: all five referenced files exist in
  `resources/skins/Default/media/`; generic names are a collision risk (D20).
- 1280×720 vs 1920×1080: the `720p` folder is resolved by Kodi
  (`CSkinInfo::GetSkinPath` → closest resolution; coordinates are scaled to the
  display), so a 1080p/4K screen upscales the whole layout. Art is authored at
  1280×720/640×360; expect some softness at 4K, not a layout break.
- Animations (`WindowOpen`, `Focus`, `Visible`) are valid Kodi triggers. The
  focus zoom lives in the skin, not in Python.
- `onInit` runs *after* the first render, so anything that must never be seen
  needs `<visible>false</visible>` in the XML, not only a Python call (D14).

### 4.3 Add-on launch

- `RunScript(script.raveplayer.ui)` is correct: the add-on id is also the
  installed directory (`script.raveplayer.ui`), the extension point is
  `xbmc.python.script`, `library="default.py"`, `<provides>executable</provides>`.
  No quoting issue (no commas/quotes in the id).
- `xbmc.executebuiltin` strings are executed asynchronously enough that the
  script starts after the plugin call returns; nothing in the route needs to
  wait.
- The old route ended a directory it had opened, then launched the script —
  that is what produced the `DialogBusy` race and the empty folder (D2). The
  new program-style row avoids the directory entirely; a legacy folder
  invocation still ends its directory first.
- Dependency/version: `xbmc.python 3.0.0` is fine for 19-22; the plugin needs
  `3.0.1` (Kodi 20+), so the pair installs on 20-22. The plugin dependency is a
  **minimum**, and Kodi 22 still executes an enabled script whose dependency
  version is unmet (device diagnosis), so packaging must be deliberate (D13).
- Repository: both zips are built from `scripts/build.sh`, listed in
  `repo/addons.xml`, and the committed script zip contains the skin XML, media,
  spinner frames and all `raveui` modules. `check-repo-artifacts.sh` passes on
  `0084d18`.

### 4.4 Data/import bridge

- The private-alias trick (`raveplayer_plugin` with `__path__` set to the
  plugin root) is sound: relative imports inside the plugin resolve, no plugin
  `resources` package is added to the script's namespace, and `sys.path` is not
  polluted.
- Add-on context: `xbmcaddon.Addon()` with no argument resolves **this** script
  add-on, so the plugin's own `kodi.py` module-level constants are initially
  wrong. The bridge repairs them — but only *after* the import, which left
  module-level copies stale (D18, fixed by binding before the rest of the
  imports).
- Missing plugin: `PluginUnavailable` is raised before any network work; the
  window now notifies and closes (D8). Missing individual helpers (older plugin
  without `radio.curated`, etc.) fail the whole bridge with one status line —
  acceptable, and the declared dependency should prevent it.
- The bridge imports `ui` → `handoff`, and all plugin modules import
  `xbmcplugin`; none of them call a plugin handle at import time. Import cost
  is small and happens once per window.
- The plugin's HTTP cache is written through the repaired context (plugin
  profile), which contradicts the "no caches written" doc line (D21).

### 4.5 Spinning Surprise — single-pick / re-entry / playback handoff

- Exactly one pick: `on_click` → `surprise()` sets `_busy`, the worker runs
  `random_pick()` once (`latest.random_pack()` → `archive.audio_files()` →
  one `random.choice`), the animator runs once, `_handoff` runs once. Repeated
  OK is rejected by `_handed_off`. The tests cover this.
- Re-entry: `_busy` gates the whole spinner+load; because callbacks can be
  re-entered during `xbmc.sleep`, this matters in practice and works.
- Animation: 10 fps, 10 frames, ≥1.2 s, `setImage` + `xbmc.sleep` on the
  script thread; the GUI thread repaints. A dead control fails soft (no
  playback). The extra `_surprising` flag is dead state (set/reset, never
  read); remove it or use it in `on_back` for clarity.
- Playback handoff while the window is open: one-item music playlist,
  `Player().play(playlist)`, clear-then-add, so Kodi cannot auto-advance or
  repeat. The raw-URL path is wrong for RTP (D3) and has no failure detection
  (D9).
- Back: pops a level while browsing; after a handoff it closes from any depth
  (deliberate); Back during a load closes (and now cancels the load, D6); Back
  during the spin cancels the reveal without playback (tested).
- No auto-advance loop and no watchdog/retry in `PlaybackService` — correct.
- Cross-process: no guarantee (D11/D12).

### 4.6 Fallback

- Missing script add-on: notification, no dead directory (D2/D5).
- Disabled/broken script add-on: notification, no action (D5).
- Script crashes at import: `default.py` logs the traceback and exits (silent
  to the user, but no crash); there is no notification — acceptable, could be
  improved with one `xbmcgui.Dialog().notification` in the fatal handler.
- Plugin missing/broken at runtime: blank window previously (D8), now
  notify+close.
- Refused activation: previously an unbreakable headless loop (D1), now
  notify+exit.
- Repeated songs: not guaranteed across instances (D12); the one-item playlist
  prevents Kodi-level repeats.
- The plugin's normal lists are untouched by all of this (tests pass; the root
  gains one non-folder row).

---

## 5. Is the design fundamentally sound?

**Yes — keep the custom window, but treat the launcher as part of the design.**
The architecture (script add-on owns one `WindowXML`; plugin stays the data
provider; read-only alias; explicit Back stack; single-pick surprise) is the
right one and is materially better than the legacy overlay. The evidence from
the device is that the window itself renders and behaves well on Kodi 22.

What should change, in order of value:

1. **Launcher (done):** non-folder plugin row + `RunScript`, plus the script's
   activation guard/fail-fast. This removes both the common modal race and the
   empty-folder dead end.
2. **Playback (open):** stop re-implementing playback. Delegate to the plugin's
   `mode=play` resolver (RTP bridge, live reconnect, pre-buffer) or at minimum
   bring the RTP bridge into the screen. One playback model, one set of fixes.
3. **Fewer moving parts (optional):** the in-window Surprise panel with five
   controls is the most complex part of the XML. If the design permits, a
   single full-window image plus one label (or the existing plugin
   `SurpriseReveal` pattern) would cut the failure surface; the current
   implementation works, but it is the part that flashed before `onInit` and
   the part most likely to drift from the design snapshot.
4. **`WindowXMLDialog` + `doModal()`?** It would replace the keepalive with a
   blocking loop that pumps pending calls and uses the dialog registration path
   (allowed on top of other dialogs). It also makes Back's semantics modal and
   changes the window stack — and the device run disproved the class as the
   root cause. Not recommended as a default; keep it as a fallback if a future
   Kodi release refuses non-modal script windows.
5. **Do not move the list to a different id** to work around focus: control ids
   50-59 are the WindowXML list range; 50 is correct.

---

## 6. What must be tested on the device (Kodi 22 / SHIELD, Estuary)

Record Kodi build, skin, add-on versions and the full log. The first three are
release gates.

**Launch and stack**

- [ ] Install **both** 3.9.47 zips (and merge the route into 3.9.48 before any
      3.9.48 release). Rave Player root shows **Rave Screen** as row 1.
- [ ] Select it: the full-screen window opens; the plugin root list is still
      behind it; Back returns to the root list, **not** an empty "Rave Screen"
      folder.
- [ ] Launch from Add-ons → Programs and via JSON-RPC `Addons.ExecuteAddon`.
- [ ] Launch while a modal is open (open the search keyboard or start another
      directory load, then launch): the script must wait ≤10 s for the modal,
      then either open or notify "Could not open Rave Screen…" and exit. The
      log must show the new `window activation refused` error in that case.
      There must be **no** invoker left looping after the window is gone
      (check `Kodi.log` for a continuing `CPythonInvoker` / `open_screen`).
- [ ] Launch while a directory is loading (the old `DialogBusy` race) 10×.
- [ ] Double-press OK on the row: current build opens two instances (known,
      D11); confirm behaviour is at least not a crash and note it.
- [ ] Cold start (Kodi just booted) and launch immediately.

**Window and skin**

- [ ] No `Control 50 … asked to focus, but it can't` in the log.
- [ ] No `Unknown animation` / `invalid texture` / unknown-control errors.
- [ ] Type sizes: wordmark 45, view title 27, rows 13/14, now playing 14,
      surprise caption 37. (If any label suddenly looks 13 pt, a font name is
      wrong again.)
- [ ] Surprise overlay is **not** visible when the window first opens; it
      appears only after OK on SPINNING SURPRISE.
- [ ] Subtitle is not clipped.
- [ ] Try one non-Estuary skin: expect font13 fallback for unknown names and
      check that no skin texture overrides the backdrop (D20).

**Focus and back**

- [ ] D-pad ↑/↓ scrolls the list; hero art changes; focus plate animates; hold
      to repeat does not lose focus.
- [ ] Back pops section → home; Back at home exits; Back during "Loading…" exits
      within ~100 ms (D6), with no late re-render.
- [ ] Back during the spin cancels without playback.
- [ ] Remote/keymap that sends `ACTION_PARENT_DIR` (9) also exits.

**Sources and playback**

- [ ] Latest → pack → track list loads; play a track.
- [ ] Toronto → genre → list → play.
- [ ] JungleTapes → show list (400+ rows) loads without a multi-second freeze
      (D7). If it still chugs, check the list message count in debug.
- [ ] **RaveTapePacks → pack → play**: expected to fail until D3 is fixed. After
      the fix: plays on the LAN where the origin is TCP-blocked, Referer is
      preserved through the bridge, no 403.
- [ ] Live Radio: Kool/Rinse/Centreforce plays; a slow station does not lock
      the UI; Back while tuning works.
- [ ] Slow source (>15 s): status shows a timeout (D10) or the load succeeds if
      the cap is raised; Back cancels the wait.

**Spinning Surprise**

- [ ] OK once: pick, spinner visible for ≥1.2 s, then audio; now-playing line
      reads `Now playing: <track> — <pack>`.
- [ ] Repeated OK during/after: status only, no second pick/play.
- [ ] After the track ends: pressing OK on another row (current design refuses;
      confirm D9 decision).
- [ ] 5 runs: one pick/animation/play each; music playlist length is 1.
- [ ] Force a bad URL: no repeated playback; status shows the failure; window
      can be closed.

**Failure paths and packaging**

- [ ] Disable `script.raveplayer.ui`: row notifies "installed but disabled".
- [ ] Uninstall it: row notifies "not installed"; the rest of the root list is
      unchanged.
- [ ] Break the plugin package (rename `resources/lib`): window notifies and
      closes, no blank screen.
- [ ] `Monitor.abortRequested`/Kodi quit while the window is open: script exits
      cleanly.
- [ ] Re-open the screen 3×: no leaked window (ids 13000-13002 max), no growing
      invoker list, no memory growth.

**Regression**

- [ ] Normal root/hub/track lists, favourites, downloads and the legacy
      Surprise Me route behave as 3.9.44.
- [ ] No new autoplay on any directory route.

---

## 7. Fix branch and patches for the open items

### 7.1 Branch contents

Branch `fix/rave-screen-review`, based on `0084d18`, 6 commits (see
`git log fix/rave-screen-review`):

| # | Contents |
|---|---|
| 1 | non-folder launcher row; enabled check; no directory in the program path |
| 2 | activation wait/verify/fail-fast (`onInit` flag); `finally` close; `addItems` batching; missing-control logging; close on data failure; `ACTION_PARENT_DIR`; drop `setFocusId` |
| 3 | Estuary fonts; spinner hidden in XML; wordmark box |
| 4 | `TaskCancelled`/cancel predicate; plugin-context bind order; shorter subtitle |
| 5 | tests (activation, launcher, list batching, cancellation, XML/font/control contract) |
| 6 | this report |

Verification on the branch: `python3 -m unittest discover -s test` → **600 OK**
(47 → 58 in `test_rave_screen.py`; the rest of the suite unchanged).
`scripts/check-repo-artifacts.sh` is unaffected (no version bump; the committed
zips do **not** contain these fixes until `scripts/build.sh` is run):

```sh
git switch fix/rave-screen-review
./scripts/build.sh && ./scripts/build-repo.sh && ./scripts/check-repo-artifacts.sh
```

The branch deliberately does **not** change `addon.xml` versions. A release
needs a coordinated bump of `plugin.audio.raveplayer`, `script.raveplayer.ui`
and the repo zips, on a line that contains the `mode=screen` route (D13).

### 7.2 Patch: recovery after playback (D9)

```python
# raveui/playback.py
def is_playing(self):
    try:
        return bool(self.xbmc.Player().isPlaying())
    except Exception:
        return False

# raveui/controller.py
import time                             # add to the module imports
# in __init__: self._handed_at = 0.0
# in _handoff(): self._handed_at = (self._clock or time.monotonic)()
def tick(self):
    """Re-arm the screen when playback stops (called from the window loop)."""
    if not self._handed_off or self._busy:
        return
    now = (self._clock or time.monotonic)()
    if now - self._handed_at < 2.0:      # Player().play() is asynchronous
        return
    if self.playback.is_playing():
        return
    self._handed_off = False
    self.view.set_status("Ready — pick another row.")
```

Call `window.tick()` from `open_screen`'s keepalive loop (e.g. every 500 ms).
If the intended rule is "one play per screen session", keep D9 but at least
verify playback once after the grace period and show "Playback failed" instead
of "Now playing" (clear `_handed_off` in that case). The latter is the smaller
change and keeps the single-pick intent.

### 7.3 Patch: singleton (D11)

```python
# default.py
import xbmcgui
HOME = xbmcgui.Window(10000)
LOCK = "script.raveplayer.ui.running"
if HOME.getProperty(LOCK):
    return
HOME.setProperty(LOCK, "1")
try:
    ...
finally:
    HOME.clearProperty(LOCK)
```

A hard-kill can leave the property set; store a timestamp and expire it, or
clear it from a service/watchdog. The non-folder launch already removes the
most common double-launch path (key repeat on the directory row).

### 7.4 Patch: delegate playback to the plugin resolver (D3)

```python
# raveui/playback.py
import urllib.parse

def play(self, track):
    params = {"mode": "play", "url": track.url, "label": track.title}
    if track.art:
        params["thumb"] = track.art
    if track.live:
        params["live"] = 1
        params["station"] = track.title
    url = "plugin://plugin.audio.raveplayer/?" + urllib.parse.urlencode(params)
    item = self.xbmcgui.ListItem(label=track.title, path=url)
    item.setProperty("IsPlayable", "true")
    playlist = self.xbmc.PlayList(self.xbmc.PLAYLIST_MUSIC)
    playlist.clear()
    playlist.add(url, item)
    self.xbmc.Player().play(playlist)
    ...
```

The plugin's `mode=play` (`routes.py:2093`) then applies `_playable_url`, the
RTP loopback bridge (and keeps itself alive with `wait_for_playback`), live
reconnect and pre-buffer. Verify on device that a live station started from
inside our window behaves (that route starts its own playlist), and that
closing the screen does not cut the plugin's bridge before playback starts.
If that interaction is a problem, the fallback is to import
`rtp_bridge`/`http` through the existing alias and keep a `RTPBridge` alive in
the screen (`rtp_bridge` must be added to `pluginbridge.MODULE_NAMES`).

Either way: **do not ship RaveTapePacks playback from the screen until this is
tested**; today it cannot work where the origin blocks the WAN address.

### 7.5 Smaller follow-ups

- Raise the runner timeout (D10) to 30-45 s for user-initiated loads.
- Rename skin media with a `rave-screen-` prefix or use absolute paths (D20).
- Remove the unused `_surprising` flag.
- Add a notification to `default.py`'s fatal handler (the user currently gets a
  silent return).
- Correct the docs prose listed in D21, and declare the design snapshot or the
  implementation authoritative.

---

## 8. Verification notes (Kodi source facts used)

Checked against `xbmc/xbmc` Piers (Kodi 22), Omega (21), Nexus (20) and Matrix
(19):

- `Window::show()` sends `TMSG_GUI_ACTIVATE_WINDOW` and returns; `Window::doModal()`
  runs the pending-call loop; `Window::getNextAvailableWindowId()` allocates
  13000-13099 for Python windows (`xbmc/interfaces/legacy/Window.cpp`).
- `xbmcgui.getCurrentWindowId()` = `GetActiveWindow()` (history back);
  `getCurrentWindowDialogId()` = topmost modal dialog. The Python `Window`
  wrapper has no `getId()` (`getId()` is on `Action`), so activation is proved
  by the `onInit` callback, which a refused activation never reaches.
- `WindowXML` constructor defaults: `defaultSkin="Default"`,
  `defaultRes="720p"`; the XML is resolved under
  `resources/skins/<skin>/720p/` (`WindowXML.h` / `WindowXML.cpp`).
- `CGuiWindow::Load` ignores `<window type=…>`/`id=…` (only children such as
  `<defaultcontrol>`, `<controls>`, `<coordinates>` are read); `WindowXML`
  allocates the window id itself.
- Python window callbacks are queued (`RetardedAsyncCallbackHandler`) and only
  run on the creating thread (`PythonCallbackHandler::isStateOk`);
  `xbmc.sleep` calls `MakePendingCalls` after each ≤100 ms chunk
  (`xbmc/interfaces/legacy/ModuleXbmc.cpp`).
- `GUIFontManager::GetFont` silently falls back to `font13` for unknown names;
  Estuary (Matrix..Piers) has no `font16`, `font20` or `font30`.
- `ControlList::addItem` re-sends the whole vector via `GUI_MSG_LABEL_BIND`;
  `CGUIBaseContainer::OnMessage` only honours that message when the control has
  no `<content>` provider.
- Add-on window texture lookup appends the add-on skin dir after the active
  skin's media path (`WindowXML::AllocResources`,
  `CGUITextureManager::GetTexturePath`), so same-named skin textures win.
- `CGUIMediaWindow::OnClick` routes a non-folder, non-playable plugin item
  through `CPluginDirectory::RunScriptWithParams` (which runs the plugin
  asynchronously and does not wait).
- `System.HasAddon` and `System.AddonIsEnabled` are distinct (Estuary uses
  both); `System.HasActiveModalDialog` exists across 19-22.
- `<import version>` is a minimum version, not an exact pin
  (`AddonManager.cpp`, `MeetsVersion`).

---

## 9. Recommended sequence

1. Merge `fix/rave-screen-review` (or cherry-pick its commits) and rebuild both
   zips.
2. Decide D9 and implement §7.2; implement §7.4 (RTP playback) and test on the
   LAN where the origin is blocked.
3. Merge the plugin `mode=screen` route into the 3.9.48 line, bump the pair
   together, rebuild `repo/`, run `check-repo-artifacts.sh` (D13).
4. Run the §6 checklist on the Shield, starting with the launch-while-modal case
   and RaveTapePacks playback.
5. Only then tag/publish; do not ship 3.9.47 as-is.

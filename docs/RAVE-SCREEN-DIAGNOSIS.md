# Rave Screen — device diagnosis (Kodi 22 / NVIDIA Shield)

**Date:** 5 Nov 2026
**Branch:** `feat/rave-screen-3.9.47`
**Device:** SHIELD Android TV, Android 11, Kodi `22.0-BETA1 (21.90.801)`, Estuary 4.1.0
**Add-ons at start:** `plugin.audio.raveplayer` 3.9.46, `script.raveplayer.ui` 3.9.47,
`service.raveplayer.ui` 3.9.46
**Scope:** diagnosis only. No plugin route/version change, no push, tag or release.
The script add-on was restored to the clean 3.9.47 artifact at the end. The
plugin add-on did **not** stay at the starting version: during the session it
changed to **3.9.48** (not by this diagnosis — see §7.1), which also has no
`mode=screen` route.

---

## 1. Verdict

The Rave Screen **does run and render on Kodi 22**. The failure is not “Kodi 22
refuses a custom `WindowXML`”, and it is not a Python traceback.

The failing step is the single `window.show()` call in
`script.raveplayer.ui/raveui/window.py:265`. Kodi refuses to activate the
window when **any modal dialog is already on screen**:

```
Activate of window '13000' refused because there are active modal dialogs
```

Kodi does **not** raise an exception for this. `show()` returns normally, so
`default.py` catches nothing, writes nothing, and `open_screen()` then enters:

```python
while not getattr(window, "closed", False):
    ...
    xbmc.sleep(100)
```

and waits forever for a window that was never created. Result: **no window, no
`[script.raveplayer.ui]` error line, a live Python invoker looping in the
background, and the plugin/UI underneath carries on** (which is why the user
then heard repeated songs). This exactly matches the reported symptom.

The `info` line that explains it does not contain the add-on id, so a log
search for `script.raveplayer.ui` misses it. That is why the log looked clean.

**Is the approach viable on Kodi 22?** Yes — bluntly, the window itself is fine,
but this launcher is not. It works whenever no modal is up and silently
self-destructs when one is. It must not ship until `show()` is verified/retried
and the add-on pair is installed together (see §8).

---

## 2. Test ladder and results

### Step 1 — direct launch (`Addons.ExecuteAddon`)

From Kodi Home:

```json
{"method":"Addons.ExecuteAddon","params":{"addonid":"script.raveplayer.ui"}}
```

Result: **started and rendered**. With debug logging enabled the invoker is
visible:

```
CPythonInvoker(14, .../script.raveplayer.ui/default.py): start processing
...
Activating window ID: 13000
------ Window Init (.../script.raveplayer.ui/resources/skins/Default/720p/script-raveplayer-ui.xml) ------
Loading skin file: .../script-raveplayer-ui.xml, load type: LOAD_ON_GUI_INIT
error: Control 50 in window 13000 has been asked to focus, but it can't
```

The window is Kodi-assigned id `13000` (the XML's `id="15047"` is not used for
add-on windows). A screenshot at this point showed the full 1280×720 Rave
Screen: RAVE SCREEN wordmark, six rows (LATEST, TORONTO…, JUNGLETAPES.COM,
RAVETAPEPACKS.COM, LIVE RADIO, SPINNING SURPRISE), hero art, focus plate on
LATEST and the footer. There was no traceback.

The same direct launch was repeated with the exact original pair (script 3.9.47
+ plugin 3.9.46) and **also worked**. Kodi 22 does not block execution of an
enabled script add-on whose declared dependency version is unmet; the script
just runs. So the version mismatch is not the launch blocker (but see §7).

### Step 2 — minimal window / skin XML

No separate blank-window harness was needed: the real XML was the first thing
loaded, and it loaded correctly. `WindowXML` + `resources/skins/Default/720p/`
works; there is no skin-path, `WindowXML` vs `WindowXMLDialog`, or control-id
problem in the XML itself.

The one error is the non-fatal focus complaint:

```
Control 50 in window 13000 has been asked to focus, but it can't
```

Kodi still focuses the list via `defaultcontrol=50`, and D-pad/OK respond. This
is an init-timing wart (explicit `setFocusId(50)` during `onInit`), not the
launch failure.

### Step 3 — real window, rows, focus, actions

Once activated, the real window is usable: six home rows, hero art switches as
selection moves, the list shows `Loading …` while a section loads, and Back
closes the window. The only issues seen were cosmetic/init-level:

- `Control 50 … asked to focus, but it can't` (above).
- The subtitle is clipped: `OK opens a source · SPINNING SURPRISE picks one rando…`
  (label width 530 at font13; text is longer).
- Kodi 22 logs `ListItem.setInfo()` deprecation warnings for the rows. They are
  warnings, not failures.

I did not exhaustively exercise every source/playback path; the launch failure
was reproduced before that was useful.

### Step 4 — `RunScript` from the plugin (`mode=screen`)

With `plugin.audio.raveplayer` 3.9.47 installed, Rave Player root shows the
**Rave Screen** row, and selecting it normally **works**:

```
CGUIMediaWindow::GetDirectory (plugin://plugin.audio.raveplayer/?mode=screen)
CScriptRunner: running add-on script Rave Player('plugin://plugin.audio.raveplayer/', ...)
[plugin.audio.raveplayer] route screen took 15 ms
------ Window Deinit (DialogBusy.xml) ------
CPythonInvoker(7, .../script.raveplayer.ui/default.py): start processing
Activating window ID: 13000
------ Window Init (.../script-raveplayer-ui.xml) ------
```

Note the ordering: the route ends, Kodi tears down `DialogBusy`, then the script
starts ~400 ms later and the window activates. The common path is sound.

The failure is timing/state dependent: if a modal dialog is still active when
`show()` runs, the same call is refused. The plugin route itself can collide
with `DialogBusy` if another directory load is in flight (double OK / remote
key repeat / another route still running), and launching the script from
Add-ons → Programs can collide with the add-on information/busy dialog.

---

## 3. Deterministic reproduction of the reported symptom

I opened the plugin's own search keyboard (`mode=search`, window `10103`) to
hold a real modal dialog, then launched `script.raveplayer.ui` directly. Log:

```
02:01:08.783 info: RAVE-SCREEN BOOT (diagnostic build)
02:01:08.892 info: RAVE-SCREEN open_screen: window constructed
02:01:08.900 debug: Activating window ID: 13000
02:01:08.900 info: Activate of window '13000' refused because there are active modal dialogs
02:01:09.150 info: RAVE-SCREEN show attempt 1: current window id=10502
02:01:09.150 debug: Activating window ID: 13000
02:01:09.150 info: Activate of window '13000' refused because there are active modal dialogs
...
02:01:52.464 error: RAVE-SCREEN show FAILED: no add-on window after 30 attempts
```

No `Window Init (.../script-raveplayer-ui.xml)` ever appears. `GUI.GetProperties`
stayed on the plugin window, not `13000`. The script process had started, read
`default.py`, constructed the window and looped; there was no fatal log because
nothing raised. That is the user's symptom, byte for byte.

The same line was seen earlier, at normal log level, while the plugin's packs
menu was on screen:

```
01:49:43.332 info: Activate of window '13000' refused because there are active modal dialogs
```

i.e. this is not an artifact of the diagnostic build.

### Why it leaves a zombie

`open_screen()` only exits when `window.closed` becomes true or Kodi aborts.
If activation was refused, no window exists to receive Back, `on_back()` never
runs, `close()` is never called, and the Python invoker keeps looping at
100 ms. The user cannot Back out of it; only restarting Kodi clears it. Repeat
launches can stack several of these invokers.

---

## 4. Exact failing code

`script.raveplayer.ui/raveui/window.py:261-275` (feature branch):

```python
def open_screen(window_factory=None, monitor_factory=None):
    factory = window_factory or RaveScreenWindow
    window = factory(XML_FILE, ADDON_PATH)
    window.show()                       # <-- refused; returns None, raises nothing
    monitor = monitor_factory() if monitor_factory else xbmc.Monitor()
    while not getattr(window, "closed", False):
        try:
            if monitor.abortRequested():
                window.close()
                break
        except Exception:
            pass
        xbmc.sleep(100)
```

`script.raveplayer.ui/default.py` only logs on an exception escaping this
function. A refused activation is not an exception, so the log stays silent.

`resources/lib/routes.py:610-627`:

```python
def rave_screen(handle, params):
    ...
    kodi.end_directory(handle, "files")
    xbmc.executebuiltin("RunScript(script.raveplayer.ui)")
```

`end_directory()` returns before Kodi has finished the directory/busy teardown.
`RunScript` is queued and normally runs after that teardown (verified above),
but it is still a race against any other modal dialog on the GUI thread.

---

## 5. Root cause

1. **Immediate cause:** `xbmcgui.WindowXML.show()` is called while Kodi has an
   active modal dialog. `CGUIWindowManager::ActivateWindow` refuses the
   activation (`window '13000'`), logs one `info` line and returns.
2. **Why it is fatal here:** `show()` failure is not signalled to Python and is
   not checked. `open_screen()` treats “shown” as unconditional and waits for a
   close that can never happen.
3. **Why the log looked empty:** the only explanatory line does not mention
   `script.raveplayer.ui`; the script itself logs nothing on this path.
4. **Why it is intermittent:** in the normal single-route case the plugin's
   `DialogBusy` is torn down before the script's `show()` (measured ~400 ms
   gap), so it works. It fails when another modal (a second directory load,
   the search keyboard, an add-on info dialog, etc.) is still up at that
   instant.

Not the cause:
- Kodi 22 refusing custom `WindowXML` windows — disproved; the window renders.
- Wrong skin path / wrong XML / `WindowXMLDialog` — disproved; the XML loads.
- Python 3.14 incompatibility — disproved; the script imports and runs.
- The 3.9.46/3.9.47 dependency mismatch — real packaging bug, but Kodi 22 still
  executes the enabled script. It does, however, mean the `mode=screen` route
  does not exist in plugin 3.9.46.

---

## 6. Minimal fix proposal

### 6.1 Script-side: verify activation, retry, then fail fast

Replace the blind `show()` with a bounded activation loop. Sketch (not deployed):

```python
def open_screen(window_factory=None, monitor_factory=None):
    factory = window_factory or RaveScreenWindow
    window = factory(XML_FILE, ADDON_PATH)

    activated = False
    for attempt in range(30):              # ~7.5 s
        window.show()
        xbmc.sleep(250)
        current = xbmcgui.getCurrentWindowId()
        if 13000 <= current < 14000:       # Kodi add-on window range
            activated = True
            break

    if not activated:
        xbmc.log("[script.raveplayer.ui] window activation refused "
                 "(modal dialog?)", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Rave Screen", "Could not open the screen — close any dialog and retry.",
            "", 4000)
        try:
            window.close()
        except Exception:
            pass
        return window

    monitor = monitor_factory() if monitor_factory else xbmc.Monitor()
    while not window.closed:
        if monitor.abortRequested():
            window.close()
            break
        xbmc.sleep(100)
```

What the diagnostic build proved on the Shield:

- `default.py` **does** run; a first-line `xbmc.log("RAVE-SCREEN BOOT")` is
  visible at normal log level.
- `show()` can be called repeatedly after a refusal; it does not raise and does
  not take Kodi down (30 attempts logged, no crash).
- A fail-fast path removes the zombie: the script logs one error, notifies and
  returns instead of looping forever.

What it did **not** prove: a successful recovery after the modal goes away. The
keyboard used for the test stayed open past the 30 attempts, so every attempt
was refused. The next device run should close a transient `DialogBusy` (or the
keyboard) while the loop is running and confirm `current >= 13000` flips true.
There is no reason it should not, but it is unverified.

Better long-term variant: don't launch from inside the plugin route at all. Use
a small service (the existing `service.raveplayer.ui` pattern) to receive a
“open Rave Screen” request, let the plugin directory/busy dialog finish, then
run `RunScript` from the service. That removes the race rather than retrying
through it. It is more moving parts, so the retry guard is the minimal fix.

### 6.2 Plugin-side: do not rely on an immediate `RunScript`

If the retry guard is not adopted, at minimum make `rave_screen()` deterministic:
close the directory, then launch the script from a context that is not the
plugin's GUI callback (service or a guarded post-directory action). A
`xbmc.sleep()` inside the route does **not** help: the busy dialog is only torn
down after the route returns, so sleeping in-route prolongs the modal.

### 6.3 Always install the pair

`script.raveplayer.ui` 3.9.47 requires `plugin.audio.raveplayer` 3.9.47. Install
both zips together. A 3.9.46 plugin has no `Rave Screen` row and no `screen`
route at all.

---

## 7. Packaging mismatch found on the Shield

This is separate from the window bug and needs a decision before the next test:

- Installed `plugin.audio.raveplayer` **3.9.46** root has **no Rave Screen row**
  (`grep -c "Rave Screen" resources/lib/routes.py` = 0; root shows Latest,
  Tape Packs, Pirate Radio, Mixes & Shows, Live Radio, Favourites, Search,
  Surprise Me, About). It also requires `service.raveplayer.ui` 3.9.46.
- Installed `script.raveplayer.ui` 3.9.47 declares
  `<import addon="plugin.audio.raveplayer" version="3.9.47"/>`.

Consequences:

- On the Shield as found, the reported “Rave Player → Rave Screen” row could
  not have come from plugin 3.9.46. Either the plugin was 3.9.47 at the time of
  the attempt and was later reverted, or the script was launched from
  Add-ons → Programs (or another entry point), not the plugin root.
- Kodi 22 still shows the script as enabled/not broken and executes it, so the
  mismatch produces no visible error — just a missing row and an unmet
  dependency.
- After installing plugin 3.9.47, the row appears and the route works. I did
  that for the route tests.

This needs to be resolved as part of the release: bump the plugin (and install
both), or relax the script's dependency. Do not ship 3.9.46 + 3.9.47 as a pair.

### 7.1 During the session the plugin became 3.9.48 — also without the route

After I restored 3.9.46, the installed plugin directory was replaced again at
`02:03` with **3.9.48** (timestamp and `addon.xml`), without any Kodi
add-on-update log line. That was not done by this diagnosis; a concurrent
install/push from another process is the likely source. Whatever the cause, the
result matters:

- `plugin.audio.raveplayer` 3.9.48 is installed and enabled right now.
- Its `resources/lib/routes.py` has **no `screen` route and no Rave Screen row**
  (`grep -c "Rave Screen"` = 0).
- `script.raveplayer.ui` 3.9.47 remains installed and enabled; its dependency
  `>= 3.9.47` is satisfied by 3.9.48, so Kodi sees nothing wrong. The row is
  simply gone.
- Therefore the feature is invisible on the currently-installed plugin pair,
  and any 3.9.48-based build that does not merge the Rave Screen route will
  erase it for users. The 3.9.47 screen work is on `feat/rave-screen-3.9.47`,
  not on `fix/rtp-category-nav-3.9.48` as far as this checkout shows.

This is probably more important than the window bug for “the row does nothing”:
with 3.9.46 or 3.9.48 installed there is no route to run. The window bug is
what happens *after* a 3.9.47 plugin is installed and the row is used.

---

## 8. Is the approach viable on Kodi 22? (blunt)

**Yes, with a fixed launcher.** Evidence:

- The custom `WindowXML` window renders at 1280×720 on Kodi 22 beta from the
  script add-on's own `resources/skins/Default/720p/` XML.
- Rows, ListItem labels/art, list focus, D-pad movement and Back all work once
  the window is active.
- No Kodi 22 API removal broke `WindowXML`, `ControlList`, `Monitor` or
  `xbmcgui.ListItem`.

But:

- `show()` has no error return and no exception on refusal. Any code that
  assumes it worked is wrong on Kodi 22.
- The script must tolerate/avoid modal dialogs at launch. The current
  `while not window.closed` keepalive turns one refused activation into an
  invisible zombie that only a Kodi restart clears.
- The add-on pair must be installed together, and the route must exist.

Verdict: **viable, not shippable as-is.** Fix the activation guard and the
packaging mismatch, then re-run the launch tests (plugin row, Add-ons → Programs,
cold start, and a launch while a directory is loading).

---

## 9. Other observations / cleanup

- `Control 50 … asked to focus, but it can't`: remove the explicit
  `setFocusId(CONTROL_LIST)` in `onInit()` and let `defaultcontrol=50` handle it,
  or set focus only after the window reports active. Non-fatal, but it is an
  `error` line in every launch.
- Subtitle clipping: “OK opens a source · SPINNING SURPRISE picks one rando…” —
  widen label 23 or shorten the text.
- `ListItem.setInfo()` deprecation warnings on Kodi 22: not a failure; migrate
  to `InfoTagMusic` later if desired.
- The diagnostic build (boot log + retry/fail-fast) is on scratch branch
  `diag/rave-screen-activation`, commit `f909918`, and is **not** part of the
  feature branch or the installed add-on.
- Final state: `script.raveplayer.ui` 3.9.47 (clean artifact), debug logging
  off, Kodi on Home. The plugin is **3.9.48** (see §7.1), not the 3.9.46 the
  session started with; 3.9.48 has no screen route.

---

## 10. Reproduction notes

Useful commands (paths on the Shield):

```sh
# enable Kodi debug logging (resets on restart)
curl -u kodi:bobhope0 -X POST http://192.168.1.189:8080/jsonrpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"Settings.SetSettingValue",
       "params":{"setting":"debug.showloginfo","value":true}}'

# direct script launch
curl -u kodi:bobhope0 -X POST http://192.168.1.189:8080/jsonrpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"Addons.ExecuteAddon",
       "params":{"addonid":"script.raveplayer.ui"}}'

# hold a modal open, then launch the script: keyboard dialog
curl -u kodi:bobhope0 -X POST http://192.168.1.189:8080/jsonrpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"Addons.ExecuteAddon",
       "params":{"addonid":"plugin.audio.raveplayer","params":"mode=search"}}'
```

Log: `/sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp/kodi.log`.
Grep for `Activate of window '13000' refused`, not just for
`script.raveplayer.ui`.

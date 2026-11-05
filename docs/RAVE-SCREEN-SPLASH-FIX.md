# Spinning Surprise splash — device fix (3.9.48)

**Date:** 5 Nov 2026 · **Device:** NVIDIA Shield TV, Kodi `22.0-BETA1 (21.90.801)`
**Add-ons:** `plugin.audio.raveplayer` 3.9.48, `script.raveplayer.ui` 3.9.48
**Branch:** `integration/3.9.48` · no push, tag or deploy.

## Symptom

During a Spinning Surprise the debug log printed

```
[script.raveplayer.ui] spinner visible=True controls=14
```

for several seconds, then `visible=False`, and audio started — but the
full-screen splash never painted. The Rave Screen home (rows, hero, footer)
stayed on screen; only the transient status line changed.

## Root cause

The 14 splash controls (700-713) carried a **literal visibility condition**:

```xml
<visible>false</visible>
```

Kodi does not treat that as an initial value. A `<visible>` element becomes a
per-frame condition on the control; every GUI update calls
`CGUIControl::UpdateVisibility()`, re-evaluates the condition and calls
`SetVisible()` with the result. A constant `false` therefore re-hides the
control on the next frame after Python calls `Control.setVisible(True)`.

`Control.setVisible()` does not raise, and the adapter counted 14 successful
calls, so the log looked healthy while the renderer was being told "hidden"
every frame. The `controls=14` number is a count of accepted calls, not of
painted controls.

The other candidates were checked on the device and ruled out:

| Candidate | Evidence |
|---|---|
| Wrong window / not activated | `GUI.GetProperties.currentwindow` = 13000; `Window Init (.../script-raveplayer-ui.xml)` in the log; home renders |
| Z-order / stacking | 700-713 are the last controls in the XML; removing only the static condition made the burst cover the whole window |
| Missing textures / bad `special://` paths | All files exist under the installed add-on; the experiment rendered burst, ring, head, labels and keycaps |
| Group / window visibility | Window and all home controls are visible; only 700-713 were suppressed |
| Worker thread visibility | Splash was made visible from `onClick` (Python callback), not the pick worker |
| Focus / modal overlay | No modal dialog at select time; `onInit` ran and the list accepted D-pad/OK |

**Proof of cause:** temporarily removing the 14 `<visible>false</visible>`
lines from the *installed* XML and re-running the same JSON-RPC sequence made
the splash paint immediately. Restoring the lines brought the bug back.

## Fix

1. `resources/skins/Default/720p/script-raveplayer-ui.xml` — every splash
   control now uses one window-property binding:

   ```xml
   <visible>String.IsEqual(Window.Property(rp_splash),1)</visible>
   ```

   The property is absent when the window opens, so the splash starts hidden.
   No literal `false` remains on 700-713.

2. `raveui/window.py` — `KodiView.set_spinner_visible()` sets
   `rp_splash=1`/`0` **before** calling `setVisible()` on the 14 controls. The
   XML condition and the Python state can no longer disagree; setting the
   property first also avoids a one-frame stale-condition window. The debug
   line now includes the property:

   ```
   spinner visible=True rp_splash=1 controls=14
   ```

3. Behaviour is unchanged: one bounded random pick, the existing
   `SpinnerAnimator` with `MIN_DURATION = 1.2`, one playback handoff, and the
   same Back/fail guards. `raveui/animation.py`'s docstring was corrected: the
   reveal runs on the reveal worker, and device capture confirms Kodi paints
   the frame changes.

## Device verification (3/3 runs)

Method: `Addons.ExecuteAddon` → six `Input.Down` moves focus to
`SPINNING SURPRISE` → `Input.Select`, then `adb exec-out screencap -p` during
the reveal. Run 1 also recorded the screen and extracted frames with
AVFoundation at 0.6 s spacing.

| Run | Splash set visible | Splash hidden | Playback started | Screenshot |
|---|---|---|---|---|
| 1 | `10:09:02.407` | `10:09:06.571` | `10:09:06.583` | `after-run1-splash.jpg` |
| 2 | `10:10:34.600` | `10:10:40.628` | `10:10:40.643` | `after-run2-splash.jpg` |
| 3 | `10:11:12.093` | `10:11:21.452` | `10:11:21.467` | `after-run3-splash.jpg` |
| 4 (rebuilt zip) | `10:14:25.603` | `10:14:30.791` | `10:14:30.810` | `after-run4-rebuilt-artifact.jpg` |

Each run showed the burst, ring, head, SURPRISE ME plate and B CANCEL, then
disappeared exactly as the log hid it; `Player.GetActivePlayers` returned the
internal audio player. Run 1's video pulled at 5.4 s, 6.0 s and 6.6 s shows
three distinct head angles, proving the 1.2 s spin is painted, not merely
computed. Run 4 was a final smoke after re-pushing the rebuilt
`dist/script.raveplayer.ui-3.9.48.zip`; the installed `window.py`,
`animation.py` and skin XML checksums matched the zip byte-for-byte. Back
returned to window 10000 and the log ended with
`CPythonInvoker(...): script successfully run` — no lingering invoker.

### Before / after

- `before-splash-hidden.jpg` — during `spinner visible=True`, the home screen
  is still fully visible and only the status text says "Spinning…". This is
  the reported bug.
- `after-run1-splash.jpg`, `after-run2-splash.jpg`,
  `after-run3-splash.jpg`, `after-run4-rebuilt-artifact.jpg` — the splash on
  the Shield in four separate runs (run 4 on the rebuilt zip).
- `spin-frame-06.0s.jpg`, `spin-frame-06.6s.jpg` — two captured head angles
  from the 1.2 s reveal.

## Tests and artifacts

```sh
python3 -m unittest discover -s test        # 645 tests, OK
./scripts/build.sh                          # both 3.9.48 zips
./scripts/build-repo.sh                     # repo catalogue + zips
./scripts/check-repo-artifacts.sh           # current and committed
```

The offline suite now asserts that all 14 splash controls use the property
binding, that no splash control uses a literal `false`, and that
`set_spinner_visible()` writes the matching `rp_splash` value.

## Rollback

Revert the splash-fix commit and rebuild/reinstall the previous 3.9.48
artifacts; no data, settings or cache schema changed.

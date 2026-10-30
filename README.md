<p align="center"><img src="doppleganger/assets/logo_dark.png" alt="Doppleganger — A seamless switch." width="420"></p>

**Doppleganger** records a short, seamless loop of you, then lets you switch between that loop and your live webcam in Zoom, Teams or any browser meeting — without anyone noticing. Windows 10/11.

## Install

1. Download **DopplegangerSetup.exe** from the [latest release](https://github.com/busybeavernc/doppleganger/releases/latest) and run it. No admin rights needed. It adds a Start-menu entry, an optional desktop shortcut, and an uninstall entry in *Settings → Apps*.
2. Doppleganger opens with a short **setup guide**:
   1. **Add the Doppleganger camera.** Windows asks for permission once.
   2. **Choose your webcam.**
   3. **Record your first loop.**
   4. **Pick "Doppleganger" as your camera** in Zoom/Teams.

You can reopen the guide any time from the *Setup guide* button. OBS Studio is not needed.

Your loops and settings live in `%APPDATA%\Doppleganger` and are kept if you uninstall. A copy run from its own folder that already contains `config.json` or `loops\` (as earlier versions did) keeps using that folder.

### Updates
Each time it opens, Doppleganger checks the releases. If there's a newer version, it shows an "Updating…" window, swaps itself out and reopens. *Settings → Updates → Check now* checks manually. An update never interrupts you while the LOOP is on air or a recording is running.

### Code signing (self-signed)
Release files are signed with a self-signed "Doppleganger" certificate (`doppleganger-publisher.cer` is attached to each release). Windows only trusts it on PCs that choose to: tick *Trust the Doppleganger publisher on this PC* in the installer, and Windows asks you to confirm. Other PCs still see the SmartScreen "unknown publisher" prompt (**More info → Run anyway**). A commercial code-signing certificate would remove that prompt everywhere; the build already supports one, so just swap the secrets.

## The window

| Area | What it does |
|---|---|
| **LIVE / LOOP** | What Zoom sees right now. LIVE is Aqua, LOOP is Violet; GLITCH appears in amber while a fake bad connection is running. |
| **Sync** | How seamless a cut would be right now (Aqua = in sync). |
| **Cut button** | **Tap:** cut immediately (hard cut). **Hold:** Doppleganger waits and cuts by itself the moment you're in sync; let go first to cancel. The button wears the colour of where you're cutting *to*. |
| **Glitch / Record loop** | See below. |
| **Webcam** | Pick which camera is your live feed (virtual cameras are never offered). |
| **Loops** | Your loop library: thumbnails, names (*Rename*), *Use*, *Delete*. A ⚠ appears when a loop's lighting doesn't match your room right now (darker, brighter, different colour). |
| **Mini bar** | A compact always-on-top strip with a live thumbnail, sync meter, Cut and Glitch, to park beside Zoom. Drag it by the logo; *Full view* brings the window back. |
| **Settings** | Privacy, crossfade, guides, overlay strength, the Doppleganger camera, updates. |

**Hidden from screen sharing:** Doppleganger's windows (main, mini bar, setup, settings) are excluded from screen capture. When you share your screen, viewers see what's behind them. This also hides them from your own screenshots. Turn it off in *Settings → Privacy*.

**Silence while on the LOOP:** loops never contain sound, since Doppleganger only handles video. While the LOOP is on air, Doppleganger also **mutes your microphone** at the Windows level, so nothing you say or no background noise goes out, and unmutes it the moment you cut back to live. It only touches microphones that were unmuted, and if the app is ever closed unexpectedly while muted, your mic is restored the next time it starts. Turn it off in *Settings → Privacy*.

## Hotkeys (work while Zoom is focused)

| Key | Action |
|---|---|
| **F9** | **Tap** = cut now. **Hold** = cut when in sync |
| **F10** | Fake a bad connection (glitch) |
| Space | Same as F9 (tap/hold), while the Doppleganger window is focused |
| R | Record a loop; press again (or Esc) to **cancel** a recording in progress. Nothing is saved |
| B / K / C | Glitch / next webcam / calibrate the room (optional) |
| E | End the recording now (final stretch) |
| O | Show or hide the live (aqua) and loop (violet) **outlines** |
| G / M | Show or hide guides / switch to the mini bar |

The tray icon (by the clock) has the same commands, plus a webcam picker and Install/Remove camera.

## Finding you in the picture (no setup)

Doppleganger uses **AI person detection** (Google's MediaPipe selfie segmentation, the kind of model video-call apps use for background blur) to find you in every frame. It needs no setup, works in any room and with any webcam, and copes with lighting changes. The mask is snapped to real edges in the picture (guided filter, plus GrabCut for the start-pose silhouette), so hair and shoulders get a clean outline.

*Settings → Calibrate room* is still there as an optional fallback, and is used automatically only if the AI model can't run on a PC. Lean or step slowly to the side the banner asks for while it learns what the empty room looks like.

## Recording a loop

| Time (default 90 s) | What you'll see | What to do |
|---|---|---|
| 3 s countdown | "Get in your start pose" | Settle into a comfortable, centered position |
| 0–10 s | **HOLD STILL** + movement meter | No big head or body movement; this becomes the loop's first frame and your silhouette |
| 10–80 s | "Recording – move naturally" | Look at the screen, nod, blink, look like you're listening |
| 80–90 s | "Step back into your silhouette" + first-frame thumbnail + **Match %** | Line up with the silhouette and copy your starting expression; it **glows aqua** when you're back. Hold still |

The app finds the frame in the final seconds that best matches the first, ends the loop there, and adds a few motion-matched bridge frames if needed, so the restart is invisible. The loop starts at its first frame the first time you cut to it, then keeps playing in the background, so later cuts pick it up wherever it is.

## Before you cut

- **Before the first cut**, the loop's start pose shows as a soft violet shape with your aqua outline on top (with outlines on). Line them up ("In start pose – cut is seamless"), then cut, or just *hold* F9 and let Doppleganger cut when you're there. The white silhouette appears only while recording.
- **After that**, the preview shows the off-air feed faded over the on-air one: the loop while you're LIVE, your camera while the LOOP is on air. Line up until the aqua border appears, or hold F9.
- **Outlines** (O, or the checkbox under the sync meter): an aqua line traces you live and a violet line traces the loop, or the frozen picture during a glitch. When the two lines sit on top of each other, the cut is seamless.

## Called on unexpectedly? Fake a bad connection

Press **F10**. Zoom's picture turns jerky and random: frozen frames, uneven bursts, and the occasional sharp in-between frame. It never goes blurry or blocky and never drops out. Your preview keeps the overlay, so you can line up with the frozen picture. Then press (or hold) **F9**: the next jump reveals you live, with a few catch-up steps before it runs smoothly. F10 again also ends it, and it stops by itself after 30 s.

## The Doppleganger camera

A small DirectShow camera filter (64- and 32-bit) installed in `C:\ProgramData\Doppleganger`, built from [softcam](https://github.com/tshino/softcam) (MIT) with its own name and ID, so it never clashes with OBS or other virtual cameras.

Zoom can select it any time. Whenever the Doppleganger app isn't running (not started yet, or quit), the camera shows a neutral dark **"Camera starting…"** picture. It's deliberately generic, because meeting participants can see it, and it's never a frozen frame of you. To make sure the camera always has a real picture, turn on *Settings → Start Doppleganger when Windows starts*; it opens minimized. If it isn't installed, Doppleganger falls back to OBS Virtual Camera (OBS must be installed and closed).

## Settings file

`config.json` in the data folder. Useful fields: `camera_name`, `output_camera` (`auto`/`doppleganger`/`obs`), `width`/`height`/`fps`, `loop_seconds`, `hold_still_seconds`, `return_prompt_seconds`, `crossfade_ms`, `overlay_opacity`, `hotkey`, `glitch_hotkey` (pynput format, e.g. `"<ctrl>+<alt>+l"`), `glitch_max_seconds`, `mute_mic_on_loop`, `hide_from_screen_share`, `auto_update`.

## Development

```
pip install -r requirements.txt pytest
python -m pytest tests
python launcher.py            # run from source (OBS Virtual Camera is used unless the camera DLLs are built)
```

Every push to `main` is built by GitHub Actions (*Build Windows app*). It compiles the camera driver and helpers, packages `Doppleganger.exe`, builds the Inno Setup installer, signs everything when the `SIGNING_CERT_PFX_BASE64` / `SIGNING_CERT_PASSWORD` secrets are set, and publishes a release.

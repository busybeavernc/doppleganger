# Doppleganger

A tiny Windows app that replaces an OBS setup for one job: **record a seamless 1–3 minute loop of yourself before a meeting, then cut between that loop and your live webcam during the meeting.** The result appears in Zoom, Teams, Meet, etc. as a camera.

## Install

1. Keep **OBS Studio** installed. Doppleganger uses OBS's virtual camera *driver*, but OBS itself does not need to be open. If OBS is open, make sure its own **Start Virtual Camera** is off.
2. Download **Doppleganger.exe** from the repo's **Releases** page (newest at the top).
3. Put it in its own folder, e.g. `Documents\Doppleganger`. Your loops and settings are saved next to it.
4. Double-click it. The first time, Windows SmartScreen may warn about an unrecognized app: click **More info → Run anyway**. Right-click the taskbar icon → *Pin to taskbar* for one-click access.

In Zoom, choose **OBS Virtual Camera** as your camera.

No Python or VS Code is needed. Every change pushed to `main` is built automatically by GitHub (Actions → *Build Windows app*) and published as a new release.

### Updates
- **Automatic:** each time you open the app, it checks Releases. If there's a newer version, it shows an "Updating…" window, swaps in the new .exe and reopens. If you're offline, it simply opens as usual.
- **Manual:** right-click the Doppleganger icon by the clock → **Check for updates**, or press **U** in the preview. If a recording is in progress, the update waits until it's finished.
- Turn off automatic checks with `"auto_update": false` in `config.json`.
- **While the repo is private**, the app needs a read-only token to see releases. Create a fine-grained GitHub token with *Contents: Read-only* access to this repo only, and paste it into `config.json` as `"update_token"`. If the repo is public, no token is needed.

### Run from source instead
Install Python 3.10+, then double-click `run.bat`. It creates a `.venv` and installs the requirements on the first run.

## Calibrating the silhouette (once per room)

The first time you press **R**, Doppleganger runs a ~10-second calibration before recording. You can redo it any time with **C** or the tray menu's *Calibrate silhouette*, e.g. after moving the camera or changing the lighting.

Keep facing the camera and lean or step slowly to the side the banner asks for. Red tint marks parts of the room it hasn't seen yet; it fades as you uncover them. It switches sides for you and finishes on its own once about 97% of the room has been seen.

This teaches the app what the empty room looks like (saved as `background.png`). Your silhouette is then cut out by comparing against it, so the outline follows your hair, shoulders and arms instead of guessing, and the green "matched" glow is judged by how well your body shape overlaps the silhouette. Without a calibration it still works, with a rougher outline.

## Recording a loop

Press **R** while LIVE. Then:

| Time (default 90s loop) | What you'll see | What to do |
|---|---|---|
| 3s countdown | "Get in your start pose" | Settle into a comfortable, centered position |
| 0–10s | **HOLD STILL – start pose** + movement meter. Your silhouette is captured from the first frame and stays in the background for the rest of the recording | No big head/body movement |
| 10–80s | "Recording – move naturally" | Look at the screen, nod, blink, look like you're listening |
| 80–90s | "Step back into your silhouette" + first-frame thumbnail + **Match %** meter | Line yourself up with the silhouette and copy your starting expression. The silhouette **glows green** when you're back in position: hold still |

Press **E** in the final stretch to end early once you're matched, or **Esc** to cancel.

### How the seam is hidden
- The app searches the final seconds for the frame that best matches frame 1 and ends the loop there.
- If a small difference remains, it inserts a few **motion-matched bridge frames** (optical-flow morph from the last frame back to the first), so the restart glides instead of jumping. This is not a crossfade.
- Each loop gets a `.json` next to it with the seam difference and number of bridge frames (lower difference = better match).

Loops are saved in `loops/`. The newest one loads automatically.

## During the meeting

| Key | Action |
|---|---|
| **F9** (works even while Zoom is focused) or **Space** | Cut LIVE ↔ LOOP |
| C | Calibrate the silhouette (see above) |
| G | Show/hide the silhouette / off-air overlay (preview only, never sent to Zoom) |
| **F10** or B | Fake bad connection (see below) |
| X | Toggle a 300 ms crossfade on cuts (**off by default** – hard cuts) |
| U | Check for updates |
| Q | Quit |

The tray icon by the clock has the same menu: Cut LIVE/LOOP (also a double-click on the icon), Fake bad connection, Record new loop, Calibrate silhouette, Check for updates, Quit.

**First cut to the loop:** the loop starts at its first frame (your start pose). Before that first cut, the LIVE preview shows the start-pose silhouette. When it glows green ("In start pose – cut is seamless"), cut.

**After that, the loop never restarts.** It keeps playing in the background, so cutting back and forth picks it up wherever it is. The preview then shows the feed that is *not* on air as a faint see-through overlay: the loop while you're LIVE, or your live camera while the LOOP is on air. Line yourself up with it. When the preview gets a green border ("In sync – cut is seamless"), cut. The overlay appears only in your preview, never in Zoom. G hides it; `overlay_opacity` in `config.json` sets its strength (default 0.35).

## Called on unexpectedly? Fake a bad connection

Press **F10** (works while Zoom is focused), **B** in the preview, or *Fake bad connection* in the tray menu.

- Zoom's picture starts freezing for 1–3 seconds at a time, stutters through a few frames now and then, and goes blocky and low-res, like a struggling connection.
- Your preview switches to your live camera so you can get into position. A small "Zoom sees:" inset shows the choppy picture people are seeing.
- When you're ready, press **F9**. The next "jump" reveals you live, then the picture sharpens over about 2 seconds, like the connection coming back.
- Pressing F10 again also ends it. It ends on its own after 30 seconds (`glitch_max_seconds`).

This affects video only. Your microphone is untouched, so if you need a moment, mute until you're live.

## Settings

`config.json` is created on first run. Useful fields: `camera_index`, `width`/`height`/`fps`, `loop_seconds`, `hold_still_seconds`, `return_prompt_seconds`, `crossfade_ms`, `overlay_opacity`, `glitch_hotkey`, `glitch_max_seconds`, `hotkey` (pynput format, e.g. `"<ctrl>+<alt>+l"`).

Command-line shortcuts: `run.bat --camera 1 --seconds 120`, or `run.bat --no-vcam` for preview only.

## Roadmap
- Own "Doppleganger" camera without OBS (Windows 11 Media Foundation virtual camera)
- Automatic cut back to live when you start talking
- Loop library / picker

## Development
```
pip install -r requirements.txt pytest
python -m pytest tests
```

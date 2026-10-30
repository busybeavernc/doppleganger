# Doppleganger

A tiny Windows app that replaces an OBS setup for one job: **record a seamless 1–3 minute loop of yourself before a meeting, then cut between that loop and your live webcam during the meeting.** The result appears in Zoom, Teams, Meet, etc. as a camera.

## Setup (once)

1. Install **Python 3.10+** from python.org (tick "Add python.exe to PATH").
2. Keep **OBS Studio** installed. Doppleganger uses OBS's virtual camera *driver*, but OBS itself does not need to be open. If OBS is open, make sure its own **Start Virtual Camera** is off.
3. Double-click **`run.bat`**. The first run creates a `.venv` and installs the requirements.

In Zoom, choose **OBS Virtual Camera** as your camera.

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
| G | Show/hide the loop's start-pose silhouette while LIVE (preview only, never sent to Zoom) |
| X | Toggle a 300 ms crossfade on cuts (**off by default** – hard cuts) |
| Q | Quit |

By default, cutting to the loop starts it from its first frame. While LIVE, the preview shows the loop's start-pose silhouette. When it glows green ("In start pose – cut is seamless"), cut to the loop and the switch is invisible.

## Settings

`config.json` is created on first run. Useful fields: `camera_index`, `width`/`height`/`fps`, `loop_seconds`, `hold_still_seconds`, `return_prompt_seconds`, `crossfade_ms`, `restart_loop_on_cut`, `hotkey` (pynput format, e.g. `"<ctrl>+<alt>+l"`).

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

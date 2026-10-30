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
| 3s countdown | "Get in your start pose" | Line your head up with the orange center dots |
| 0–10s | **HOLD STILL – start pose** + movement meter | No big head/body movement. This is the loop's first frame |
| 10–80s | "Recording – move naturally" | Look at the screen, nod, blink, look like you're listening |
| 80–90s | Ghost of the first frame + cyan dots where your head was + **Match %** meter + **HOLD STILL** | Return to the same position *and* expression; hold still once the meter is green |

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
| G | Show/hide alignment dots (preview only, never sent to Zoom) |
| X | Toggle a 300 ms crossfade on cuts (**off by default** – hard cuts) |
| Q | Quit |

By default, cutting to the loop starts it from its first frame. Get into your start pose before cutting, so the switch is invisible.

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

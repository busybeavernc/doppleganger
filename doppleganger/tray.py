"""Tray icon (by the clock) with the app's menu. Optional: skipped if pystray isn't installed."""
from __future__ import annotations

from typing import Callable


def start_tray(request: Callable[[str], None], version: str):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(30, 120, 220))
    d.ellipse((20, 14, 44, 38), fill=(255, 255, 255))        # head
    d.pieslice((10, 36, 54, 80), 180, 360, fill=(255, 255, 255))  # shoulders

    item = pystray.MenuItem
    menu = pystray.Menu(
        item("Cut LIVE / LOOP", lambda: request("toggle"), default=True),
        item("Fake bad connection (glitch)", lambda: request("glitch")),
        item("Record new loop", lambda: request("record")),
        item("Calibrate silhouette", lambda: request("calibrate")),
        pystray.Menu.SEPARATOR,
        item("Check for updates", lambda: request("update")),
        item(f"Version {version}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Quit", lambda: request("quit")),
    )
    icon = pystray.Icon("Doppleganger", img, "Doppleganger", menu)
    icon.run_detached()
    return icon

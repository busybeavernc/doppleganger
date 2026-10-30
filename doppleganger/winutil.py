"""Windows-only helpers. Everything is a no-op elsewhere."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("doppleganger")

WDA_NONE = 0x0
WDA_MONITOR = 0x1
WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+: window is invisible to screen sharing/recording


def toplevel_hwnd(widget) -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    hwnd = widget.winfo_id()
    return ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT


def hide_from_capture(widget, hide: bool = True) -> bool:
    """Exclude a window from screen sharing / screenshots (you still see it; viewers don't).
    Returns True if Windows accepted it."""
    hwnd = toplevel_hwnd(widget)
    if not hwnd:
        return False
    import ctypes
    user32 = ctypes.windll.user32
    if not hide:
        return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_NONE))
    if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        return True
    # Older Windows: the window shows as a black box in captures instead of disappearing.
    ok = bool(user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR))
    log.info("Exclude-from-capture unavailable; using black-box fallback: %s", ok)
    return ok

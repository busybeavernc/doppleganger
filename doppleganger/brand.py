"""Doppleganger brand: "A seamless switch."

Palette (from the brand sheet):
  Midnight #111827   Violet #7C3AED   Aqua #2DD4BF   Cloud #F8FAFC
Usage: LIVE = Aqua, LOOP = Violet. The cut button wears the colour of where you're cutting TO.
"""
from __future__ import annotations

import os
import sys

TAGLINE = "A seamless switch."

MIDNIGHT = "#111827"
VIOLET = "#7C3AED"
AQUA = "#2DD4BF"
CLOUD = "#F8FAFC"

# supporting shades (derived)
SURFACE = "#1A2233"       # panels on Midnight
SURFACE_HI = "#243049"    # hover / selected
BORDER = "#2C3852"
MUTED = "#94A3B8"
VIOLET_DARK = "#5B21B6"
AQUA_DARK = "#0F766E"
AMBER = "#F59E0B"         # glitch / warnings (functional, not a brand colour)
DANGER = "#F87171"


def bgr(hex_color: str) -> tuple[int, int, int]:
    """'#RRGGBB' -> OpenCV (B, G, R)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return b, g, r


# OpenCV colours for the preview overlays
CV_AQUA = bgr(AQUA)
CV_VIOLET = bgr(VIOLET)
CV_VIOLET_DARK = bgr(VIOLET_DARK)
CV_AQUA_DARK = bgr(AQUA_DARK)
CV_AMBER = bgr(AMBER)
CV_MIDNIGHT = bgr(MIDNIGHT)
CV_DANGER = bgr(DANGER)


def asset(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(base, "doppleganger", "assets", name), os.path.join(base, "assets", name)):
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)

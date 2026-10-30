"""Live / loop subject outlines for lining up a cut.

Each outline is "what differs from the calibrated empty room", traced at a small
size (cheap enough for every frame), smoothed, and scaled up to the preview.
Live = Aqua, loop = Violet: when the two lines sit on top of each other, you're in sync.
"""
from __future__ import annotations

import cv2
import numpy as np

from .calibrate import split_background

TRACE_WIDTH = 320


class OutlineTracer:
    def __init__(self, background: np.ndarray):
        bg, known = split_background(background)
        h = round(bg.shape[0] * TRACE_WIDTH / bg.shape[1])
        self.size = (TRACE_WIDTH, h)
        self.bg_lab = cv2.cvtColor(cv2.resize(bg, self.size, interpolation=cv2.INTER_AREA),
                                   cv2.COLOR_BGR2LAB).astype(np.float32)
        self.known = cv2.resize(known.astype(np.uint8), self.size, interpolation=cv2.INTER_NEAREST) > 0

    def mask(self, frame: np.ndarray) -> np.ndarray:
        """Person mask (uint8 0/255) at trace size."""
        lab = cv2.cvtColor(cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA),
                           cv2.COLOR_BGR2LAB).astype(np.float32)
        d = lab - self.bg_lab
        diff = np.sqrt(0.35 * d[..., 0] ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)
        diff = cv2.GaussianBlur(diff, (5, 5), 0)
        # where the room was never seen, we can't tell - lean towards "person" so the outline closes
        m = ((diff > 14) | (~self.known & (diff > 6))).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        return m

    def contour(self, frame: np.ndarray, out_size: tuple[int, int], mirrored: bool) -> np.ndarray | None:
        """Outline of the largest person-shaped blob, in preview pixel coordinates."""
        m = self.mask(frame)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) < 0.03 * m.shape[0] * m.shape[1]:
            return None
        c = cv2.approxPolyDP(c, 1.0, True).astype(np.float32)
        sx, sy = out_size[0] / self.size[0], out_size[1] / self.size[1]
        c[..., 0] *= sx
        c[..., 1] *= sy
        if mirrored:
            c[..., 0] = out_size[0] - 1 - c[..., 0]
        return c.astype(np.int32)


def draw(img: np.ndarray, contour: np.ndarray | None, color, thickness: int = 2) -> None:
    if contour is None:
        return
    cv2.polylines(img, [contour], True, (17, 24, 39), thickness + 3, cv2.LINE_AA)  # dark edge = readable on any background
    cv2.polylines(img, [contour], True, color, thickness, cv2.LINE_AA)

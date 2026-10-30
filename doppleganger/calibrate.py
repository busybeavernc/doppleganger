"""Background calibration: learn what the room looks like without you in it.

You lean or step slowly to one side, then the other. For every pixel, the app
keeps only the moments when you were NOT covering it (judged from your face
position), and takes the median of those - that's the empty background.
With a clean background, the silhouette is simply "what differs from it".
"""
from __future__ import annotations

import time
import warnings

import cv2
import numpy as np

from .guides import Box, detect_face

CALIB_WIDTH = 320
MAX_SAMPLES = 90


def person_zone(face: Box, shape) -> np.ndarray:
    """Generous region a seated person probably covers, given their face box. True = covered."""
    h, w = shape[:2]
    fx, fy, fw, fh = face
    zone = np.zeros((h, w), bool)
    x0, x1 = max(0, int(fx - 1.5 * fw)), min(w, int(fx + fw + 1.5 * fw))
    zone[max(0, int(fy - 0.8 * fh)):, x0:x1] = True
    return zone


class Calibrator:
    def __init__(self, min_seconds: float = 4.0, max_seconds: float = 15.0, target: float = 0.97):
        self.min_seconds, self.max_seconds, self.target = min_seconds, max_seconds, target
        self.t0 = time.monotonic()
        self.frames: list[np.ndarray] = []
        self.valid: list[np.ndarray] = []
        self.seen: np.ndarray | None = None
        self.face_visible = True
        self._tick = 0
        self._stride = 2

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    @property
    def coverage(self) -> float:
        """Fraction of the picture seen without you in front of it."""
        return 0.0 if self.seen is None else float(self.seen.mean())

    def add(self, frame: np.ndarray, face: Box | None = None, detect: bool = True) -> None:
        self._tick += 1
        if self._tick % self._stride:  # sample every Nth frame
            return
        s = CALIB_WIDTH / frame.shape[1]
        small = cv2.resize(frame, (CALIB_WIDTH, int(round(frame.shape[0] * s))), interpolation=cv2.INTER_AREA)
        if face is None and detect:
            face = detect_face(small)
        self.face_visible = face is not None
        if face is None:
            return
        valid = ~person_zone(face, small.shape)
        if len(self.frames) >= MAX_SAMPLES:  # thin out evenly, keeping a spread over the whole calibration
            self.frames, self.valid = self.frames[::2], self.valid[::2]
            self._stride *= 2
        self.frames.append(small)
        self.valid.append(valid)
        self.seen = valid.copy() if self.seen is None else (self.seen | valid)

    def side_needed(self) -> str | None:
        """Which half of the (unmirrored) image is least uncovered: 'left', 'right' or None."""
        if self.seen is None:
            return "left"
        half = self.seen.shape[1] // 2
        left, right = self.seen[:, :half].mean(), self.seen[:, half:].mean()
        if min(left, right) >= self.target:
            return None
        return "left" if left <= right else "right"

    def done(self) -> bool:
        t = self.elapsed
        return t >= self.max_seconds or (t >= self.min_seconds and self.coverage >= self.target
                                         and len(self.frames) >= 10)

    def background(self) -> np.ndarray | None:
        """Empty-room image as BGRA: alpha 255 where the room was actually seen, 0 where you always covered it."""
        if len(self.frames) < 3:
            return None
        f = np.stack(self.frames).astype(np.float32)
        v = np.stack(self.valid)
        masked = np.where(v[..., None], f, np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            bg = np.nanmedian(masked, axis=0)
        known = v.any(axis=0)
        bg[~known] = np.median(f, axis=0)[~known]
        bgra = np.dstack([np.clip(bg, 0, 255).astype(np.uint8), np.where(known, 255, 0).astype(np.uint8)])
        return bgra


def split_background(bg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(BGR image, known-mask bool) from a BGRA or BGR background."""
    if bg.ndim == 3 and bg.shape[2] == 4:
        return np.ascontiguousarray(bg[..., :3]), bg[..., 3] > 127
    return bg, np.ones(bg.shape[:2], bool)


def lab_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-pixel colour difference, less sensitive to brightness changes (shadows, auto-exposure)."""
    la = cv2.cvtColor(a, cv2.COLOR_BGR2LAB).astype(np.float32)
    lb = cv2.cvtColor(b, cv2.COLOR_BGR2LAB).astype(np.float32)
    d = la - lb
    return np.sqrt(0.35 * d[..., 0] ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)

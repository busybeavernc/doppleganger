"""Fake bad connection: freezes, sudden jumps, short stutters and blocky low-res frames.

Typical use: you're on the LOOP and get called on. Press the glitch hotkey; Zoom
sees a frozen, choppy picture while you get into position; press the cut hotkey
and the next "jump" reveals you live, then the picture recovers like a connection
coming back.
"""
from __future__ import annotations

import random

import cv2
import numpy as np


class Glitch:
    def __init__(self, max_seconds: float = 30.0, recover_seconds: float = 2.0, seed: int | None = None):
        self.max_seconds = max_seconds
        self.recover_seconds = recover_seconds
        self.rng = random.Random(seed)
        self.active = False
        self.recovering = False
        self._held: np.ndarray | None = None
        self._next_change = 0.0
        self._burst = 0
        self._t0 = 0.0
        self._recover_start = 0.0

    # ---------- control ----------
    def start(self, now: float) -> None:
        self.active, self.recovering = True, False
        self._t0 = now
        self._held = None
        self._burst = 0
        # first symptom: a short stutter, then the freezes begin
        self._next_change = now

    def recover(self, now: float, delay: float = 0.0) -> None:
        """Begin 'connection coming back' (after `delay` seconds)."""
        if self.active and not self.recovering:
            self.recovering = True
            self._recover_start = now + delay
            # make sure the next jump (which reveals the new picture) comes soon
            self._next_change = min(self._next_change, now + delay + self.rng.uniform(0.15, 0.5))

    def toggle(self, now: float) -> None:
        if not self.active:
            self.start(now)
        else:
            self.recover(now)

    # ---------- per frame ----------
    def process(self, frame: np.ndarray, now: float) -> np.ndarray:
        if not self.active:
            return frame
        if not self.recovering and now - self._t0 >= self.max_seconds:
            self.recover(now)
        if self.recovering and now >= self._recover_start + self.recover_seconds:
            self.active = self.recovering = False
            self._held = None
            return frame

        if self._held is None or now >= self._next_change:
            self._held = self._degrade(frame, self._quality(now))
            self._next_change = now + self._hold_time(now)
        return self._held

    def _quality(self, now: float) -> float:
        """0 = very blocky, 1 = clean."""
        if self.recovering and now >= self._recover_start:
            return min(1.0, (now - self._recover_start) / self.recover_seconds + 0.25)
        return self.rng.uniform(0.0, 0.55)

    def _hold_time(self, now: float) -> float:
        r = self.rng
        if self.recovering and now >= self._recover_start:
            return r.uniform(0.04, 0.25)  # catching up: quick, slightly uneven frames
        if self._burst > 0:
            self._burst -= 1
            return r.uniform(0.06, 0.2)  # a few frames get through...
        if r.random() < 0.3:
            self._burst = r.randint(2, 5)
            return r.uniform(0.06, 0.2)
        return r.uniform(0.8, 2.8)  # ...then it freezes again

    def _degrade(self, frame: np.ndarray, quality: float) -> np.ndarray:
        if quality >= 0.97:
            return frame
        h, w = frame.shape[:2]
        # Low bitrate look: tiny resolution, blocky upscale, a bit of colour banding.
        factor = 4 + (1 - quality) * 14  # downscale by 4x .. 18x
        sw, sh = max(8, int(w / factor)), max(6, int(h / factor))
        small = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA)
        interp = cv2.INTER_NEAREST if quality < 0.45 else cv2.INTER_LINEAR
        out = cv2.resize(small, (w, h), interpolation=interp)
        if quality < 0.6:
            levels = 12 + int(quality * 40)
            out = ((out.astype(np.int16) // (256 // levels)) * (256 // levels)).astype(np.uint8)
        return out

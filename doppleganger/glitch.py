"""Fake bad connection: the picture freezes, then jumps - jerky and random.

What Zoom sees while glitching:
- frozen frames held for random lengths (short hiccups and longer stalls)
- some jumps land on a frozen *in-between* frame (a sharp motion-based midpoint
  between the previous picture and the new one), like a decoder catching up
- bursts of a few uneven updates between stalls
The picture is never blurred, pixelated, or blanked - always a full, sharp frame.

Typical use: you're on the LOOP and get called on. Press the glitch hotkey; while
Zoom sees a frozen, jerky picture you get into position; press the cut hotkey and
the next jump reveals you live (a clean jump - never a mix of loop and live), then
a few uneven catch-up steps and it runs smoothly again.
"""
from __future__ import annotations

import random

import numpy as np

from .stitch import morph


class Glitch:
    def __init__(self, max_seconds: float = 30.0, recover_seconds: float = 1.5, seed: int | None = None,
                 interpolate=morph):
        self.max_seconds = max_seconds
        self.recover_seconds = recover_seconds
        self.rng = random.Random(seed)
        self.interpolate = interpolate
        self.active = False
        self.recovering = False
        self._held: np.ndarray | None = None
        self._held_raw: np.ndarray | None = None  # last real (non-interpolated) frame shown
        self._next_change = 0.0
        self._burst = 0
        self._t0 = 0.0
        self._recover_start = 0.0
        self._clean_jump = False

    # ---------- control ----------
    def start(self, now: float) -> None:
        self.active, self.recovering = True, False
        self._t0 = now
        self._held = self._held_raw = None
        self._burst = 0
        self._next_change = now  # freeze on the very next frame

    def recover(self, now: float, delay: float = 0.0, clean_jump: bool = False) -> None:
        """Begin 'connection coming back' (after `delay` seconds).
        `clean_jump`: the next jump must show the new picture as-is (used when the
        source was just cut, so loop and live are never mixed)."""
        if self.active and not self.recovering:
            self.recovering = True
            self._recover_start = now + delay
            self._clean_jump = clean_jump
            # the next jump (which reveals the current picture) comes soon
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
            self._held = self._held_raw = None
            return frame
        if self._held is None:
            self._held = self._held_raw = frame
            self._next_change = now + self._hold_time(now)
        elif now >= self._next_change:
            self._held = self._jump(frame, now)
            self._next_change = now + self._hold_time(now)
        return self._held

    def _jump(self, frame: np.ndarray, now: float) -> np.ndarray:
        prev = self._held_raw
        self._held_raw = frame
        if self._clean_jump:
            self._clean_jump = False
            return frame
        catching_up = self.recovering and now >= self._recover_start
        chance = 0.15 if catching_up else 0.4
        if prev is not None and prev.shape == frame.shape and self.rng.random() < chance:
            # land part-way: a frozen in-between frame; the real frame shows on a later jump
            self._held_raw = prev
            return self.interpolate(prev, frame, self.rng.uniform(0.35, 0.75))
        return frame

    def _hold_time(self, now: float) -> float:
        r = self.rng
        if self.recovering and now >= self._recover_start:
            return r.uniform(0.05, 0.3)   # catching up: quick, uneven steps
        if self._burst > 0:
            self._burst -= 1
            return r.uniform(0.07, 0.25)  # a few uneven updates get through...
        roll = r.random()
        if roll < 0.25:
            self._burst = r.randint(2, 4)
            return r.uniform(0.07, 0.25)
        if roll < 0.55:
            return r.uniform(0.3, 0.8)    # short hiccup
        return r.uniform(0.9, 2.6)        # ...then a proper stall

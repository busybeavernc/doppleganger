"""Tap vs hold on the cut key.

- Tap (released within HOLD_SECONDS): hard cut immediately on release.
- Hold: "armed" - the cut happens by itself the moment live and the target
  picture are in sync. Let go before that and nothing happens.
"""
from __future__ import annotations

HOLD_SECONDS = 0.35
SYNC_THRESHOLD = 0.82


class CutController:
    def __init__(self, hold_seconds: float = HOLD_SECONDS, threshold: float = SYNC_THRESHOLD):
        self.hold_seconds = hold_seconds
        self.threshold = threshold
        self.pressed_at: float | None = None
        self.armed = False

    @property
    def waiting(self) -> bool:
        """True while held down and waiting for sync (for the UI)."""
        return self.armed

    def press(self, now: float) -> None:
        if self.pressed_at is None:  # ignore key auto-repeat
            self.pressed_at = now
            self.armed = False

    def tick(self, now: float, sync: float) -> str | None:
        """Call every frame. Returns "cut" when a held press reaches sync."""
        if self.pressed_at is None:
            return None
        if not self.armed and now - self.pressed_at >= self.hold_seconds:
            self.armed = True
        if self.armed and sync >= self.threshold:
            self._reset()
            return "cut"
        return None

    def release(self, now: float) -> str | None:
        """Returns "cut" for a tap, "cancel" for a hold that never reached sync, None otherwise."""
        if self.pressed_at is None:
            return None  # already cut while held, or a stray release
        held = now - self.pressed_at
        was_armed = self.armed
        self._reset()
        if was_armed or held >= self.hold_seconds:
            return "cancel"
        return "cut"

    def _reset(self) -> None:
        self.pressed_at = None
        self.armed = False

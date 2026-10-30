"""Global hotkeys with key-down AND key-up (needed for hold-to-sync), working while Zoom is focused."""
from __future__ import annotations

import logging
from typing import Callable, Hashable

log = logging.getLogger("doppleganger")

Callback = Callable[[], None]


class ComboTracker:
    """Pure state machine: which hotkey combos are currently held. Keys are any hashables."""

    def __init__(self):
        self.combos: dict[str, tuple[frozenset, Callback, Callback | None]] = {}
        self.pressed: set = set()
        self.active: set[str] = set()

    def add(self, name: str, keys: frozenset, on_press: Callback, on_release: Callback | None = None):
        self.combos[name] = (keys, on_press, on_release)

    def press(self, key: Hashable) -> None:
        self.pressed.add(key)
        for name, (keys, on_press, _) in self.combos.items():
            if name not in self.active and keys <= self.pressed:
                self.active.add(name)  # auto-repeat presses don't fire again
                on_press()

    def release(self, key: Hashable) -> None:
        for name in list(self.active):
            keys, _, on_release = self.combos[name]
            if key in keys:
                self.active.discard(name)
                if on_release:
                    on_release()
        self.pressed.discard(key)


class GlobalHotkeys:
    """pynput keyboard listener feeding a ComboTracker. Spec format: "<f9>", "<ctrl>+<alt>+l"."""

    def __init__(self, bindings: dict[str, tuple[Callback, Callback | None]]):
        from pynput import keyboard
        self._kb = keyboard
        self.tracker = ComboTracker()
        for spec, (on_press, on_release) in bindings.items():
            keys = frozenset(keyboard.HotKey.parse(spec))
            self.tracker.add(spec, keys, on_press, on_release)
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)

    def _canon(self, key):
        return self.listener.canonical(key)

    def _press(self, key):
        try:
            self.tracker.press(self._canon(key))
        except Exception:  # noqa: BLE001 - never let a hotkey error kill the listener
            log.exception("hotkey press")

    def _release(self, key):
        try:
            self.tracker.release(self._canon(key))
        except Exception:  # noqa: BLE001
            log.exception("hotkey release")

    def start(self) -> None:
        self.listener.start()

    def stop(self) -> None:
        self.listener.stop()

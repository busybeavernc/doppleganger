"""Doppleganger main window.

Keys (preview window focused):
  SPACE  cut between LIVE and LOOP        (also the global hotkey, default F9)
  R      record a new loop                ESC  cancel recording
  E      end recording now (only in the final return zone)
  G      show/hide alignment dots         X    toggle crossfade on cuts
  Q      quit
"""
from __future__ import annotations

import argparse
import os
import threading
import time

import cv2
import numpy as np

from . import guides
from .camera import Camera
from .config import Config
from .player import LoopPlayer, latest_loop
from .recorder import Recorder, State

WINDOW = "Doppleganger"


class Output:
    """Virtual camera (OBS Virtual Camera driver) with a graceful fallback."""

    def __init__(self, cfg: Config, enabled: bool):
        self.cam = None
        self.error = ""
        if not enabled:
            return
        try:
            import pyvirtualcam
            self.cam = pyvirtualcam.Camera(cfg.width, cfg.height, cfg.fps,
                                           fmt=pyvirtualcam.PixelFormat.BGR, backend="obs")
        except Exception as e:  # noqa: BLE001
            self.error = (f"Virtual camera unavailable ({e}). Install OBS Studio and make sure "
                          "OBS's own 'Start Virtual Camera' is OFF.")

    def send(self, frame: np.ndarray) -> None:
        if self.cam:
            self.cam.send(frame)

    def close(self) -> None:
        if self.cam:
            self.cam.close()


class App:
    def __init__(self, cfg: Config, vcam: bool, config_path: str):
        self.cfg = cfg
        self.config_path = config_path
        self.camera = Camera(cfg.camera_index, cfg.width, cfg.height, cfg.fps)
        self.output = Output(cfg, vcam)
        self.recorder = Recorder(cfg)
        self.mode = "live"
        self.fade_from: str | None = None
        self.fade_start = 0.0
        self.player: LoopPlayer | None = None
        self.toast = self.output.error
        self.toast_until = time.monotonic() + (15 if self.toast else 0)
        self._toggle_requested = threading.Event()
        path = latest_loop(cfg.loops_dir)
        if path:
            self._load_loop(path)
        self._start_global_hotkey()

    # ---------- setup ----------
    def _load_loop(self, path: str) -> None:
        if self.player:
            self.player.close()
        self.player = LoopPlayer(path, (self.cfg.width, self.cfg.height))
        self.notify(f"Loop loaded: {os.path.basename(path)}")

    def _start_global_hotkey(self) -> None:
        try:
            from pynput import keyboard
            self._hk = keyboard.GlobalHotKeys({self.cfg.hotkey: self._toggle_requested.set})
            self._hk.start()
        except Exception as e:  # noqa: BLE001
            self._hk = None
            print(f"Global hotkey disabled: {e}")

    def notify(self, msg: str, secs: float = 4.0) -> None:
        self.toast, self.toast_until = msg, time.monotonic() + secs

    # ---------- actions ----------
    def toggle(self) -> None:
        if self.player is None:
            self.notify("No loop yet - press R to record one.")
            return
        new = "loop" if self.mode == "live" else "live"
        if new == "loop" and self.cfg.restart_loop_on_cut:
            self.player.restart()
        if self.cfg.crossfade_ms > 0:
            self.fade_from, self.fade_start = self.mode, time.monotonic()
        self.mode = new

    # ---------- main loop ----------
    def run(self) -> None:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, 960, 540)
        frame_dt = 1.0 / self.cfg.fps
        next_t = time.monotonic()
        live = None
        while live is None:
            live = self.camera.latest()
            time.sleep(0.01)
        try:
            while True:
                fresh = self.camera.latest()
                if fresh is not None:
                    live = fresh
                self.recorder.update(live)
                if self.recorder.result_path:
                    self._load_loop(self.recorder.result_path)
                    self.recorder.result_path = None

                out = self._compose(live)
                self.output.send(out)

                if not self._ui(out, live):
                    break
                if self._toggle_requested.is_set():
                    self._toggle_requested.clear()
                    self.toggle()

                next_t += frame_dt
                delay = next_t - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.monotonic()
        finally:
            self.close()

    def _source(self, which: str, live: np.ndarray) -> np.ndarray:
        if which == "loop" and self.player is not None:
            f = self.player.next_frame()
            if f is not None:
                return f
        return live

    def _compose(self, live: np.ndarray) -> np.ndarray:
        cur = self._source(self.mode, live)
        if self.fade_from and self.cfg.crossfade_ms > 0:
            t = (time.monotonic() - self.fade_start) * 1000 / self.cfg.crossfade_ms
            if t >= 1:
                self.fade_from = None
            else:
                prev = live if self.fade_from == "live" else self.player._last
                if prev is not None:
                    return cv2.addWeighted(prev, 1 - t, cur, t, 0)
        return cur

    def _ui(self, out: np.ndarray, live: np.ndarray) -> bool:
        cfg = self.cfg
        recording = self.recorder.state in (State.COUNTDOWN, State.RECORDING)
        # While recording, the preview shows the live camera (what's being recorded).
        base = live if recording else out
        prev = cv2.flip(base, 1) if cfg.mirror_preview else base.copy()
        if cfg.show_guides and (recording or self.mode == "live"):
            guides.draw_dot_grid(prev)
        prev = self.recorder.draw(prev, cfg.mirror_preview)

        h, w = prev.shape[:2]
        tag, color = ("LIVE", (0, 170, 0)) if self.mode == "live" else ("LOOP", (0, 0, 210))
        cv2.rectangle(prev, (w - 120, 10), (w - 10, 50), color, -1)
        guides.put_text(prev, tag, (w - 100, 42), 0.9)
        if not recording:
            fade = f"crossfade {cfg.crossfade_ms}ms" if cfg.crossfade_ms else "hard cut"
            guides.put_text(prev, f"SPACE/{cfg.hotkey.strip('<>').upper()} cut ({fade})  R record  "
                                  f"G dots  X fade  Q quit", (12, h - 14), 0.5)
        msg = self.recorder.message if self.recorder.state == State.PROCESSING else ""
        if not msg and time.monotonic() < self.toast_until:
            msg = self.toast
        if msg:
            guides.put_text(prev, msg, (12, 30), 0.6, (180, 255, 255))
        if self.recorder.message and self.recorder.state == State.IDLE:
            self.notify(self.recorder.message)
            self.recorder.message = ""

        cv2.imshow(WINDOW, prev)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            return False
        if key == ord(" "):
            self.toggle()
        elif key in (ord("r"), ord("R")):
            if self.mode == "loop":
                self.notify("Cut back to LIVE before recording.")
            else:
                self.recorder.start()
        elif key == 27:
            self.recorder.cancel()
        elif key in (ord("e"), ord("E")):
            self.recorder.end_now()
        elif key in (ord("g"), ord("G")):
            cfg.show_guides = not cfg.show_guides
            cfg.save(self.config_path)
        elif key in (ord("x"), ord("X")):
            cfg.crossfade_ms = 0 if cfg.crossfade_ms else 300
            cfg.save(self.config_path)
            self.notify("Crossfade " + ("ON (300ms)" if cfg.crossfade_ms else "OFF - hard cuts"))
        return True

    def close(self) -> None:
        if getattr(self, "_hk", None):
            self._hk.stop()
        self.camera.close()
        self.output.close()
        if self.player:
            self.player.close()
        cv2.destroyAllWindows()


def main() -> None:
    ap = argparse.ArgumentParser(description="Doppleganger - loop/live virtual camera")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--camera", type=int, help="webcam index (0, 1, ...)")
    ap.add_argument("--seconds", type=float, help="loop length in seconds")
    ap.add_argument("--no-vcam", action="store_true", help="preview only, no virtual camera")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.seconds is not None:
        cfg.loop_seconds = args.seconds
    if not os.path.exists(args.config):
        cfg.save(args.config)
    App(cfg, vcam=not args.no_vcam, config_path=args.config).run()

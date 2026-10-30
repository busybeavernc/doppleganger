"""Doppleganger main window.

Keys (preview window focused):
  SPACE  cut between LIVE and LOOP        (also the global hotkey, default F9)
  R      record a new loop                ESC  cancel recording
  E      end recording now (only in the final return zone)
  G      show/hide start-pose silhouette  X    toggle crossfade on cuts
  Q      quit
"""
from __future__ import annotations

import argparse
import logging
import os
import queue
import threading
import time

import cv2
import numpy as np

from . import guides
from .camera import Camera
from .config import Config
from .player import LoopPlayer, latest_loop
from . import updater
from .recorder import Recorder, State
from .tray import start_tray
from .silhouette import Silhouette, glow_amount

WINDOW = "Doppleganger"
log = logging.getLogger("doppleganger")


class Output:
    """Sends frames to the OBS Virtual Camera driver.

    If it can't connect (OBS not installed, or OBS's own virtual camera is already
    running and holding the camera), it keeps retrying every few seconds and the
    preview shows why, so the problem is never silent.
    """

    RETRY_SECONDS = 3.0

    def __init__(self, cfg: Config, enabled: bool):
        self.cfg = cfg
        self.enabled = enabled
        self.cam = None
        self.error = "" if enabled else "Virtual camera disabled (--no-vcam)"
        self.device = ""
        self._next_try = 0.0
        self._last_logged = ""
        self._connect()

    def _connect(self) -> None:
        self._next_try = time.monotonic() + self.RETRY_SECONDS
        try:
            import pyvirtualcam
            self.cam = pyvirtualcam.Camera(self.cfg.width, self.cfg.height, self.cfg.fps,
                                           fmt=pyvirtualcam.PixelFormat.BGR, backend="obs")
            self.device, self.error = self.cam.device, ""
            log.info("Virtual camera connected: %s", self.device)
        except Exception as e:  # noqa: BLE001
            self.cam = None
            self.error = _explain_vcam_error(str(e))
            if self.error != self._last_logged:  # log each distinct problem once
                log.warning("Virtual camera not connected: %s", e)
                self._last_logged = self.error

    @property
    def connected(self) -> bool:
        return self.cam is not None

    def send(self, frame: np.ndarray) -> None:
        if self.cam is None:
            if self.enabled and time.monotonic() >= self._next_try:
                self._connect()
            return
        try:
            self.cam.send(frame)
        except Exception as e:  # noqa: BLE001
            log.warning("Virtual camera send failed: %s", e)
            self.close()
            self.error = "Lost connection to OBS Virtual Camera - reconnecting..."

    def close(self) -> None:
        if self.cam:
            try:
                self.cam.close()
            except Exception:  # noqa: BLE001
                pass
            self.cam = None


def _explain_vcam_error(msg: str) -> str:
    m = msg.lower()
    if "not installed" in m:
        return "OBS Virtual Camera driver not found - install OBS Studio (it doesn't need to be open)"
    if "could not be started" in m or "in use" in m or "already" in m:
        return "OBS Virtual Camera is busy - in OBS click 'Stop Virtual Camera' (or close OBS)"
    return f"Virtual camera not connected: {msg}"


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
        self.loop_sil: Silhouette | None = None
        self.loop_matcher: guides.PoseMatcher | None = None
        self.loop_running = False   # becomes True on the first cut to the loop
        self._sync = 0.0            # how well live and the current loop frame line up
        self.toast = ""
        self.toast_until = 0.0
        self._actions: queue.Queue[str] = queue.Queue()  # from hotkey, tray menu, update thread
        self._pending_update: str | None = None
        self._updating = False
        path = latest_loop(cfg.loops_dir)
        if path:
            self._load_loop(path)
        self._start_global_hotkey()
        self._tray = start_tray(self._actions.put, updater.current_version())

    # ---------- setup ----------
    def _load_loop(self, path: str) -> None:
        if self.player:
            self.player.close()
        self.player = LoopPlayer(path, (self.cfg.width, self.cfg.height))
        self.loop_running = False
        self._sync = 0.0
        # Start-pose silhouette + matcher, so LIVE preview shows when a cut to the loop will be invisible.
        self.loop_sil = Silhouette.load(path + ".mask.png") if os.path.exists(path + ".mask.png") else None
        first = self.player.first_frame
        self.loop_matcher = None
        if first is not None:
            weight = self.loop_sil.weight_small if self.loop_sil else None
            self.loop_matcher = guides.PoseMatcher(first, weight=weight)
        self.notify(f"Loop loaded: {os.path.basename(path)}")

    def _start_global_hotkey(self) -> None:
        try:
            from pynput import keyboard
            self._hk = keyboard.GlobalHotKeys({self.cfg.hotkey: lambda: self._actions.put("toggle")})
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
        if new == "loop" and not self.loop_running:
            # First activation starts at frame 1 (your start pose). From then on the loop
            # keeps playing in the background and is never restarted by a cut.
            self.player.restart()
            self.loop_running = True
        if self.cfg.crossfade_ms > 0:
            self.fade_from, self.fade_start = self.mode, time.monotonic()
        self.mode = new

    def record(self) -> None:
        if self.mode == "loop":
            self.notify("Cut back to LIVE before recording.")
        else:
            self.recorder.start()

    def check_for_updates(self) -> None:
        """Manual check (menu item / U key). Runs in the background; never blocks the camera."""
        if self._updating:
            return
        if not updater.can_self_update():
            self.notify("Updates are available in the installed Doppleganger.exe only.")
            return
        self._updating = True
        self.notify("Checking for updates...", 30)

        def work():
            try:
                rel = updater.check(self.cfg.update_repo, self.cfg.update_token)
                if rel is None:
                    self.notify(f"You're up to date (v{updater.current_version()}).")
                    return
                self.notify(f"Downloading v{rel.version}...", 600)
                path = updater.download(rel, self.cfg.update_token,
                                        lambda p: self.notify(f"Downloading v{rel.version}... {int(p * 100)}%", 600))
                self._pending_update = path
                self._actions.put("apply_update")
            except updater.UpdateError as e:
                self.notify(f"Update check failed: {e}", 8)
            finally:
                self._updating = False

        threading.Thread(target=work, daemon=True).start()

    def _handle_actions(self) -> bool:
        """Run queued actions on the main thread. False = quit."""
        while not self._actions.empty():
            a = self._actions.get_nowait()
            if a == "toggle":
                self.toggle()
            elif a == "record":
                self.record()
            elif a == "update":
                self.check_for_updates()
            elif a == "quit":
                return False
            elif a == "apply_update" and self._pending_update:
                if self.recorder.state != State.IDLE:
                    self.notify("Update downloaded - it will install when this recording finishes.", 10)
                    threading.Timer(2.0, self._actions.put, ("apply_update",)).start()
                    continue
                self.close()
                updater.apply_and_restart(self._pending_update)
        return True

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

                # Once activated, the loop advances every frame whether or not it's on air.
                loop_frame = self.player.next_frame() if (self.loop_running and self.player) else None
                out = self._compose(live, loop_frame)
                self.output.send(out)

                if not self._ui(out, live, loop_frame) or not self._handle_actions():
                    break

                next_t += frame_dt
                delay = next_t - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.monotonic()
        finally:
            self.close()

    def _compose(self, live: np.ndarray, loop_frame: np.ndarray | None) -> np.ndarray:
        cur = loop_frame if (self.mode == "loop" and loop_frame is not None) else live
        if self.fade_from and self.cfg.crossfade_ms > 0:
            t = (time.monotonic() - self.fade_start) * 1000 / self.cfg.crossfade_ms
            if t >= 1:
                self.fade_from = None
            else:
                prev = live if self.fade_from == "live" else loop_frame
                if prev is not None:
                    return cv2.addWeighted(prev, 1 - t, cur, t, 0)
        return cur

    def _draw_offair_overlay(self, prev: np.ndarray, live: np.ndarray, loop_frame: np.ndarray) -> np.ndarray:
        """Ghost the feed that's NOT on air over the preview, so you can line up before cutting back."""
        cfg = self.cfg
        other = loop_frame if self.mode == "live" else live
        ghost = cv2.flip(other, 1) if cfg.mirror_preview else other
        prev = cv2.addWeighted(prev, 1 - cfg.overlay_opacity, ghost, cfg.overlay_opacity, 0)
        weight = self.loop_sil.weight_small if self.loop_sil is not None else None
        diff = guides.frame_diff(guides.small_gray(live), guides.small_gray(loop_frame), weight)
        self._sync = 0.7 * self._sync + 0.3 * max(0.0, 1.0 - diff / 35.0)
        h, w = prev.shape[:2]
        label = "loop" if self.mode == "live" else "live camera"
        if self._sync >= 0.82:
            cv2.rectangle(prev, (3, 3), (w - 4, h - 4), (60, 220, 60), 6)
            guides.put_text(prev, "In sync - cut is seamless", (12, 60), 0.7, (80, 255, 80))
        else:
            guides.put_text(prev, f"Faded: {label}  (sync {int(self._sync * 100)}%)", (12, 60), 0.6)
        return prev

    def _draw_output_status(self, prev: np.ndarray) -> None:
        """Always-visible: is the picture actually reaching Zoom?"""
        h, w = prev.shape[:2]
        if self.output.connected:
            cv2.circle(prev, (w - 228, 74), 7, (60, 220, 60), -1, cv2.LINE_AA)
            guides.put_text(prev, "Sending to OBS Virtual Camera", (w - 214, 80), 0.45)
        else:
            cv2.rectangle(prev, (0, h - 64), (w, h - 34), (30, 30, 190), -1)
            guides.put_text(prev, "NOT SENDING TO ZOOM: " + self.output.error, (10, h - 42), 0.5)

    def _ui(self, out: np.ndarray, live: np.ndarray, loop_frame: np.ndarray | None) -> bool:
        cfg = self.cfg
        recording = self.recorder.state in (State.COUNTDOWN, State.RECORDING)
        # While recording, the preview shows the live camera (what's being recorded).
        base = live if recording else out
        prev = cv2.flip(base, 1) if cfg.mirror_preview else base.copy()
        if recording or self.recorder.state == State.PROCESSING:
            prev = self.recorder.draw(prev, cfg.mirror_preview)
        elif cfg.show_guides and self.loop_running and loop_frame is not None:
            prev = self._draw_offair_overlay(prev, live, loop_frame)
        elif cfg.show_guides and self.mode == "live" and self.loop_matcher is not None:
            # Line up with the loop's start pose before cutting to it.
            glow = glow_amount(self.loop_matcher.update(live))
            if self.loop_sil is not None:
                self.loop_sil.draw(prev, cfg.mirror_preview, glow)
            if glow >= 0.99:
                guides.put_text(prev, "In start pose - cut is seamless", (12, 60), 0.7, (80, 255, 80))

        h, w = prev.shape[:2]
        tag, color = ("LIVE", (0, 170, 0)) if self.mode == "live" else ("LOOP", (0, 0, 210))
        cv2.rectangle(prev, (w - 120, 10), (w - 10, 50), color, -1)
        guides.put_text(prev, tag, (w - 100, 42), 0.9)
        self._draw_output_status(prev)
        if not recording:
            fade = f"crossfade {cfg.crossfade_ms}ms" if cfg.crossfade_ms else "hard cut"
            guides.put_text(prev, f"SPACE/{cfg.hotkey.strip('<>').upper()} cut ({fade})  R record  "
                                  f"G silhouette  X fade  U update  Q quit", (12, h - 14), 0.5)
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
            self.record()
        elif key in (ord("u"), ord("U")):
            self.check_for_updates()
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
        if getattr(self, "_closed", False):
            return
        self._closed = True
        if getattr(self, "_hk", None):
            self._hk.stop()
        if getattr(self, "_tray", None):
            self._tray.stop()
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

    logging.basicConfig(filename="doppleganger.log", filemode="w", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("Doppleganger v%s starting", updater.current_version())
    cfg = Config.load(args.config)
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.seconds is not None:
        cfg.loop_seconds = args.seconds
    if not os.path.exists(args.config):
        cfg.save(args.config)
    if cfg.auto_update and updater.can_self_update():
        startup_update(cfg)
    App(cfg, vcam=not args.no_vcam, config_path=args.config).run()


def startup_update(cfg: Config) -> None:
    """On launch: if a newer release exists, download it with a small progress window and restart.
    Any problem (offline, GitHub down) just skips the update and opens the app normally."""
    try:
        rel = updater.check(cfg.update_repo, cfg.update_token, timeout=4)
    except updater.UpdateError as e:
        print(f"Update check skipped: {e}")
        return
    if rel is None:
        return
    title = "Doppleganger - updating"
    cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)

    def show(p: float) -> None:
        img = np.full((140, 520, 3), 32, np.uint8)
        guides.put_text(img, f"Updating to v{rel.version}...", (20, 50), 0.8)
        cv2.rectangle(img, (20, 80), (500, 104), (70, 70, 70), -1)
        cv2.rectangle(img, (20, 80), (20 + int(480 * p), 104), (60, 200, 60), -1)
        cv2.imshow(title, img)
        cv2.waitKey(1)

    show(0)
    try:
        path = updater.download(rel, cfg.update_token, show)
    except updater.UpdateError as e:
        print(f"Update skipped: {e}")
        cv2.destroyWindow(title)
        return
    cv2.destroyWindow(title)
    updater.apply_and_restart(path)

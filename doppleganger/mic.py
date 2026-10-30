"""Silence while the LOOP is on air: mute the PC's microphones at the Windows level.

Muting happens through micmute.exe (built on CI). Only microphones that were
*unmuted* get muted, and exactly those are restored - so a mic you'd muted
yourself stays muted. The list is written to disk first, so if the app is
closed unexpectedly while muted, the next start restores your microphone.
All calls run on one background worker, in order, so the video never waits.
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading

from . import vcam

log = logging.getLogger("doppleganger")
STATE_FILE = "mic-muted-by-doppleganger.txt"


class MicMuter:
    def __init__(self, runner=None, state_file: str = STATE_FILE):
        self._run = runner or _run_helper
        self.state_file = state_file
        self.muted_ids: list[str] = []
        self.is_muted = False
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()
        self._q.put(("recover",))

    @staticmethod
    def available() -> bool:
        return os.path.exists(_helper_path())

    # ---------- public (non-blocking) ----------
    def mute(self) -> None:
        self._q.put(("mute",))

    def restore(self) -> None:
        self._q.put(("restore",))

    def flush(self, timeout: float = 5.0) -> None:
        """Wait for queued work (used on exit, so the mic is never left muted)."""
        done = threading.Event()
        self._q.put(("flush", done))
        done.wait(timeout)

    # ---------- worker ----------
    def _worker(self) -> None:
        while True:
            job = self._q.get()
            try:
                if job[0] == "mute":
                    self._do_mute()
                elif job[0] == "restore":
                    self._do_restore()
                elif job[0] == "recover":
                    self._recover()
                elif job[0] == "flush":
                    job[1].set()
            except Exception:  # noqa: BLE001
                log.exception("microphone %s failed", job[0])

    def _do_mute(self) -> None:
        if self.is_muted:
            return
        out = self._run(["mute"])
        ids = [ln.strip() for ln in out.splitlines() if ln.strip()]
        self.muted_ids, self.is_muted = ids, True
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write("\n".join(ids))
        log.info("Muted %d microphone(s) while LOOP is on air", len(ids))

    def _do_restore(self) -> None:
        if not self.is_muted:
            return
        if self.muted_ids:
            self._run(["unmute", *self.muted_ids])
        log.info("Restored %d microphone(s)", len(self.muted_ids))
        self.muted_ids, self.is_muted = [], False
        try:
            os.remove(self.state_file)
        except OSError:
            pass

    def _recover(self) -> None:
        """A previous run was closed while muted: give the microphone back."""
        if not os.path.exists(self.state_file):
            return
        with open(self.state_file, encoding="utf-8") as f:
            ids = [ln.strip() for ln in f if ln.strip()]
        if ids:
            self._run(["unmute", *ids])
            log.info("Restored %d microphone(s) left muted by a previous session", len(ids))
        os.remove(self.state_file)


def _helper_path() -> str:
    return os.path.join(vcam.bundle_dir(), "micmute.exe")


def _run_helper(args: list[str]) -> str:
    exe = _helper_path()
    if not os.path.exists(exe):
        return ""
    r = subprocess.run([exe, *args], capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.decode("utf-8", "replace")

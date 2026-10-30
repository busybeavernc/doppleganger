"""Plays a recorded loop forever, frame by frame, in step with the output clock."""
from __future__ import annotations

import glob
import os

import cv2
import numpy as np


class LoopPlayer:
    def __init__(self, path: str, size: tuple[int, int]):
        self.path = path
        self.size = size
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open loop {path}")
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._last: np.ndarray | None = None

    def restart(self) -> None:
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def next_frame(self) -> np.ndarray | None:
        ok, f = self.cap.read()
        if not ok:
            self.restart()
            ok, f = self.cap.read()
        if ok:
            if (f.shape[1], f.shape[0]) != self.size:
                f = cv2.resize(f, self.size)
            self._last = f
        return self._last

    def close(self) -> None:
        self.cap.release()


def latest_loop(loops_dir: str) -> str | None:
    files = sorted(glob.glob(os.path.join(loops_dir, "loop_*.mp4")))
    return files[-1] if files else None

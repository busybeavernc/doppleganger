"""Make the loop seam invisible.

1. find_best_end(): among the last few seconds, pick the frame that looks most
   like frame 0 and cut the loop there.
2. bridge_frames(): generate a few motion-compensated in-between frames that
   carry the picture from that last frame back to frame 0 (optical-flow morph,
   not a plain crossfade), so small leftover differences glide instead of jump.
"""
from __future__ import annotations

import cv2
import numpy as np

from .guides import frame_diff


def find_best_end(smalls: list[np.ndarray], search_from: int) -> tuple[int, float]:
    """Index (>= search_from) of the frame most similar to frame 0, and its diff."""
    if len(smalls) < 2:
        return len(smalls) - 1, 0.0
    search_from = int(np.clip(search_from, 1, len(smalls) - 1))
    ref = smalls[0]
    diffs = [frame_diff(ref, s) for s in smalls[search_from:]]
    i = int(np.argmin(diffs))
    return search_from + i, float(diffs[i])


def bridge_length(diff: float, max_frames: int) -> int:
    """Bigger mismatch -> more in-between frames (0 if already near-identical)."""
    if diff < 1.5:
        return 0
    return int(np.clip(round(diff / 2.5), 2, max_frames))


def _flow(a_gray: np.ndarray, b_gray: np.ndarray, scale: float) -> np.ndarray:
    a = cv2.resize(a_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    b = cv2.resize(b_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    f = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 21, 3, 7, 1.5, 0)
    f = cv2.resize(f, (a_gray.shape[1], a_gray.shape[0]), interpolation=cv2.INTER_LINEAR)
    return f / scale


def bridge_frames(last: np.ndarray, first: np.ndarray, n: int) -> list[np.ndarray]:
    """n frames morphing `last` -> `first` along the optical flow between them."""
    if n <= 0:
        return []
    h, w = last.shape[:2]
    gl = cv2.cvtColor(last, cv2.COLOR_BGR2GRAY)
    gf = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    scale = min(1.0, 480.0 / w)
    flow_lf = _flow(gl, gf, scale)  # where each pixel of `last` moves to reach `first`
    flow_fl = _flow(gf, gl, scale)
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    out = []
    for k in range(1, n + 1):
        t = k / (n + 1)
        wl = cv2.remap(last, gx - t * flow_lf[..., 0], gy - t * flow_lf[..., 1],
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        wf = cv2.remap(first, gx - (1 - t) * flow_fl[..., 0], gy - (1 - t) * flow_fl[..., 1],
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        out.append(cv2.addWeighted(wl, 1 - t, wf, t, 0))
    return out

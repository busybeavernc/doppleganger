"""Pose matching and preview text/meters (preview only, never sent to the virtual camera)."""
from __future__ import annotations

import cv2
import numpy as np

Box = tuple[int, int, int, int]  # x, y, w, h

SMALL_SIZE = (160, 90)
_cascade = None


def small_gray(frame: np.ndarray) -> np.ndarray:
    """Tiny blurred grayscale thumbnail used for fast frame comparisons."""
    g = cv2.cvtColor(cv2.resize(frame, SMALL_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g, (5, 5), 0)


def frame_diff(a_small: np.ndarray, b_small: np.ndarray, weight: np.ndarray | None = None) -> float:
    """Mean absolute pixel difference (0 = identical), optionally weighted by a 0..1 map."""
    d = cv2.absdiff(a_small, b_small).astype(np.float32)
    if weight is None:
        return float(np.mean(d))
    return float(np.sum(d * weight) / max(np.sum(weight), 1.0))


def detect_face(frame: np.ndarray) -> Box | None:
    """Largest face, or None. Returns None (pixel matching only) if no detector is available."""
    global _cascade
    if _cascade is None:
        try:
            _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        except Exception:  # noqa: BLE001
            _cascade = False
        if _cascade is not False and _cascade.empty():
            _cascade = False
    if _cascade is False:
        return None
    scale = 320.0 / frame.shape[1]
    gray = cv2.cvtColor(cv2.resize(frame, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
    faces = _cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x / scale), int(y / scale), int(w / scale), int(h / scale)


def match_score(ref_small, live_small, ref_box: Box | None, live_box: Box | None, width: int,
                weight: np.ndarray | None = None) -> float:
    """0..1, how closely the live frame matches the start pose."""
    pix = max(0.0, 1.0 - frame_diff(ref_small, live_small, weight) / 35.0)
    if ref_box is None or live_box is None:
        return pix
    rcx, rcy = ref_box[0] + ref_box[2] / 2, ref_box[1] + ref_box[3] / 2
    lcx, lcy = live_box[0] + live_box[2] / 2, live_box[1] + live_box[3] / 2
    dist = np.hypot(rcx - lcx, rcy - lcy) / (0.1 * width)
    size = abs(np.log(max(live_box[2], 1) / max(ref_box[2], 1))) / 0.15
    pos = max(0.0, 1.0 - 0.5 * dist - 0.5 * size)
    return 0.5 * pix + 0.5 * pos


class PoseMatcher:
    """Tracks how well the live camera matches a reference (start) frame."""

    def __init__(self, ref_frame: np.ndarray, ref_box: Box | None = None, weight: np.ndarray | None = None):
        self.ref_small = small_gray(ref_frame)
        self.ref_box = ref_box if ref_box is not None else detect_face(ref_frame)
        self.width = ref_frame.shape[1]
        self.weight = weight          # silhouette weight map (set once it's computed)
        self.live_box: Box | None = None
        self.score = 0.0
        self._tick = 0

    def update(self, frame: np.ndarray, small: np.ndarray | None = None) -> float:
        small = small_gray(frame) if small is None else small
        if self._tick % 3 == 0:  # face detection every 3rd frame is plenty
            self.live_box = detect_face(frame)
        self._tick += 1
        s = match_score(self.ref_small, small, self.ref_box, self.live_box, self.width, self.weight)
        self.score = 0.7 * self.score + 0.3 * s  # smooth so the glow doesn't flicker
        return self.score


# ---------- drawing helpers ----------

def draw_meter(img, label: str, value: float, y: int, good_high: bool = True) -> None:
    """Horizontal bar 0..1. Green when good."""
    w = img.shape[1]
    x0, bw, bh = 20, w // 3, 18
    value = float(np.clip(value, 0, 1))
    good = value >= 0.82 if good_high else value <= 0.35
    ok_mid = value >= 0.6 if good_high else value <= 0.6
    color = (60, 200, 60) if good else ((0, 200, 255) if ok_mid else (40, 40, 230))
    cv2.rectangle(img, (x0, y), (x0 + bw, y + bh), (40, 40, 40), -1)
    cv2.rectangle(img, (x0, y), (x0 + int(bw * value), y + bh), color, -1)
    put_text(img, label, (x0 + bw + 12, y + bh - 3), 0.6)


def put_text(img, text: str, org, scale: float = 0.8, color=(255, 255, 255), thick: int = 2) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def banner(img, text: str, color=(0, 0, 0)) -> None:
    h, w = img.shape[:2]
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
    y = int(h * 0.12)
    cv2.rectangle(img, (w // 2 - tw // 2 - 16, y - th - 14), (w // 2 + tw // 2 + 16, y + 12), color, -1)
    cv2.putText(img, text, (w // 2 - tw // 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

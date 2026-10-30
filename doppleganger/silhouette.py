"""Start-pose silhouette: the person cut out of the loop's first frame.

Drawn in the background of the PREVIEW only (never sent to the virtual camera).
It glows green when the live pose matches it closely enough.
"""
from __future__ import annotations

import cv2
import numpy as np

from .guides import SMALL_SIZE, Box

OUTLINE_IDLE = (235, 235, 235)
OUTLINE_MATCH = (80, 255, 80)


class Silhouette:
    def __init__(self, mask: np.ndarray):
        self.mask = np.where(mask > 127, 255, 0).astype(np.uint8)
        h, w = self.mask.shape
        # Matching weight: the person plus a margin, so shifted shoulders still count.
        k = max(3, w // 25) | 1
        grown = cv2.dilate(self.mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        self.weight_small = cv2.resize(grown, SMALL_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        self._cache: dict = {}

    # ---------- persistence ----------
    def save(self, path: str) -> None:
        cv2.imwrite(path, self.mask)

    @classmethod
    def load(cls, path: str) -> "Silhouette | None":
        m = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        return cls(m) if m is not None and m.any() else None

    # ---------- drawing ----------
    def _layers(self, mirrored: bool, size: tuple[int, int]):
        key = (mirrored, size)
        if key not in self._cache:
            w, h = size
            m = cv2.resize(self.mask, size, interpolation=cv2.INTER_LINEAR)
            m = cv2.flip(m, 1) if mirrored else m
            m = np.where(m > 127, 255, 0).astype(np.uint8)
            contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            outline = np.zeros((h, w), np.uint8)
            cv2.drawContours(outline, contours, -1, 255, max(2, w // 450), cv2.LINE_AA)
            glow = np.zeros((h, w, 3), np.uint8)
            cv2.drawContours(glow, contours, -1, (60, 255, 60), max(8, w // 55), cv2.LINE_AA)
            glow = cv2.GaussianBlur(glow, (0, 0), max(4, w / 110))
            glow = cv2.add(glow, glow)  # brighten after the blur spreads it out
            glow[m > 0] = 0             # glow AROUND the silhouette, never over your face
            tint = np.zeros((h, w, 3), np.uint8)
            tint[m > 0] = (45, 30, 10)  # faint cool fill so the shape reads as "you were here"
            self._cache[key] = (outline > 0, glow, tint)
        return self._cache[key]

    def draw(self, img: np.ndarray, mirrored: bool, glow: float = 0.0) -> None:
        outline, glow_layer, tint = self._layers(mirrored, (img.shape[1], img.shape[0]))
        cv2.add(img, tint, dst=img)
        if glow > 0:
            cv2.addWeighted(img, 1.0, glow_layer, float(glow), 0, dst=img)
        img[outline] = OUTLINE_MATCH if glow >= 0.99 else OUTLINE_IDLE


def glow_amount(match: float) -> float:
    """Match score -> glow strength. Fully green at 82% match and above."""
    return float(np.clip((match - 0.70) / 0.12, 0.0, 1.0))


# ---------- extraction ----------

def extract(frame: np.ndarray, face: Box | None) -> Silhouette:
    """Segment the person in `frame` (GrabCut seeded from the face position)."""
    try:
        mask = _grabcut(frame, face)
        if mask is not None:
            return Silhouette(mask)
    except cv2.error:
        pass
    return Silhouette(_fallback_shape(frame.shape, face))


def _grabcut(frame: np.ndarray, face: Box | None) -> np.ndarray | None:
    H, W = frame.shape[:2]
    s = 320.0 / W
    img = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    m = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    if face is not None:
        fx, fy, fw, fh = (int(v * s) for v in face)
        x0, x1 = max(0, int(fx - 1.6 * fw)), min(w, int(fx + fw + 1.6 * fw))
        m[max(0, int(fy - 0.5 * fh)):, x0:x1] = cv2.GC_PR_FGD
        m[int(fy + 0.15 * fh):int(fy + 0.85 * fh), int(fx + 0.2 * fw):int(fx + 0.8 * fw)] = cv2.GC_FGD
        m[min(h, int(fy + 1.3 * fh)):, fx:fx + fw] = cv2.GC_FGD  # chest under the face
    else:
        m[int(0.15 * h):, int(0.25 * w):int(0.75 * w)] = cv2.GC_PR_FGD
        m[int(0.45 * h):, int(0.42 * w):int(0.58 * w)] = cv2.GC_FGD
    edge = max(2, w // 100)
    for sl in (np.s_[:edge, :], np.s_[:, :edge], np.s_[:, -edge:]):  # top/left/right are background
        region = m[sl]
        region[region != cv2.GC_FGD] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, m, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
    fg = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(biggest) < 0.02 * w * h:
        return None
    clean = np.zeros_like(fg)
    cv2.drawContours(clean, [biggest], -1, 255, -1)  # filled: no holes
    clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    full = cv2.resize(clean, (W, H), interpolation=cv2.INTER_LINEAR)
    full = cv2.GaussianBlur(full, (0, 0), 2)
    return np.where(full > 127, 255, 0).astype(np.uint8)


def _fallback_shape(shape, face: Box | None) -> np.ndarray:
    """Head + shoulders outline from the face box (or a centered default)."""
    H, W = shape[:2]
    if face is None:
        fw = fh = int(H * 0.28)
        face = (W // 2 - fw // 2, int(H * 0.25), fw, fh)
    fx, fy, fw, fh = face
    m = np.zeros((H, W), np.uint8)
    cx = fx + fw // 2
    cv2.ellipse(m, (cx, fy + fh // 2), (int(fw * 0.55), int(fh * 0.7)), 0, 0, 360, 255, -1)
    cv2.rectangle(m, (cx - fw // 4, fy + fh), (cx + fw // 4, fy + int(fh * 1.4)), 255, -1)
    cv2.ellipse(m, (cx, fy + int(fh * 1.4) + fh * 2), (int(fw * 1.6), fh * 2), 0, 180, 360, 255, -1)
    return m

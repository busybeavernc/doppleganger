"""AI person segmentation: finds you in any frame - no room calibration needed.

Uses Google's MediaPipe Selfie Segmentation (landscape) model, the kind of model
video-call apps use for background blur (~3 ms per frame on a laptop CPU).
The low-resolution mask is snapped to the real edges in the picture with a guided
filter, so hair and shoulders get a clean outline. Live streams are lightly
smoothed over time so outlines don't flicker.

If the model can't be loaded, callers fall back to the calibrated-room method.
"""
from __future__ import annotations

import logging
import threading

import cv2
import numpy as np

from . import brand

log = logging.getLogger("doppleganger")

MODEL_WIDTH = 256           # the landscape model's native input (256x144)
EDGE_WIDTH = 480            # resolution at which mask edges are refined


class PersonSegmenter:
    def __init__(self, model_path: str | None = None):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self._mp = mp
        path = model_path or brand.asset("models/selfie_segmenter_landscape.tflite")
        self._seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=path), output_confidence_masks=True))
        self._lock = threading.Lock()  # one inference at a time
        self._has_guided = hasattr(cv2, "ximgproc")

    def probability(self, frame: np.ndarray) -> np.ndarray:
        """Person probability 0..1 (float32) at model resolution, same aspect as `frame`."""
        h = max(16, round(frame.shape[0] * MODEL_WIDTH / frame.shape[1]))
        small = cv2.resize(frame, (MODEL_WIDTH, h), interpolation=cv2.INTER_AREA)
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                             data=np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
        with self._lock:
            result = self._seg.segment(img)
        m = result.confidence_masks[0].numpy_view()
        return np.ascontiguousarray(m.reshape(m.shape[0], m.shape[1]), dtype=np.float32)

    def refine(self, prob: np.ndarray, frame: np.ndarray, width: int = EDGE_WIDTH) -> np.ndarray:
        """Upscale the mask to `width` and snap its edges to the picture (guided filter)."""
        h = round(frame.shape[0] * width / frame.shape[1])
        p = cv2.resize(prob, (width, h), interpolation=cv2.INTER_LINEAR)
        if self._has_guided:
            guide = cv2.resize(frame, (width, h), interpolation=cv2.INTER_AREA)
            p = cv2.ximgproc.guidedFilter(guide=guide, src=p, radius=6, eps=1e-3)
        return np.clip(p, 0.0, 1.0)

    def mask(self, frame: np.ndarray, width: int = EDGE_WIDTH) -> np.ndarray:
        """Refined person mask 0/255 at `width` (one-shot, no smoothing)."""
        return (self.refine(self.probability(frame), frame, width) > 0.5).astype(np.uint8) * 255

    def close(self) -> None:
        try:
            self._seg.close()
        except Exception:  # noqa: BLE001
            pass


class SmoothedStream:
    """Per-stream temporal smoothing (live camera, loop...): steadier outlines, same responsiveness."""

    def __init__(self, segmenter: PersonSegmenter, keep: float = 0.45):
        self.seg = segmenter
        self.keep = keep
        self._prob: np.ndarray | None = None

    def probability(self, frame: np.ndarray) -> np.ndarray:
        p = self.seg.probability(frame)
        if self._prob is not None and self._prob.shape == p.shape:
            p = self.keep * self._prob + (1 - self.keep) * p
        self._prob = p
        return p

    def reset(self) -> None:
        self._prob = None


_instance: PersonSegmenter | None = None
_failed = False


def get() -> PersonSegmenter | None:
    """Shared segmenter, or None if the model can't be loaded (then the room-calibration fallback is used)."""
    global _instance, _failed
    if _instance is None and not _failed:
        try:
            _instance = PersonSegmenter()
            log.info("AI person segmentation ready")
        except Exception as e:  # noqa: BLE001
            _failed = True
            log.warning("AI person segmentation unavailable, using room calibration instead: %s", e)
    return _instance

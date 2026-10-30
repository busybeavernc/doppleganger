"""AI person segmentation: real model smoke test + the pipelines that use it (with a stand-in model)."""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_calibrate as T  # noqa: E402

from doppleganger.guides import PoseMatcher  # noqa: E402
from doppleganger.outline import OutlineTracer  # noqa: E402
from doppleganger.silhouette import extract, glow_amount  # noqa: E402


class FakeSegmenter:
    """Stand-in for the AI model: knows where the drawn test person is (blurry, like the real low-res mask)."""

    def __init__(self):
        self.calls = 0

    def probability(self, frame):
        self.calls += 1
        dx = int(frame[0, 0, 2]) - 100 if frame[0, 0, 2] >= 50 else 0  # test frames encode their offset
        _, truth, _ = T.scene(dx)
        p = cv2.resize(truth.astype(np.float32), (256, 144), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(p, (0, 0), 2)

    def refine(self, prob, frame, width=480, steady=False):
        h = round(frame.shape[0] * width / frame.shape[1])
        return cv2.resize(prob, (width, h), interpolation=cv2.INTER_LINEAR)


def frame_at(dx):
    f, truth, face = T.scene(dx)
    f = f.copy()
    f[0, 0, 2] = 100 + dx  # offset tag for FakeSegmenter (one pixel)
    return f, truth, face


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def test_silhouette_from_ai_mask_needs_no_calibration():
    f, truth, face = frame_at(0)
    sil = extract(f, face, background=None, segmenter=FakeSegmenter())
    assert iou(sil.mask > 0, truth) > 0.93


def test_outlines_from_ai_mask_per_stream():
    seg = FakeSegmenter()
    tr = OutlineTracer(segmenter=seg)
    f0, _, _ = frame_at(0)
    f1, _, _ = frame_at(60)
    c_live = tr.contour(f0, (640, 360), False, "live")
    c_loop = tr.contour(f1, (640, 360), False, "other")
    assert c_live is not None and c_loop is not None
    assert c_loop[..., 0].mean() - c_live[..., 0].mean() > 40   # each stream traces its own person


def test_match_glow_from_ai_mask():
    seg = FakeSegmenter()
    ref, _, face = frame_at(0)
    sil = extract(ref, face, segmenter=seg)
    m = PoseMatcher(ref, ref_box=face, segmenter=seg)
    m.set_silhouette(sil)
    for _ in range(15):
        away = m.update(frame_at(120)[0])
    assert glow_amount(away) == 0.0
    for _ in range(15):
        back = m.update(frame_at(2)[0])
    assert glow_amount(back) == 1.0 and m.shape_overlap > 0.85


def test_real_model_loads_and_runs():
    pytest.importorskip("mediapipe")
    from doppleganger.segment import PersonSegmenter
    seg = PersonSegmenter()
    frame = np.full((720, 1280, 3), 120, np.uint8)
    p = seg.probability(frame)
    assert p.shape == (144, 256) and p.dtype == np.float32 and 0 <= p.min() <= p.max() <= 1
    r = seg.refine(p, frame, 480)
    assert r.shape == (270, 480)
    seg.close()


def test_outline_is_steady_when_still_and_follows_movement():
    """Noise alone must not wiggle the outline; a real move must show up within a few frames."""
    seg = FakeSegmenter()
    tr = OutlineTracer(segmenter=seg)
    rng = np.random.default_rng(0)
    base, _, _ = frame_at(0)
    shapes = []
    for _ in range(12):
        noisy = np.clip(base.astype(np.int16) + rng.normal(0, 5, base.shape), 0, 255).astype(np.uint8)
        noisy[0, 0, 2] = 100  # keep the FakeSegmenter offset tag
        m = np.zeros((360, 640), np.uint8)
        cv2.fillPoly(m, [tr.contour(noisy, (640, 360), False)], 255)
        shapes.append(m > 0)
    flicker = max(np.logical_xor(a, b).sum() for a, b in zip(shapes[4:], shapes[5:]))
    assert flicker <= 40, flicker
    still_x = tr.contour(base, (640, 360), False)[..., 0].mean()
    moved = [tr.contour(frame_at(80)[0], (640, 360), False)[..., 0].mean() for _ in range(4)]
    assert moved[-1] - still_x > 60      # followed the 80 px move within 4 frames


def _person_frame(dx=0):
    """A real photo of a person (public-domain portrait), framed like a 1280x720 webcam picture."""
    img = cv2.imread(os.path.join(os.path.dirname(__file__), "data", "person.jpg"))
    pad = (img.shape[0] * 16 // 9 - img.shape[1]) // 2
    f = cv2.copyMakeBorder(img, 0, 0, pad, pad, cv2.BORDER_REPLICATE)
    f = cv2.resize(f, (1280, 720))
    return np.roll(f, dx, axis=1)


def test_real_model_outlines_a_real_person_in_both_streams():
    """End to end with the real AI model, like the preview: live + loop outlines, mirrored, many frames."""
    from doppleganger import segment
    seg = segment.get()
    if seg is None:
        pytest.skip("MediaPipe not available")
    tr = OutlineTracer(segmenter=seg)
    rng = np.random.default_rng(1)
    size = (960, 540)
    for i in range(12):
        live = np.clip(_person_frame(4 * i).astype(np.int16) + rng.normal(0, 5, (720, 1280, 3)), 0, 255).astype(np.uint8)
        loop = _person_frame(-40)
        for stream, frame in (("other", loop), ("live", live)):
            c = tr.contour(frame, size, True, stream)
            assert c is not None, f"no {stream} outline on frame {i}"
            x, y, w, h = cv2.boundingRect(c)
            area = cv2.contourArea(c) / (size[0] * size[1])
            # a person in the middle of the picture - not nothing, not the whole frame
            assert 0.08 < area < 0.7, f"{stream} outline covers {area:.0%} of the picture"
            assert w < 0.8 * size[0], f"{stream} outline is as wide as the picture"

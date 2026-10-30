import os

import cv2
import numpy as np

from doppleganger import guides
from doppleganger.config import Config
from doppleganger.recorder import Recorder
from doppleganger.stitch import bridge_frames, bridge_length, find_best_end

W, H = 320, 180


def scene(x: float) -> np.ndarray:
    """Textured background with a 'head' circle at horizontal position x."""
    rng = np.random.default_rng(0)
    img = cv2.GaussianBlur(rng.integers(0, 255, (H, W, 3), dtype=np.uint8), (0, 0), 3)
    cv2.circle(img, (int(x), H // 2), 30, (40, 160, 230), -1, cv2.LINE_AA)
    return img


def test_find_best_end_picks_frame_matching_first():
    xs = [100, 120, 140, 160, 140, 103, 115, 130]
    smalls = [guides.small_gray(scene(x)) for x in xs]
    idx, diff = find_best_end(smalls, 4)
    assert idx == 5
    assert diff < find_best_end(smalls, 6)[1] + 1e-6


def test_bridge_length_scales_with_mismatch():
    assert bridge_length(0.5, 8) == 0
    assert 2 <= bridge_length(5, 8) <= bridge_length(30, 8) == 8


def test_bridge_moves_head_smoothly():
    last, first = scene(120), scene(100)
    frames = bridge_frames(last, first, 4)
    assert len(frames) == 4 and frames[0].shape == last.shape

    def head_x(img):
        mask = cv2.inRange(img, (30, 140, 210), (60, 190, 255))
        m = cv2.moments(mask)
        return m["m10"] / m["m00"]

    xs = [head_x(last)] + [head_x(f) for f in frames] + [head_x(first)]
    # head should travel monotonically from 120 toward 100
    assert all(a >= b - 0.5 for a, b in zip(xs, xs[1:])), xs
    assert xs[1] < 119.5 and xs[-2] > 100.5, xs


def test_process_raw_trims_and_stitches(tmp_path):
    cfg = Config(fps=10, loops_dir=str(tmp_path), return_prompt_seconds=3, max_bridge_frames=6)
    xs = list(np.linspace(100, 160, 20)) + list(np.linspace(160, 104, 10)) + [112, 125]
    raw = os.path.join(tmp_path, "raw.avi")
    vw = cv2.VideoWriter(raw, cv2.VideoWriter_fourcc(*"MJPG"), 10, (W, H))
    frames = [scene(x) for x in xs]
    for f in frames:
        vw.write(f)
    vw.release()
    smalls = [guides.small_gray(f) for f in frames]
    out = Recorder.process_raw(raw, smalls, cfg)
    cap = cv2.VideoCapture(out)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    import json
    meta = json.load(open(out + ".json"))
    assert meta["end_frame"] == 29          # x=104, closest to start x=100
    assert n == meta["frames"] == 30 + meta["bridge_frames"]

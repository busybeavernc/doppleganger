import cv2
import numpy as np

from doppleganger.calibrate import Calibrator, split_background
from doppleganger.guides import PoseMatcher
from doppleganger.silhouette import extract, glow_amount

W, H = 640, 360
_rng = np.random.default_rng(3)
ROOM = cv2.GaussianBlur(_rng.integers(70, 190, (H, W, 3), dtype=np.uint8), (0, 0), 5)
cv2.rectangle(ROOM, (40, 60), (170, 220), (40, 90, 140), -1)    # shelf
cv2.rectangle(ROOM, (470, 40), (600, 160), (150, 150, 60), -1)  # picture
CHAIR = ((250, 230), (390, 360))                                  # chair back, always behind you


def scene(dx=0):
    """Room + chair + person (head, neck, shirt with a jagged collar); returns frame, true mask, face box."""
    f = ROOM.copy()
    cv2.rectangle(f, *CHAIR, (60, 60, 60), -1)
    m = np.zeros((H, W), np.uint8)
    cx = 320 + dx
    for img, c in ((f, None), (m, 255)):
        cv2.ellipse(img, (cx, 360), (150, 95), 0, 180, 360, c or (90, 50, 140), -1)
        cv2.rectangle(img, (cx - 22, 205), (cx + 22, 275), c or (110, 150, 205), -1)
        cv2.ellipse(img, (cx, 150), (50, 66), 0, 0, 360, c or (120, 160, 215), -1)
        cv2.ellipse(img, (cx, 100), (54, 34), 0, 180, 360, c or (40, 40, 50), -1)
    face = (cx - 45, 95, 90, 110)
    return f, m > 0, face


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def calibrated_background():
    cal = Calibrator(min_seconds=0, max_seconds=99)
    for dx in list(range(0, -260, -20)) + list(range(-260, 261, 20)) + list(range(260, 0, -20)):
        f, _, face = scene(dx)
        s = 320 / W
        cal.add(f, face=tuple(int(v * s) for v in face), detect=False)
        cal.add(f, face=tuple(int(v * s) for v in face), detect=False)  # (samples every other frame)
    return cal, cal.background()


def test_calibration_recovers_empty_room_and_knows_what_it_saw():
    cal, bg = calibrated_background()
    rgb, known = split_background(bg)
    assert cal.coverage > 0.85 and known.mean() > 0.85
    room = cv2.resize(ROOM, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_AREA)
    err = np.abs(rgb.astype(int) - room.astype(int)).mean(axis=2)
    assert np.median(err[known]) < 6           # seen areas match the empty room
    assert cal.side_needed() is None


def test_calibrated_silhouette_is_much_more_accurate():
    _, bg = calibrated_background()
    frame, truth, face = scene(0)
    plain = iou(extract(frame, face).mask > 0, truth)
    calibrated = iou(extract(frame, face, bg).mask > 0, truth)
    assert calibrated > 0.9, calibrated
    assert calibrated > plain


def test_shape_overlap_drives_glow():
    _, bg = calibrated_background()
    frame, _, face = scene(0)
    sil = extract(frame, face, bg)
    m = PoseMatcher(frame, ref_box=face, background=bg)
    m.set_silhouette(sil)
    for _ in range(15):
        away = m.update(scene(120)[0])
    assert glow_amount(away) == 0.0 and m.shape_overlap < 0.6
    for _ in range(15):
        back = m.update(scene(3)[0])
    assert glow_amount(back) == 1.0 and m.shape_overlap > 0.85

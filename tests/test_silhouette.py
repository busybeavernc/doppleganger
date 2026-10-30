import cv2
import numpy as np

from doppleganger.guides import PoseMatcher
from doppleganger.silhouette import Silhouette, extract, glow_amount


def person(dx=0):
    rng = np.random.default_rng(1)
    f = cv2.GaussianBlur(rng.integers(60, 200, (360, 640, 3), dtype=np.uint8), (0, 0), 4)
    cx = 320 + dx
    cv2.ellipse(f, (cx, 355), (150, 100), 0, 180, 360, (70, 40, 30), -1)
    cv2.rectangle(f, (cx - 22, 190), (cx + 22, 260), (120, 150, 200), -1)
    cv2.ellipse(f, (cx, 150), (52, 67), 0, 0, 360, (130, 165, 215), -1)
    return f


def test_extract_finds_person_in_center():
    sil = extract(person(), None)
    m = sil.mask > 0
    assert 0.08 < m.mean() < 0.5
    assert m[150, 320] and m[340, 320]       # head and chest inside
    assert not m[20, 20] and not m[150, 40]  # background outside


def test_draw_glow_only_outside_and_roundtrip(tmp_path):
    sil = extract(person(), None)
    img = np.zeros((360, 640, 3), np.uint8)
    sil.draw(img, mirrored=False, glow=1.0)
    inside = img[sil.mask > 0]
    assert inside[:, 1].mean() < 120          # no green wash over the person
    p = str(tmp_path / "m.png")
    sil.save(p)
    assert np.array_equal(Silhouette.load(p).mask, sil.mask)


def test_matcher_glows_only_when_back_in_pose():
    ref = person()
    sil = extract(ref, None)
    m = PoseMatcher(ref, weight=sil.weight_small)
    for _ in range(15):
        away = m.update(person(150))
    assert glow_amount(away) == 0.0
    for _ in range(15):
        back = m.update(person(2))
    assert glow_amount(back) == 1.0

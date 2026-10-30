import numpy as np

from doppleganger.glitch import Glitch

FPS = 30


def frame(i, value=None):
    """Sharp test frame with a moving block; `value` tags which feed it came from."""
    f = np.zeros((72, 128, 3), np.uint8)
    f[:, :, 0] = (i % 200) if value is None else value
    f[10:60, 20 + i % 80:40 + i % 80] = 255
    return f


def tagged_morph(a, b, t):
    """Stand-in interpolator that marks its output so tests can recognise in-between frames."""
    out = a.copy()
    out[0, 0] = (1, 2, 3)
    return out


def run(g, start, seconds, src=frame):
    out = []
    for k in range(int(seconds * FPS)):
        t = start + k / FPS
        out.append((t, k, g.process(src(k), t)))
    return out


def held_runs(frames):
    runs, n = [], 1
    for a, b in zip(frames, frames[1:]):
        if np.array_equal(a, b):
            n += 1
        else:
            runs.append(n)
            n = 1
    runs.append(n)
    return runs


def test_inactive_passes_frames_through():
    g = Glitch(seed=1)
    f = frame(3)
    assert g.process(f, 0.0) is f


def test_freezes_are_random_and_jerky():
    runs = []
    for seed in range(4):
        g = Glitch(seed=seed, interpolate=tagged_morph)
        g.start(0.0)
        runs += held_runs([f for _, _, f in run(g, 0.0, 20)])
    assert max(runs) >= int(0.9 * FPS)     # real stalls
    assert min(runs) <= int(0.25 * FPS)    # ...and quick uneven updates
    assert len(set(runs)) >= 10            # random, not a fixed rhythm


def test_every_frame_is_sharp_full_picture_or_in_between():
    """No blur, pixelation or blank frames: each output is an exact source frame or an interpolated one."""
    g = Glitch(seed=5, interpolate=tagged_morph)
    g.start(0.0)
    sources = {k: frame(k) for k in range(12 * FPS)}
    exact = between = 0
    for t, k, f in run(g, 0.0, 12):
        if any(np.array_equal(f, sources[j]) for j in range(k + 1)):
            exact += 1
        else:
            assert tuple(f[0, 0]) == (1, 2, 3)  # only our in-between frames differ
            between += 1
        assert f.shape == (72, 128, 3) and f.max() == 255
    assert exact > 0 and between > 0


def test_cut_during_glitch_is_a_clean_reveal_then_recovers():
    g = Glitch(seed=3, recover_seconds=1.5, interpolate=tagged_morph)
    g.start(0.0)
    run(g, 0.0, 3, src=lambda i: frame(i, value=10))             # "loop" on air
    g.recover(3.0, delay=0.4, clean_jump=True)                     # user cut to live
    after = run(g, 3.0, 4, src=lambda i: frame(i, value=200))     # "live" feed
    first_live = next((t, f) for t, _, f in after if f[5, 5, 0] == 200)
    assert first_live[0] - 3.0 < 1.0                              # live shows up within ~1s
    assert tuple(first_live[1][0, 0]) != (1, 2, 3)                # ...as a clean frame, never a loop/live mix
    assert not g.active                                           # fully recovered afterwards
    t_end, k_end, last = after[-1]
    assert np.array_equal(last, frame(k_end, value=200))          # smooth pass-through again


def test_safety_timeout_ends_glitch():
    g = Glitch(max_seconds=5, recover_seconds=1, seed=4, interpolate=tagged_morph)
    g.start(0.0)
    run(g, 0.0, 7)
    assert not g.active


def test_real_morph_is_sharp_and_in_between():
    from doppleganger.stitch import morph
    import cv2
    a = np.zeros((90, 160, 3), np.uint8)
    b = np.zeros((90, 160, 3), np.uint8)
    rng = np.random.default_rng(0)
    tex = rng.integers(0, 255, (40, 40, 3), dtype=np.uint8)
    a[25:65, 30:70] = tex
    b[25:65, 50:90] = tex
    m = morph(a, b, 0.5)
    cols = np.where(cv2.cvtColor(m, cv2.COLOR_BGR2GRAY).max(axis=0) > 30)[0]
    assert 40 < cols.mean() < 75                           # moved part-way
    assert m.std() > 0.8 * a.std()                         # still crisp, not a soft blend

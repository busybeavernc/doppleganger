import numpy as np

from doppleganger.glitch import Glitch

FPS = 30


def frame(i, value=None):
    f = np.zeros((72, 128, 3), np.uint8)
    f[:, :, 0] = i % 256 if value is None else value
    f[10:60, 20 + i % 80:40 + i % 80] = 255  # moving block so frames differ
    return f


def run(g, start, seconds, src=lambda i: frame(i)):
    out = []
    for k in range(int(seconds * FPS)):
        t = start + k / FPS
        out.append((t, g.process(src(k), t)))
    return out


def held_runs(frames):
    """Lengths of runs of identical consecutive output frames."""
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


def test_glitch_freezes_and_jumps():
    g = Glitch(seed=2)
    g.start(0.0)
    out = [f for _, f in run(g, 0.0, 10)]
    runs = held_runs(out)
    assert max(runs) >= int(0.8 * FPS)          # real freezes (>= 0.8s)
    assert len(runs) >= 4                        # ...with jumps in between
    assert not np.array_equal(out[0], frame(0))  # degraded (blocky), not clean


def test_cut_during_glitch_reveals_new_feed_then_recovers():
    g = Glitch(seed=3, recover_seconds=2.0)
    g.start(0.0)
    run(g, 0.0, 3, src=lambda i: frame(i, value=10))       # "loop" on air
    g.recover(3.0, delay=0.4)                                # user cut to live
    after = run(g, 3.0, 4, src=lambda i: frame(i, value=200))  # "live" feed
    revealed = next(t for t, f in after if abs(int(f[..., 0].mean()) - 200) < 40)
    assert revealed - 3.0 < 1.0                              # live shows up within ~1s
    assert not g.active                                      # fully recovered afterwards
    t_end, last = after[-1]
    assert np.array_equal(last, frame(int((t_end - 3.0) * FPS), value=200))  # clean pass-through


def test_safety_timeout_ends_glitch():
    g = Glitch(max_seconds=5, recover_seconds=1, seed=4)
    g.start(0.0)
    run(g, 0.0, 7)
    assert not g.active

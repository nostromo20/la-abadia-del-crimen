#!/usr/bin/env python3
"""The parchment's page turn: the fast paths (src/colour.s ql_play_triangle: span fills; the
border restores as packed-byte blits) against the old per-pixel ones (header +30 bit 3), screen
for screen. Both runs play the intro on the nominal clock, so they make the same calls at the
same steps; the QL screen is hashed at every Pergamino::pasaPagina call (= the picture the
previous animation frame left) and must be identical in both, for every frame of every page
turn played. Also reports the 68008 time of the turns (cyclest model) in both.

  pagetest.py [--ticks 500]      500 steps: the first page turn (both halves, 95 frames)
"""
import argparse, hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, cyclest
from unicorn import UC_HOOK_CODE


def run(old, ticks):
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    path = os.path.join(QL, "build", "tmp", "pagetest_script.txt")
    open(path, "w").write("\n")
    for k in ("QEMU_KEYS", "FORCE_NIGHT", "FORCE_MIRROR", "REALCLOCK"):
        os.environ.pop(k, None)
    os.environ["INTRO"] = "1"
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(path), realq=True, sv164=0xC1000)
    os.environ.pop("INTRO", None)
    if old:
        b = bytes(r.mu.mem_read(r.base + 30, 1))[0] | 0x08
        r.mu.mem_write(r.base + 30, bytes([b]))
    est = cyclest.Estimator(r)
    frames = []
    turn_cost = [0, None]
    a = r.base + syms["_ZN6Abadia9Pergamino10pasaPaginaEv"]

    def at(mu, addr, size, data):
        frames.append(hashlib.md5(r.screen()).hexdigest())
    r.mu.hook_add(UC_HOOK_CODE, at, begin=a, end=a)
    marks = []
    r.tick_cb = lambda rr: marks.append((est.total, len(frames)))
    r.run(ticks)
    # the 68008 time of the steps in which page-turn frames were drawn
    cost = sum(marks[i][0] - marks[i - 1][0] for i in range(1, len(marks)) if marks[i][1] > marks[i - 1][1] + 1)
    final = hashlib.md5(r.screen()).hexdigest()
    return frames, final, cost / (cyclest.MHZ * 1000.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=500)
    a = ap.parse_args()
    fo, eo, co = run(True, a.ticks)
    fn, en, cn = run(False, a.ticks)
    same = fo == fn and eo == en
    diff = next((i for i in range(min(len(fo), len(fn))) if fo[i] != fn[i]), None)
    print("%-4s %d page-turn frames, the screen identical at every one (old per-pixel paths vs the fast ones)%s"
          % ("ok" if same else "FAIL", len(fn), "" if same else "; first difference at frame %s" % diff))
    print("     68008 time of the steps drawing the turn (cyclest model): old %.2f s, new %.2f s" % (co / 1000, cn / 1000))
    print("PAGE: %d failures" % (0 if same else 1))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())

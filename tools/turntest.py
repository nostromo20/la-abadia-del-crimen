#!/usr/bin/env python3
"""Turning: one 90-degree turn per logic step while LEFT/RIGHT is held, one for a tap (the CPC:
Guillermo.cpp, the key read once a pass). The two QL key paths (src/qlhooks.s scan_keyrows):

  KEYROW  (the held state, read once a step): the harness answers it from the script.
  typed   (characters from the keyboard queue, QDOS auto-repeat: AR_DELAY 15 frames, then
          every AR_RATE 2 frames): QEMU_KEYS=1, as Q-emuLator over Remote Desktop (KEYROW dead);
          qlrun models the auto-repeat from the delay and rate the game set.

Cases:
  KEYROW: a 1-step tap = 1 turn; LEFT held 3 steps = 3 turns; UP held: walks every step it can.
  KEYROW + a late typed character of the same key (the old double count) = still 1 turn.
  typed:  a 1-step tap (< 300 ms) = 1 turn; LEFT held 10 steps = at most 1 turn a step;
          UP held: walks once the auto-repeat runs.
  Q/R, Y/N and the F-keys keep the typed path (tools/qrtest.py, yntest.py, striptest.py).

  turntest.py      exit 1 on failure
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun

fails = []


def run(lines, ticks, qemu=False, extra_typed=None):
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    path = os.path.join(QL, "build", "tmp", "turntest_script.txt")
    open(path, "w").write("\n".join("%d %d %s" % l for l in lines) + "\n")
    for k in ("QEMU_KEYS", "INTRO", "FORCE_NIGHT", "FORCE_MIRROR", "REALCLOCK", "AUTOREPEAT_EVERY_FRAME"):
        os.environ.pop(k, None)
    if qemu:
        os.environ["QEMU_KEYS"] = "1"
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(path), realq=True, sv164=0xC1000)
    os.environ.pop("QEMU_KEYS", None)
    if extra_typed:
        def cb(rr):
            for t, k in extra_typed:
                if rr.tick + 1 == t:            # typed just before step t starts (after its own keys)
                    rr.typed.append(qlrun.KEYCODE[k])
        r.tick_cb = cb
    r.run(ticks)
    g = [(st[20], st[21], st[23]) for st in r.states]          # Guillermo x, y, orientation
    return g


def turns(g, a, b):
    return sum(1 for t in range(max(a, 1), min(b, len(g))) if g[t][2] != g[t - 1][2])


def moves(g, a, b):
    return sum(1 for t in range(max(a, 1), min(b, len(g))) if g[t][:2] != g[t - 1][:2])


def check(name, ok, detail):
    print("%-4s %-52s %s" % ("ok" if ok else "FAIL", name, detail))
    if not ok:
        fails.append(name)


def main():
    # KEYROW path
    g = run([(5, 5, "UP"), (10, 10, "LEFT"), (20, 22, "LEFT")], 30)
    n = turns(g, 10, 16)
    check("KEYROW: LEFT tapped for 1 step", n == 1, "%d turn(s)" % n)
    n = turns(g, 20, 26)
    check("KEYROW: LEFT held 3 steps", n == 3, "%d turns" % n)
    # walking (walk1's first leg: no wall for 50 steps); the reference: every frame typed, KEYROW on
    os.environ["AUTOREPEAT_EVERY_FRAME"] = "1"
    ref = moves(run([(10, 49, "UP")], 52), 10, 52)
    os.environ.pop("AUTOREPEAT_EVERY_FRAME", None)
    m = moves(run([(10, 49, "UP")], 52), 10, 52)
    check("KEYROW: UP held 40 steps walks as before", m == ref, "%d steps with a position change (before: %d)" % (m, ref))
    # the old double count: KEYROW sees the tap at step 30, its typed character comes a step later
    g = run([(5, 5, "UP"), (30, 30, "LEFT")], 40, extra_typed=[(31, "LEFT")])
    n = turns(g, 30, 36)
    check("KEYROW + a late typed character of the same key", n == 1, "%d turn(s)" % n)
    # typed path (Q-emuLator over RDP: KEYROW shows nothing)
    g = run([(10, 10, "LEFT"), (20, 29, "LEFT")], 34, qemu=True)
    n = turns(g, 10, 16)
    check("typed: LEFT tapped for 1 step (< 300 ms)", n == 1, "%d turn(s)" % n)
    n = turns(g, 20, 32)
    check("typed: LEFT held 10 steps: at most 1 turn a step", 1 <= n <= 10, "%d turns in 10 steps" % n)
    m = moves(run([(10, 49, "UP")], 52, qemu=True), 10, 52)
    check("typed: UP held 40 steps walks (after the 300 ms delay)", m >= ref - 3,
          "%d steps with a position change (KEYROW: %d)" % (m, ref))
    print("TURN: %d failures" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

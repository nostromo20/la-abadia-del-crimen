#!/usr/bin/env python3
"""The panel phrase is paced by FRAMES, 7.5 frames (150 ms) a character, as the CPC's 300 Hz
interrupt paces it (every 45 interrupts), whatever the logic step takes (docs/speed_vs_cpc.md).

hdiff and the other harness tests run on the NOMINAL clock (header +30 bit 2: the oracle's
step schedule of 6/7 frames), so both sides see the same frames. This test runs the REAL clock
(REALCLOCK=1: the frames the harness's poll model counts) and checks the time between the
characters of the abbot's phrases on tests/enter.txt (from step 20): their mean must be 7.5
frames. (A long step lets the frames it took come out as several characters at once, as the
CPC's interrupt would have scrolled them meanwhile.)

  phrasetest.py      exit 1 on failure
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun
from unicorn import UC_HOOK_CODE


def main():
    os.environ["REALCLOCK"] = "1"
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    script = os.path.join(QL, "tests", "enter.txt")     # to the abbot: his phrases
    for k in ("QEMU_KEYS", "INTRO", "FORCE_NIGHT", "FORCE_MIRROR"):
        os.environ.pop(k, None)
    os.environ["SAVENAME"] = "win1_abadia_sav"
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(script), realq=True, sv164=0xC1000)
    chars = []
    a = r.base + syms["_ZN6Abadia12GestorFrases11scrollFraseEv"]       # one per character shown
    r.mu.hook_add(UC_HOOK_CODE, lambda mu, addr, size, data: chars.append(
        (r.tick, struct.unpack(">I", bytes(mu.mem_read(r.base + 20, 4)))[0])), begin=a, end=a)
    frames = []
    r.tick_cb = lambda rr: frames.append(struct.unpack(">I", bytes(rr.mu.mem_read(rr.base + 20, 4)))[0])
    r.run(400)
    os.environ.pop("REALCLOCK", None)
    chars = [c for c in chars if c[0] >= 20]        # past the first screen's long step (its frames come out at once)
    steps = [frames[i + 1] - frames[i] for i in range(len(frames) - 1)]
    mean = (chars[-1][1] - chars[0][1]) / max(1, len(chars) - 1) if len(chars) > 1 else 0
    mstep = sum(steps) / len(steps)
    ok = len(chars) > 20 and abs(mean - 7.5) < 0.6
    print("%-4s %d characters, %.2f frames apart on average (%.0f ms; the CPC: 7.5 = 150 ms); the logic steps "
          "took %.2f frames on average here" % ("ok" if ok else "FAIL", len(chars), mean, mean * 20, mstep))
    print("PHRASE: %d failures" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

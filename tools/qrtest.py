#!/usr/bin/env python3
"""The mirror code: Q and R typed (as Q-emuLator over RDP delivers them: typed characters only,
no KEYROW) must open the mirror even when they land in different steps (qlhooks.s QR_STEPS).

A save (from tests/arch28_sav) puts Guillermo in front of the closed mirror (screen 0x72) on a
staircase (posX 0x22, altura 0x1a, posY 0x6d / 0x69 / 0x65) with numeroRomano 1 (the left
staircase, posY 0x6d, is the right one). It is loaded with F2 at step 5; Q and R are then typed,
each ONCE (qlrun types every key of a script line once, at the start of its step; Q and R are on
no KEYROW row the game reads). Checked in the state block after the run: bonus 0x0400 set or
not, the mirror open (espejoCerrado clear) on the right staircase, Guillermo dead (haFracasado)
on a wrong one.

The PC oracle is not compared: it gets keys per step (held for the script line's steps), so it
needs Q and R in the same step and has no typed-key latch.

  qrtest.py      exit 1 on any failure
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, savefmt

STAIRS = {0x6d: 1, 0x69: 2, 0x65: 3}
CASES = [  # name, script lines (step, key), trigger expected
    ("Q, R 2 steps later", [(12, "Q"), (14, "R")], True),
    ("R, Q 2 steps later", [(12, "R"), (14, "Q")], True),
    ("Q and R in one step", [(12, "Q"), (12, "R")], True),
    ("Q, R 3 steps later", [(12, "Q"), (15, "R")], True),
    ("Q, R 6 steps later", [(12, "Q"), (18, "R")], False),
    ("Q alone", [(12, "Q")], False),
    ("R alone", [(12, "R")], False),
]


def make_save(posy):
    L = open(os.path.join(QL, "tests", "arch28_sav.txt")).read().split("\n")   # the text source

    def setv(i, v):
        L[i] = "%d%s" % (v, L[i][L[i].index("//"):])
    assert "numeroRomano" in L[11] and "espejoCerrado" in L[10]
    assert "posX" in L[82] and "posX" in L[105]
    setv(10, 1)          # espejoCerrado
    setv(11, 1)          # numeroRomano: the left staircase
    setv(81, 1)          # Guillermo: facing the mirror (-y)
    setv(82, 0x22); setv(83, posy); setv(84, 0x1a)
    setv(104, 1)         # Adso just behind him
    setv(105, 0x22); setv(106, posy + 2); setv(107, 0x1a)
    return savefmt.to_compact(savefmt.values_of_text("\n".join(L).encode()))   # the game's format


def run(save, keys, ticks=30):
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    lines = [(5, 5, "F2")] + [(t, t, k) for t, k in keys]
    script = os.path.join(QL, "build", "tmp", "qrtest_script.txt")
    open(script, "w").write("\n".join("%d %d %s" % l for l in lines) + "\n")
    os.environ.pop("QEMU_KEYS", None)
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(script), realq=True, sv164=0xC1000)
    r.files["win1_abadia_sav"] = save
    r.run(ticks)
    st = r.states[-1]
    first = next((i for i, s in enumerate(r.states) if struct.unpack(">H", s[14:16])[0] & 0x0400), None)
    return r.stop_reason, st, first


def main():
    bad = 0
    for posy, num in STAIRS.items():
        save = make_save(posy)
        for name, keys, want in CASES:
            reason, st, first = run(save, keys)
            bonus = struct.unpack(">H", st[14:16])[0]
            hit = bool(bonus & 0x0400)
            flags = st[11]
            g = st[20:24]
            # Guillermo stays where the save put him (unless he fell through the trap)
            ok = reason == "tick limit" and hit == want and ((g[0], g[2]) == (0x22, 0x1a) or bool(flags & 1))
            what = ""
            if hit:
                open_ = not (flags & 4)
                dead = bool(flags & 1)
                what = "%s" % ("the mirror opens" if not dead else "the trap: Guillermo dead (haFracasado)")
                if num == 1 and (dead or not open_):
                    ok = False          # the right staircase: the mirror opens
                if num != 1 and not dead:
                    ok = False          # a wrong one: the trap
            print("%-4s staircase posY %02x (%d): %-22s -> bonus 0x0400 %s%s%s" % (
                "ok" if ok else "FAIL", posy, num, name, "set at step %d" % first if hit else "not set",
                ("; " + what) if what else "", "" if reason == "tick limit" else " (%s)" % reason))
            bad += not ok
    print("QR: %d cases failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

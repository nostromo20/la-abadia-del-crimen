#!/usr/bin/env python3
"""Adso's night question ("SHALL WE SLEEP, MASTER? Y/N"): a save (from tests/arch28_sav.txt)
puts Guillermo and Adso in their cell (screen 0x3e) at night with Adso about to ask; after the
phrase the answer is read every other step (Adso.cpp). English: Y = sleep (avanzarMomentoDia, so
the time of day moves on), N = stay up (Adso's state 5), S = nothing. Spanish (Juego::idioma 0,
poked): S = sleep. Also a PNG of the phrase in build/yntest/.

  yntest.py      exit 1 on any failure
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, savefmt

OUT = os.path.join(QL, "build", "yntest")
NOCHE = 0


def make_save():
    L = open(os.path.join(QL, "tests", "arch28_sav.txt")).read().split("\n")

    def setv(i, name, v):
        assert name in L[i], (i, name, L[i])
        L[i] = "%d%s" % (v, L[i][L[i].index("//"):])
    setv(1, "momentoDia", NOCHE)
    setv(3, "oldMomentoDia", NOCHE)
    # Guillermo beside Adso in their cell, Adso where he sleeps (Adso::posicionesPredef[2])
    setv(81, "orientacion", 3); setv(82, "posX", 0xa8); setv(83, "posY", 0x1a); setv(84, "altura", 0)
    setv(104, "orientacion", 3); setv(105, "posX", 0xa8); setv(106, "posY", 0x18); setv(107, "altura", 0)
    setv(108, "estado", 6)            # Adso: back in the cell at night -> asks
    setv(130, "cntParaDormir", 0)
    return savefmt.to_compact(savefmt.values_of_text("\n".join(L).encode()))


def run(keys, ticks, spanish=False, shots=()):
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    lines = [(5, 5, "F2")] + [(t, t, k) for t, k in keys]
    script = os.path.join(QL, "build", "tmp", "yntest_script.txt")
    open(script, "w").write("\n".join("%d %d %s" % l for l in lines) + "\n")
    for k in ("QEMU_KEYS", "INTRO", "FORCE_NIGHT", "FORCE_MIRROR"):
        os.environ.pop(k, None)
    os.environ["SAVENAME"] = "win1_abadia_sav"
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(script), realq=True, sv164=0xC1000)
    r.files["win1_abadia_sav"] = make_save()
    adso = []
    pics = {}

    def cb(rr):
        jp = struct.unpack(">I", bytes(rr.mu.mem_read(rr.base + syms["_ZL5juego"], 4)))[0]
        if spanish and rr.tick == 2:
            rr.mu.mem_write(jp, struct.pack(">i", 0))        # Juego::idioma = 0 (Spanish)
        if rr.tick in shots:
            pics[rr.tick] = rr.screen()
    r.tick_cb = cb
    r.run(ticks)
    return r, pics


def main():
    os.makedirs(OUT, exist_ok=True)
    import pngout
    bad = 0
    # the question: find when the phrase is up and when Adso waits for the answer (state flag 32 =
    # a phrase showing; the answer is read once the phrase has scrolled away)
    r, pics = run([], 140, shots=set(range(0, 140, 2)))
    busy = [bool(st[11] & 32) for st in r.states]
    t0 = next((t for t in range(6, len(busy)) if busy[t]), None)
    t1 = next((t for t in range(t0 or 6, len(busy)) if not busy[t]), None) if t0 else None
    print("phrase showing from step %s to %s" % (t0, t1))
    if t0 is None or t1 is None:
        print("FAIL: no question asked")
        return 1
    # the phrase mid-scroll, with Y/N in it: PNGs
    for t in sorted(pics):
        if t0 + 4 <= t <= t1:
            pngout.ql_rows_to_png(os.path.join(OUT, "phrase_%03d.png" % t), pngout.ql_mode8_to_indices(pics[t]), 2)

    def outcome(keys, spanish=False):
        rr, _ = run(keys, t1 + 30, spanish=spanish)
        return rr

    def momento_of(rr, t):
        return rr.states[t][9]            # state block +9: momentoDia (tools/state_layout.txt)
    base = outcome([])
    cases = [("Y (English): sleeps", [(t1 + 2, "Y"), (t1 + 3, "Y")], False, "sleep"),
             ("N (English): stays up", [(t1 + 2, "N"), (t1 + 3, "N")], False, "up"),
             ("S (English): nothing", [(t1 + 2, "S"), (t1 + 3, "S")], False, "none"),
             ("S (Spanish): sleeps", [(t1 + 2, "S"), (t1 + 3, "S")], True, "sleep")]
    end = t1 + 29
    for name, keys, sp, want in cases:
        rr = outcome(keys, sp)
        ref = outcome([], sp) if sp else base
        moved = momento_of(rr, end) != momento_of(ref, end)
        diff = rr.states[end] != ref.states[end]
        if want == "sleep":
            ok = moved
        elif want == "up":
            ok = not moved and any(rr.states[t][32] == 5 for t in range(t1, end + 1))   # +32: Adso's estado
        else:
            ok = not diff
        print("%-4s %-28s momentoDia %d -> %d (no answer: %d); state differs from no answer: %s"
              % ("ok" if ok else "FAIL", name, momento_of(rr, t1), momento_of(rr, end), momento_of(ref, end), diff))
        bad += not ok
    print("YN: %d failures (PNGs in %s)" % (bad, OUT))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

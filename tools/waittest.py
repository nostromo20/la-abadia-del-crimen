#!/usr/bin/env python3
"""The CPC's "no wait" rule (docs/speed_vs_cpc.md, option 5), the QL against the ORIGINAL CPC code:

  CPC: the main loop waits for the interrupt counter to reach [0x2618] (36 = 120 ms) - set to 0
  (no wait at all) when no cursor key has been pressed for 50 passes and no phrase is showing
  (0x41a1-0x41c2), back to 36 when a cursor key is pressed or the camera returns to Guillermo.
  QL: Logica::qlEspera -> ql_sin_espera -> src/qlstart.s wait_tick.

Both run tests/walk1.txt (keys per step / per main-loop pass); the QL's flag for every step is
compared with the CPC's [0x2618] for the same pass (tools/cpctime.py). They must agree on every
pass but those within 3 passes of a change (the two games' phrases can start a pass apart).

  waittest.py [--steps 300]      exit 1 on failure
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, cpctime


def ql_flags(script, n):
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    for k in ("QEMU_KEYS", "INTRO", "FORCE_NIGHT", "FORCE_MIRROR", "REALCLOCK"):
        os.environ.pop(k, None)
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(script), realq=True, sv164=0xC1000)
    out = []
    r.tick_cb = lambda rr: out.append(bytes(rr.mu.mem_read(rr.base + syms["ql_sin_espera"], 1))[0])
    r.run(n)
    return out


def cpc_waits(script, n):
    c = cpctime.Cpc()
    c.m.pc = 0x249A
    c.m.sp = 0xBFFE
    keys = cpctime.parse_keys(script)
    c.keys = {cpctime.KEYNUM["SPACE"]}

    def released(cc):
        cc.keys = set()
    c.hooks[0x2509] = released
    waits = []

    def at_wait(cc):                    # 0x2614 (first pass of the spin only)
        if len(waits) < its[0]:
            waits.append(cc.m.memory[0x2618])
    its = [0]

    def at_loop(cc):
        its[0] += 1
        cc.keys = {cpctime.KEYNUM[k] for f, l, k in keys if f <= its[0] <= l and k in cpctime.KEYNUM}
    c.hooks[0x25B7] = at_loop
    c.hooks[0x2614] = at_wait
    while its[0] <= n:
        c.step()
    return waits[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    a = ap.parse_args()
    script = os.path.join(QL, "tests", "walk1.txt")
    q = ql_flags(script, a.steps)            # q[t]: after step t (0-based), the wait before step t+1
    c = cpc_waits(script, a.steps)           # c[i]: the wait of pass i+1 (1-based passes)
    qn = [1 if x else 0 for x in q]
    cn = [1 if x == 0 else 0 for x in c]     # CPC 0 = no wait
    # align: QL step t's flag governs the wait after step t; the CPC's pass i's value is set during pass i
    n = min(len(qn), len(cn))
    changes = [i for i in range(1, n) if cn[i] != cn[i - 1]] + [i for i in range(1, n) if qn[i] != qn[i - 1]]
    near = lambda i: any(abs(i - k) <= 3 for k in changes)
    bad = [i for i in range(n) if qn[i] != cn[i] and not near(i)]
    first_q = next((i for i in range(n) if qn[i]), None)
    first_c = next((i for i in range(n) if cn[i]), None)
    ok = not bad and first_q is not None and first_c is not None and abs(first_q - first_c) <= 3
    print("%-4s walk1 %d steps: no-wait from step %s on the QL, pass %s on the CPC; no-wait steps QL %d, CPC %d; "
          "disagreements away from a change: %d" % ("ok" if ok else "FAIL", n, first_q, first_c, sum(qn[:n]),
                                                     sum(cn[:n]), len(bad)))
    print("WAIT: %d failures" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

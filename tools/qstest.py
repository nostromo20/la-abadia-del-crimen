#!/usr/bin/env python3
"""QSound detection (qlhooks.s qsound_init) on the harness: for each QSound vector (sysvar +$164)
and OS version (MT.INF D2), whether the game uses the AY and whether it writes the AY ports.

  QDOS (JS / Minerva, "1.xx"): any even, non-zero vector = QSound (as other QSound games decide it)
    - in the ROM port ($0C000), in RAM (a Gold Card's copy), in the expansion area: QSound
  SMSQ/E ("2.xx" and up, QPC2): only a vector in $C0000-$FFFFF (QPC2 has its own AY there)
  no vector / odd vector: no QSound
Start-up: AY.INIT through the vector in $C0000-$FFFFF (tested on Q-emuLator), else the ports are
written (mixer off, volumes 0). The AY writes while playing are checked by sndtest (regress.sh).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun

CASES = [  # (vector, version, expected QSound)
    (0, "1.60", 0), (0x0C000, "1.60", 1), (0x0C0A6, "1.60", 1), (0x3F0000, "1.98", 1),
    (0xC1000, "1.10", 1), (0x0C001, "1.60", 0),
    (0, "3.38", 0), (0x0C000, "3.38", 0), (0x3F0000, "3.38", 0), (0xC1000, "3.38", 1),
]


def main():
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    path = os.path.join(QL, "build", "tmp", "qstest_script.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n")
    fails = 0
    for vec, ver, want in CASES:
        os.environ["QDOS_VERSION"] = ver
        r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(path), sv164=vec)
        r.run(40)
        got = bytes(r.mu.mem_read(r.base + syms["qs_present"], 1))[0] and 1
        # start-up silencing through the ports where AY.INIT is not called (vector outside
        # $C0000-$FFFFF); in that range AY.INIT runs instead (the stub), as on Q-emuLator
        in_range = 0xC0000 <= vec < 0x100000
        ok = got == want and (r.ay_port_writes > 0) == bool(want and not in_range)
        fails += not ok
        print("%-4s vector %06x  version %s  QSound %d (want %d)  AY port writes %d"
              % ("ok" if ok else "FAIL", vec, ver, got, want, r.ay_port_writes))
    os.environ.pop("QDOS_VERSION", None)
    print("QSTEST: %d failures" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

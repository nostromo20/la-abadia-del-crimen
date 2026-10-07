#!/usr/bin/env python3
"""The room generator's asm twins (src/gen.s, QL_ASM_GEN) against the C++ they replace: every
screen (0..0x73) generated both ways in the same image (dev header +30 bit 5 = the C), the tile
buffers (tile, depth x, depth y of both layers, abadia_tilebuf) and the finished play area
compared byte for byte; also the generation time of each in the cyclest 68008 model.

  gentest.py          exit 1 on a difference
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, cyclest, hdiff

TB = 0x30000
TBLEN = 20 * 16 * 2 * 3
PLAY = 0x20000 + hdiff.PLAY_Y * 128


def main():
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)
    est = cyclest.Estimator(r)
    r.mu.ctl_flush_tb()
    gen = syms["_ZN6Abadia18GeneradorPantallas6generaEPh"]
    bad = []
    t = {True: 0, False: 0}
    for pal in (2, 3):
        r.call("ql_set_palette", pal)
        for n in range(0x74):
            out = {}
            for old in (True, False):
                b = bytes(r.mu.mem_read(r.base + 30, 1))[0]
                r.mu.mem_write(r.base + 30, bytes([(b | 0x20) if old else (b & ~0x20)]))
                t0 = est.total
                r.call("abadia_show_screen", n)
                t[old] += est.total - t0
                r.call("abadia_tilebuf", TB)
                out[old] = (bytes(r.mu.mem_read(TB, TBLEN)), bytes(r.mu.mem_read(PLAY, 160 * 128)))
            if out[True] != out[False]:
                bad.append((pal, n, out[True][0] != out[False][0]))
    b = bytes(r.mu.mem_read(r.base + 30, 1))[0]
    r.mu.mem_write(r.base + 30, bytes([b & ~0x20]))
    k = 2 * 0x74 * 7500.0
    print("%-4s 116 screens x day/night: tile buffers and screens, asm = C   %s"
          % ("ok" if not bad else "FAIL", "%d differ %s" % (len(bad), bad[:5])))
    print("     a room build (generation + spiral), cyclest model: C %.1f ms, asm %.1f ms a screen"
          % (t[True] / k, t[False] / k))
    print("GEN: %d failures" % (1 if bad else 0))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

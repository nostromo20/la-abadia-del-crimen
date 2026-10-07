#!/usr/bin/env python3
"""Byte-identity test of the asm memcpy/memmove/memset (src/libgcc68k.s, speed option 6) against
their C references (cpp/port/ql_runtime.cpp: c_memcpy, c_memmove, c_memset, dev build only), both
in the same QL image, run in unicorn on the same random buffer: every parity of destination and
source, overlapping moves both ways, lengths 0..600 (and a few long ones), the return value too.

  memtest.py [--cases 3000] [--seed 1]      exit 1 on a mismatch
"""
import argparse, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun

BUF_C = 0x2C000      # scratch between the system variables and the image (as kerntest.py)
BUF_A = 0x34000
BLEN = 0x6000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)
    mu = r.mu
    fails = {"memcpy": 0, "memmove": 0, "memset": 0}
    counts = dict.fromkeys(fails, 0)
    for i in range(a.cases):
        kind = ("memcpy", "memmove", "memset")[i % 3]
        n = rnd.choice([rnd.randrange(0, 40), rnd.randrange(0, 600), rnd.randrange(0, 600),
                        rnd.randrange(0, 0x2400) if rnd.random() < 0.1 else 3])
        buf = bytes(rnd.randrange(256) for _ in range(BLEN))
        mu.mem_write(BUF_C, buf)
        mu.mem_write(BUF_A, buf)
        if kind == "memset":
            d = rnd.randrange(0, BLEN - n)
            args = (d, rnd.randrange(-300, 300), n)
        elif kind == "memcpy":            # no overlap
            while True:
                d, s = rnd.randrange(0, BLEN - n), rnd.randrange(0, BLEN - n)
                if d + n <= s or s + n <= d:
                    break
            args = (d, s, n)
        else:                             # overlapping either way, or not
            d = rnd.randrange(0, BLEN - n)
            s = max(0, min(BLEN - n, d + rnd.choice([-1, 1, -2, 2, -3, 3, -4, 4, -5, 7, -8, 8, -16, 17,
                                                      rnd.randrange(-n - 8, n + 8)])))
            args = (d, s, n)
        if kind == "memset":
            ra = r.call(kind, BUF_A + args[0], args[1], n)
            rc = r.call("c_" + kind, BUF_C + args[0], args[1], n)
            ok_ret = (ra == BUF_A + args[0] and rc == BUF_C + args[0])
        else:
            ra = r.call(kind, BUF_A + args[0], BUF_A + args[1], n)
            rc = r.call("c_" + kind, BUF_C + args[0], BUF_C + args[1], n)
            ok_ret = (ra == BUF_A + args[0] and rc == BUF_C + args[0])
        same = bytes(mu.mem_read(BUF_C, BLEN)) == bytes(mu.mem_read(BUF_A, BLEN))
        counts[kind] += 1
        if not (same and ok_ret):
            fails[kind] += 1
            if fails[kind] <= 5:
                print("FAIL %s args %s ret ok %s" % (kind, args, ok_ret))
    for k in fails:
        print("%-8s %d cases, %d mismatches" % (k, counts[k], fails[k]))
    tot = sum(fails.values())
    print("MEM: %d failures" % tot)
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())

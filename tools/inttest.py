#!/usr/bin/env python3
"""The interleaved mixing buffer (QL_INTERLEAVE, 2026-10-06) against the plane layout it replaced:
the new kernels (src/kernels.s a_*_pi / a_*_pmi, tiles.s a_tiles_prof with p[14] bit 1,
colour.s ql_play_blit_pi) run on the same contents as the old ones (which kerntest checks against
their C references and colourcheck pixel for pixel), the planes interleaved for the new ones:
  - the buffer after every kernel, de-interleaved, = the planes after the old kernel;
  - the screen after ql_play_blit_pi = the screen after ql_play_blit_p, in every palette of the
    colour mapping (as colourcheck), with and without the plain-copy flag, any line parity,
    left clips.
Element i of the interleaved buffer: the mask byte at 2i, the pens at 2i + 1.

  inttest.py [--cases 3000] [--seed 1]      exit 1 on a difference
"""
import argparse, json, os, struct, sys

import random

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun

OLD = 0x2C000           # pens plane; its mask plane at +MASK_OFF (scratch below the image)
MASK_OFF = 4096
N = 0xC00               # elements used
NEW = 0x30000           # interleaved, 2 bytes an element
SRC = 0x32000           # sprite / tile source bytes
TB_O, TB_N, P_O, P_N = 0x34000, 0x34800, 0x35000, 0x35100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    assert NEW >= OLD + MASK_OFF + N and NEW + 2 * N <= SRC
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)
    mu = r.mu
    roms = r.base + syms["rom_image"] + 0x4000
    fails = {}
    counts = {}

    def setup():
        pens = bytes(rnd.randrange(256) if rnd.random() < 0.85 else 0 for _ in range(N))
        masks = bytes(rnd.choice([0, 0, rnd.randrange(16)]) for _ in range(N))
        mu.mem_write(OLD, pens)
        mu.mem_write(OLD + MASK_OFF, masks)
        il = bytearray(2 * N)
        il[0::2] = masks
        il[1::2] = pens
        mu.mem_write(NEW, bytes(il))
        mu.mem_write(SRC, bytes(rnd.randrange(256) if rnd.random() < 0.7 else 0 for _ in range(0x1000)))

    def same():
        pens = bytes(mu.mem_read(OLD, N))
        masks = bytes(mu.mem_read(OLD + MASK_OFF, N))
        il = bytes(mu.mem_read(NEW, 2 * N))
        return il[1::2] == pens and il[0::2] == masks

    def count(name, ok):
        counts[name] = counts.get(name, 0) + 1
        if not ok:
            fails[name] = fails.get(name, 0) + 1

    def tile_case(kind):
        stride = rnd.randrange(4, 40)
        off = rnd.randrange(0, N - 8 * stride - 4)
        tile = roms + 0x8300 + 32 * rnd.randrange(256)
        transp = rnd.choice([-1, 1, 2])
        r.call("a_combina_tile_%s" % kind, OLD + off, stride, tile, transp)
        r.call("a_combina_tile_%si" % kind, NEW + 2 * off, stride, tile, transp)
        return same()

    def sprite_case(kind):
        stride = rnd.randrange(1, 40)
        w = rnd.randrange(0, min(stride, 20) + 1)
        h = rnd.randrange(0, 40)
        if h * stride + w >= N:
            h = (N - w - 1) // stride
        off = rnd.randrange(0, N - h * stride - w)
        sstride = rnd.randrange(max(w, 1), 40)
        src = SRC + rnd.randrange(0, 0x400)
        r.call("a_sprite_blit_%s" % kind, OLD + off, stride, src, sstride, w, h)
        r.call("a_sprite_blit_%si" % kind, NEW + 2 * off, stride, src, sstride, w, h)
        return same()

    def tiles_case():
        tb = bytearray()
        for _ in range(20 * 16):
            px = [rnd.randrange(0, 40) | (0x80 if rnd.random() < 0.2 else 0) for _ in range(2)]
            py = [rnd.randrange(0, 40) for _ in range(2)]
            tl = [rnd.choice([0, 0, rnd.randrange(256), rnd.randrange(0x0b)]) for _ in range(2)]
            tb += bytes(px + py + tl)
        mu.mem_write(TB_O, bytes(tb))
        mu.mem_write(TB_N, bytes(tb))
        nx, ny = rnd.randrange(1, 7), rnd.randrange(1, 7)
        bx, by = rnd.randrange(-3, 16), rnd.randrange(-3, 20)
        pmin = [rnd.choice([0, rnd.randrange(0, 40)]) for _ in range(2)]
        pmax = [rnd.choice([0xfd, rnd.randrange(1, 41)]) for _ in range(2)]
        desp = 4 * rnd.randrange(0, 64)
        ult = rnd.randrange(2)
        keep = rnd.randrange(2)
        for base, tbb, pb, flag in ((OLD, TB_O, P_O, keep), (NEW, TB_N, P_N, keep | 2)):
            mu.mem_write(pb, struct.pack(">15i", tbb, bx, by, nx, ny, pmin[0], pmin[1], pmax[0], pmax[1],
                                         base, desp, 4 * nx, ult, roms + 0x8300, flag))
        r.call("a_tiles_prof", P_O)
        r.call("a_tiles_prof", P_N)
        return same() and bytes(mu.mem_read(TB_O, 1920)) == bytes(mu.mem_read(TB_N, 1920))

    # the palettes of the author's mapping, as colourcheck (the game's tables are built by ql_set_palette)
    def blit_case():
        pal = rnd.choice([2, 3, 2, 3, 1])
        r.call("ql_set_palette", pal)
        plain = rnd.randrange(2)
        mu.mem_write(qlrun.BASE + syms["ql_blit_plain"], bytes([plain]))
        wb = rnd.randrange(1, 20)
        h = rnd.randrange(1, 40)
        stride = wb + rnd.randrange(0, 8)
        off = rnd.randrange(0, N - h * stride - 1)
        x = 32 + 4 * rnd.randrange(-6, 60)
        y = rnd.randrange(0, 160 - h)
        outs = []
        for fn, src in (("ql_play_blit_p", OLD + off), ("ql_play_blit_pi", NEW + 2 * off)):
            mu.mem_write(0x20000, bytes(0x8000))
            r.call(fn, x, y, 4 * wb, h, src, stride)
            outs.append(bytes(mu.mem_read(0x20000, 0x8000)))
        mu.mem_write(qlrun.BASE + syms["ql_blit_plain"], bytes([0]))
        return outs[0] == outs[1]

    kinds = [("combina_tile_p", lambda: tile_case("p")), ("combina_tile_pm", lambda: tile_case("pm")),
             ("sprite_blit_p", lambda: sprite_case("p")), ("sprite_blit_pm", lambda: sprite_case("pm")),
             ("tiles_prof", tiles_case), ("blit", blit_case)]
    for i in range(a.cases):
        name, fn = kinds[i % len(kinds)]
        setup()
        count(name, fn())
    for name, _ in kinds:
        print("%-16s %5d cases, %d differ" % (name, counts.get(name, 0), fails.get(name, 0)))
    tot = sum(fails.values())
    print("INT: %d failures" % tot)
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""CPC-true reference: runs the ORIGINAL Z80 code of La Abadia del Crimen (CPC 6128) on a
Z80 emulator (pip package z80, kosarev) with a 64 KB memory image built from build/roms.bin
the way the CPC has it at run time:

  0x0000-0xbfff  roms[0x0000-0xbfff] (VIGASOCO layout = CPC banks 0, 1, 2 at their addresses)
  0x6d00-0x8cff  the abbey graphics, copied there from 0x8300 at start-up (CPC 0x24f2 ldir)
  0x4000-0x7fff  abadia8 (the screens' block data) while a screen is generated (CPC 0x19ef)
  0x9d00-0xa0ff  the AND/OR tables, made by the CPC's own routine at 0x3ad1

Used by tools/mixcheck.py (the sprite mixer) and by this file's own --tiles check:
  cpcref.py --tiles [first last]   the tile buffer of every screen, CPC (0x19d8 path: 0x1a70
                                   clear + 0x1a0a generator) vs build/roomcmp/tiles_NNN.bin
                                   (the C++ GeneradorPantallas, written by roomcmp's tour)
"""
import argparse, os, sys

import z80

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
HALT_AT = 0x00fe            # return address used to stop a called routine (a HALT is put there)


def roms():
    return open(os.path.join(QL, "build", "roms.bin"), "rb").read()[0x4000:]


def base_memory(r=None):
    """CPC memory in the game's normal configuration (banks 0, 1, 2, 3 = abadia1, 2, 3)"""
    r = r or roms()
    mem = bytearray(0x10000)
    mem[0:0xc000] = r[0:0xc000]
    mem[0x6d00:0x8d00] = r[0x8300:0xa300]          # 0x24f2: ldir 0x8300 -> 0x6d00, 0x2000 bytes
    mem[HALT_AT] = 0x76
    return mem


# the CPC 6128's second 64 KB, as VIGASOCO lays the banks out in roms (abadia5..8)
BANKS = {4: 0x10000, 5: 0x14000, 6: 0x18000, 7: 0x1c000}


class Cpu:
    """Z80 + the 0x4000-0x7fff bank switching the game does (OUT (0x7fxx), 0xc0 / 0xc4..0xc7)"""
    def __init__(self, mem, r=None):
        r = r or roms()
        self.m = z80.Z80Machine()
        self.m.set_memory_block(0, bytes(mem))
        self.banks = {n: bytearray(r[o:o + 0x4000]) for n, o in BANKS.items()}
        self.banks[1] = None                        # bank 1 is what is at 0x4000 now
        self.cur = 1
        self.m.set_output_callback(self._out)

    def _out(self, port, value):
        if (port >> 8) == 0x7f and (value & 0xc0) == 0xc0:
            new = (value & 7) if (value & 7) >= 4 else 1
            self.page(new)

    def page(self, new):
        if new == self.cur:
            return
        mem = self.m.memory
        self.banks[self.cur] = bytearray(mem[0x4000:0x8000])
        mem[0x4000:0x8000] = self.banks[new]
        self.cur = new

    def call(self, addr, limit=50_000_000, **regs):
        m = self.m
        m.sp = 0x00fc
        mem = m.memory
        mem[0xfc] = HALT_AT & 0xff
        mem[0xfd] = HALT_AT >> 8
        for k, v in regs.items():
            setattr(m, k, v)
        m.pc = addr
        m.set_breakpoint(HALT_AT)
        m.ticks_to_stop = limit
        while True:
            ev = m.run()
            if ev & (m._BREAKPOINT_HIT | m._TICKS_LIMIT_HIT):
                break
        if m.pc != HALT_AT:
            raise RuntimeError("Z80 call %04x did not return (pc %04x, events %d)" % (addr, m.pc, ev))

    def mem(self):
        return self.m.memory


def tables(cpu):
    """the AND/OR tables (0x9d00-0xa0ff) and flip table, from the CPC's own code (0x3ad1)"""
    cpu.call(0x3ad1)


def screen_addr(r, n):
    """CPC address of screen n's data with abadia8 at 0x4000 (0x2d00)"""
    a8 = r[0x1c000:0x20000]
    hl = 0x4000
    for _ in range(n):
        hl += a8[hl - 0x4000]
    return hl


def gen_tiles(n, r=None):
    """runs 0x1a70 + 0x1a0a for screen n; returns the tile buffer 0x8d80 (16x20 x 6 bytes)"""
    r = r or roms()
    cpu = Cpu(base_memory(r), r)
    cpu.call(0x3a61)                                  # start-up: flip table, the mirror closed
    cpu.page(1)
    cpu.page(7)                                       # abadia8 paged in (0x19ef)
    mem = cpu.mem()
    a = screen_addr(r, n)
    if n == 0:
        a = 0x4000
    cpu.call(0x1a70, a=0)                             # clear the tile buffer (+ the play area)
    mem[0x165e] = 0x67
    mem[0x165f] = 0x16                                # 0x19e9: jp 0x1667 (write the tile)
    cpu.call(0x1a0a, ix=a + 1)
    return bytes(mem[0x8d80:0x8d80 + 0x780])


def cpc_to_cpp_layout(tb):
    """CPC entry [pX0 pY0 t0 pX1 pY1 t1] -> abadia_tilebuf's [t0 pX0 pY0 t1 pX1 pY1]"""
    out = bytearray()
    for i in range(0, len(tb), 6):
        e = tb[i:i + 6]
        out += bytes([e[2], e[0], e[1], e[5], e[3], e[4]])
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", nargs="*", type=lambda s: int(s, 0))
    ap.add_argument("--dir", default=os.path.join(QL, "build", "roomcmp"), help="where the tour's tiles_NNN.bin are")
    a = ap.parse_args()
    if a.tiles is not None:
        first, last = (a.tiles + [0, 0x73])[:2] if a.tiles else (0, 0x73)
        r = roms()
        bad = 0
        for n in range(first, last + 1):
            p = os.path.join(a.dir, "tiles_%03d.bin" % n)
            if not os.path.exists(p):
                continue
            cpp = open(p, "rb").read()
            cpc = cpc_to_cpp_layout(gen_tiles(n, r))
            diffs = []
            for e in range(320):
                if cpp[e * 6:e * 6 + 6] != cpc[e * 6:e * 6 + 6]:
                    diffs.append((e // 16, e % 16, cpc[e * 6:e * 6 + 6].hex(), cpp[e * 6:e * 6 + 6].hex()))
            if diffs:
                bad += 1
                print("screen %02x: %d entries differ (row, col, CPC t0 x0 y0 t1 x1 y1, C++)" % (n, len(diffs)))
                for d in diffs[:6]:
                    print("    ", d)
        print("TILES: %d screens differ" % bad)
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

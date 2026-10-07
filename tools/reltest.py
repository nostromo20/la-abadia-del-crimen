#!/usr/bin/env python3
"""Runs the RELEASE jobs' own 68000 code in unicorn, as QDOS would start them, and checks them
(build_release.sh outputs; docs/release.md):

  abadia        loaded at a job base with its dataspace above (from the QDOS header that
                mkrelease.py wrote), A7 at the top: the stub moves the packed image up, unpacks
                it and patches the settings into the header; stopped where it JSRs to the game.
                The unpacked image must be byte-identical to build/rel/abadia_r_bin (the build
                before packing; the default settings are the image's own), and is written to
                build/rel/unpacked_bin for hdiff (--image/--sym).
  abadia_title  unpacks the loading screen into $20000: identical to loadscreen/A4S_scr.

Times are cyclest's 68008 model (8-bit bus, 4 clocks a byte, 7.5 MHz, roughly +-30%). The game
area is above the screen, so there is no display contention; the title job writes INTO the
screen memory, which a real QL slows a little more (not modelled).

  reltest.py [--base 0x40000]
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cyclest
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_BLOCK, UC_HOOK_INTR
from unicorn import m68k_const as M

REL = os.path.join(QL, "build", "rel")
WIN = os.path.join(QL, "release", "win")


class Timer:
    def __init__(self, mu):
        self.cost, self.cycles = {}, 0
        mu.hook_add(UC_HOOK_BLOCK, self.on_block)

    def on_block(self, mu, addr, size, data):
        c = self.cost.get((addr, size))
        if c is None:
            code = bytes(mu.mem_read(addr, size))
            c = sum(cyclest.insn_cost(i) for i in cyclest.md.disasm(code, addr))
            self.cost[(addr, size)] = c
        self.cycles += c


def job(name):
    """the job file as the folder version holds it: (code, dataspace)"""
    d = open(os.path.join(WIN, name), "rb").read()
    assert d[:18] == b"]!QDOS File Header" and d[19] == 15
    acc, typ, ds, ex = struct.unpack(">BBII", d[20:30])
    assert typ == 1
    return d[30:], ds


def start(code, ds, base):
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68040)
    mu.mem_map(0, 0x100000)
    top = base + len(code) + ds
    assert top <= 0x100000
    mu.mem_write(base, code)
    sp = top - 8                                 # QDOS: a word of channel count, a null command string
    mu.mem_write(sp, bytes(8))
    mu.reg_write(M.UC_M68K_REG_A7, sp)
    mu.reg_write(M.UC_M68K_REG_A6, base)
    stop = {}

    def on_intr(mu, intno, data):
        stop["trap"] = (intno, mu.reg_read(M.UC_M68K_REG_D0), mu.reg_read(M.UC_M68K_REG_D3))
        mu.emu_stop()
    mu.hook_add(UC_HOOK_INTR, on_intr)
    return mu, top, stop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="0x40000")
    a = ap.parse_args()
    base = int(a.base, 16)
    bad = 0
    # ---- the game job
    code, ds = job("abadia")
    image = open(os.path.join(REL, "abadia_r_bin"), "rb").read()
    apl = open(os.path.join(REL, "abadia_r.apl"), "rb").read()
    dest = code.find(apl)
    mu, top, stop = start(code, ds, base)
    t = Timer(mu)
    mu.emu_start(base, base + dest)                # until the JSR lands on the game
    pc = mu.reg_read(M.UC_M68K_REG_PC)
    out = bytes(mu.mem_read(base + dest, len(image)))
    open(os.path.join(REL, "unpacked_bin"), "wb").write(out)
    same = out == image and pc == base + dest and not stop
    print("%-4s abadia: job area %d bytes (file %d + dataspace %d); unpacked %d bytes at +%d, identical to "
          "build/rel/abadia_r_bin: %s; stub (move + aPLib unpack) %d cycles = %.2f s on a 68008"
          % ("ok" if same else "FAIL", len(code) + ds, len(code), ds, len(image), dest, out == image,
             t.cycles, t.cycles / (cyclest.MHZ * 1e6)))
    bad += not same
    # the game's BSS must stay below the stack the stub was entered with
    need = int(open(os.path.join(REL, "mkimage.log")).read().split("RESPR(")[1].split(")")[0])
    room = top - 8 - (base + dest + need)
    print("%-4s abadia: %d bytes between the end of the game's BSS and the job's stack" % ("ok" if room >= 1024 else "FAIL", room))
    bad += room < 1024
    # a dataspace too small: the stub must refuse (out of memory) before writing anything
    mu, top, stop = start(code, need // 2, base)
    mu.emu_start(base, base + dest, count=2000000)
    ok = stop.get("trap", (None,))[0] is not None and stop["trap"][1] == 5 and stop["trap"][2] == 0xFFFFFFFD
    print("%-4s abadia: with too little memory the job removes itself with 'out of memory' (MT.FRJOB, D3 = -3)" % ("ok" if ok else "FAIL"))
    bad += not ok
    # ---- the title job
    code, ds = job("abadia_title")
    scr = open(os.path.join(QL, "loadscreen", "A4S_scr"), "rb").read()
    mu, top, stop = start(code, ds, base)
    t = Timer(mu)
    mu.emu_start(base, 0, count=20000000)
    shown = bytes(mu.mem_read(0x20000, 0x8000))
    ok = shown == scr and stop.get("trap", (None, None))[1] == 5
    print("%-4s abadia_title: screen identical to loadscreen/A4S_scr: %s, then MT.FRJOB; %d cycles = %.2f s on a 68008"
          % ("ok" if ok else "FAIL", shown == scr, t.cycles, t.cycles / (cyclest.MHZ * 1e6)))
    bad += not ok
    print("RELTEST: %d failures" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

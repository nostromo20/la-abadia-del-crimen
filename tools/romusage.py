#!/usr/bin/env python3
"""Which bytes of the embedded CPC data image (rom_image = VIGASOCO romsPtr, build/roms.bin,
0x24000 bytes) does the QL game actually use?  DYNAMIC part of the usage map for
docs/compression.md (the static part is worked out there).

Runs the QL image in the harness (qlrun) over many scenarios with a memory hook on the whole
rom_image range and records, per byte, the FIRST access: read (the initial content matters) or
write (the game generates it: the initial content is dead, e.g. the flipped graphics).

  romusage.py [--out build/romusage.bin]    then prints the per-bank summary and unread spans

Scenarios: walk1 4000, enter 900, saveload 900, speed_walk 900, the intro (whole, with page
turns, SPACE at the end, then play), night (FORCE_NIGHT enter 600), the mirror harness, arch28
and the mirror staircases (saves), every screen drawn (abadia_show_screen 0..0x73), every
sound entry and both parchment tunes.
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, savefmt
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

SIZE = 0x24000
# VIGASOCO romsPtr layout (tools/mkroms.py); roms = romsPtr + 0x4000
BANKS = [(0x00000, 0x04000, "abadia0 (CPC title screen)"),
         (0x04000, 0x04100, "gap before abadia1"),
         (0x04100, 0x08000, "abadia1 (CPC 0x0100-0x3fff: code + tables)"),
         (0x08000, 0x0c000, "abadia2 (CPC 0x4000-0x7fff: code + tables)"),
         (0x0c000, 0x10000, "abadia3 (CPC 0x8000-0xbfff: gfx, tiles, text)"),
         (0x10000, 0x14000, "unused (romsPtr 0x10000-0x13fff)"),
         (0x14000, 0x18000, "abadia5 (CPC bank 4)"),
         (0x18000, 0x1c000, "abadia6 (CPC bank 5: flipped gfx built here)"),
         (0x1c000, 0x20000, "abadia7 (CPC bank 6: heights)"),
         (0x20000, 0x24000, "abadia8 (CPC bank 7: screens, panel, ending tune)")]

SAVE_SRC = os.path.join(QL, "tests", "arch28_sav.txt")   # the text source of tests/arch28_sav


class Usage:
    def __init__(self):
        self.first = bytearray(SIZE)       # 0 never, 1 read first, 2 written first
        self.read = bytearray(SIZE)

    def attach(self, r, syms):
        base = qlrun.BASE + syms["rom_image"]
        first, read = self.first, self.read

        def on_read(mu, access, addr, size, value, data):
            o = addr - base
            for i in range(size):
                if 0 <= o + i < SIZE:
                    read[o + i] = 1
                    if not first[o + i]:
                        first[o + i] = 1

        def on_write(mu, access, addr, size, value, data):
            o = addr - base
            for i in range(size):
                if 0 <= o + i < SIZE and not first[o + i]:
                    first[o + i] = 2
        r.mu.hook_add(UC_HOOK_MEM_READ, on_read, begin=base, end=base + SIZE - 1)
        r.mu.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=base, end=base + SIZE - 1)


def runner(script_lines=None, script=None, env=None, save=None, realq=True):
    for k in ("INTRO", "FORCE_NIGHT", "FORCE_MIRROR", "HG_VERIFY", "QEMU_KEYS"):
        os.environ.pop(k, None)
    os.environ.update(env or {})
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    if script_lines is not None:
        script = os.path.join(QL, "build", "tmp", "romusage_script.txt")
        open(script, "w").write("\n".join("%d %d %s" % l for l in script_lines) + "\n")
    sc = qlrun.load_script(os.path.join(QL, script)) if script else []
    r = qlrun.Runner(image, syms, qlrun.BASE, sc, realq=realq, sv164=0xC1000)
    if save:
        r.files["win1_abadia_sav"] = save
    return r, syms


def mirror_save(posy):
    L = open(SAVE_SRC).read().split("\n")

    def setv(i, v):
        L[i] = "%d%s" % (v, L[i][L[i].index("//"):])
    setv(10, 1); setv(11, 1); setv(81, 1); setv(82, 0x22); setv(83, posy); setv(84, 0x1a)
    setv(104, 1); setv(105, 0x22); setv(106, posy + 2); setv(107, 0x1a)
    return savefmt.to_compact(savefmt.values_of_text("\n".join(L).encode()))   # the game's format


def scenarios():
    yield "walk1 4000", dict(script="tests/walk1.txt"), 4000
    yield "enter 900", dict(script="tests/enter.txt"), 900
    yield "saveload 900", dict(script="tests/saveload.txt"), 900
    yield "speed_walk 900", dict(script="tests/speed_walk.txt"), 900
    yield "intro, whole (page turns), SPACE, play", dict(script="tests/intro_full.txt", env={"INTRO": "1"}), 3700
    yield "night (FORCE_NIGHT) enter 600", dict(script="tests/enter.txt", env={"FORCE_NIGHT": "1"}), 600
    yield "mirror harness walk1 300", dict(script="tests/walk1.txt", env={"FORCE_MIRROR": "1"}), 300
    yield "arch28 (save)", dict(script="tests/arch28.txt", save=open(os.path.join(QL, "tests", "arch28_sav"), "rb").read()), 45
    # the ending: Juego::enFinal set (the static juego pointer, byte +7: abadia_ending reads it
    # there), so the next step goes to the ending parchment (its text and tune)
    yield "ending parchment (enFinal poked at step 30)", dict(script="tests/enter.txt", poke=(30, "_ZL5juego", 7, 1)), 3500
    for posy in (0x6d, 0x69):
        yield "mirror staircase %02x, Q+R" % posy, dict(script_lines=[(5, 5, "F2"), (12, 12, "Q"), (12, 12, "R")],
                                                      save=mirror_save(posy)), 120


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(QL, "build", "romusage.bin"))
    ap.add_argument("--quick", action="store_true", help="short runs only (tool check)")
    ap.add_argument("--only", help="run only the scenarios whose name contains this, and merge into --out")
    a = ap.parse_args()
    u = Usage()
    if a.only and os.path.exists(a.out):
        u.first[:] = open(a.out, "rb").read()
    for name, kw, ticks in scenarios():
        if a.only and a.only not in name:
            continue
        if a.quick:
            ticks = min(ticks, 60)
        poke = kw.pop("poke", None)
        r, syms = runner(**kw)
        u.attach(r, syms)
        if poke:
            def cb(rr, poke=poke, syms=syms):
                if rr.tick == poke[0]:
                    ptr = struct.unpack(">I", bytes(rr.mu.mem_read(qlrun.BASE + syms[poke[1]], 4)))[0]
                    rr.mu.mem_write(ptr + poke[2], bytes([poke[3]]))
            r.tick_cb = cb
        r.run(ticks)
        print("%-45s %s after %d steps" % (name, r.stop_reason, r.tick), flush=True)
    if a.only:
        open(a.out, "wb").write(bytes(u.first))
        report(u.first)
        return 0
    # every screen drawn (as roomcmp's tour; no frame interrupts: they would end a call early)
    r, syms = runner(realq=False)
    u.attach(r, syms)
    r.run(1)
    for n in range(0x74):
        r.call("abadia_show_screen", n)
    print("%-45s 116 screens" % "every screen (abadia_show_screen)", flush=True)
    # every sound and both tunes (as sndtest)
    r, syms = runner(realq=False)
    u.attach(r, syms)
    r.run(1)
    roms = qlrun.BASE + syms["rom_image"] + 0x4000
    cases = [0x0ffd, 0x1002, 0x1007, 0x100c, 0x1011, 0x1016, 0x101b, 0x1020, 0x1025, 0x102a, 0x102f, -1, -2]
    for c in cases:
        r.call("snd_init", roms)
        if c == -1:
            r.call("ql_music", 0)
        elif c == -2:
            r.call("ql_music", 1)
        else:
            r.call("snd_play", c)
        for f in range(1 if a.quick else (12000 if c < 0 else 300)):
            r.call("snd_poll")
    print("%-45s %d cases" % ("every sound entry + both tunes", len(cases)), flush=True)
    open(a.out, "wb").write(bytes(u.first))
    report(u.first)
    return 0


def spans(first, lo, hi, val):
    out, s = [], None
    for i in range(lo, hi):
        if (first[i] == val) != (s is not None):
            if s is None:
                s = i
            else:
                out.append((s, i))
                s = None
    if s is not None:
        out.append((s, hi))
    return out


def report(first):
    print()
    print("%-50s %7s %7s %7s %7s" % ("bank (romsPtr range)", "size", "read1st", "write1st", "never"))
    for lo, hi, name in BANKS:
        c = [0, 0, 0]
        for i in range(lo, hi):
            c[first[i]] += 1
        print("%05x-%05x %-38s %7d %7d %7d %7d" % (lo, hi - 1, name, hi - lo, c[1], c[2], c[0]))


if __name__ == "__main__":
    sys.exit(main())

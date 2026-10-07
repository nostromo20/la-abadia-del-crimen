#!/usr/bin/env python3
"""The CPC's room build (2026-10-05): black play area, then the cells from the centre outwards.

  1. order: the cells GeneradorPantallas::dibujaBufferTiles hands to ql_play_cell, in order, against
     the positions the ORIGINAL CPC routine (0x4eb2, its loop at 0x4f20: ix = 0x8d80 + row*0x60 +
     column*6) visits, run on the Z80 (tools/cpcref.py's machine)
  2. finished screens: every screen (0..0x73) in the day and the night palettes, drawn on a screen
     full of junk, the QL's play area byte for byte against the old build (header +30 bit 4: pen 0
     fill, then the tiles row by row)
  3. the transition: in the middle of a build (after the first cells) the rest of the play area
     is QL black, not pen 0

  spiraltest.py [--story [screen]]   exit 1 on failure; --story writes build/story/spiral_*.png
"""
import argparse, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, cpcref, pngout, hdiff
from unicorn import UC_HOOK_CODE
import unicorn.m68k_const as M

PLAY = 0x20000 + hdiff.PLAY_Y * 128
PLAY_LEN = 160 * 128
fails = []


def check(name, ok, detail):
    print("%-4s %-60s %s" % ("ok" if ok else "FAIL", name, detail))
    if not ok:
        fails.append(name)


def cpc_order():
    r = cpcref.roms()
    cpu = cpcref.Cpu(cpcref.base_memory(r), r)
    cpcref.tables(cpu)
    m = cpu.m
    m.sp = 0x00fc
    mem = m.memory
    mem[0xfc] = cpcref.HALT_AT & 0xff
    mem[0xfd] = cpcref.HALT_AT >> 8
    m.pc = 0x4eb2
    order = []
    for _ in range(3_000_000):
        if m.pc == 0x4f20:
            off = m.ix - 0x8d80
            order.append((off % 0x60 // 6, off // 0x60))     # (column, row)
        if m.pc == cpcref.HALT_AT:
            break
        m.ticks_to_stop = 1
        m.run()
    return order


def runner():
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    for k in ("QEMU_KEYS", "INTRO", "FORCE_NIGHT", "FORCE_MIRROR", "REALCLOCK"):
        os.environ.pop(k, None)
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)
    return r


def set_old(r, old):
    b = bytes(r.mu.mem_read(r.base + 30, 1))[0]
    b = (b | 0x10) if old else (b & ~0x10)
    r.mu.mem_write(r.base + 30, bytes([b]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", nargs="?", const=0x1d, type=lambda x: int(x, 0), default=None)
    a = ap.parse_args()
    r = runner()
    mu = r.mu
    cells = []

    def on_cell(uc, addr, size, data):
        sp = uc.reg_read(M.UC_M68K_REG_A7)
        x, y = [int.from_bytes(uc.mem_read(sp + 4 + 4 * i, 4), "big", signed=True) for i in range(2)]
        cells.append(((x - 32) // 16, y // 8))
    ad = r.base + r.syms["ql_play_cell"]
    mu.hook_add(UC_HOOK_CODE, on_cell, begin=ad, end=ad)
    mu.ctl_flush_tb()                                 # (hooks added after code was translated)

    # 1. order
    cpc = cpc_order()
    set_old(r, False)
    cells.clear()
    r.call("abadia_show_screen", 0x1d)
    check("cell order = the CPC's 0x4eb2 (Z80 trace of its 0x4f20 loop)",
          cells == cpc and len(cpc) == 320 and len(set(cpc)) == 320,
          "%d cells drawn, CPC %d; first %s" % (len(cells), len(cpc), cpc[:6]))

    # 2. finished screens, day and night
    rnd = random.Random(5)
    bad = []
    paths_bad = []                                    # the old build must not use ql_play_cell
    for pal in (2, 3):
        r.call("ql_set_palette", pal)
        for n in range(0, 0x74):
            shots = []
            for old in (True, False):
                set_old(r, old)
                mu.mem_write(PLAY, bytes(rnd.randrange(256) for _ in range(PLAY_LEN)))
                cells.clear()
                r.call("abadia_show_screen", n)
                shots.append(bytes(mu.mem_read(PLAY, PLAY_LEN)))
                if len(cells) != (0 if old else 320):
                    paths_bad.append((pal, n, old, len(cells)))
            if shots[0] != shots[1]:
                bad.append((pal, n, sum(1 for i in range(PLAY_LEN) if shots[0][i] != shots[1][i])))
    set_old(r, False)
    check("116 screens x day/night: QL screen identical to the old build", not bad,
          "%d differ %s" % (len(bad), bad[:5]))
    check("each build took its own path (old: no ql_play_cell; new: 320 cells)", not paths_bad, str(paths_bad[:4]))

    # 3. mid-build: black where no cell has been drawn yet
    r.call("ql_set_palette", 2)
    snap = {}
    count = [0]

    def on_cell2(uc, addr, size, data):
        count[0] += 1
        if count[0] == 101:
            snap["scr"] = bytes(uc.mem_read(PLAY, PLAY_LEN))
            snap["cells"] = list(cells)
    h = mu.hook_add(UC_HOOK_CODE, on_cell2, begin=ad, end=ad)
    mu.ctl_flush_tb()
    cells.clear()
    mu.mem_write(PLAY, bytes(rnd.randrange(256) for _ in range(PLAY_LEN)))
    r.call("abadia_show_screen", 0x1d)
    mu.hook_del(h)
    drawn = set(snap["cells"][:100])
    nonblack = 0
    for cy in range(20):
        for cx in range(16):
            if (cx, cy) in drawn:
                continue
            for j in range(8):
                o = (cy * 8 + j) * 128 + cx * 8
                nonblack += sum(1 for b in snap["scr"][o:o + 8] if b)
    check("mid-build (100 cells drawn): every other cell QL black", nonblack == 0,
          "%d non-black bytes outside the drawn cells" % nonblack)

    if a.story is not None:
        story(r, a.story)
    print("SPIRAL: %d failures" % len(fails))
    return 1 if fails else 0


def story(r, n):
    """one room build (screen n after screen 0x1b) as the 68008 would show it: a frame every 2
    QL frames (40 ms) of cyclest-modelled time from the start of the build (the black clear),
    to the finished room: build/story/spiral_NN.png (2x) and spiral_strip.png (all, 6 a row)"""
    import cyclest
    out = os.path.join(QL, "build", "story")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.startswith("spiral_"):
            os.remove(os.path.join(out, f))
    mu = r.mu
    r.call("ql_set_palette", 2)
    r.call("abadia_show_screen", 0x1b)                 # some room on the screen first
    est = cyclest.Estimator(r)
    step = int(0.040 * 7.5e6)                         # 40 ms of 7.5 MHz cycles
    frames = [bytes(mu.mem_read(0x20000, 0x8000))]
    nxt = [step]

    def on_block(uc, addr, size, data):
        if est.total >= nxt[0]:
            nxt[0] += step
            frames.append(bytes(uc.mem_read(0x20000, 0x8000)))
    mu.hook_add(cyclest.UC_HOOK_BLOCK, on_block)
    mu.ctl_flush_tb()
    r.call("abadia_show_screen", n)
    frames.append(bytes(mu.mem_read(0x20000, 0x8000)))
    imgs = []
    for k, fr in enumerate(frames):
        rows = pngout.ql_mode8_to_indices(fr)[hdiff.PLAY_Y:hdiff.PLAY_Y + 160]
        imgs.append(rows)
        pngout.ql_rows_to_png(os.path.join(out, "spiral_%02d.png" % k), rows, 2)
    per = 6
    strip = []
    for g in range(0, len(imgs), per):
        group = imgs[g:g + per]
        for y in range(164):
            line = []
            for im in group:
                line += (im[y] if y < 160 else [7] * 256) + [7] * 4
            line += [7] * (260 * (per - len(group)))
            strip.append(line)
    pngout.ql_rows_to_png(os.path.join(out, "spiral_strip.png"), strip, 1)
    print("storyboard: %d frames (one every 40 ms of modelled 68008 time, %.0f ms in all), "
          "build/story/spiral_NN.png and spiral_strip.png (screen %02x)" % (len(imgs), est.total / 7500.0, n))


if __name__ == "__main__":
    sys.exit(main())

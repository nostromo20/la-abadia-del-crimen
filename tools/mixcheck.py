#!/usr/bin/env python3
"""Sprite mixer vs the CPC: every mixer batch the C++ (VIGASOCO MezcladorSprites, as compiled
for the QL and the PC oracle) ran is run again through the ORIGINAL Z80 mixer of the CPC game
(0x4914: depth sort, 0x4d9e tiles between depths, 0x4e49 tile combine, 0x4b14 sprite draw),
on the same inputs, and the sprite buffer areas are compared pixel by pixel (pens). The tile
buffer the C++ mixed with is also compared with the one the CPC's own screen generator (0x1a70 +
0x1a0a, tools/cpcref.py) builds for that screen, so the depths the mixer works from are checked
too (that is where the arch-pillar bug was: tools/cpcref.py, Comandos.cpp FlipX).

Inputs come from the host scene recorder (build/host/oracle_scenes, cpp/build_oracle_scenes.sh)
run with MIXDUMP=file: per batch the tile buffer, the sprites and their graphics; per processed
sprite its mixed area. The Z80 side gets them as the CPC holds them: the tile buffer at 0x8d80,
sprite entries at 0x2e17 (20 bytes each, in the C++ order), the graphics copied to 0xc000+
(monks: the head there and the habit through the table at 0x48c8), the AND/OR tables made by
the CPC's own 0x3ad1. Batches with the lamp (SpriteLuz) visible are skipped (its CPC path
needs state set by 0x26a3).

  mixcheck.py --script tests/enter.txt --ticks 900      record + compare
  mixcheck.py --dump file.bin                           compare an existing dump
  mixcheck.py --script tests/arch28.txt --ticks 30 --save tests/arch28_sav
The recording runs with NOCOMPOSE=1: the QL_TILE_COMPOSE patches are not on the CPC (they are
checked by tools/tilecompose.py --check instead).
                                                        start from a save file (loaded by F2)
  options: --show N  print the first N differing areas in detail
Exit 1 on any difference.
"""
import argparse, os, struct, subprocess, sys
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cpcref

WSL_QL = qlpaths.WSL_QL
GFX_BASE = 0xc000
STOP = 0x4bdf                  # the mixer's postprocess (screen copy): the batch is mixed


def parse(data):
    """-> list of (tick, tilebuf 1920 bytes CPC layout, sprites[], outputs{idx: (...)})"""
    p = 0
    batches = []

    def i32():
        nonlocal p
        v = struct.unpack_from("<i", data, p)[0]
        p += 4
        return v
    while p < len(data):
        tag = data[p]
        p += 1
        if tag == ord('B'):
            tick = i32()
            room = i32()
            tb = data[p:p + 1920]
            p += 1920
            num = i32()
            sprs = []
            for i in range(num):
                v = [i32() for _ in range(19)]
                s = dict(zip(["vis", "chg", "des", "prof", "x", "y", "ox", "oy", "w", "h", "ow", "oh", "gfx",
                              "lx", "ly", "kind", "anim", "traje", "pad"], v))
                s["idx"] = i
                if s["vis"] and s["kind"] != 2:
                    n = s["w"] * s["h"]
                    s["data"] = data[p:p + n]
                    p += n
                sprs.append(s)
            batches.append({"tick": tick, "room": room, "tb": tb, "sprs": sprs, "out": {}})
        elif tag == ord('O'):
            idx, desp, xt, yt, wf, hf = [i32() for _ in range(6)]
            n = wf * 4 * hf
            batches[-1]["out"][idx] = (desp, xt, yt, wf, hf, data[p:p + n])
            p += n
        else:
            raise ValueError("bad record %02x at %d" % (tag, p - 1))
    return batches


def pens(b):
    """CPC Mode 1 byte -> 4 pens (pixel k: pen bit 0 = bit 7-k, pen bit 1 = bit 3-k)"""
    return [((b >> (7 - k)) & 1) | (((b >> (3 - k)) & 1) << 1) for k in range(4)]


def covered(xt, yt, wf, hf):
    """the play-area rectangle an area is copied to (vuelcaBufferAPantalla), or None"""
    if xt >= (32 + 256) // 4 or yt >= 200:
        return None
    x0, x1 = max(xt * 4, 32), min(xt * 4 + wf * 4, 288)
    y0, y1 = max(yt, 40), min(yt + hf, 200)
    return (x0, y0, x1, y1) if x0 < x1 and y0 < y1 else None


class Ref:
    def __init__(self):
        r = cpcref.roms()
        self.r = r
        cpu = cpcref.Cpu(cpcref.base_memory(r), r)
        cpcref.tables(cpu)
        self.base = bytes(cpu.mem())

    def run(self, b):
        cpu = cpcref.Cpu(self.base, self.r)
        m = cpu.m
        mem = m.memory
        mem[0x8d80:0x8d80 + 1920] = b["tb"]
        ent = 0x2e17
        gfx = GFX_BASE
        where = {}
        for s in b["sprs"]:
            if not s["vis"]:
                continue
            if s["kind"] == 2:
                return None                                   # the lamp: skipped
            if ent + 20 > 0x2fe3:
                raise RuntimeError("more visible sprites than the CPC table holds")
            e = bytearray(20)
            e[0] = (0x80 if s["chg"] else 0) | (s["prof"] & 0x3f)
            e[1], e[2], e[3], e[4] = s["x"] & 0xff, s["y"] & 0xff, s["ox"] & 0xff, s["oy"] & 0xff
            e[5] = (s["w"] & 0x7f) | (0x80 if s["des"] else 0)
            e[6] = s["h"] & 0xff
            mem[gfx:gfx + len(s["data"])] = s["data"]
            e[7], e[8] = gfx & 0xff, gfx >> 8
            e[9], e[10] = s["ow"] & 0xff, s["oh"] & 0xff
            if s["kind"] == 1:
                e[11] = s["anim"] & 0x0f
                suit = gfx + s["w"] * 10
                mem[0x48c8 + 2 * (s["anim"] & 0x0f)] = suit & 0xff
                mem[0x48c9 + 2 * (s["anim"] & 0x0f)] = suit >> 8
            else:
                e[11] = 0x80
            e[0x12], e[0x13] = s["lx"] & 0xff, s["ly"] & 0xff
            gfx += len(s["data"])
            gfx = (gfx + 1) & ~1
            if gfx > 0xfff0:
                raise RuntimeError("sprite graphics do not fit")
            mem[ent:ent + 20] = e
            where[s["idx"]] = ent
            ent += 20
        mem[ent] = 0xff
        m.sp = 0x00fc
        mem[0xfc] = cpcref.HALT_AT & 0xff
        mem[0xfd] = cpcref.HALT_AT >> 8
        m.pc = 0x4914
        m.set_breakpoint(STOP)
        m.set_breakpoint(cpcref.HALT_AT)
        m.ticks_to_stop = 200_000_000
        while True:
            ev = m.run()
            if ev & (m._BREAKPOINT_HIT | m._TICKS_LIMIT_HIT):
                break
        if m.pc not in (STOP, cpcref.HALT_AT):
            raise RuntimeError("the Z80 mixer did not finish (pc %04x)" % m.pc)
        out = {}
        for idx, a in where.items():
            if mem[a] & 0x40:
                buf = mem[a + 0x10] | (mem[a + 0x11] << 8)
                xt, yt, wf, hf = mem[a + 0x0c], mem[a + 0x0d], mem[a + 0x0e], mem[a + 0x0f]
                px = []
                for byte in mem[buf:buf + wf * hf]:
                    px += pens(byte)
                out[idx] = (buf - 0x9500, xt, yt, wf, hf, bytes(px))
        return out


def wsl_path(path):
    return WSL_QL + "/" + os.path.relpath(os.path.abspath(path), QL).replace("\\", "/")


def record(script, ticks, path, save=None):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    wp = wsl_path(path)
    extra = ["NOCOMPOSE=1"]      # QL_TILE_COMPOSE off: the CPC's own tile buffers (tools/tilecompose.py)
    if save:
        tmp = os.path.join(QL, "build", "tmp", "mixcheck_sav")
        open(tmp, "wb").write(open(save, "rb").read())     # the oracle may write it (F1)
        extra += ["SAVEFILE=" + wsl_path(tmp)]
    subprocess.run(["wsl", "env", "MIXDUMP=" + wp] + extra + [WSL_QL + "/build/host/oracle_scenes", WSL_QL + "/build/roms.bin",
                    WSL_QL + "/" + script, str(ticks), WSL_QL + "/build/tmp/mixcheck_state.bin"], check=True, env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script")
    ap.add_argument("--ticks", type=int, default=900)
    ap.add_argument("--dump")
    ap.add_argument("--show", type=int, default=3)
    ap.add_argument("--save", help="save file for the F2 load in the script")
    a = ap.parse_args()
    path = a.dump
    if a.script:
        path = os.path.join(QL, "build", "tmp", "mixcheck_%s.bin" % os.path.splitext(os.path.basename(a.script))[0])
        record(a.script, a.ticks, path, a.save)
    batches = parse(open(path, "rb").read())
    ref = Ref()
    n_areas = n_bad = n_skip = n_px = 0
    shown = 0
    gen = {}
    n_tb = n_tb_bad = 0
    for b in batches:
        # the tile buffer against the CPC's generator (marks clear at a batch's start)
        room = b["room"]
        if room not in gen:
            gen[room] = cpcref.gen_tiles(room, ref.r)
        n_tb += 1
        if b["tb"] != gen[room]:
            n_tb_bad += 1
            if shown < a.show:
                shown += 1
                d = [e for e in range(320) if b["tb"][e * 6:e * 6 + 6] != gen[room][e * 6:e * 6 + 6]]
                print("tick %d screen %02x: tile buffer differs from the CPC's in %d entries, first (row %d, col %d) "
                      "C++ %s CPC %s" % (b["tick"], room, len(d), d[0] // 16, d[0] % 16,
                                         b["tb"][d[0] * 6:d[0] * 6 + 6].hex(), gen[room][d[0] * 6:d[0] * 6 + 6].hex()))
        out = ref.run(b)
        if out is None:
            n_skip += 1
            continue
        for idx, (desp, xt, yt, wf, hf, px) in b["out"].items():
            if idx not in out:
                continue                       # not processed in the CPC's batch (buffer size)
            n_areas += 1
            c = out[idx]
            # the area's geometry matters only for what it covers on screen (an area wholly
            # outside the play area is not copied; off-screen widths may differ by the CPC's
            # 8-bit wrap at the left edge)
            geo_ok = covered(c[1], c[2], c[3], c[4]) == covered(xt, yt, wf, hf)
            # only what reaches the screen: the play area is CPC x 32..287, y 40..199 in sprite
            # coordinates (vuelcaBufferAPantalla clips the rest; outside the tile buffer the CPC
            # reads past it and the C++ draws no tiles)
            w = wf * 4
            bad = [i for i in range(min(len(px), len(c[5])))
                   if px[i] != c[5][i] and 32 <= xt * 4 + i % w < 288 and 40 <= yt + i // w < 200]
            if not geo_ok or bad:
                n_bad += 1
                n_px += len(bad)
                if shown < a.show:
                    shown += 1
                    w = wf * 4
                    print("tick %d sprite %d: area at tile (%d,%d) %dx%d, CPC (%d,%d) %dx%d, %d pixels differ"
                          % (b["tick"], idx, xt, yt, w, hf, c[1], c[2], c[3] * 4, c[4], len(bad)))
                    if bad and geo_ok:
                        rows = sorted(set(i // w for i in bad))
                        for y in rows[:12]:
                            print("   y%3d C++ %s" % (y, "".join(".123"[v] for v in px[y * w:(y + 1) * w])))
                            print("        CPC %s" % "".join(".123"[v] for v in c[5][y * w:(y + 1) * w]))
    print("MIX: %d batches (%d with the lamp skipped), %d areas compared, %d differ (%d pixels); "
          "tile buffers vs the CPC generator: %d of %d differ"
          % (len(batches), n_skip, n_areas, n_bad, n_px, n_tb_bad, n_tb))
    return 1 if (n_bad or n_tb_bad) else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Byte-identity test of the asm kernels (src/kernels.s) against their C references
(cpp/port/ql_kernels.c), both compiled into the same QL image and run in unicorn on the
same inputs: random tile/sprite bytes, random existing buffer contents, random strides,
sizes, transparency and (for a_fill) odd/even start addresses and lengths.

  kerntest.py [--cases 300] [--seed 1]
"""
import argparse, os, random, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun
from hdiff import PLAY_Y as hdiff_play_y

SRC = 0x2C000      # scratch areas between the system variables and the image (qlrun.BASE)
DST_C = 0x30000
DST_A = 0x34000
DLEN = 0x3000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)                       # initialises (unpack LUT, game)
    mu = r.mu
    fails = {"combina_tile": 0, "sprite_blit": 0, "fill": 0, "and_mask": 0,
             "combina_tile_p": 0, "sprite_blit_p": 0, "x_tile_p": 0, "x_sprite_p": 0, "x_blit_p": 0,
             "bfs24": 0, "puertas_ruta": 0, "rellena_alturas": 0,
             "avance": 0, "reconstruye": 0, "bfs16": 0,
             "tiles_prof": 0, "combina_tile_pm": 0, "sprite_blit_pm": 0, "mask_scene": 0, "blit_pm": 0}
    counts = dict.fromkeys(fails, 0)

    def setup():
        mu.mem_write(SRC, bytes(rnd.randrange(256) if rnd.random() < 0.8 else 0 for _ in range(0x2000)))
        dst = bytes(rnd.randrange(256) for _ in range(DLEN))
        mu.mem_write(DST_C, dst)
        mu.mem_write(DST_A, dst)

    def same():
        return bytes(mu.mem_read(DST_C, DLEN)) == bytes(mu.mem_read(DST_A, DLEN))

    def pack(pens):
        out = bytearray()
        for i in range(0, len(pens), 4):
            b = 0
            for k in range(4):
                p = pens[i + k]
                b |= (p & 1) << (7 - k) | ((p >> 1) & 1) << (3 - k)
            out.append(b)
        return bytes(out)

    def cross(kind):
        """byte-per-pixel C kernel on pens vs packed kernel on the packed pens: pack(result) must match"""
        nb = 0x400                                   # packed bytes in the region
        pens = bytes(rnd.randrange(4) for _ in range(nb * 4))
        mu.mem_write(DST_C, pens)
        mu.mem_write(DST_A, pack(pens))
        if kind == "x_tile_p":
            sb = rnd.choice([4, 8, 12, 16, 20, 24])  # stride in bytes
            ob = rnd.randrange(0, 64)
            transp = rnd.choice([-1, 1, 2, 0, 3])
            tile = SRC + 32 * rnd.randrange(64)
            r.call("c_combina_tile", DST_C + 4 * ob, 4 * sb, tile, transp)
            r.call("a_combina_tile_p", DST_A + ob, sb, tile, transp)
        elif kind == "x_sprite_p":
            w = rnd.randrange(0, 7)
            h = rnd.randrange(0, 40)
            sb = w + rnd.randrange(0, 8)
            sstride = w + rnd.randrange(0, 4)
            ob = rnd.randrange(0, 100)
            src = SRC + rnd.randrange(0, 0x800)
            r.call("c_sprite_blit", DST_C + 4 * ob, 4 * sb, src, sstride, w, h)
            r.call("a_sprite_blit_p", DST_A + ob, sb, src, sstride, w, h)
        u = bytes(mu.mem_read(DST_C, nb * 4))
        return pack(u) == bytes(mu.mem_read(DST_A, nb))

    def cross_blit():
        """ql_play_blit (pens) vs ql_play_blit_p (packed): same screen"""
        w = 4 * rnd.randrange(1, 20)
        h = rnd.randrange(1, 30)
        x = 4 * rnd.randrange(0, 80)                 # CPC x (32 = left edge of the play area), clipped
        y = rnd.randrange(0, 160 - h)
        sb = w // 4 + rnd.randrange(0, 4)
        pens = bytes(rnd.randrange(4) for _ in range(sb * 4 * h))
        mu.mem_write(DST_C, pens)
        mu.mem_write(DST_A, pack(pens))
        mu.mem_write(DST_A + 4096, bytes(len(pens) // 4 + 64))   # CHARCOL: no sprite pixels (terrain path)
        scr = bytes(rnd.randrange(256) for _ in range(0x8000))
        mu.mem_write(0x20000, scr)
        r.call("ql_play_blit", x, y, w, h, DST_C, 4 * sb)
        s1 = bytes(mu.mem_read(0x20000, 0x8000))
        mu.mem_write(0x20000, scr)
        r.call("ql_play_blit_p", x, y, w, h, DST_A, sb)
        return s1 == bytes(mu.mem_read(0x20000, 0x8000))

    def grid24():
        """a height grid as the game makes them: floors of a few levels, steps, walls,
        the odd flag bit; sometimes a goal cell (0x40), sometimes cells already explored"""
        base = [[0] * 24 for _ in range(24)]
        lv = rnd.randrange(0, 4)
        smooth = rnd.random() < 0.6          # rooms: flat floors, walls, a few steps
        pn, pw = (0.01, 0.0) if smooth else (0.15, 0.08)
        for y in range(24):
            for x in range(24):
                v = lv
                if rnd.random() < pn:
                    v = lv + rnd.choice([-1, 1, 2, 3])
                if rnd.random() < pw:
                    v = rnd.choice([0x0e, 0x0f, 0x0d, 0x20 + lv])
                if rnd.random() < 0.05:
                    v |= 0x10
                v = max(0, v) & 0x3f
                if rnd.random() < 0.02:
                    v |= 0x80
                base[y][x] = v
            if rnd.random() < (0.05 if smooth else 0.3):
                lv = max(0, min(6, lv + rnd.choice([-1, 1])))
        if smooth:                           # wall blocks
            for _ in range(rnd.randrange(0, 6)):
                x0, y0 = rnd.randrange(24), rnd.randrange(24)
                for yy in range(y0, min(24, y0 + rnd.randrange(1, 8))):
                    for xx in range(x0, min(24, x0 + rnd.randrange(1, 8))):
                        base[yy][xx] = 0x0f
        sx, sy = rnd.randrange(1, 23), rnd.randrange(1, 23)
        if rnd.random() < 0.7:
            gx, gy = rnd.randrange(0, 24), rnd.randrange(0, 24)
            base[gy][gx] |= 0x40
        return bytes(v for row in base for v in row), sx, sy

    GRID_C, GRID_A, IO_C, IO_A = SRC, SRC + 0x400, SRC + 0x800, SRC + 0x840

    def bfs_case():
        g, sx, sy = grid24()
        mu.mem_write(GRID_C, g)
        mu.mem_write(GRID_A, g)
        junk = bytes(rnd.randrange(256) for _ in range(DLEN))
        mu.mem_write(DST_C, junk)
        mu.mem_write(DST_A, junk)
        io = struct.pack(">7i", sx, sy, 0x11, 0x22, 0x33, 0x44, 0x55)
        mu.mem_write(IO_C, io)
        mu.mem_write(IO_A, io)
        rc = r.call("c_bfs24", GRID_C, DST_C, IO_C)
        ra = r.call("a_bfs24", GRID_A, DST_A, IO_A)
        return (rc == ra and same() and bytes(mu.mem_read(GRID_C, 576)) == bytes(mu.mem_read(GRID_A, 576))
                and bytes(mu.mem_read(IO_C, 28)) == bytes(mu.mem_read(IO_A, 28))), rc

    def puertas_case():
        hab = bytes(rnd.randrange(256) for _ in range(256))
        hp = bytes(rnd.randrange(256) for _ in range(24))
        mu.mem_write(DST_C, hab)
        mu.mem_write(DST_A, hab)
        mu.mem_write(SRC, hp)
        m = rnd.choice([rnd.randrange(64), rnd.randrange(1 << 16), -rnd.randrange(1, 100)])
        r.call("c_puertas_ruta", DST_C, SRC, m)
        r.call("a_puertas_ruta", DST_A, SRC, m)
        return same()

    ROMS = qlrun.BASE + syms["rom_image"] + 0x4000

    def rellena_case():
        """random block tables (all types, 4/5-byte entries, any position) or the game's
        three floor tables, through random windows; grid at odd or even addresses"""
        if rnd.random() < 0.5:
            tab = bytearray()
            for _ in range(rnd.randrange(0, 40)):
                t = rnd.randrange(256)
                if rnd.random() < 0.9:
                    t = (t & 0xF8) | rnd.randrange(1, 6)
                tab += bytes([t, rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)])[:5 if t & 8 else 4]
            tab += bytes([0xFF])
            mu.mem_write(SRC, bytes(tab) + bytes(16))
            datos = SRC
        else:
            datos = ROMS + rnd.choice([0x18a00, 0x18f00, 0x19080])
        if rnd.random() < 0.7:
            mx, my = (rnd.randrange(256) & 0xF0) - 4, (rnd.randrange(256) & 0xF0) - 4
        else:
            mx, my = rnd.randrange(-40, 260), rnd.randrange(-40, 260)
        off = rnd.randrange(0, 0x200)
        r.call("c_rellena_alturas", DST_C + off, datos, mx, my)
        r.call("a_rellena_alturas", DST_A + off, datos, mx, my)
        cells = sum(1 for b in bytes(mu.mem_read(DST_A + off, 576)) if b)
        found["grid cells>50"] = found.get("grid cells>50", 0) + (cells > 50)
        found["grid from ROM, cells>50"] = found.get("grid from ROM, cells>50", 0) + (cells > 50 and datos != SRC)
        return same()

    TAB = qlrun.BASE + syms["_ZN6Abadia15RejillaPantalla21calculoAvancePosicionE"]

    def avance_case():
        """grid of random heights (some with character bits 0x10-0x30), positions in the 20x20
        centre (sometimes anywhere), the game's 4 direction rows or random small tables"""
        g = bytes(rnd.choice([rnd.randrange(0, 16), rnd.randrange(256)]) for _ in range(24 * 24 + 200))
        GR = SRC + 0x100                     # 0x100 of random bytes before the grid
        mu.mem_write(SRC, bytes(rnd.randrange(256) for _ in range(0x100)) + g)
        if rnd.random() < 0.8:
            tab = TAB + 32 * rnd.randrange(4)
        else:
            mu.mem_write(SRC + 0x800, struct.pack(">8i", *[rnd.randrange(-2, 3) for _ in range(8)]))
            tab = SRC + 0x800
        if rnd.random() < 0.9:
            x, y = rnd.randrange(2, 22), rnd.randrange(2, 22)
        else:
            x, y = rnd.randrange(-3, 27), rnd.randrange(-3, 27)
        desn = rnd.randrange(2)
        alt = rnd.choice([0, rnd.randrange(16), rnd.randrange(-5, 40)])
        junk = bytes(rnd.randrange(256) for _ in range(96))
        mu.mem_write(DST_C, junk)
        mu.mem_write(DST_A, junk)
        r.call("c_avance", GR, DST_C, x, y, tab, desn, alt, DST_C + 64)
        r.call("a_avance", GR, DST_A, x, y, tab, desn, alt, DST_A + 64)
        return same()

    def reconstruye_case():
        """a real search: c_bfs24 on room-like grids until one finds its goal, then both
        reconstructions on copies of its stack"""
        for _ in range(60):
            g, sx, sy = grid24()
            if not any(b & 0x40 for b in g):
                continue
            mu.mem_write(GRID_C, g)
            mu.mem_write(DST_C, bytes(DLEN))
            mu.mem_write(IO_C, struct.pack(">7i", sx, sy, 0, 0, 0, 0, 0))
            rc = r.call("c_bfs24", GRID_C, DST_C, IO_C)
            if rc:
                break
        else:
            return None
        io = struct.unpack(">7i", bytes(mu.mem_read(IO_C, 28)))
        fx, fy, ori = {1: (io[2] + 1, io[3], 2), 2: (io[2], io[3] - 1, 3),
                       3: (io[2] - 1, io[3], 0), 4: (io[2], io[3] + 1, 1)}[rc]
        found["reconstruye levels>5"] = found.get("reconstruye levels>5", 0) + (io[4] > 5)
        stack = bytes(mu.mem_read(DST_C, DLEN))
        mu.mem_write(DST_A, stack)
        rio = struct.pack(">9i", io[6], io[4], fx, fy, ori, sx, sy, 0x77, 0x88)
        mu.mem_write(IO_C, rio)
        mu.mem_write(IO_A, rio)
        r.call("c_reconstruye", DST_C, DLEN // 4, IO_C)
        r.call("a_reconstruye", DST_A, DLEN // 4, IO_A)
        return same() and bytes(mu.mem_read(IO_C, 36)) == bytes(mu.mem_read(IO_A, 36))

    HAB = qlrun.BASE + syms["_ZN6Abadia13BuscadorRutas12habitacionesE"]
    HPU = qlrun.BASE + syms["_ZN6Abadia13BuscadorRutas18habitacionesPuertaE"]
    HAB0 = bytes(mu.mem_read(HAB, 3 * 256))

    def bfs16_case():
        """room search: the game's floors (doors set by a_puertas_ruta with a random mask) or
        random tables; start in a room, goal = a room marked 0x40 or the mask of a flag bit"""
        mu.mem_write(HAB, HAB0)
        if rnd.random() < 0.7:
            r.call("a_puertas_ruta", HAB, HPU, rnd.randrange(64))
            planta = rnd.randrange(3)
            tab = bytes(mu.mem_read(HAB + 256 * planta, 256)) + bytes(mu.mem_read(HAB + 256 * ((planta + 1) % 3), 0x20))
        else:
            tab = bytes(rnd.choice([0, 0, rnd.randrange(16), rnd.randrange(256)]) for _ in range(0x120))
        tab = bytearray(tab)
        for i in range(len(tab)):
            tab[i] &= 0x3f                      # as limpiaBits leaves them
        sx, sy = rnd.randrange(16), rnd.randrange(16)
        if rnd.random() < 0.7:
            m = 0x40
            g = rnd.randrange(256)
            tab[g] |= 0x40
        else:
            m = rnd.choice([0x10, 0x20, 0x30, rnd.randrange(1 << 9)])
        mu.mem_write(GRID_C, bytes(tab))
        mu.mem_write(GRID_A, bytes(tab))
        junk = bytes(rnd.randrange(256) for _ in range(0x800))
        mu.mem_write(DST_C, junk)
        mu.mem_write(DST_A, junk)
        io = struct.pack(">7i", sx, sy, m, 0x11, 0x22, 0x33, 0x44)
        mu.mem_write(IO_C, io)
        mu.mem_write(IO_A, io)
        rc = r.call("c_bfs16", GRID_C, DST_C, IO_C)
        ra = r.call("a_bfs16", GRID_A, DST_A, IO_A)
        found["bfs16 found"] = found.get("bfs16 found", 0) + (rc != 0)
        return (rc == ra and same() and bytes(mu.mem_read(GRID_C, 0x120)) == bytes(mu.mem_read(GRID_A, 0x120))
                and bytes(mu.mem_read(IO_C, 28)) == bytes(mu.mem_read(IO_A, 28)))

    def tiles_case():
        """tile depth pass: random 20x16 tile buffers (tile 0 often, drawn marks), a sprite
        window partly outside the buffer, random depth limits, both passes; real tile graphics"""
        TB_C, TB_A, P_C, P_A = SRC, SRC + 0x800, SRC + 0x1000, SRC + 0x1040
        tb = bytearray()
        for _ in range(20 * 16):
            px = [rnd.randrange(0, 40) | (0x80 if rnd.random() < 0.2 else 0) for _ in range(2)]
            py = [rnd.randrange(0, 40) for _ in range(2)]
            tl = [rnd.choice([0, 0, rnd.randrange(256), rnd.randrange(0x0b)]) for _ in range(2)]
            tb += bytes(px + py + tl)
        mu.mem_write(TB_C, bytes(tb))
        mu.mem_write(TB_A, bytes(tb))
        nx, ny = rnd.randrange(1, 7), rnd.randrange(1, 7)
        bx, by = rnd.randrange(-3, 16), rnd.randrange(-3, 20)
        pmin = [rnd.choice([0, rnd.randrange(0, 40)]) for _ in range(2)]
        pmax = [rnd.choice([0xfd, rnd.randrange(1, 41)]) for _ in range(2)]
        desp = 4 * rnd.randrange(0, 64)
        ult = rnd.randrange(2)
        keepmask = rnd.randrange(2)                  # CHARCOL: p[14], the masked tile combine
        for base, tbb, pb in ((DST_C, TB_C, P_C), (DST_A, TB_A, P_A)):
            mu.mem_write(pb, struct.pack(">15i", tbb, bx, by, nx, ny, pmin[0], pmin[1], pmax[0], pmax[1],
                                         base, desp, 4 * nx, ult, ROMS + 0x8300, keepmask))
        pre = bytes(mu.mem_read(DST_A, DLEN))
        r.call("c_tiles_prof", P_C)
        r.call("a_tiles_prof", P_A)
        found["tiles drew"] = found.get("tiles drew", 0) + (bytes(mu.mem_read(DST_A, DLEN)) != pre)
        return same() and bytes(mu.mem_read(TB_C, 1920)) == bytes(mu.mem_read(TB_A, 1920))

    MASK_OFF = 4096
    PIXM = [0x88 >> k for k in range(4)]

    def pen_of(b, k):
        return ((b >> (3 - k)) & 1) << 1 | ((b >> (7 - k)) & 1)

    def tile_pm_case():
        stride = rnd.choice([4, 8, 12, 16, 20, 24])
        off = rnd.randrange(0, 256)
        transp = rnd.choice([-1, 1, 2, 0, 3])
        tile = SRC + 32 * rnd.randrange(64)
        r.call("c_combina_tile_pm", DST_C + off, stride, tile, transp)
        r.call("a_combina_tile_pm", DST_A + off, stride, tile, transp)
        return same()

    def sprite_pm_case():
        w, h = rnd.randrange(0, 7), rnd.randrange(0, 40)
        dstride, sstride = w + rnd.randrange(0, 8), w + rnd.randrange(0, 4)
        off = rnd.randrange(0, 200)
        src = SRC + rnd.randrange(0, 0x800)
        r.call("c_sprite_blit_pm", DST_C + off, dstride, src, sstride, w, h)
        r.call("a_sprite_blit_pm", DST_A + off, dstride, src, sstride, w, h)
        return same()

    def scene_case():
        """a sprite's area: cleared (pens and mask), a tile BEHIND the sprite, the sprite, a tile IN
        FRONT of it; asm == C, and pens + mask == a pixel model (mask bit = drawn last by the sprite)"""
        sb = rnd.choice([8, 12, 16])                 # area width in bytes (CPC bytes = 4 pixels)
        hh = 24
        model = [[(0, 0)] * (sb * 4) for _ in range(hh)]     # (pen, sprite?)
        for base in (DST_C, DST_A):
            mu.mem_write(base, bytes(sb * hh))
            mu.mem_write(base + MASK_OFF, bytes(sb * hh))
        src = bytes(rnd.randrange(256) if rnd.random() < 0.75 else 0 for _ in range(0x200))
        mu.mem_write(SRC + 0x1000, src)
        ops = []
        for _ in range(rnd.randrange(1, 4)):
            ops.append(("tile", rnd.randrange(0, sb - 3), 8 * rnd.randrange(0, hh // 8), 32 * rnd.randrange(64),
                        rnd.choice([-1, 1, 2])))
        ops.append(("sprite", rnd.randrange(0, sb - 2), rnd.randrange(0, hh - 8), rnd.randrange(0, 0x100),
                    rnd.randrange(1, 4), rnd.randrange(1, 9)))
        for _ in range(rnd.randrange(1, 4)):
            ops.append(("tile", rnd.randrange(0, sb - 3), 8 * rnd.randrange(0, hh // 8), 32 * rnd.randrange(64),
                        rnd.choice([-1, 1, 2])))
        tiles = bytes(mu.mem_read(SRC, 0x800))
        for op in ops:
            if op[0] == "tile":
                _, bx, y, toff, tr = op
                for kern, base in (("c_combina_tile_pm", DST_C), ("a_combina_tile_pm", DST_A)):
                    r.call(kern, base + y * sb + bx, sb, SRC + toff, tr)
                for j in range(8):
                    for i in range(4):
                        b = tiles[toff + j * 4 + i]
                        for k in range(4):
                            pen = pen_of(b, k)
                            if tr < 0 or pen != tr:
                                model[y + j][(bx + i) * 4 + k] = (pen, 0)
            else:
                _, bx, y, soff, w, h = op
                h = min(h, hh - y)
                w = min(w, sb - bx)
                for kern, base in (("c_sprite_blit_pm", DST_C), ("a_sprite_blit_pm", DST_A)):
                    r.call(kern, base + y * sb + bx, sb, SRC + 0x1000 + soff, w, w, h)
                for j in range(h):
                    for i in range(w):
                        b = src[soff + j * w + i]
                        for k in range(4):
                            pen = pen_of(b, k)
                            if pen:
                                model[y + j][(bx + i) * 4 + k] = (pen, 1)
        if not same():
            return False
        pens = bytes(mu.mem_read(DST_A, sb * hh))
        mask = bytes(mu.mem_read(DST_A + MASK_OFF, sb * hh))
        for y in range(hh):
            for x in range(sb * 4):
                b, k = pens[y * sb + x // 4], x % 4
                if pen_of(b, k) != model[y][x][0] or ((mask[y * sb + x // 4] >> (3 - k)) & 1) != model[y][x][1]:
                    return False
        found["scene sprite pixels shown"] = found.get("scene sprite pixels shown", 0) + \
            sum(1 for row in model for v in row if v[1])
        return True

    BLIT_PAL = None

    def blit_case():
        """ql_play_blit_p with separate character colours (palette 2 of the author's mapping)
        against c_blit_pm on the same tables; any line parity, left clip"""
        nonlocal BLIT_PAL
        if BLIT_PAL is None:
            r.call("ql_set_palette", 3)
            r.call("ql_set_palette", 2)
            BLIT_PAL = mu.mem_read(qlrun.BASE + syms["char_sep"], 1)[0]
        if not BLIT_PAL:
            return None
        sb = rnd.randrange(1, 12)
        stride = sb + rnd.randrange(0, 4)
        h = rnd.randrange(1, 20)
        x = 32 + 4 * rnd.randrange(-3, 60)
        y = rnd.randrange(0, 150)
        src = bytes(rnd.randrange(256) for _ in range(stride * h + 8))
        msk = bytes(rnd.choice([0, 0, rnd.randrange(16), 15]) for _ in range(stride * h + 8))
        mu.mem_write(DST_A, src)
        mu.mem_write(DST_A + MASK_OFF, msk)
        scr = bytes(rnd.randrange(256) for _ in range(0x8000))
        mu.mem_write(0x20000, scr)
        plain = rnd.randrange(3) == 0                   # an area with no sprite: the plain copy
        mu.mem_write(qlrun.BASE + syms["ql_blit_plain"], bytes([1 if plain else 0]))
        r.call("ql_play_blit_p", x, y, 4 * sb, h, DST_A, stride)
        mu.mem_write(qlrun.BASE + syms["ql_blit_plain"], bytes([0]))
        if plain:                                        # reference: the same with an empty mask
            mu.mem_write(DST_A + MASK_OFF, bytes(len(msk)))
        found["blit plain areas"] = found.get("blit plain areas", 0) + plain
        got = bytes(mu.mem_read(0x20000, 0x8000))
        # C reference into a copy of the screen, then the same clipping by hand
        cmb_e = qlrun.BASE + syms["cmb_e"]
        cmb_o = struct.unpack(">I", bytes(mu.mem_read(qlrun.BASE + syms["cmb_odd_ptr"], 4)))[0]
        qx = x - 32
        skip = 0
        if qx < 0:
            skip = (-qx) // 4
            qx = 0
        wb = min(sb - skip, (256 - qx) // 4)
        if wb <= 0:
            return got == scr
        play_y = hdiff_play_y
        mu.mem_write(0x20000, scr)
        r.call("c_blit_pm", 0x20000 + (play_y + y) * 128 + qx // 2, 64, DST_A + skip, stride, wb, h,
               cmb_e, cmb_o, (play_y + y) & 1)
        return got == bytes(mu.mem_read(0x20000, 0x8000))

    found = {}
    for n in range(a.cases):
        setup()
        k = n % 20
        if k in (11, 12, 13, 14, 15, 16, 17, 18, 19):
            name = ["rellena_alturas", "avance", "reconstruye", "bfs16", "tiles_prof",
                    "combina_tile_pm", "sprite_blit_pm", "mask_scene", "blit_pm"][k - 11]
            ok = [rellena_case, avance_case, reconstruye_case, bfs16_case, tiles_case,
                  tile_pm_case, sprite_pm_case, scene_case, blit_case][k - 11]()
            if ok is None:
                continue
            counts[name] += 1
            if not ok:
                fails[name] += 1
                if fails[name] <= 3:
                    print("MISMATCH", name, "case", n)
            continue
        if k in (9, 10):
            if k == 9:
                name = "bfs24"
                ok, rc = bfs_case()
                found[rc] = found.get(rc, 0) + 1
                pp = struct.unpack(">i", bytes(mu.mem_read(IO_C + 20, 4)))[0]
                found["pushed>50"] = found.get("pushed>50", 0) + (pp > 50)
            else:
                name = "puertas_ruta"
                ok = puertas_case()
            counts[name] += 1
            if not ok:
                fails[name] += 1
                if fails[name] <= 3:
                    print("MISMATCH", name, "case", n)
            continue
        if k == 4:
            stride = rnd.choice([4, 8, 12, 16, 20, 24])
            off = rnd.randrange(0, 256)
            transp = rnd.choice([-1, 1, 2, 0, 3])
            tile = SRC + 32 * rnd.randrange(64)
            r.call("c_combina_tile_p", DST_C + off, stride, tile, transp)
            r.call("a_combina_tile_p", DST_A + off, stride, tile, transp)
            name = "combina_tile_p"
        elif k == 5:
            w = rnd.randrange(0, 7)
            h = rnd.randrange(0, 40)
            dstride = w + rnd.randrange(0, 8)
            sstride = w + rnd.randrange(0, 4)
            off = rnd.randrange(0, 200)
            src = SRC + rnd.randrange(0, 0x800)
            r.call("c_sprite_blit_p", DST_C + off, dstride, src, sstride, w, h)
            r.call("a_sprite_blit_p", DST_A + off, dstride, src, sstride, w, h)
            name = "sprite_blit_p"
        elif k in (6, 7, 8):
            name = ["x_tile_p", "x_sprite_p", "x_blit_p"][k - 6]
            ok = cross_blit() if name == "x_blit_p" else cross(name)
            counts[name] += 1
            if not ok:
                fails[name] += 1
                if fails[name] <= 3:
                    print("MISMATCH", name, "case", n)
            continue
        elif k == 0:
            stride = 4 * rnd.choice([4, 8, 12, 16, 20, 24])
            off = rnd.choice([4 * rnd.randrange(0, 64), rnd.randrange(0, 256)])
            transp = rnd.choice([-1, 1, 2, 0, 3])
            tile = SRC + 32 * rnd.randrange(64)
            r.call("c_combina_tile", DST_C + off, stride, tile, transp)
            r.call("a_combina_tile", DST_A + off, stride, tile, transp)
            name = "combina_tile"
        elif k == 1:
            w = rnd.randrange(0, 7)
            h = rnd.randrange(0, 40)
            dstride = 4 * (w + rnd.randrange(0, 8))
            sstride = w + rnd.randrange(0, 4)
            off = 2 * rnd.randrange(0, 200)
            src = SRC + rnd.randrange(0, 0x800)
            r.call("c_sprite_blit", DST_C + off, dstride, src, sstride, w, h)
            r.call("a_sprite_blit", DST_A + off, dstride, src, sstride, w, h)
            name = "sprite_blit"
        elif k == 3:
            off = rnd.randrange(0, 0x100)
            ln = rnd.choice([0, 1, 3, 4, 5, 576, rnd.randrange(0, 0x2000)])
            m = rnd.randrange(256)
            r.call("c_and_mask", DST_C + off, m, ln)
            r.call("a_and_mask", DST_A + off, m, ln)
            name = "and_mask"
        else:
            off = rnd.randrange(0, 0x100)
            ln = rnd.choice([0, 1, 2, 3, 4, 5, 7, 8, 9, 63, 64, 65, 1000, rnd.randrange(0, 0x2000)])
            val = rnd.randrange(256)
            r.call("c_fill", DST_C + off, val, ln)
            r.call("a_fill", DST_A + off, val, ln)
            name = "fill"
        counts[name] += 1
        if not same():
            fails[name] += 1
            if fails[name] <= 3:
                print("MISMATCH", name, "case", n)
    print("bfs24 outcomes (0 = no path, 1-4 = goal side):", found)
    for name in fails:
        print("%-13s %4d cases, %d mismatches" % (name, counts[name], fails[name]))
    return 1 if any(fails.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

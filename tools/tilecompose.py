#!/usr/bin/env python3
"""Tile composition (QL_TILE_COMPOSE): the graphics the CPC's two-layer tile buffer drops.

The screen generator (CPC 0x1667, GeneradorPantallas::actualizaTile) keeps two graphics per
16x8 cell: every new graphic pushes the old front one to the back layer and the old back one
is lost. Where three or more graphics overlap (columns over columns over a wall...) the lost
ones leave holes in the background, on the CPC as here (tools/cpcref.py traces the CPC's own
generator). This tool works out, OFFLINE, how to put them back without touching the per-step
drawing code: a cell keeps two layers, but a layer's graphic may be a COMPOSITE (several
graphics painted in order into one 16x8 tile, transparent where none of them draws), stored in
a tile number that the screen does not use. The patches are applied when the screen is built
(GeneradorPantallas::qlCompone); the sprite mixer and the screen copy are unchanged.

Occlusion. A cell's writes w0..wn-1 (in generation order) each have a depth: the earlier ones
their generation depth, the last two the depths the CPC leaves in the cell (its own merge rule).
The writes are split into a back group w0..wk-1 and a front group wk..wn-1, each drawn as one
layer at one depth. That is EXACT when, for every position a character can stand on in the
screen and whose sprite can overlap the cell, each group member is drawn on the same side of
the sprite (before/after, the mixer's rule: before iff profX <= x and profY <= y) at the group
depth as at its own depth. Positions: the screen's height grid (the CPC tables, as
RejillaPantalla fills them), cells reachable from the window's border in steps of at most 1,
through the screen's camera; sprite rectangles are taken generously (any character, door or
object). A cell with no exact split, or whose composite would need both pen 1 and pen 2 and
transparency, is left as the CPC has it.

  tilecompose.py --gen       write cpp/port/ql_compose_data.h (and build/tilecompose/plan.pkl)
  tilecompose.py --check DIR compare a tour's tiles (DIR/tiles_NNN.bin, oracle with the
                             composition on) with the CPC generator + the plan, and every
                             composed cell's picture with the painter's picture of all its
                             writes; also prove the occlusion claim cell by cell with the CPC's
                             own Z80 mixer (a sprite at every reachable overlapping position,
                             vs an N-layer reference mixer in Python)
"""
import argparse, collections, os, pickle, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cpcref

OUT = os.path.join(QL, "build", "tilecompose")
HEADER = os.path.join(QL, "cpp", "port", "ql_compose_data.h")
NSCREENS = 0x74
OBJ_IDS = {0x2e, 0x2f, 0x30, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9}   # object graphics live in the tile table


# ---------------------------------------------------------------- CPC data
class Cpc:
    def __init__(self):
        self.r = cpcref.roms()
        cpu = cpcref.Cpu(cpcref.base_memory(self.r), self.r)
        cpcref.tables(cpu)
        self.mem = bytes(cpu.mem())
        self.tg = self.mem[0x6d00:0x8d00]

    def trace(self, n, close_mirror=True):
        """every tile write of screen n's generation: {cell: [(tile, x, y), ...]}, tile buffer"""
        cpu = cpcref.Cpu(cpcref.base_memory(self.r), self.r)
        if close_mirror:
            cpu.call(0x3a61)
        cpu.page(1)
        cpu.page(7)
        m = cpu.m
        mm = m.memory
        a = cpcref.screen_addr(self.r, n)
        cpu.call(0x1a70, a=0)
        mm[0x165e] = 0x67
        mm[0x165f] = 0x16
        m.sp = 0xfc
        mm[0xfc] = cpcref.HALT_AT & 0xff
        mm[0xfd] = cpcref.HALT_AT >> 8
        m.ix = a + 1
        m.pc = 0x1a0a
        m.set_breakpoint(0x1667)
        m.set_breakpoint(cpcref.HALT_AT)
        w = {}
        while True:
            ev = m.run()
            if not ev & 1:
                continue
            if m.pc == cpcref.HALT_AT:
                break
            e = (m.hl - 0x8d80) // 6
            w.setdefault(e, []).append((m.c, mm[0x1fde], mm[0x1fdf]))
            m.step_over_breakpoint()
        return w, bytes(mm[0x8d80:0x8d80 + 1920])

    def pens(self, t, gfx=None):
        g = gfx if gfx is not None else self.tg[t * 32:t * 32 + 32]
        out = []
        for v in g:
            out += [((v >> (7 - k)) & 1) | (((v >> (3 - k)) & 1) << 1) for k in range(4)]
        return out


def transp(t):
    return 1 if t & 0x80 else 2


def compose(cpc, tiles):
    """painter's order, each tile with its own transparent pen: 128 pens or None (nothing drawn)"""
    px = [None] * 128
    for t in tiles:
        if not t:
            continue
        T = transp(t)
        for i, p in enumerate(cpc.pens(t)):
            if p != T:
                px[i] = p
    return px


def picture(px):
    return [0 if p is None else p for p in px]       # over the cleared (pen 0) play area


def encode(px, T):
    """128 pens (None = transparent -> pen T) -> 32 CPC Mode 1 bytes"""
    out = bytearray(32)
    for i in range(128):
        p = T if px[i] is None else px[i]
        b, k = i // 4, i % 4
        out[b] |= ((p & 1) << (7 - k)) | (((p >> 1) & 1) << (3 - k))
    return bytes(out)


# ---------------------------------------------------------------- where characters can be
def plantas():
    s = open(os.path.join(QL, "cpp", "vigasoco", "MotorGrafico.cpp"), encoding="latin-1").read()
    s = s[s.index("plantas[3][256]"):]
    s = s[:s.index("};")]
    vals = []
    for line in s.splitlines():
        if re.match(r"^\s*(0x[0-9a-fA-F]+|0)\s*,", line):
            vals += [int(v.strip(), 0) for v in line.split("//")[0].split(",") if v.strip()]
    assert len(vals) == 768
    return [vals[0:256], vals[256:512], vals[512:768]]


def height_grid(r, floor, minX, minY):
    """RejillaPantalla::rellenaAlturasPantalla (ql_kernels.c c_rellena_alturas)"""
    inc = [(1, 0), (0, -1), (-1, 0), (0, 1)]
    buf = [[0] * 24 for _ in range(24)]
    p = [0x18a00, 0x18f00, 0x19080][floor]
    while r[p] != 0xff:
        tb = r[p]
        if (tb & 7) == 0 or (tb & 7) >= 6:
            break
        lx, ly = r[p + 3], r[p + 4]
        if (tb & 8) == 0:
            ly = lx & 0x0f
            lx = (lx >> 4) & 0x0f
        alt = (tb >> 4) & 0x0f
        px, py = r[p + 1], r[p + 2]
        p += 4 if (tb & 8) == 0 else 5
        for j in range(ly + 1):
            old = alt
            for i in range(lx + 1):
                X, Y = px + i - minX, py + j - minY
                if 0 <= X < 24 and 0 <= Y < 24:
                    buf[Y][X] = alt & 0xff
                if (tb & 7) != 5:
                    alt += inc[(tb & 7) - 1][0]
            if (tb & 7) != 5:
                alt = old + inc[(tb & 7) - 1][1]
    return buf


def reachable(buf):
    seen, st = set(), []
    for i in range(24):
        for (x, y) in ((i, 0), (i, 23), (0, i), (23, i)):
            if buf[y][x] <= 0x0e and (x, y) not in seen:
                seen.add((x, y))
                st.append((x, y))
    while st:
        x, y = st.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            X, Y = x + dx, y + dy
            if 0 <= X < 24 and 0 <= Y < 24 and (X, Y) not in seen and buf[Y][X] <= 0x0e \
                    and abs(buf[Y][X] - buf[y][x]) <= 1:
                seen.add((X, Y))
                st.append((X, Y))
    return seen


def cam(ori, x, y):
    """TransformacionesCamara.cpp (CPC 0x2485-0x2494)"""
    if ori == 1:
        return 40 - y, x
    if ori == 2:
        return 40 - x, 40 - y
    if ori == 3:
        return y, 40 - x
    return x, y


def positions(r, n, occ):
    out = set()
    for (floor, X, Y) in occ.get(n, []):
        pxp, pyp = X * 16, Y * 16
        buf = height_grid(r, floor, pxp - 4, pyp - 4)
        ori = (((pxp >> 4) & 1) << 1) | (((pxp >> 4) & 1) ^ ((pyp >> 4) & 1))
        for (i, j) in reachable(buf):
            lx, ly = cam(ori, i + 8, j + 8)
            out.add((lx, ly, buf[j][i]))
    return out


def rect(lx, ly, h):
    """generous sprite rectangle (x in bytes, y in pixels, sprite coordinates): MotorGrafico::
    actualizaCoordCamara + the frame offsets of characters (x -2, y -34), doors (x -7..+3, 6 wide,
    y -42, 40 high) and objects"""
    x = 2 * (lx - ly) + 40
    y = 4 * (lx + ly - h - 5)
    return (x - 8, y - 48, x + 10, y + 8)


def overlaps(rc, row, col):
    x0, y0, x1, y1 = rc
    cx0, cy0 = col * 4 + 8, row * 8 + 40
    return x0 < cx0 + 4 and cx0 < x1 and y0 < cy0 + 8 and cy0 < y1


def before(lx, ly, d):
    """the mixer draws a tile at depth d before a sprite at (lx, ly) iff both are <="""
    return d[0] <= lx and d[1] <= ly


# ---------------------------------------------------------------- the plan
def plan_screen(cpc, n, w, tb, pos):
    """{cell: (k, Db, Df)}: split at k, back group at depth Db, front group at Df"""
    out = {}
    for e, hist in w.items():
        if len(hist) <= 2:
            continue
        tiles = [h[0] for h in hist]
        full = compose(cpc, tiles)
        if picture(compose(cpc, [tb[e * 6 + 2], tb[e * 6 + 5]])) == picture(full):
            continue                                 # nothing visible was dropped
        row, col = e // 16, e % 16
        refd = [(h[1], h[2]) for h in hist]
        refd[-2] = (tb[e * 6], tb[e * 6 + 1])
        refd[-1] = (tb[e * 6 + 3], tb[e * 6 + 4])
        matter = [k for k in range(len(hist)) if tiles[k] and
                  picture(compose(cpc, tiles[:k] + tiles[k + 1:])) != picture(full)]
        rel = [(lx, ly) for (lx, ly, h) in pos if overlaps(rect(lx, ly, h), row, col)]
        # the reference: every write its own layer at its own depth, through the mixer's rules
        ideal = [([None if q == transp(t) else q for q in cpc.pens(t)], refd[k]) for k, t in enumerate(tiles) if t]

        def ok(members, D):
            return all(before(lx, ly, refd[k]) == before(lx, ly, D) for k in members if k in matter for (lx, ly) in rel)

        def fits(g):
            """a composite of more than one graphic must have a transparent pen it does not draw"""
            if len(g) == 1:
                return True
            used = set(p for p in compose(cpc, g) if p is not None)
            return not ({1, 2} <= used)
        nw = len(hist)
        found = None
        for k in [nw - 1] + list(range(nw - 2, 0, -1)):
            back, front = list(range(k)), list(range(k, nw))
            if not (fits(tiles[:k]) and fits(tiles[k:])):
                continue
            gb, gf = group_pens(cpc, tiles[:k]), group_pens(cpc, tiles[k:])
            for Db in [refd[-2]] + sorted(set(refd[i] for i in back) - {refd[-2]}):
                if not ok(back, Db):
                    continue
                for Df in [refd[-1]] + sorted(set(refd[i] for i in front) - {refd[-1]}):
                    if ok(front, Df) and all(mix_cell(ideal, S) == mix_cell([(gb, Db), (gf, Df)], S) for S in rel):
                        found = (k, Db, Df)
                        break
                if found:
                    break
            if found:
                break
        out[e] = found
    return out


def group_pens(cpc, g):
    """a group of writes as one layer: one tile as it is, several as their composite"""
    if len(g) == 1:
        T = transp(g[0])
        return [None if q == T else q for q in cpc.pens(g[0])]
    return compose(cpc, g)


def build_plan():
    cpc = Cpc()
    P = plantas()
    occ = collections.defaultdict(list)
    for f in range(3):
        for i, n in enumerate(P[f]):
            if n:
                occ[n].append((f, i & 15, i >> 4))
    screens = {}
    for n in range(NSCREENS):
        w, tb = cpc.trace(n)
        used = set(tb[2::6]) | set(tb[5::6])
        if n == 0x72:                                # the mirror room, open: its tiles stay reserved
            w2, tb2 = cpc.trace(n, close_mirror=False)
            used |= set(tb2[2::6]) | set(tb2[5::6])
        pos = positions(cpc.r, n, occ)
        screens[n] = {"w": w, "tb": tb, "used": used, "plan": plan_screen(cpc, n, w, tb, pos), "pos": pos}
    return cpc, screens


def patches(cpc, screens):
    """-> gfx pool (list of 32-byte composites), {screen: [patch tuples]}, stats"""
    pool, pool_ix = [], {}
    out = {}
    st = collections.Counter()
    for n in range(NSCREENS):
        s = screens[n]
        free = {0: [t for t in range(0x0b, 0x80) if t not in s["used"] and t not in OBJ_IDS],
                1: [t for t in range(0x80, 0x100) if t not in s["used"] and t not in OBJ_IDS]}
        given = {}
        lst = []
        for e in sorted(s["plan"]):
            f = s["plan"][e]
            if f is None:
                st["left"] += 1
                continue
            k, Db, Df = f
            hist = s["w"][e]
            tiles = [h[0] for h in hist]
            tb = s["tb"]
            new = []
            skip = False
            for g, D in ((tiles[:k], Db), (tiles[k:], Df)):
                if len(g) == 1:
                    new.append((g[0], D, 0))
                    continue
                px = tuple(compose(cpc, g))
                used = set(p for p in px if p is not None)
                cls = 0 if 2 not in used else 1          # pen 2 transparent (0x0b-0x7f) or pen 1
                if cls == 0 and not free[0] and 1 not in used:
                    cls = 1
                key = (px, cls)
                if key not in given and not free[cls]:
                    skip = True                          # no free tile number of that kind left
                    break
                if key not in given:
                    T = 2 if cls == 0 else 1
                    gfx = encode(px, T)
                    if gfx not in pool_ix:
                        pool_ix[gfx] = len(pool)
                        pool.append(gfx)
                    given[key] = (free[cls].pop(0), pool_ix[gfx])
                tid, gi = given[key]
                new.append((tid, D, gi + 1))
            if skip:
                st["left"] += 1
                continue
            lst.append((e, tb[e * 6 + 2], tb[e * 6 + 5], tb[e * 6], tb[e * 6 + 1], tb[e * 6 + 3], tb[e * 6 + 4],
                        new[0][0], new[1][0], new[0][1][0], new[0][1][1], new[1][1][0], new[1][1][1], new[0][2], new[1][2]))
            st["composed"] += 1
        out[n] = lst
    return pool, out, st


def write_header(pool, out, st):
    L = ["/* ql_compose_data.h -- GENERATED by tools/tilecompose.py --gen: do not edit.",
         " * QL_TILE_COMPOSE: per screen, the cells whose dropped graphics are put back (see the tool),",
         " * and the composite tile graphics (CPC Mode 1, 32 bytes each). %d cells composed, %d left as"
         % (st["composed"], st["left"]),
         " * the CPC has them, %d composites. Made from build/roms.bin by build_hybrid.sh (tilecompose.py" % len(pool),
         " * --gen, rewritten only when it changes); tools/regress.sh checks it is in sync (--sync). */",
         "#define QL_COMPOSE_NSCREENS %d" % NSCREENS,
         "#define QL_COMPOSE_NGFX %d" % len(pool),
         "/* cell, the CPC's (t0 t1 x0 y0 x1 y1) the patch expects, the new (t0 t1 x0 y0 x1 y1), the",
         " * composite graphics of the new t0 and t1 (index + 1, 0 = a ROM tile) */",
         "static const unsigned short qlComposeFirst[QL_COMPOSE_NSCREENS + 1] = {"]
    acc, first = 0, []
    for n in range(NSCREENS):
        first.append(acc)
        acc += len(out[n])
    first.append(acc)
    for i in range(0, len(first), 16):
        L.append("\t" + ", ".join(str(v) for v in first[i:i + 16]) + ",")
    L.append("};")
    L.append("static const unsigned char qlComposePatch[%d][16] = {" % max(1, acc))
    for n in range(NSCREENS):
        for p in out[n]:
            e = p[0]
            vals = [e >> 8, e & 0xff] + list(p[1:13]) + [p[13], p[14]]
            L.append("\t{ " + ", ".join("0x%02x" % v for v in vals) + " },\t/* screen %02x r%d c%d */" % (n, e // 16, e % 16))
    if not acc:
        L.append("\t{ 0 }")
    L.append("};")
    L.append("static const unsigned char qlComposeGfx[%d][32] = {" % max(1, len(pool)))
    for g in pool:
        L.append("\t{ " + ", ".join("0x%02x" % v for v in g) + " },")
    L.append("};")
    text = "\n".join(L) + "\n"
    old = open(HEADER).read() if os.path.exists(HEADER) else None
    if old != text:                      # rewritten only when it changes (no needless rebuilds)
        open(HEADER, "w", newline="\n").write(text)
    return old == text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--sync", action="store_true", help="like --gen, but fail if the header was out of date")
    ap.add_argument("--check")
    ap.add_argument("--z80", type=int, default=0, help="with --check: every Nth position also through the Z80 mixer")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.gen or a.sync:
        cpc, screens = build_plan()
        pool, out, st = patches(cpc, screens)
        same = write_header(pool, out, st)
        if a.sync and not same:
            print("COMPOSE DATA: ql_compose_data.h was OUT OF DATE (rewritten): rebuild")
            return 1
        pickle.dump({n: {k: v for k, v in s.items()} for n, s in screens.items()},
                    open(os.path.join(OUT, "plan.pkl"), "wb"))
        print("composed %d cells, left %d; %d composites (%d bytes), %d patches; max per screen %d"
              % (st["composed"], st["left"], len(pool), 32 * len(pool), sum(len(v) for v in out.values()),
                 max(len(v) for v in out.values())))
        return 0
    if a.check:
        return check(a.check, a.z80)




# ---------------------------------------------------------------- checks
def mix_cell(layers, S):
    """the sprite mixer (MezcladorSprites::dibujaTilesEntreProfundidades, CPC 0x4d9e) on one cell
    with one sprite at S = (x, y) covering it with pen 3: pass up to the sprite, the sprite, the
    last pass. layers: [(pens with None = transparent, (profX, profY))] in layer order"""
    px = [0] * 128
    drawn = [False] * len(layers)

    def draw(k):
        for i, p in enumerate(layers[k][0]):
            if p is not None:
                px[i] = p
    for k, (g, d) in enumerate(layers):          # first pass: min (0, 0), max (x+1, y+1)
        if before(S[0], S[1], d):
            drawn[k] = True
            draw(k)
    px = [3] * 128                                 # the sprite (opaque over the whole cell)
    if True:
        hp = False
        for k, (g, d) in enumerate(layers):      # last pass: min (x+1, y+1), max (0xfd, 0xfd)
            if hp and drawn[k]:
                draw(k)                            # drawn earlier: over the layer below again
                continue
            if not before(S[0], S[1], d) and not drawn[k]:
                drawn[k] = True
                hp = True
                draw(k)
    return px


class Z80Mixer:
    """the CPC's own mixer (0x4914) on one cell: a solid pen-3 sprite exactly over the cell at
    local position S, the given tile buffer (CPC layout) and extra tile graphics"""
    def __init__(self, cpc):
        self.base = cpc.mem
        self.r = cpc.r

    def cell(self, tb, gfx, row, col, S):
        cpu = cpcref.Cpu(self.base, self.r)
        m = cpu.m
        mem = m.memory
        mem[0x8d80:0x8d80 + 1920] = tb
        for t, g in gfx.items():
            mem[0x6d00 + t * 32:0x6d00 + t * 32 + 32] = g
        x, y = col * 4 + 8, row * 8 + 40
        e = bytearray(20)
        e[0] = 0x80 | (max(0, S[0] + S[1] - 16) & 0x3f)
        e[1], e[2], e[3], e[4], e[5], e[6] = x, y, x, y, 4, 8
        e[7], e[8] = 0x00, 0xc0
        e[9], e[10], e[11] = 4, 8, 0x80
        e[0x12], e[0x13] = S[0], S[1]
        mem[0xc000:0xc020] = bytes([0xff] * 32)
        mem[0x2e17:0x2e17 + 20] = e
        mem[0x2e17 + 20] = 0xff
        m.sp = 0x00fc
        mem[0xfc] = cpcref.HALT_AT & 0xff
        mem[0xfd] = cpcref.HALT_AT >> 8
        m.pc = 0x4914
        m.set_breakpoint(0x4bdf)
        m.set_breakpoint(cpcref.HALT_AT)
        m.ticks_to_stop = 50_000_000
        while True:
            ev = m.run()
            if ev & (m._BREAKPOINT_HIT | m._TICKS_LIMIT_HIT):
                break
        a = mem[0x2e17 + 0x10] | (mem[0x2e17 + 0x11] << 8)
        assert (mem[0x2e17 + 0x0e], mem[0x2e17 + 0x0f]) == (4, 8)
        out = []
        for b in mem[a:a + 32]:
            out += [((b >> (7 - k)) & 1) | (((b >> (3 - k)) & 1) << 1) for k in range(4)]
        return out


def check(tourdir, z80_every=0):
    cpc = Cpc()
    z = Z80Mixer(cpc) if z80_every else None
    n_z80 = 0
    plan = pickle.load(open(os.path.join(OUT, "plan.pkl"), "rb"))
    pool, out, st = patches(cpc, plan)
    bad = 0
    n_cells = n_pos = 0
    for n in range(NSCREENS):
        s = plan[n]
        tb = bytearray(s["tb"])
        gfx = {}
        for p in out[n]:
            e = p[0]
            tb[e * 6 + 2], tb[e * 6 + 5] = p[7], p[8]
            tb[e * 6], tb[e * 6 + 1], tb[e * 6 + 3], tb[e * 6 + 4] = p[9], p[10], p[11], p[12]
            for t, g in ((p[7], p[13]), (p[8], p[14])):
                if g:
                    gfx[t] = pool[g - 1]
        # 1. the tile buffer the C++ built (tour, composition on) = the CPC's + the plan
        f = os.path.join(tourdir, "tiles_%03d.bin" % n)
        cpp = open(f, "rb").read()
        mine = cpcref.cpc_to_cpp_layout(bytes(tb))
        if cpp != mine:
            d = [e for e in range(320) if cpp[e * 6:e * 6 + 6] != mine[e * 6:e * 6 + 6]]
            print("screen %02x: tile buffer differs from CPC + plan in %d cells (first r%d c%d)" % (n, len(d), d[0] // 16, d[0] % 16))
            bad += 1
        # 2. every composed cell shows what all its writes paint; 3. occlusion = own layers
        for p in out[n]:
            e = p[0]
            n_cells += 1
            hist = s["w"][e]
            tiles = [h[0] for h in hist]

            def pens_of(t):
                g = cpc.pens(t, gfx.get(t))
                T = transp(t)
                return [None if q == T else q for q in g]
            two = [(pens_of(p[7]), (p[9], p[10])), (pens_of(p[8]), (p[11], p[12]))]
            if picture(compose(cpc, tiles)) != picture([q for q in mix_full(two)]):
                print("screen %02x r%d c%d: the composed cell does not show all its writes" % (n, e // 16, e % 16))
                bad += 1
                continue
            refd = [(h[1], h[2]) for h in hist]
            refd[-2] = (s["tb"][e * 6], s["tb"][e * 6 + 1])
            refd[-1] = (s["tb"][e * 6 + 3], s["tb"][e * 6 + 4])
            ideal_layers = [([None if q == transp(t) else q for q in cpc.pens(t)], refd[k]) for k, t in enumerate(tiles) if t]
            row, col = e // 16, e % 16
            for (lx, ly, h) in s["pos"]:
                if not overlaps(rect(lx, ly, h), row, col):
                    continue
                n_pos += 1
                want = mix_cell(ideal_layers, (lx, ly))
                if want != mix_cell(two, (lx, ly)):
                    print("screen %02x r%d c%d: a sprite at (%d,%d) is occluded differently" % (n, row, col, lx, ly))
                    bad += 1
                    break
                if z and n_pos % z80_every == 0:
                    # the same through the CPC's own Z80 mixer, on the composed tile buffer
                    n_z80 += 1
                    got = z.cell(bytes(tb), gfx, row, col, (lx, ly))
                    if got != want:
                        print("screen %02x r%d c%d: the CPC mixer puts a sprite at (%d,%d) differently" % (n, row, col, lx, ly))
                        bad += 1
                        break
    print("COMPOSE: %d problems; %d composed cells, %d sprite positions checked (%d through the CPC's Z80 mixer); "
          "%d cells left as the CPC has them" % (bad, n_cells, n_pos, n_z80, st["left"]))
    return 1 if bad else 0


def mix_full(layers):
    px = [None] * 128
    for g, d in layers:
        for i, q in enumerate(g):
            if q is not None:
                px[i] = q
    return px


if __name__ == "__main__":
    sys.exit(main())

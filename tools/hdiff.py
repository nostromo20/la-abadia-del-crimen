#!/usr/bin/env python3
"""Differential harness: runs the PC oracle and the QL image (unicorn) on the same key script
and reports the first logic step where they differ.

  hdiff.py --script s.txt --ticks N [--screens t1,t2,...] [--every K]

State: the 256-byte block (layout in tools/state_layout.txt) after every step.
Screens: at the listed ticks (and every K ticks with --every) the QL Mode 8 screen is mapped
back to CPC pens through the palette the QL image is using (ink_words) and compared pixel by
pixel with the oracle's 320x200 pen buffer: play area (CPC x 32..287, y 0..159) and the panel
in the provisional layout (CPC panel x 32..287 at QL line PANEL_QL_Y).
"""
import argparse, os, subprocess, struct, sys
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, pngout, colourmodel

def _equ(name):
    """screen placement constants, read from src/qlhooks.s so the tools follow the game"""
    import re
    s = open(os.path.join(QL, "src", "qlhooks.s")).read()
    return int(re.search(r"^%s\s+equ\s+(\d+)" % name, s, re.M).group(1))


PANEL_QL_Y = _equ("PANEL_QL_Y")
PLAY_Y = _equ("PLAY_Y")
WSL_QL = qlpaths.WSL_QL

FIELDS = [("tag", 0, 4), ("ticks", 4, 4), ("dia", 8, 1), ("momentoDia", 9, 1), ("obsequium", 10, 1),
          ("flags", 11, 1), ("duracionMomentoDia", 12, 2), ("bonus", 14, 2), ("numPantalla", 16, 1),
          ("oriCamara", 17, 1), ("numPersonajeCamara", 18, 1), ("mascaraPuertas", 19, 1)]
PERS = ["guillermo", "adso", "malaquias", "abad", "berengario", "severino", "jorge", "bernardo"]
PF = ["posX", "posY", "altura", "orientacion", "estado", "contadorAnimacion", "objetos", "flags"]
for i, n in enumerate(PERS):
    for j, f in enumerate(PF):
        FIELDS.append(("%s.%s" % (n, f), 20 + i * 8 + j, 1))
for i in range(7):
    for j, f in enumerate(["orientacion", "abierta", "posX", "posY"]):
        FIELDS.append(("puerta%d.%s" % (i, f), 84 + i * 4 + j, 1))
for i in range(8):
    for j, f in enumerate(["posX", "posY", "altura", "quien"]):
        FIELDS.append(("objeto%d.%s" % (i, f), 112 + i * 4 + j, 1))
for i in range(24):
    for j, f in enumerate(["visible", "posXPant", "posYPant", "profundidad"]):
        FIELDS.append(("sprite%d.%s" % (i, f), 144 + i * 4 + j, 1))


def field_diffs(a, b):
    out = []
    for name, off, n in FIELDS:
        if a[off:off + n] != b[off:off + n]:
            out.append("%s: oracle %s ql %s" % (name, a[off:off + n].hex(), b[off:off + n].hex()))
    if not out and a != b:
        out.append("unnamed bytes differ")
    return out


def ql_pens(runner):
    """QL screen -> rows of pens (or -1 where the colour is not in the palette)."""
    syms = runner.syms
    words = struct.unpack(">4H", runner.mu.mem_read(runner.base + syms["ink_words"], 8))
    idx = pngout.ql_mode8_to_indices(runner.screen())
    # colour index of a solid word: decode pixel 0 of the word
    def word_index(w):
        g = w >> 8
        rb = w & 0xff
        return ((g >> 7) & 1) * 4 + ((rb >> 7) & 1) * 2 + ((rb >> 6) & 1)
    inv = {}
    for pen, w in enumerate(words):
        inv.setdefault(word_index(w), pen)
    return [[inv.get(v, -1) for v in row] for row in idx]


def compare_colours(host_bin, host_cls, pal, mapping, idx, full=False):
    """CHARCOL: every pixel's QL colour against tools/colourmodel.py: the oracle's pen and source
    (oracle_scenes), the palette in force, the author's mapping (data/colour_mapping.json)"""
    diffs = []
    rows = [(y, PLAY_Y + y) for y in range(200)] if full else \
        [(y, PLAY_Y + y) for y in range(160)] + [(y, PANEL_QL_Y + y - 160) for y in range(160, 200)]
    for y, qy in rows:
        for x in range(256):
            i = y * 320 + 32 + x
            want = colourmodel.colour(mapping, pal, host_cls[i] & 3, host_bin[i] & 3, x, qy)
            got = idx[qy][x]
            if want != got:
                diffs.append(("full" if full else ("play" if y < 160 else "panel"), x, y, want, got))
    return diffs


def compare_screens(host_bin, pens, full=False):
    """full: parchment states, where the whole CPC screen (200 lines) is drawn 1:1"""
    diffs = []
    if full:
        for y in range(200):
            for x in range(256):
                if host_bin[y * 320 + 32 + x] != pens[PLAY_Y + y][x]:
                    diffs.append(("full", x, y, host_bin[y * 320 + 32 + x], pens[PLAY_Y + y][x]))
        return diffs
    for y in range(160):
        for x in range(256):
            h = host_bin[y * 320 + 32 + x]
            q = pens[PLAY_Y + y][x]
            if h != q:
                diffs.append(("play", x, y, h, q))
    for y in range(40):
        for x in range(256):
            h = host_bin[(160 + y) * 320 + 32 + x]
            q = pens[PANEL_QL_Y + y][x]
            if h != q:
                diffs.append(("panel", x, y, h, q))
    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--ticks", type=int, default=100)
    ap.add_argument("--screens", default="")
    ap.add_argument("--every", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(QL, "build", "run"))
    ap.add_argument("--base", default=hex(qlrun.BASE))
    ap.add_argument("--png", action="store_true", help="write PNGs of compared screens")
    ap.add_argument("--intro", action="store_true", help="start with the intro parchment (both sides)")
    ap.add_argument("--realq", action="store_true", help="QL side under the real-QDOS model (qlrun --realq)")
    ap.add_argument("--align-check", action="store_true")
    ap.add_argument("--sv164", default="0")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--mirror", action="store_true", help="the mirror / save-load harness at tick 3, both sides (+ QL cache verify)")
    ap.add_argument("--night", action="store_true", help="night from tick 2 on both sides (FORCE_NIGHT)")
    ap.add_argument("--image", default=os.path.join(QL, "abadia_h_bin"), help="QL image (e.g. the release one, build/rel/unpacked_bin)")
    ap.add_argument("--sym", default=os.path.join(QL, "build", "abadia_h.sym"))
    ap.add_argument("--pens", action="store_true", help="compare pens with the plain oracle (pre-CHARCOL check)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    shots = set(int(x) for x in a.screens.split(",") if x)
    if a.every:
        shots |= set(range(0, a.ticks, a.every))
    shots = sorted(t for t in shots if t < a.ticks)

    def wsl(p):
        return WSL_QL + "/" + os.path.relpath(p, QL).replace("\\", "/")

    host_state = os.path.join(a.out, "oracle.state")
    if a.intro:
        os.environ["INTRO"] = "1"
    # oracle_scenes = the oracle + each pixel's source and the palette (host only, same game):
    # the screens are compared as COLOURS (CHARCOL); --pens uses the plain oracle and pens
    exe = "/build/host/oracle" if a.pens else "/build/host/oracle_scenes"
    if a.night:
        os.environ["FORCE_NIGHT"] = "1"     # both sides: night from tick 2 (qlrun -> header +31 bit 5)
    if a.mirror:
        os.environ["FORCE_MIRROR"] = "1"    # both sides: save, mirror opens, load at tick 3 (header +31 bit 6)
        os.environ["HG_VERIFY"] = "1"       # QL: every height-grid cache hit checked (header +31 bit 7)
    cmd = ["wsl", "env", "SAVEFILE=/tmp/abadia_sav_hdiff", "PALTRACE=1"] + (["INTRO=1"] if a.intro else []) + \
          (["FORCE_NIGHT=1"] if a.night else []) + (["FORCE_MIRROR=1"] if a.mirror else []) + \
          [WSL_QL + exe, WSL_QL + "/build/roms.bin", wsl(a.script), str(a.ticks),
           wsl(host_state), wsl(a.out)] + [str(t) for t in shots]
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    res = subprocess.run(cmd, check=True, env=env, stderr=subprocess.PIPE, text=True)
    # palette changes (tick t: during abadia_tick of tick t); 0 = the black palette, under which
    # the QL keeps drawing in the previous palette's colours
    palchanges = []
    for line in res.stderr.splitlines():
        f = line.split()
        if len(f) == 4 and f[0] == "tick" and f[2] == "palette":
            palchanges.append((int(f[1]), int(f[3])))
    mapping = colourmodel.load()

    def palette_at(t):
        pal = 2
        for tt, pp in palchanges:
            if tt <= t and pp != 0:
                pal = pp
        return pal
    hs = open(host_state, "rb").read()

    image = open(a.image, "rb").read()
    syms = qlrun.load_symbols(a.sym)
    r = qlrun.Runner(image, syms, int(a.base, 0), qlrun.load_script(a.script), a.align_check, a.realq,
                     int(a.sv164, 0), a.seed)
    screen_report = []

    def on_tick(r):
        t = r.tick
        if t in shots:
            hb = open(os.path.join(a.out, "screen_%05d.bin" % t), "rb").read()
            estado = r.states[-1][240] if r.states else 1
            if a.pens:
                d = compare_screens(hb, ql_pens(r), full=estado in (0, 3))
            else:
                hc = open(os.path.join(a.out, "cls_%05d.bin" % t), "rb").read()
                d = compare_colours(hb, hc, palette_at(t), mapping, pngout.ql_mode8_to_indices(r.screen()),
                                    full=estado in (0, 3))
            screen_report.append((t, d))
            if a.png:
                r.dump_png(os.path.join(a.out, "ql_%05d.png" % t))
                rows = [list(hb[y * 320:(y + 1) * 320]) for y in range(200)]
                pngout.ink_rows_to_png(os.path.join(a.out, "host_%05d.png" % t), rows)

    r.tick_cb = on_tick
    dt = r.run(a.ticks)
    qs = b"".join(r.states)
    print("QL run: %s, %d ticks, %.1f s" % (r.stop_reason, r.tick, dt))
    r.report()
    if r.odd:
        print("ODD ACCESSES:", ["pc %06x addr %06x size %d" % o for o in r.odd[:10]])

    n = min(len(hs), len(qs)) // 256
    first = None
    for t in range(n):
        if hs[t * 256:(t + 1) * 256] != qs[t * 256:(t + 1) * 256]:
            first = t
            break
    if first is None:
        print("STATE: identical for %d ticks" % n)
    else:
        print("STATE: first difference at tick %d" % first)
        for line in field_diffs(hs[first * 256:(first + 1) * 256], qs[first * 256:(first + 1) * 256])[:30]:
            print("   ", line)
    bad_screens = 0
    for t, d in screen_report:
        if d:
            bad_screens += 1
            print("SCREEN tick %d: %d pixels differ, first %s" % (t, len(d), d[:5]))
    print("SCREENS: %d compared, %d differ" % (len(screen_report), bad_screens))
    qsound = 0xC0000 <= int(a.sv164, 0) < 0x100000      # modelled as present: port writes expected
    bad_model = bool(r.poll_faults or r.susjb_a1 or (r.ay_port_writes and not qsound) or r.odd)
    if bad_model:
        print("REAL-QDOS MODEL: problems reported above")
    return 0 if first is None and bad_screens == 0 and r.tick == a.ticks and not bad_model else 1


if __name__ == "__main__":
    sys.exit(main())

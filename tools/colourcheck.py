#!/usr/bin/env python3
"""Colour check (CHARCOL): the scenes of tools/colour_mapper.html (tools/colour_scenes.js: real
oracle frames, each pixel = CPC pen + source) drawn through the QL image's REAL copy path in
unicorn, for every palette of the author's mapping (data/colour_mapping.json), compared pixel for
pixel with tools/colourmodel.py (the rules the tool's "Game" view uses).

  - play area: the scene's pens packed as the mixer packs them, its sprite mask from the
    characters source, through ql_play_blit_p (the per-palette tables, the sprite-mask path,
    dithers by line parity);
  - panel: the scene's bottom 40 rows through ql_panel_present (the panel tables);
  - palette 0 only blanks the screen (the game draws nothing in it): checked to be all black.

  colourcheck.py          exit 1 on any difference
"""
import base64, json, os, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, pngout, colourmodel
from hdiff import PLAY_Y, PANEL_QL_Y

BUF = 0x30000           # scratch: packed play area; its sprite mask at +MASK_OFF
MASK_OFF = 4096
PANEL = 0x34000         # 320 x 40 panel pens


def scenes():
    t = open(os.path.join(HERE, "colour_scenes.js")).read()
    d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    out = []
    for s in d["scenes"]:
        b = zlib.decompress(base64.b64decode(s["z"]))
        px = []
        for byte in b:
            px += [byte >> 4, byte & 15]
        out.append((s, px))
    return out


def pack_row(pens):
    out = bytearray()
    for i in range(0, len(pens), 4):
        b = 0
        for k in range(4):
            p = pens[i + k]
            b |= (p & 1) << (7 - k) | ((p >> 1) & 1) << (3 - k)
        out.append(b)
    return bytes(out)


def main():
    mapping = colourmodel.load()
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)
    mu = r.mu
    sc = scenes()
    fails = 0
    for pal in (1, 2, 3, 0):
        r.call("ql_set_palette", 3 if pal != 3 else 2)      # a real change, so the tables are built
        r.call("ql_set_palette", pal)
        sep = mu.mem_read(qlrun.BASE + syms["char_sep"], 1)[0]
        if pal == 0:
            ok = all(v == 0 for v in bytes(mu.mem_read(0x20000, 0x8000)))
            print("%-4s palette 0 (black): screen blanked, %s" % ("ok" if ok else "FAIL", "all black" if ok else "NOT black"))
            fails += not ok
            continue
        for s, px in sc:
            # play area: packed pens + sprite mask (bit 3-k = characters source)
            data, mask = bytearray(), bytearray()
            for y in range(160):
                row = px[y * 256:(y + 1) * 256]
                data += pack_row([v & 3 for v in row])
                for i in range(0, 256, 4):
                    m = 0
                    for k in range(4):
                        if (row[i + k] >> 2) == 1:
                            m |= 8 >> k
                    mask.append(m)
            mu.mem_write(0x20000, bytes(0x8000))
            for band in range(0, 160, 40):      # 40 rows = 2560 bytes: the mask (+4096) never overlaps,
                lo, hi = band * 64, (band + 40) * 64     # as in the game (the mixer's area is at most 2 KB)
                mu.mem_write(BUF, bytes(data[lo:hi]))
                mu.mem_write(BUF + MASK_OFF, bytes(mask[lo:hi]))
                r.call("ql_play_blit_p", 32, band, 256, 40, BUF, 64)
            panel = bytearray(320 * 40)
            for y in range(40):
                for x in range(256):
                    panel[y * 320 + 32 + x] = px[(160 + y) * 256 + x] & 3
            mu.mem_write(PANEL, bytes(panel))
            r.call("ql_panel_present", 32, 0, 256, 40, PANEL)
            idx = pngout.ql_mode8_to_indices(bytes(mu.mem_read(0x20000, 0x8000)))
            bad = 0
            first = None
            for y in range(200):
                qy = PLAY_Y + y if y < 160 else PANEL_QL_Y + y - 160
                for x in range(256):
                    v = px[y * 256 + x]
                    cls = (v >> 2) if y < 160 else 3          # the panel rows go through the panel path
                    want = colourmodel.colour(mapping, pal, cls, v & 3, x, qy)
                    if idx[qy][x] != want:
                        bad += 1
                        if first is None:
                            first = (x, y, want, idx[qy][x])
            print("%-4s palette %d%s  %-22s %s" % ("ok" if not bad else "FAIL", pal, " (sprite mask)" if sep else "              ",
                                                    s["id"], ("%d pixels differ, first %s" % (bad, first)) if bad else "all 51200 pixels"))
            fails += bad > 0
    print("COLOUR: %d checks failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

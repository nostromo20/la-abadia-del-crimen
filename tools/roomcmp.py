#!/usr/bin/env python3
"""Step 3 renderer check: every screen of the abbey, three ways.

 1. oracle (PC): VIGASOCO GeneradorPantallas -> tile buffer -> CPC tile drawing  (reference)
 2. QL image (unicorn): the same C++ compiled for the 68000 -> tile buffer -> asm tile
    blitter (src/qlhooks.s ql_play_tile on tools/convert_tiles.py data)
 3. the OLD all-asm renderer's precomputed room grids (src/room_data.s from
    tools/convert_rooms.py), matched to screens by content

Reports, per screen: tile buffer QL vs oracle (bytes), pixels QL vs oracle (play area),
and for the old grids the cells whose tile lists differ from the C++ buffer.
Writes build/roomcmp/sheet_*.png contact sheets and build/roomcmp/report.txt.

  roomcmp.py [--first 0] [--last 0x73]
"""
import argparse, os, re, struct, subprocess, sys
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, pngout, hdiff

WSL_QL = qlpaths.WSL_QL
OUT = os.path.join(QL, "build", "roomcmp")
TB = 20 * 16 * 2 * 3


def parse_old_rooms(path):
    """room_data.s -> {room_id: {(row,col): [tiles in draw order]}}"""
    rooms = {}
    cur = None
    base = []
    ov_count = None
    ov = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"room_(\d+):", line)
        if m:
            if cur is not None:
                rooms[cur] = (base, ov)
            cur = int(m.group(1))
            base, ov, ov_count = [], [], None
            continue
        if cur is None:
            continue
        m = re.match(r"\s+dc\.w\s+(\d+)", line)
        if m:
            ov_count = int(m.group(1))
            continue
        m = re.match(r"\s+dc\.b\s+([^;]+)", line)
        if m:
            vals = []
            for v in m.group(1).split(","):
                v = v.strip()
                vals.append(int(v[1:], 16) if v.startswith("$") else int(v))
            if ov_count is None:
                base += vals
            else:
                ov += vals
    if cur is not None:
        rooms[cur] = (base, ov)
    out = {}
    for rid, (base, ov) in rooms.items():
        cells = {}
        for i, t in enumerate(base[:320]):
            if t:
                cells[(i // 16, i % 16)] = [t]
        for i in range(0, len(ov) - 2, 3):
            r, c, t = ov[i], ov[i + 1], ov[i + 2]
            cells.setdefault((r, c), []).append(t)
        out[rid] = cells
    return out


def cpp_cells(tb):
    cells = {}
    for r in range(20):
        for c in range(16):
            o = (r * 16 + c) * 6
            ts = [tb[o], tb[o + 3]]
            ts = [t for t in ts if t]
            if ts:
                cells[(r, c)] = ts
    return cells


def draw_cells(cells, rom):
    """Old-renderer cells drawn with the CPC tile rule -> 256x160 pens (background pen 0)."""
    scr = [[0] * 256 for _ in range(160)]
    for (r, c), ts in cells.items():
        for t in ts:
            d = rom[0x4000 + 0x8300 + t * 32:0x4000 + 0x8300 + t * 32 + 32]
            transp = 1 if t & 0x80 else 2
            for j in range(8):
                for i in range(4):
                    b = d[j * 4 + i]
                    for k in range(4):
                        ink = (((b >> (3 - k)) & 1) << 1) | ((b >> (7 - k)) & 1)
                        if ink != transp:
                            scr[r * 8 + j][c * 16 + i * 4 + k] = ink
    return scr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--last", type=lambda x: int(x, 0), default=0x73)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    rom = open(os.path.join(QL, "build", "roms.bin"), "rb").read()

    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    subprocess.run(["wsl", WSL_QL + "/build/host/oracle", "--tour", WSL_QL + "/build/roms.bin",
                    WSL_QL + "/build/roomcmp", str(a.first), str(a.last)], check=True, env=env)

    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, [])
    r.run(1)
    TBADDR = 0x30000

    old = parse_old_rooms(os.path.join(QL, "src", "room_data.s"))
    report = []
    screens = {}
    sheet = []
    n_tb_bad = n_px_bad = 0
    for n in range(a.first, a.last + 1):
        host_scr = open(os.path.join(OUT, "tour_%03d.bin" % n), "rb").read()
        host_tb = open(os.path.join(OUT, "tiles_%03d.bin" % n), "rb").read()
        r.mu.mem_write(0x20000, b"\0" * 0x8000)
        r.call("abadia_show_screen", n)
        r.call("abadia_tilebuf", TBADDR)
        ql_tb = bytes(r.mu.mem_read(TBADDR, TB))
        pens = hdiff.ql_pens(r)
        pens = pens[hdiff.PLAY_Y:hdiff.PLAY_Y + 160]      # the play area's QL lines
        px = sum(1 for y in range(160) for x in range(256) if host_scr[y * 320 + 32 + x] != pens[y][x])
        tb_ok = ql_tb == host_tb
        n_tb_bad += not tb_ok
        n_px_bad += px != 0
        cells = cpp_cells(host_tb)
        screens[n] = cells
        report.append("screen %02x: tilebuf %s, pixels %s, %d cells" %
                      (n, "identical" if tb_ok else "DIFFER", "identical" if px == 0 else "%d DIFFER" % px, len(cells)))
        sheet.append((n, [list(host_scr[y * 320 + 32:y * 320 + 288]) for y in range(160)], pens))

    # old grids: match each to the screen with the most identical cells
    report.append("")
    report.append("old asm room grids (src/room_data.s) vs the C++ tile buffer:")
    old_sheet = []
    summary = {"exact": 0, "differ": 0}
    for rid, ocells in sorted(old.items()):
        best, bestscore = None, -1
        for n, cells in screens.items():
            score = sum(1 for k, v in ocells.items() if cells.get(k) == v)
            if score > bestscore:
                best, bestscore = n, score
        cells = screens[best]
        keys = set(ocells) | set(cells)
        diff = [k for k in keys if ocells.get(k, []) != cells.get(k, [])]
        more = sum(1 for k in diff if len(ocells.get(k, [])) > 2)
        summary["exact" if not diff else "differ"] += 1
        report.append("old room %2d ~ screen %02x: %d/%d cells differ (%d of them have >2 tiles in the old grid)"
                      % (rid, best, len(diff), len(keys), more))
        oscr = draw_cells(ocells, rom)
        old_sheet.append((rid, best, oscr))
    report.append("old grids: %d exact, %d differ" % (summary["exact"], summary["differ"]))
    report.append("")
    report.append("SUMMARY: %d screens; tile buffer QL != oracle: %d; pixels QL != oracle: %d"
                  % (len(screens), n_tb_bad, n_px_bad))
    open(os.path.join(OUT, "report.txt"), "w").write("\n".join(report) + "\n")
    print("\n".join(report[-3:]))

    # contact sheets: 4 per row, oracle | QL side by side
    def sheet_png(path, items):
        cols = 4
        rows_out = []
        for i in range(0, len(items), cols):
            group = items[i:i + cols]
            for y in range(162):
                line = []
                for it in group:
                    for img in it[1:]:
                        if y < 160:
                            line += [pngout.CPC_PAL[2][v] if v >= 0 else (255, 0, 255) for v in img[y]]
                        else:
                            line += [(40, 40, 40)] * 256
                        line += [(40, 40, 40)] * 4
                line += [(40, 40, 40)] * ((cols - len(group)) * (len(items[0]) - 1) * 260)
                rows_out.append(line)
        pngout.write_png(path, len(rows_out[0]), len(rows_out), rows_out)

    for i in range(0, len(sheet), 16):
        sheet_png(os.path.join(OUT, "sheet_%02x.png" % sheet[i][0]), sheet[i:i + 16])
    print("report: build/roomcmp/report.txt, sheets build/roomcmp/sheet_*.png")
    return 0 if (n_tb_bad == 0 and n_px_bad == 0) else 1


if __name__ == "__main__":
    sys.exit(main())

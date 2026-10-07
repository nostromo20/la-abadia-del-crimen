#!/usr/bin/env python3
"""Height-grid cache check (QL_HGRID_CACHE, RejillaPantalla::qlRellenaVentana).

Every run is made with VERIFY ON HIT (header +31 bit 7): each cache hit is compared with a fresh
fill and a mismatch stops the game with fault 'HGC1'. Runs: walk1 4000, enter 900, saveload 900
(save + load in play), and the MIRROR sequence (header +31 bit 6: at tick 3 fills of the mirror
room's window, save, the mirror opens, fills, load, fills).

A memory-write hook over the whole CPC image (roms) lists every function that writes into it;
the writers of the HEIGHT TABLES the fill reads (roms 0x18a00 - 0x190ff) must be exactly the ones
that bump ql_hgen (ql_port.h). For the mirror sequence the test also checks the pattern of its
six fills (miss, hit, miss, hit, miss, hit: every height write made the cache miss) and that the
mirror's grid really changed.

  hgridtest.py          exit 1 on any problem
"""
import bisect, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn import m68k_const as M

IMAGE = 0x20000                      # roms = the CPC image (roms.bin minus its 0x4000 header)


def height_range():
    """the three floors' height tables as the fill reads them (to each 0xff), + the mirror's
    5-byte entry at the end of floor 2's: roms offsets [start, end)"""
    r = open(os.path.join(QL, "build", "roms.bin"), "rb").read()[0x4000:]
    end = 0
    for st in (0x18a00, 0x18f00, 0x19080):
        d = st
        while r[d] != 0xff and (r[d] & 7) and (r[d] & 7) < 6:
            d += 5 if r[d] & 8 else 4
        end = max(end, d + 8)
    return 0x18a00, end


HEIGHT = height_range()
KNOWN = {"Logica::iniciaHabitacionEspejo", "Logica::compruebaAbreEspejo", "Logica::qlHarnessAbreEspejo",
         "Logica::despHabitacionEspejo", "Serializar"}


def demangle(n):
    import re
    m = re.match(r"_ZN6Abadia(\d+)", n)
    if not m:
        return n
    rest = n[m.end():]
    l1 = int(m.group(1))
    cls = rest[:l1]
    rest = rest[l1:]
    m2 = re.match(r"(\d+)", rest)
    return cls + "::" + rest[len(m2.group(1)):len(m2.group(1)) + int(m2.group(1))] if m2 else cls


def main():
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    funcs = sorted((v, k) for k, v in syms.items() if not k.startswith("."))
    faddr = [v for v, k in funcs]
    os.environ["HG_VERIFY"] = "1"
    bad = 0
    total_h = total_m = 0
    for name, script, ticks, mirror in (("walk1", "tests/walk1.txt", 4000, False),
                                        ("enter", "tests/enter.txt", 900, False),
                                        ("saveload", "tests/saveload.txt", 900, False),
                                        ("mirror", "tests/walk1.txt", 300, True)):
        if mirror:
            os.environ["FORCE_MIRROR"] = "1"
        else:
            os.environ.pop("FORCE_MIRROR", None)
        os.environ["SAVEFILE"] = os.path.join(QL, "build", "tmp", "hgrid_sav")
        r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(os.path.join(QL, script)), realq=True, sv164=0xC1000)
        roms = qlrun.BASE + syms["rom_image"] + 0x4000
        writers = {}

        def on_write(mu, access, addr, size, value, data):
            off = addr - roms
            pc = mu.reg_read(M.UC_M68K_REG_PC) - qlrun.BASE
            k = bisect.bisect_right(faddr, pc) - 1
            fn = demangle(funcs[k][1]) if k >= 0 else "?"
            if "rsER4QLIn" in funcs[k][1] or "Serializar" in funcs[k][1]:
                fn = "Serializar"          # operator>>(QLIn &, Logica *): the save loader
            region = "HEIGHT" if HEIGHT[0] <= off < HEIGHT[1] else "other"
            writers.setdefault((region, fn), set()).add(off)
        r.mu.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=roms, end=roms + IMAGE - 1)
        r.run(ticks)
        hits = struct.unpack(">I", bytes(r.mu.mem_read(qlrun.BASE + syms["ql_hg_hits"], 4)))[0]
        misses = struct.unpack(">I", bytes(r.mu.mem_read(qlrun.BASE + syms["ql_hg_misses"], 4)))[0]
        gen = struct.unpack(">I", bytes(r.mu.mem_read(qlrun.BASE + syms["ql_hgen"], 4)))[0]
        ok = r.stop_reason == "tick limit"
        total_h += hits
        total_m += misses
        print("%-4s %-9s %s; fills %d, hits %d (%.0f%%), ql_hgen %d" % ("ok" if ok else "FAIL", name, r.stop_reason,
              hits + misses, hits, 100.0 * hits / max(1, hits + misses), gen))
        for (region, fn), offs in sorted(writers.items()):
            known = fn in KNOWN
            print("       writes %-6s %-36s %4d bytes at %05x-%05x %s" % (region, fn, len(offs), min(offs), max(offs),
                  "" if region != "HEIGHT" or known else "  <-- NOT A KNOWN WRITER"))
            if region == "HEIGHT" and not known:
                ok = False
        if mirror:
            t = struct.unpack(">16i", bytes(r.mu.mem_read(qlrun.BASE + syms["ql_hg_test"], 64)))
            seq = ["hit" if v else "miss" for v in t[:10]]
            print("       mirror sequence (closed x2, OPENED x2, LOADED closed save x2, CLOSED x2, LOADED open save x2):")
            print("       ", seq)
            print("       opening changed the grid: %s; load of the closed save gives the closed grid: %s; load of the "
                  "open save gives the open grid: %s" % (bool(t[10]), bool(t[11]), bool(t[12])))
            if seq != ["miss", "hit"] * 5 or not (t[10] and t[11] and t[12]):
                print("       FAIL: expected miss, hit five times and the right grids")
                ok = False
        bad += not ok
    print("height tables: roms %05x-%05x" % HEIGHT)
    print("HGRID: %d runs failed; overall hit rate %.0f%% (%d of %d fills)" % (bad, 100.0 * total_h / max(1, total_h + total_m),
          total_h, total_h + total_m))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

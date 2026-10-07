#!/usr/bin/env python3
"""The conservative trim of the embedded CPC data image for a release build (docs/compression.md).

KEEP = every byte the game was seen to READ before writing it (tools/romusage.py, the dynamic
map) UNION the static extents of every table the C++/asm reads by a constant address (below).
Everything else is set to 0: bytes nothing reads, and bytes the game writes before it reads them
(the flipped graphics built in abadia6). The layout (addresses) does not change, so the game
code is the same; a release build would embed build/roms_trim.bin instead of build/roms.bin.

  romtrim.py [--usage build/romusage.bin] [--out build/roms_trim.bin]
  romtrim.py --english --out build/roms_trim_en.bin    (the English-only release, IDIOMA=1)

--english also zeroes the CPC's own Spanish parchment texts, which the game never reads (it
draws the parchments from cpp/vigasoco/PergaminoTextos.cpp); they lie inside two kept extents:
  roms 0x7300-0x787a  the start parchment (ends in 0x1a), inside the parchment stroke-data extent;
                      the bytes read right after it (romusage: 0x788a on) are the parchment
                      border graphics (Pergamino::dibujaTriangulo/restaura*, 0x788a/0x7a0a/...),
                      their own extent below, untouched
  roms 0x1ee58-0x1f7c0  the end parchment (ends in 0x1a), inside the ending tune window
                      (ql_sound.c reads 0x1eb28 + 0x1518 bytes; the tune data never reaches it:
                      no reads in the dynamic map, which plays both parchment tunes)
"""
import argparse, lzma, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
P = 0x4000                 # romsPtr = roms + 0x4000 (roms = the CPC address space as VIGASOCO indexes it)

BANKS = [(0x00000, 0x04000, "abadia0 (CPC title screen)"),
         (0x04000, 0x04100, "gap before abadia1 (CPC 0x0000-0x00ff)"),
         (0x04100, 0x08000, "abadia1 (CPC 0x0100-0x3fff: code + tables)"),
         (0x08000, 0x0c000, "abadia2 (CPC 0x4000-0x7fff: code + tables)"),
         (0x0c000, 0x10000, "abadia3 (CPC 0x8000-0xbfff: gfx, tiles, text)"),
         (0x10000, 0x14000, "romsPtr 0x10000-0x13fff (no bank)"),
         (0x14000, 0x18000, "abadia5 (CPC bank 4)"),
         (0x18000, 0x1c000, "abadia6 (CPC bank 5; flips are built here)"),
         (0x1c000, 0x20000, "abadia7 (CPC bank 6: heights)"),
         (0x20000, 0x24000, "abadia8 (CPC bank 7: screens, panel, ending tune)")]


def static_extents(r):
    """(start, end) in roms (CPC) addresses, end exclusive: tables read at constant addresses"""
    roms = r[P:]
    ext = [
        (0x0000, 0x0100, "CPC 0x0000-0x00ff: kept (UNCERTAIN: a zero pointer could reach it)"),
        (0x0f96, 0x1034, "sound: work area image + effect entry table (ql_sound.c snd_init/snd_play)"),
        (0x1306, 0x1318, "sound: command table (ql_sound.c 0x1306)"),
        (0x156d, 0x166d, "screen generator: block-type table (0x80 pointers)"),
        # conservative: the whole regions the data-driven readers walk, gaps included
        (0x0f96, 0x161b, "sound engine data region, whole (0x0f96-0x161a; the dynamic map has gaps)"),
        (0x156d, 0x2236, "screen generator materials + bytecode, whole (0x156d-0x2235, up to its code)"),
        (0x38e7, 0x38ef, "panel: blank character (Marcador 0x38e7)"),
        (0x4fa7, 0x4fed, "panel: day numerals (3 x 7) + time-of-day names (7 x 7)"),
        (0x5581, 0x5591, "panel: blank digit (Marcador 0x5581)"),
        (0x788a, 0x7e8a, "parchment border graphics (0x788a/0x7a0a/0x7b8a/0x7d0a)"),
        (0x8000, 0x9518, "intro tune window (ql_sound.c 0x8000-0x9517)"),
        (0x8300, 0xa300, "tile graphics (all 256: build_tiles, the mixer)"),
        (0xa300, 0xb3c0, "character, monk, door graphics (flip sources) + panel digits 0xab39/0xab49"),
        (0xb400, 0xb6a0, "font (Marcador 0xb400 + 8*(c-0x2d), c up to 0x7f)"),
        (0x18a00, 0x19422, "height tables of the three floors + the mirror's entry"),
        (0x1e328, 0x1eb28, "panel graphics (Marcador 0x1e328, 32 lines x 64 bytes)"),
        (0x1eb28, 0x20000, "ending tune window (ql_sound.c 0x1eb28, 0x1518 bytes, clipped at the end)"),
    ]
    # the screens' block data: up to the end of the last screen (0x73)
    d = 0x1c000
    for i in range(0x74):
        d += roms[d]
    ext.append((0x1c000, d + 1, "screen block data, screens 0x00-0x73 (MotorGrafico::obtenerDirPantalla)"))
    # parchment strokes: the character table and the data its pointers can reach
    ptrs = [roms[0x680c + 2 * c] | (roms[0x680c + 2 * c + 1] << 8) for c in range(0x80)]
    ptrs = [p for p in ptrs if 0x6000 <= p < 0x8000]
    ext.append((0x680c, 0x680c + 0x100, "parchment: character stroke table (0x680c, 0x80 entries)"))
    ext.append((min(ptrs), max(ptrs) + 0x100, "parchment: stroke data, every table pointer + 256 bytes"))
    return ext


# the CPC's Spanish parchment texts (roms addresses, end exclusive, through the 0x1a terminator)
SPANISH_TEXTS = [(0x7300, 0x787b, b" Ya al final de mi"),
                 (0x1ee58, 0x1f7c1, b" Desfigurado por la")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usage", default=os.path.join(QL, "build", "romusage.bin"))
    ap.add_argument("--out", default=os.path.join(QL, "build", "roms_trim.bin"))
    ap.add_argument("--english", action="store_true", help="also zero the CPC's Spanish parchment texts")
    a = ap.parse_args()
    r = open(os.path.join(QL, "build", "roms.bin"), "rb").read()
    first = open(a.usage, "rb").read()
    keep = bytearray(len(r))
    for i in range(len(r)):
        if first[i] == 1:
            keep[i] = 1
    ext = static_extents(r)
    for s, e, why in ext:
        for i in range(s + P, min(e + P, len(r))):
            keep[i] = 1
    if a.english:
        for s, e, txt in SPANISH_TEXTS:
            assert r[P + s:P + s + len(txt)] == txt and r[P + e - 1] == 0x1a, "Spanish parchment text not at %05x" % s
            assert not any(first[P + i] == 1 for i in range(s, e)), "a Spanish parchment byte is read"
            for i in range(s + P, e + P):
                keep[i] = 0
    out = bytes(r[i] if keep[i] else 0 for i in range(len(r)))
    open(a.out, "wb").write(out)

    def lz(b):
        f = [{"id": lzma.FILTER_LZMA1, "preset": 9 | lzma.PRESET_EXTREME, "lc": 3, "lp": 0, "pb": 2,
              "dict_size": 1 << 20}]
        return len(lzma.compress(b, format=lzma.FORMAT_RAW, filters=f))
    print("static extents added to the dynamic map:")
    for s, e, why in sorted(ext):
        print("  roms %05x-%05x  %s" % (s, e - 1, why))
    print()
    print("%-52s %7s %7s %7s %8s" % ("bank (romsPtr range)", "size", "kept", "zeroed", "LZMA saved"))
    tot = [0, 0, 0]
    for lo, hi, name in BANKS:
        k = sum(keep[lo:hi])
        a0 = lz(r[lo:hi])
        a1 = lz(out[lo:hi])
        tot[0] += k
        tot[1] += a0 - a1
        print("%05x-%05x %-40s %7d %7d %7d %8d" % (lo, hi - 1, name, hi - lo, k, hi - lo - k, a0 - a1))
    full0, full1 = lz(r), lz(out)
    print("whole image: kept %d of %d bytes; LZMA %d -> %d (saves %d)" % (tot[0], len(r), full0, full1, full0 - full1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

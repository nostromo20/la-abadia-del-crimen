#!/usr/bin/env python3
"""One-shot fix: tile transparency pens (pen 2 transparent for tiles 0x00-0x7f, pen 1 for
0x80-0xff, as the CPC AND/OR tables at 0x9d00/0x9f00 give with VIGASOCO's pen numbering)."""
import io, os

QL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fix(path, pairs):
    p = os.path.join(QL, path)
    s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old)
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    for old, new in pairs:
        assert new in io.open(p, encoding="utf-8").read()


fix("cpp/vigasoco/MezcladorSprites.cpp", [
    ("\t// CPC make ink 1 transparent for tiles 0x00-0x7f and ink 2 for tiles 0x80-0xff (the fork's\n"
     "\t// generaMascaras() has the two ink bits swapped, so it is not used here).\n",
     "\t// CPC make pen 2 transparent for tiles 0x00-0x7f and pen 1 for tiles 0x80-0xff (pens as\n"
     "\t// unpackPixelMode1 numbers them; same result as the fork's generaMascaras()).\n"),
    ("\tint transparente = (tile < 0x0b) ? -1 : ((tile & 0x80) ? 2 : 1);",
     "\tint transparente = (tile < 0x0b) ? -1 : ((tile & 0x80) ? 1 : 2);"),
])
fix("cpp/host/host_main.cpp", [
    ("// CPC tile drawing: AND/OR tables by bit 7 of the tile (ink 1 transparent for tiles\n"
     "// 0x00-0x7f, ink 2 for 0x80-0xff), as the CPC routine at 0x4f3d.",
     "// CPC tile drawing: AND/OR tables by bit 7 of the tile (pen 2 transparent for tiles\n"
     "// 0x00-0x7f, pen 1 for 0x80-0xff), as the CPC routine at 0x4f3d."),
    ("\tint transp = (tile & 0x80) ? 2 : 1;", "\tint transp = (tile & 0x80) ? 1 : 2;"),
])
fix("src/qlhooks.s", [
    ("; Day matches tools/convert_tiles.py (cyan, red, yellow, black).",
     "; Day matches tools/convert_tiles.py, whose decoder numbers pens with the two\n"
     "; nibbles swapped: true pen 1 -> yellow, pen 2 -> red (cyan, yellow, red, black)."),
    ("        dc.w    COL_CYAN,COL_RED,COL_YELLOW,COL_BLACK",
     "        dc.w    COL_CYAN,COL_YELLOW,COL_RED,COL_BLACK"),
])
print("ok")

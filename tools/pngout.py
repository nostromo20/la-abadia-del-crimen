#!/usr/bin/env python3
"""Minimal PNG writer + screen decoders shared by the harness tools (no PIL needed).

  ink_screen_to_rgb(buf, palette)   host oracle dump: 320x200 bytes of CPC inks
  ql_mode8_to_indices(buf)          QL Mode 8 screen (32 KB at $20000) -> 256x256 colour indices
"""
import struct, zlib

# CPC inks in the game palettes, as RGB (hardware colours: day 06,14,03,20; night 04,29,00,20)
CPC_PAL = {
    2: [(0, 128, 128), (255, 128, 0), (255, 255, 128), (0, 0, 0)],
    3: [(0, 0, 128), (128, 0, 255), (255, 255, 255), (0, 0, 0)],
    0: [(0, 0, 0)] * 4,
    1: [(0, 0, 0), (128, 0, 0), (0, 0, 0), (255, 255, 0)],
}
# QL Mode 8 colour index = G*4 + R*2 + B
QL_RGB = [(0, 0, 0), (0, 0, 255), (255, 0, 0), (255, 0, 255),
          (0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 255, 255)]


def write_png(path, w, h, rgb_rows):
    raw = b"".join(b"\0" + bytes(c for px in row for c in px) for row in rgb_rows)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def ql_mode8_to_indices(buf):
    """32 KB Mode 8 screen -> list of 256 rows of 256 colour indices (0-7)."""
    rows = []
    for y in range(256):
        row = []
        base = y * 128
        for xw in range(64):
            g = buf[base + xw * 2]
            rb = buf[base + xw * 2 + 1]
            for p in range(4):
                sh = 7 - 2 * p
                G = (g >> sh) & 1
                R = (rb >> sh) & 1
                B = (rb >> (sh - 1)) & 1
                row.append(G * 4 + R * 2 + B)
        rows.append(row)
    return rows


def scale_rows(rows, sx, sy):
    out = []
    for r in rows:
        nr = [px for px in r for _ in range(sx)]
        for _ in range(sy):
            out.append(nr)
    return out


def ink_rows_to_png(path, rows, palette=2, scale=2):
    pal = CPC_PAL.get(palette, CPC_PAL[2])
    rgb = [[pal[v & 3] for v in r] for r in rows]
    rgb = scale_rows(rgb, scale, scale)
    write_png(path, len(rgb[0]), len(rgb), rgb)


def ql_rows_to_png(path, rows, scale=2):
    rgb = [[QL_RGB[v] for v in r] for r in rows]
    rgb = scale_rows(rgb, scale, scale)
    write_png(path, len(rgb[0]), len(rgb), rgb)

#!/usr/bin/env python3
"""Loading/title screen candidates for the QL port (Mode 8, plus one Mode 4 comparison).

Sources (read-only):
  CPC  data/ABADIA0.BIN       16 KB screen dump of 0xC000-0xFFFF, MODE 0 (160x200, 16 pens),
                              palette from pista0.asm 0x010D (call 0x0182 + 17 hw-colour bytes).
  DOS  ABADIA.PIC             16 KB CGA 320x200x4 (banks at 0/0x2000), copied raw to B800:0 by
                              ABADIA.EXE; palette = INT 10h AX=0B00h BX=0100h after mode 4
                              (F1 "MONITOR COLOR") = palette 0, high intensity (BIOS 3D9h=30h).
  ZX   Abadia_Intro_English_snap0.z80, RAM bank 5 (page 8) = SCREEN$ of the 2002 English
                              Spectrum conversion ("The abbey of crime").

Outputs go to QL/loadscreen/: src_*.png, <id>_preview.png (2x of the 512x256 logical
display), <id>_scr (32768-byte raw screen for LBYTES to 131072), loadscreen_sheet.png,
view_bas; plus the STRETCHED set <id>S_* (whole 256x256 screen, no border),
loadscreen_sheet_stretch.png, compare_sheet.png and view_stretch_bas.  Every _scr is decoded back with an independent decoder and compared with its preview.

usage: python tools/loadscreen.py
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
ROSE = os.path.dirname(QL)
OUT = os.path.join(QL, "loadscreen")
CPC_BIN = os.path.join(QL, "data", "ABADIA0.BIN")
DOS_PIC = os.path.join(os.path.dirname(ROSE), "La-Abadia-del-Crimen_DOS_ES", "la-abadia-del-crimen", "ABADIA.PIC")
ZX_SNAP = os.path.join(ROSE, "Spectrum_abadia_source", "Source", "Abadia_Intro_English_snap0.z80")
ZX_DIR = os.path.join(ROSE, "Spectrum_abadia_source")

TOP200 = 28          # layout A: 200-line picture at QL lines 28..227
TOP192 = 32          # 192-line Spectrum picture at QL lines 32..223

# QL colour code = G<<2 | R<<1 | B  (0 black,1 blue,2 red,3 magenta,4 green,5 cyan,6 yellow,7 white)
QLRGB = np.array([[255 * ((c >> 1) & 1), 255 * ((c >> 2) & 1), 255 * (c & 1)] for c in range(8)], np.uint8)
BLACK, BLUE, RED, MAGENTA, GREEN, CYAN, YELLOW, WHITE = range(8)
# Mode 4: green bit + red bit only; G+R displays as WHITE.
M4RGB = {0: (0, 0, 0), 2: (255, 0, 0), 4: (0, 255, 0), 6: (255, 255, 255)}

# ---------------------------------------------------------------- CPC
CPC_HW = {0x00: (128, 128, 128), 0x01: (128, 128, 128), 0x02: (0, 255, 128), 0x03: (255, 255, 128),
          0x04: (0, 0, 128), 0x05: (255, 0, 128), 0x06: (0, 128, 128), 0x07: (255, 128, 128),
          0x08: (255, 0, 128), 0x09: (255, 255, 128), 0x0A: (255, 255, 0), 0x0B: (255, 255, 255),
          0x0C: (255, 0, 0), 0x0D: (255, 0, 255), 0x0E: (255, 128, 0), 0x0F: (255, 128, 255),
          0x10: (0, 0, 128), 0x11: (0, 255, 128), 0x12: (0, 255, 0), 0x13: (0, 255, 255),
          0x14: (0, 0, 0), 0x15: (0, 0, 255), 0x16: (0, 128, 0), 0x17: (0, 128, 255),
          0x18: (128, 0, 128), 0x19: (128, 255, 128), 0x1A: (128, 255, 0), 0x1B: (128, 255, 255),
          0x1C: (128, 0, 0), 0x1D: (128, 0, 255), 0x1E: (128, 128, 0), 0x1F: (128, 128, 255)}
# pista0.asm 0x0110: border, then pens 15..0 (routine 0x0182 counts a=0x11 down, pen=a-1)
CPC_PAL_BYTES = [0x14, 0x1B, 0x1F, 0x1C, 0x00, 0x1D, 0x0E, 0x05, 0x0D, 0x15, 0x04, 0x0C, 0x06, 0x03, 0x0B, 0x14, 0x07]


def cpc_palette():
    pens = [None] * 16
    for i, v in enumerate(CPC_PAL_BYTES[1:]):
        pens[15 - i] = CPC_HW[v]
    return np.array(pens, np.uint8), CPC_HW[CPC_PAL_BYTES[0]]


def load_cpc():
    """-> (200x160 pen indices, 16x3 palette)"""
    d = open(CPC_BIN, "rb").read()
    assert len(d) == 16384
    pens = np.zeros((200, 160), np.uint8)
    for y in range(200):
        base = (y // 8) * 80 + (y % 8) * 0x800      # 0xC000 + ... with the dump starting at 0xC000
        for xb in range(80):
            b = d[base + xb]
            pens[y, 2 * xb] = ((b >> 7) & 1) | (((b >> 3) & 1) << 1) | (((b >> 5) & 1) << 2) | (((b >> 1) & 1) << 3)
            pens[y, 2 * xb + 1] = ((b >> 6) & 1) | (((b >> 2) & 1) << 1) | (((b >> 4) & 1) << 2) | ((b & 1) << 3)
    return pens, cpc_palette()[0]


# ---------------------------------------------------------------- DOS
CGA_PAL0_HI = np.array([(0, 0, 0), (85, 255, 85), (255, 85, 85), (255, 255, 85)], np.uint8)
# what the QL can show exactly: black, green, red, yellow
CGA_TO_QL = np.array([BLACK, GREEN, RED, YELLOW], np.uint8)


def load_dos():
    d = open(DOS_PIC, "rb").read()
    assert len(d) == 16384
    idx = np.zeros((200, 320), np.uint8)
    for y in range(200):
        base = (y & 1) * 0x2000 + (y >> 1) * 80
        for xb in range(80):
            b = d[base + xb]
            for k in range(4):
                idx[y, xb * 4 + k] = (b >> (6 - 2 * k)) & 3
    return idx


# ---------------------------------------------------------------- ZX
ZX_RGB = [(0, 0, 0), (0, 0, 205), (205, 0, 0), (205, 0, 205), (0, 205, 0), (0, 205, 205), (205, 205, 0), (205, 205, 205)]
ZX_RGB_BR = [(0, 0, 0), (0, 0, 255), (255, 0, 0), (255, 0, 255), (0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 255, 255)]


def load_zx():
    """-> (192x256 colour 0..7 [same order as QL], 192x256 bright flag, flash cell count)"""
    sys.path.insert(0, ZX_DIR)
    from parse_z80 import parse_z80
    snap = parse_z80(ZX_SNAP)
    scr = snap["pages"][8]        # 128K page 8 = RAM bank 5 = 0x4000
    col = np.zeros((192, 256), np.uint8)
    br = np.zeros((192, 256), np.uint8)
    flash = 0
    for y in range(192):
        a = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
        for cx in range(32):
            b = scr[a + cx]
            at = scr[6144 + (y // 8) * 32 + cx]
            if y % 8 == 0 and at & 0x80:
                flash += 1
            ink, pap = at & 7, (at >> 3) & 7      # FLASH ignored: the un-inverted phase
            for bit in range(8):
                col[y, cx * 8 + bit] = ink if (b >> (7 - bit)) & 1 else pap
                br[y, cx * 8 + bit] = (at >> 6) & 1
    return col, br, flash


# ---------------------------------------------------------------- image ops
def box_resample_x(img, out_w):
    """Area-average horizontal resample of an HxWxC float image."""
    h, w = img.shape[:2]
    out = np.zeros((h, out_w) + img.shape[2:], np.float64)
    scale = w / out_w
    for i in range(out_w):
        a, b = i * scale, (i + 1) * scale
        j = int(a)
        while j < b - 1e-9:
            wgt = min(b, j + 1) - max(a, j)
            out[:, i] += img[:, j] * wgt
            j += 1
        out[:, i] /= scale
    return out


def majority_x(idx, out_w):
    """Best-fit horizontal resample of an index image: each output pixel takes the source
    pixel with the largest coverage (ties -> the left one)."""
    h, w = idx.shape
    scale = w / out_w
    cols = []
    for i in range(out_w):
        a, b = i * scale, (i + 1) * scale
        best, bw, j = None, -1, int(a)
        while j < b - 1e-9:
            wgt = min(b, j + 1) - max(a, j)
            if wgt > bw + 1e-9:
                best, bw = j, wgt
            j += 1
        cols.append(best)
    return idx[:, cols]


BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float64)


def rgb_to_ql(bits_rgb):
    """HxWx3 0/1 -> QL colour code"""
    return (bits_rgb[..., 1] << 2 | bits_rgb[..., 0] << 1 | bits_rgb[..., 2]).astype(np.uint8)


def q_nearest(rgb):
    # palette = cube corners, so Euclidean nearest is a per-channel threshold.  CPC 50% levels
    # (128) round UP (grey->white, dark red->red, dark cyan->cyan).
    return rgb_to_ql((rgb >= 127.5).astype(np.uint8))


def q_bayer(rgb, x0=0, y0=0):
    h, w = rgb.shape[:2]
    thr = (BAYER4[(np.arange(h)[:, None] + y0) % 4, (np.arange(w)[None, :] + x0) % 4] + 0.5) / 16 * 255
    return rgb_to_ql((rgb > thr[..., None]).astype(np.uint8))


def q_floyd(rgb, chans=(0, 1, 2)):
    """Serpentine Floyd-Steinberg; per-channel is exact for a cube-corner palette."""
    e = rgb.astype(np.float64).copy()
    h, w = e.shape[:2]
    bits = np.zeros((h, w, 3), np.uint8)
    for y in range(h):
        xs = range(w) if y % 2 == 0 else range(w - 1, -1, -1)
        dx = 1 if y % 2 == 0 else -1
        for x in xs:
            for c in chans:
                old = e[y, x, c]
                new = 255.0 if old >= 127.5 else 0.0
                bits[y, x, c] = new > 0
                err = old - new
                if 0 <= x + dx < w:
                    e[y, x + dx, c] += err * 7 / 16
                if y + 1 < h:
                    if 0 <= x - dx < w:
                        e[y + 1, x - dx, c] += err * 3 / 16
                    e[y + 1, x, c] += err * 5 / 16
                    if 0 <= x + dx < w:
                        e[y + 1, x + dx, c] += err * 1 / 16
    return rgb_to_ql(bits)


def pen_patterns(pen_idx, table, top):
    """Map each source pen to a (colour_a, colour_b) checkerboard (solid if a == b).
    The checker phase is taken from the final QL screen coordinates."""
    h, w = pen_idx.shape
    yy, xx = np.mgrid[0:h, 0:w]
    chk = ((xx + yy + top) & 1).astype(bool)
    a = np.array([t[0] for t in table], np.uint8)[pen_idx]
    b = np.array([t[1] for t in table], np.uint8)[pen_idx]
    return np.where(chk, b, a)


def run_lengths(idx, axis):
    """Length of the run of equal values each pixel belongs to, along axis (1 = rows)."""
    a = idx if axis == 1 else idx.T
    out = np.zeros(a.shape, np.int32)
    for y in range(a.shape[0]):
        row = a[y]
        x = 0
        while x < len(row):
            e = x
            while e < len(row) and row[e] == row[x]:
                e += 1
            out[y, x:e] = e - x
            x = e
    return out if axis == 1 else out.T


def pen_hybrid(pen_idx, table, solid, top, min_w=3, min_h=2):
    """Checker patterns for areas, but solid colours on thin strokes (runs narrower than
    min_w QL pixels or shorter than min_h lines), so outlines and lettering stay unbroken."""
    pat = pen_patterns(pen_idx, table, top)
    thin = (run_lengths(pen_idx, 1) < min_w) | (run_lengths(pen_idx, 0) < min_h)
    return np.where(thin, np.array(solid, np.uint8)[pen_idx], pat)


def place(pic, top, height=256, width=256, fill=0):
    scr = np.full((height, width), fill, np.uint8)
    h, w = pic.shape
    x0 = (width - w) // 2
    scr[top:top + h, x0:x0 + w] = pic
    return scr


# ---------------------------------------------------------------- QL screen encode / decode
def encode_mode8(scr):
    assert scr.shape == (256, 256)
    out = bytearray(32768)
    for y in range(256):
        for wx in range(64):
            hi = lo = 0
            for n in range(4):
                c = int(scr[y, wx * 4 + n])
                s = 6 - 2 * n
                hi |= ((c >> 2) & 1) << (s + 1)              # G; F (bit s) stays 0
                lo |= ((c >> 1) & 1) << (s + 1) | (c & 1) << s  # R, B
            out[y * 128 + wx * 2] = hi
            out[y * 128 + wx * 2 + 1] = lo
    return bytes(out)


def encode_mode4(scr):
    assert scr.shape == (256, 512)
    out = bytearray(32768)
    for y in range(256):
        for wx in range(64):
            g = r = 0
            for n in range(8):
                c = int(scr[y, wx * 8 + n])
                g |= ((c >> 2) & 1) << (7 - n)
                r |= ((c >> 1) & 1) << (7 - n)
            out[y * 128 + wx * 2] = g
            out[y * 128 + wx * 2 + 1] = r
    return bytes(out)


def decode_mode8_check(data):
    """Independent decoder (word masks, as in ref_ql_mode8_pixel_format): returns 256x256 RGB
    and the number of FLASH bits found."""
    assert len(data) == 32768
    a = np.frombuffer(data, np.uint8).reshape(256, 64, 2).astype(np.uint16)
    word = (a[..., 0] << 8) | a[..., 1]
    rgb = np.zeros((256, 256, 3), np.uint8)
    flash = 0
    for n, mask in enumerate((0xC0C0, 0x3030, 0x0C0C, 0x0303)):
        px = word & mask
        sh = 6 - 2 * n
        g = (px >> (8 + sh + 1)) & 1
        f = (px >> (8 + sh)) & 1
        r = (px >> (sh + 1)) & 1
        b = (px >> sh) & 1
        flash += int(f.sum())
        rgb[:, n::4, 0] = r * 255
        rgb[:, n::4, 1] = g * 255
        rgb[:, n::4, 2] = b * 255
    return rgb, flash


def decode_mode4_check(data):
    a = np.frombuffer(data, np.uint8).reshape(256, 64, 2)
    g = np.unpackbits(a[..., 0], axis=1).reshape(256, 512)
    r = np.unpackbits(a[..., 1], axis=1).reshape(256, 512)
    rgb = np.zeros((256, 512, 3), np.uint8)
    rgb[..., 0] = r * 255
    rgb[..., 1] = g * 255
    rgb[..., 2] = (r & g) * 255          # G+R = white in Mode 4
    return rgb


# ---------------------------------------------------------------- previews
def preview_mode8(scr):
    rgb = QLRGB[scr]                                   # 256x256
    return Image.fromarray(rgb).resize((1024, 512), Image.NEAREST)   # 4x wide, 2x tall


def preview_mode4(scr):
    lut = np.zeros((8, 3), np.uint8)
    for k, v in M4RGB.items():
        lut[k] = v
    return Image.fromarray(lut[scr]).resize((1024, 512), Image.NEAREST)


# ---------------------------------------------------------------- candidates
# Hand-tuned CPC pen -> QL colour(s).  Pens (hw colour): 0 pink 07, 1 black 14, 2 white 0B,
# 3 pastel yellow 03, 4 dark cyan 06, 5 red 0C, 6 dark blue 04, 7 blue 15, 8 magenta 0D,
# 9 purple 05, 10 orange 0E, 11 mauve 1D, 12 grey 00, 13 dark red 1C, 14 pastel blue 1F,
# 15 pastel cyan 1B.
CPC_HAND_DITHER = [
    (RED, WHITE),       # 0 pink         -> 50% red/white (skin, title fill)
    (BLACK, BLACK),     # 1 black
    (WHITE, WHITE),     # 2 white
    (YELLOW, WHITE),    # 3 pastel yellow
    (CYAN, BLACK),      # 4 dark cyan    -> 50% cyan/black (robe)
    (RED, RED),         # 5 red
    (BLUE, BLUE),       # 6 dark blue    -> blue (bright blue is almost unused)
    (BLUE, BLUE),       # 7 blue
    (MAGENTA, MAGENTA), # 8 magenta
    (MAGENTA, RED),     # 9 purple
    (RED, YELLOW),      # 10 orange      -> 50% red/yellow (beard, book)
    (BLUE, MAGENTA),    # 11 mauve
    (BLACK, WHITE),     # 12 grey        -> 50% black/white
    (RED, BLACK),       # 13 dark red    -> 50% red/black (chair/title shading)
    (BLUE, WHITE),      # 14 pastel blue
    (CYAN, WHITE),      # 15 pastel cyan
]
CPC_HAND_SOLID = [
    MAGENTA,  # 0 pink        (skin, title fill: kept distinct from the red chair)
    BLACK,    # 1
    WHITE,    # 2
    YELLOW,   # 3 pastel yellow
    CYAN,     # 4 dark cyan   (robe)
    RED,      # 5
    BLUE,     # 6
    BLUE,     # 7
    MAGENTA,  # 8
    MAGENTA,  # 9
    YELLOW,   # 10 orange     (beard, book)
    MAGENTA,  # 11
    WHITE,    # 12 grey       (robe folds, quill, "soft")
    RED,      # 13 dark red
    CYAN,     # 14 pastel blue
    WHITE,    # 15 pastel cyan (title outline, skull)
]

# solid colour for THIN strokes in A6: the dominant (brighter) colour of each A4 checker
CPC_HAND_THIN = [RED, BLACK, WHITE, YELLOW, CYAN, RED, BLUE, BLUE, MAGENTA, MAGENTA, YELLOW,
                 MAGENTA, WHITE, RED, CYAN, CYAN]


def build_candidates():
    pens, pal = load_cpc()
    cpc_rgb = pal[pens].astype(np.float64)               # 200x160x3
    cpc256 = box_resample_x(cpc_rgb, 256)                 # 200x256 area-averaged
    pens256 = majority_x(pens, 256)                       # best-fit pen per QL pixel
    pens320 = np.repeat(pens, 2, axis=1)                  # 320-wide intermediate
    pens_crop = pens320[:, 32:288]                        # centre 256 (cuts 16 CPC px per side)

    dos = load_dos()
    dos_rgb = CGA_PAL0_HI[dos].astype(np.float64)
    dos256_maj = majority_x(dos, 256)
    # area-average in "QL target" values (exact CGA->QL colours) then dither among the 4 colours
    dos_q_rgb = QLRGB[CGA_TO_QL[dos]].astype(np.float64)
    dos256_avg = box_resample_x(dos_q_rgb, 256)

    zx, zxbr, zxflash = load_zx()

    c = {}
    c["A1"] = ("Mode 8", "CPC scaled 160->256, area-average, nearest QL colour",
               place(q_nearest(cpc256), TOP200))
    c["A2"] = ("Mode 8", "CPC scaled 160->256, area-average, 4x4 Bayer ordered dither",
               place(q_bayer(cpc256, 0, TOP200), TOP200))
    c["A3"] = ("Mode 8", "CPC scaled 160->256, area-average, Floyd-Steinberg error diffusion",
               place(q_floyd(cpc256), TOP200))
    c["A4"] = ("Mode 8", "CPC scaled 160->256 best-fit, hand-tuned pen -> colour/50% checker",
               place(pen_patterns(pens256, CPC_HAND_DITHER, TOP200), TOP200))
    c["A5"] = ("Mode 8", "CPC scaled 160->256 best-fit, hand-tuned pen -> solid colour (no dither)",
               place(np.array(CPC_HAND_SOLID, np.uint8)[pens256], TOP200))
    c["A6"] = ("Mode 8", "CPC best-fit 160->256, hybrid: A4 checkers on areas, solid colours on thin strokes",
               place(pen_hybrid(pens256, CPC_HAND_DITHER, CPC_HAND_THIN, TOP200), TOP200))
    c["B1"] = ("Mode 8", "CPC 2x-wide pixels, centre-cropped to 256 (cuts 16 CPC px each side), hand pen checker",
               place(pen_patterns(pens_crop, CPC_HAND_DITHER, TOP200), TOP200))
    c["C1"] = ("Mode 8", "DOS CGA 320->256 best-fit columns, exact colours (black/green/red/yellow)",
               place(CGA_TO_QL[dos256_maj], TOP200))
    c["C2"] = ("Mode 8", "DOS CGA 320->256 area-average, Bayer dither within the 4 CGA colours",
               place(q_bayer(dos256_avg, 0, TOP200), TOP200))
    c["D1"] = ("Mode 8", "Spectrum SCREEN$ 1:1, ZX colour n -> QL colour n, BRIGHT dropped",
               place(zx, TOP192))
    # Mode 4 comparison: 160 -> 512, blue folded into R and G (Mode 4 has no blue)
    cpc512 = box_resample_x(cpc_rgb, 512)
    m4in = cpc512.copy()
    m4in[..., 0] = np.minimum(255, cpc512[..., 0] + 0.45 * cpc512[..., 2])
    m4in[..., 1] = np.minimum(255, cpc512[..., 1] + 0.45 * cpc512[..., 2])
    m4in[..., 2] = 0
    m4 = q_floyd(m4in, chans=(0, 1)) & 6
    c["M4"] = ("Mode 4", "MODE 4 comparison: CPC scaled 160->512, blue folded in, Floyd-Steinberg (black/red/green/white)",
               place(m4, TOP200, width=512))
    info = {"zx_flash_cells": zxflash, "zx_bright_px": int(zxbr.sum()),
            "cpc_pen_use": np.bincount(pens.ravel(), minlength=16).tolist()}
    return c, (pens, pal), dos, (zx, zxbr), info


def box_resample(img, out_w, out_h):
    """Area-average in both axes (HxWxC float)."""
    x = box_resample_x(img, out_w) if img.shape[1] != out_w else img.astype(np.float64)
    if x.shape[0] != out_h:
        x = box_resample_x(x.transpose(1, 0, 2), out_h).transpose(1, 0, 2)
    return x


def majority(idx, out_w, out_h):
    """Best-fit index resample in both axes: duplicated/dropped rows and columns are spread
    evenly (each output pixel takes the source pixel covering most of it)."""
    x = majority_x(idx, out_w) if idx.shape[1] != out_w else idx
    if x.shape[0] != out_h:
        x = majority_x(x.T, out_h).T
    return np.ascontiguousarray(x)


def build_stretched():
    """The same candidates, stretched to fill the whole 256x256 (Mode 4: 512x256) screen."""
    pens, pal = load_cpc()
    cpc_rgb = pal[pens].astype(np.float64)
    cpc_avg = box_resample(cpc_rgb, 256, 256)                     # A1-A3: area-average both axes
    pens_bf = majority(pens, 256, 256)                            # A4-A6: best-fit rows+columns
    pens_crop = majority(np.repeat(pens, 2, axis=1)[:, 32:288], 256, 256)   # B1: crop, rows best-fit
    dos = load_dos()
    dos_bf = majority(dos, 256, 256)
    dos_avg = box_resample(QLRGB[CGA_TO_QL[dos]].astype(np.float64), 256, 256)
    zx, _, _ = load_zx()
    zx_bf = majority(zx, 256, 256)                                # 192->256: every 3rd row doubled

    c = {}
    c["A1S"] = ("Mode 8", "A1 stretched: CPC 160x200->256x256 area-average, nearest colour", q_nearest(cpc_avg))
    c["A2S"] = ("Mode 8", "A2 stretched: area-average 256x256, 4x4 Bayer", q_bayer(cpc_avg))
    c["A3S"] = ("Mode 8", "A3 stretched: area-average 256x256, Floyd-Steinberg", q_floyd(cpc_avg))
    c["A4S"] = ("Mode 8", "A4 stretched: best-fit rows+columns, hand pen checker",
                pen_patterns(pens_bf, CPC_HAND_DITHER, 0))
    c["A5S"] = ("Mode 8", "A5 stretched: best-fit rows+columns, hand solid colours",
                np.array(CPC_HAND_SOLID, np.uint8)[pens_bf])
    c["A6S"] = ("Mode 8", "A6 stretched: best-fit rows+columns, hybrid checker/thin-solid",
                pen_hybrid(pens_bf, CPC_HAND_DITHER, CPC_HAND_THIN, 0))
    c["B1S"] = ("Mode 8", "B1 stretched: 2x-wide crop to 256, best-fit rows 200->256, hand pen checker",
                pen_patterns(pens_crop, CPC_HAND_DITHER, 0))
    c["C1S"] = ("Mode 8", "C1 stretched: DOS 320x200->256x256 best-fit, exact 4 colours",
                CGA_TO_QL[dos_bf])
    c["C2S"] = ("Mode 8", "C2 stretched: DOS area-average 256x256, Bayer within 4 colours", q_bayer(dos_avg))
    c["D1S"] = ("Mode 8", "D1 stretched: Spectrum 256x192->256x256, best-fit rows (every 3rd doubled)", zx_bf)
    m4src = box_resample(cpc_rgb, 512, 256)
    m4in = m4src.copy()
    m4in[..., 0] = np.minimum(255, m4src[..., 0] + 0.45 * m4src[..., 2])
    m4in[..., 1] = np.minimum(255, m4src[..., 1] + 0.45 * m4src[..., 2])
    m4in[..., 2] = 0
    c["M4S"] = ("Mode 4", "M4 stretched: MODE 4, CPC 160x200->512x256 area-average, Floyd-Steinberg",
                q_floyd(m4in, chans=(0, 1)) & 6)
    for k, (_, _, scr) in c.items():
        assert scr.shape == ((256, 512) if k == "M4S" else (256, 256)), k
    return c


# ---------------------------------------------------------------- source renders
def save_sources(cpc, dos, zx):
    pens, pal = cpc
    Image.fromarray(pal[pens]).resize((640, 400), Image.NEAREST).save(os.path.join(OUT, "src_cpc.png"))
    Image.fromarray(CGA_PAL0_HI[dos]).resize((640, 400), Image.NEAREST).save(os.path.join(OUT, "src_dos.png"))
    col, br = zx
    rgb = np.where(br[..., None] == 1, np.array(ZX_RGB_BR, np.uint8)[col], np.array(ZX_RGB, np.uint8)[col])
    Image.fromarray(rgb.astype(np.uint8)).resize((512, 384), Image.NEAREST).save(os.path.join(OUT, "src_zx.png"))


def font(sz):
    for f in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


SOURCE_TILES = [("src_cpc.png", "SOURCE CPC  mode 0 160x200, 16 pens (pista0 palette)"),
                ("src_dos.png", "SOURCE DOS  CGA 320x200, palette 0 high intensity"),
                ("src_zx.png", "SOURCE ZX  256x192 (2002 English conversion)")]


def contact_sheet(cands, name="loadscreen_sheet.png", tiles=None, cols=3):
    if tiles is None:
        tiles = list(SOURCE_TILES)
        for k, (mode, desc, _) in cands.items():
            tiles.append(("%s_preview.png" % k, "%s  [%s]  %s" % (k, mode, desc)))
    cw, ch, lab = 512, 256, 34
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + 16) + 16, rows * (ch + lab + 16) + 16), (40, 40, 48))
    d = ImageDraw.Draw(sheet)
    f = font(13)
    for i, (fn, label) in enumerate(tiles):
        im = Image.open(os.path.join(OUT, fn))
        sc = min(cw / im.width, ch / im.height)
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.BOX if sc < 1 else Image.NEAREST)
        x = 16 + (i % cols) * (cw + 16)
        y = 16 + (i // cols) * (ch + lab + 16)
        d.rectangle([x - 1, y - 1, x + cw, y + ch], outline=(90, 90, 100))
        sheet.paste(im, (x + (cw - im.width) // 2, y + (ch - im.height) // 2))
        # wrap label into two lines
        words, lines, cur = label.split(), [], ""
        for w in words:
            if d.textlength(cur + " " + w, font=f) > cw and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        for j, ln in enumerate(lines[:2]):
            d.text((x, y + ch + 3 + j * 15), ln, fill=(230, 230, 230), font=f)
    sheet.save(os.path.join(OUT, name))


def write_viewer(cands, name="view_bas", title="Abadia loading-screen candidates"):
    lines = ["100 REMark %s: any key = next" % title,
             '110 dev$="win1_"']
    n = 120
    for k, (mode, desc, _) in cands.items():
        m = 4 if mode == "Mode 4" else 8
        lines.append('%d MODE %d: LBYTES dev$&"%s_scr",131072: k$=INKEY$(-1)' % (n, m, k))
        n += 10
    lines.append("%d MODE 4" % n)
    open(os.path.join(OUT, name), "wb").write(("\n".join(lines) + "\n").encode("ascii"))


def main():
    os.makedirs(OUT, exist_ok=True)
    cands, cpc, dos, zx, info = build_candidates()
    save_sources(cpc, dos, zx)
    write_and_verify(cands)
    contact_sheet(cands)
    write_viewer(cands)
    stretched = build_stretched()
    write_and_verify(stretched)
    contact_sheet(stretched, "loadscreen_sheet_stretch.png")
    pairs = []
    for k, (mode, desc, _) in cands.items():
        pairs.append(("%s_preview.png" % k, "%s  [%s]  centred (original)" % (k, mode)))
        pairs.append(("%sS_preview.png" % k, "%sS  [%s]  %s" % (k, mode, stretched[k + "S"][1])))
    contact_sheet(None, "compare_sheet.png", tiles=pairs, cols=2)
    write_viewer(stretched, "view_stretch_bas", "Abadia loading screens, STRETCHED set")
    print("info:", info)


def write_and_verify(cands):
    for k, (mode, desc, scr) in cands.items():
        if mode == "Mode 4":
            data, prev = encode_mode4(scr), preview_mode4(scr)
        else:
            data, prev = encode_mode8(scr), preview_mode8(scr)
        assert len(data) == 32768
        open(os.path.join(OUT, "%s_scr" % k), "wb").write(data)
        prev.save(os.path.join(OUT, "%s_preview.png" % k))
        # verify: independent decode -> same geometry as the preview -> pixel compare
        back = np.array(Image.open(os.path.join(OUT, "%s_preview.png" % k)).convert("RGB"))
        if mode == "Mode 4":
            rgb = decode_mode4_check(open(os.path.join(OUT, "%s_scr" % k), "rb").read())
            exp = np.repeat(np.repeat(rgb, 2, 0), 2, 1)
            flash = 0
        else:
            rgb, flash = decode_mode8_check(open(os.path.join(OUT, "%s_scr" % k), "rb").read())
            exp = np.repeat(np.repeat(rgb, 2, 0), 4, 1)
        assert flash == 0, "%s: FLASH bits set" % k
        assert exp.shape == back.shape and (exp == back).all(), "%s: decode != preview" % k
        used = sorted(set(map(tuple, rgb.reshape(-1, 3).tolist())))
        print("%-4s %-6s ok  colours=%d  %s" % (k, mode, len(used), desc))


if __name__ == "__main__":
    main()

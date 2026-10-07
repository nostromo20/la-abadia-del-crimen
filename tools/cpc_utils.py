#!/usr/bin/env python3
"""Shared CPC pixel decoding and QL colour encoding utilities.

CPC Mode 1: 4 pixels per byte, 2bpp, bits interleaved.
QL Mode 8: 4 pixels per word, 2 bytes interleaved (green/flash planes).
"""


def decode_mode1_byte(byte):
    """Decode a CPC Mode 1 byte into 4 pixel values (0-3).

    Bit layout: P0h P1h P2h P3h P0l P1l P2l P3l
    """
    p0 = ((byte >> 7) & 1) << 1 | ((byte >> 3) & 1)
    p1 = ((byte >> 6) & 1) << 1 | ((byte >> 2) & 1)
    p2 = ((byte >> 5) & 1) << 1 | ((byte >> 1) & 1)
    p3 = ((byte >> 4) & 1) << 1 | (byte & 1)
    return (p0, p1, p2, p3)


def cpc_screen_offset(x, y):
    """Calculate CPC screen memory offset for pixel coordinates.

    CPC Mode 1: 80 bytes per line, 8 banks interleaved at $800 apart.
    x is in bytes (0-79), y is in pixels (0-199).
    """
    return (y // 8) * 80 + (y % 8) * 0x800 + x


# CPC gate array hardware colour number (0-31) to RGB
# Indexed by 5-bit value written to gate array colour registers.
# Half-bright level approximated as 128 (actual HW ~96).
# Source: MAME/MESS amstrad driver, CPC gate array decode table.
_CPC_HW_RGB = {
    0x00: (128, 128, 128), # White (half-bright grey)
    0x01: (128, 128, 128), # White (duplicate)
    0x02: (0, 255, 128),   # Sea Green
    0x03: (255, 255, 128), # Pastel Yellow
    0x04: (0, 0, 128),     # Blue
    0x05: (255, 0, 128),   # Purple
    0x06: (0, 128, 128),   # Cyan
    0x07: (255, 128, 128), # Pink
    0x08: (255, 0, 128),   # Purple (duplicate)
    0x09: (255, 255, 0),   # Bright Yellow
    0x0A: (0, 255, 255),   # Bright Cyan
    0x0B: (255, 255, 255), # Bright White
    0x0C: (255, 0, 0),     # Bright Red
    0x0D: (255, 0, 255),   # Bright Magenta
    0x0E: (255, 128, 0),   # Orange
    0x0F: (255, 128, 255), # Pastel Magenta
    0x10: (0, 0, 0),       # Black
    0x11: (0, 0, 255),     # Bright Blue
    0x12: (0, 255, 0),     # Bright Green
    0x13: (0, 255, 255),   # Bright Cyan (duplicate)
    0x14: (0, 0, 0),       # Black (duplicate)
    0x15: (0, 0, 255),     # Bright Blue (duplicate)
    0x16: (0, 255, 0),     # Bright Green (duplicate)
    0x17: (0, 255, 128),   # Sea Green (duplicate)
    0x18: (128, 0, 255),   # Mauve
    0x19: (128, 255, 128), # Pastel Green
    0x1A: (128, 255, 0),   # Lime
    0x1B: (128, 255, 255), # Pastel Cyan
    0x1C: (128, 0, 0),     # Red
    0x1D: (128, 0, 255),   # Mauve (duplicate)
    0x1E: (128, 128, 0),   # Yellow
    0x1F: (128, 128, 255), # Pastel Blue
}

# QL's 8 fixed colours with RGB values
QL_COLOURS = {
    "black":   (0, 0, 0),
    "blue":    (0, 0, 255),
    "red":     (255, 0, 0),
    "magenta": (255, 0, 255),
    "green":   (0, 255, 0),
    "cyan":    (0, 255, 255),
    "yellow":  (255, 255, 0),
    "white":   (255, 255, 255),
}

# QL Mode 8 colour word constants
QL_COLOUR_WORDS = {
    "black":   0x0000,
    "blue":    0x0055,
    "red":     0x00AA,
    "magenta": 0x00FF,
    "green":   0xAA00,
    "cyan":    0xAA55,
    "yellow":  0xAAAA,
    "white":   0xAAFF,
}

# Nibble-to-mask LUT (maps 4-bit pattern to QL white word)
NIBBLE_TO_MASK = [
    0x0000, 0x0303, 0x0C0C, 0x0F0F,
    0x3030, 0x3333, 0x3C3C, 0x3F3F,
    0xC0C0, 0xC3C3, 0xCCCC, 0xCFCF,
    0xF0F0, 0xF3F3, 0xFCFC, 0xFFFF,
]

# Default game palette: Table 2 at $3F30 (used by 68% of rooms)
# Raw bytes (reversed): $14 $03 $0E $06 $14
# Ink order 0,1,2,3 -> CPC HW values:
#   ink0=$06 Cyan(0,128,128)       -> background fill (opaque)
#   ink1=$0E Orange(255,128,0)     -> detail lines (transparent for tiles 128-255)
#   ink2=$03 PastelYellow(255,255,128) -> wall fill (transparent for tiles 0-127)
#   ink3=$14 Black(0,0,0)          -> outlines/shadows
DEFAULT_PALETTE_HW = [0x06, 0x0E, 0x03, 0x14]

# QL colour overrides: preserve visual distinction between inks
# CPC ink 0 ($06 Cyan) = opaque background fill → QL cyan
# CPC ink 1 ($0E Orange) = detail lines (transparent for tiles 0-127) → QL red
# CPC ink 2 ($03 Pastel Yellow) = wall fill (transparent for tiles 128-255) → QL yellow
# CPC ink 3 ($14 Black) = outlines/shadows → QL black
DEFAULT_QL_OVERRIDES = {0: "cyan", 1: "red", 2: "yellow", 3: "black"}


def cpc_hw_to_rgb(hw_value):
    """Convert CPC hardware colour number (0-31) to RGB tuple."""
    return _CPC_HW_RGB.get(hw_value & 0x1F, (0, 0, 0))


def rgb_distance_sq(c1, c2):
    """Squared Euclidean distance between two RGB tuples."""
    return sum((a - b) ** 2 for a, b in zip(c1, c2))


def rgb_to_nearest_ql(r, g, b):
    """Map an RGB colour to the nearest QL colour name."""
    best_name = "black"
    best_dist = float("inf")
    for name, ql_rgb in QL_COLOURS.items():
        d = rgb_distance_sq((r, g, b), ql_rgb)
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


def ql_colour_word(name):
    """Return QL Mode 8 colour word for a colour name."""
    return QL_COLOUR_WORDS[name.lower()]


def build_palette_map(hw_values=None, ql_overrides=None):
    """Build CPC ink index (0-3) -> QL colour name mapping.

    hw_values: list of 4 CPC hardware colour values [ink0, ink1, ink2, ink3]
    ql_overrides: dict {ink_index: "ql_colour_name"} to override auto-mapping
    Returns: dict {0: "white", 1: "cyan", 2: "black", 3: "red"} (example)
    """
    use_default = hw_values is None
    if hw_values is None:
        hw_values = DEFAULT_PALETTE_HW
    if ql_overrides is None and use_default:
        ql_overrides = DEFAULT_QL_OVERRIDES
    palette = {}
    for ink, hw in enumerate(hw_values):
        if ql_overrides and ink in ql_overrides:
            palette[ink] = ql_overrides[ink]
        else:
            r, g, b = cpc_hw_to_rgb(hw)
            palette[ink] = rgb_to_nearest_ql(r, g, b)
    return palette


def pixels_to_ql_word(p0, p1, p2, p3, palette_map):
    """Convert 4 CPC pixel values (0-3) to a QL Mode 8 word.

    Each pixel is mapped through palette_map to a QL colour, then the
    4 colour contributions are OR'd together using per-pixel masks.
    """
    word = 0
    for px_idx, px_val in enumerate((p0, p1, p2, p3)):
        colour_name = palette_map[px_val]
        colour_word = QL_COLOUR_WORDS[colour_name]
        # Per-pixel white masks
        masks = [0xC0C0, 0x3030, 0x0C0C, 0x0303]
        word |= colour_word & masks[px_idx]
    return word


def decode_cpc_line(data, y, bytes_start=0, bytes_end=80):
    """Decode one CPC Mode 1 scanline into pixel values (0-3).

    data: full CPC screen data (16KB)
    y: scanline number (0-199)
    bytes_start, bytes_end: byte range to decode (default full 80 bytes)
    Returns: list of pixel values, 4 per byte
    """
    pixels = []
    for bx in range(bytes_start, bytes_end):
        offset = cpc_screen_offset(bx, y)
        if offset < len(data):
            p0, p1, p2, p3 = decode_mode1_byte(data[offset])
            pixels.extend([p0, p1, p2, p3])
        else:
            pixels.extend([0, 0, 0, 0])
    return pixels


def pixels_to_ql_words(pixel_list, palette_map):
    """Convert a list of pixel values to QL Mode 8 words (4 pixels per word)."""
    words = []
    for i in range(0, len(pixel_list), 4):
        p0 = pixel_list[i] if i < len(pixel_list) else 0
        p1 = pixel_list[i + 1] if i + 1 < len(pixel_list) else 0
        p2 = pixel_list[i + 2] if i + 2 < len(pixel_list) else 0
        p3 = pixel_list[i + 3] if i + 3 < len(pixel_list) else 0
        words.append(pixels_to_ql_word(p0, p1, p2, p3, palette_map))
    return words


def parse_palette_arg(palette_str):
    """Parse a palette string like '0x10,0x1C,0x14,0x06' into list of ints."""
    parts = palette_str.split(",")
    if len(parts) != 4:
        raise ValueError(f"Palette must have 4 values, got {len(parts)}")
    return [int(p.strip(), 0) for p in parts]

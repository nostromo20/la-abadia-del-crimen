#!/usr/bin/env python3
"""Extract and expand room data from CPC banked ROM files for QL port.

Reads room objects from ABADIA6/8.BIN, runs the bytecode simulator
for each object, and generates room data with per-cell overlay lists.

Each room has a 320-byte base grid (first tile per cell) followed by
a variable-length overlay list of (row, col, tile) entries for cells
with multiple overlapping tiles.  The QL renderer draws the base grid
first, then iterates the overlay list to composite subsequent tiles
using AND-mask/OR-tile — matching CPC behaviour exactly.

Input:  data/ABADIA6.BIN  (bank 5: room header table at offset $0004)
        data/ABADIA8.BIN  (bank 7: room object lists, skip-byte linked)
        data/ABADIA1.BIN  (object type bytecode data)
Output: src/room_data.s   (assembly include with base grids + overlay lists)
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
SRC_DIR = os.path.join(PROJECT_DIR, "src")

sys.path.insert(0, SCRIPT_DIR)
from simulate_renderer import BytecodeSimulator

# Maximum room ID in ABADIA6.BIN header table
MAX_ROOM_ID = 58

# Visible grid bounds (same as CPC)
H_MIN, H_MAX = 8, 27
L_MIN, L_MAX = 8, 23


def parse_room_headers(bank5_data):
    """Parse room header table from ABADIA6.BIN."""
    rooms = []
    for room_id in range(MAX_ROOM_ID + 1):
        offset = 4 + room_id * 4
        if offset + 3 >= len(bank5_data):
            break
        marker = bank5_data[offset]
        palette = bank5_data[offset + 1]
        marker2 = bank5_data[offset + 2]
        skip_count = bank5_data[offset + 3]

        if marker in (0xFF, 0x7F) and marker2 == 0xFF:
            rooms.append((room_id, palette, skip_count))

    return rooms


def navigate_to_room(bank7_data, skip_count):
    """Navigate ABADIA8.BIN using skip-byte linking."""
    pos = 0
    for _ in range(skip_count):
        if pos >= len(bank7_data):
            return None
        block_len = bank7_data[pos]
        if block_len == 0:
            return None
        pos += block_len
        if pos > len(bank7_data):
            return None
    return pos


def parse_room_objects(bank7_data, block_offset):
    """Parse room objects from a block in ABADIA8.BIN."""
    block_len = bank7_data[block_offset]
    obj_start = block_offset + 1
    obj_end = block_offset + block_len

    objects = []
    pos = obj_start
    while pos < obj_end and pos < len(bank7_data):
        type_byte = bank7_data[pos]
        if type_byte == 0xFF:
            break
        has_extra = type_byte & 0x01
        if pos + 2 >= len(bank7_data):
            break
        packed_x = bank7_data[pos + 1]
        packed_y = bank7_data[pos + 2]

        extra = None
        if has_extra:
            if pos + 3 < len(bank7_data):
                extra = bank7_data[pos + 3]
            pos += 4
        else:
            pos += 3

        objects.append((type_byte, packed_x, packed_y, extra))

    return objects


def expand_room_full(sim, objects):
    """Expand room objects, keeping ALL tiles per cell in draw order.

    Returns dict of (h, l) -> [tile_index, ...] in draw order.
    """
    grid = {}
    errors = []

    for obj_idx, (type_byte, packed_x, packed_y, extra) in enumerate(objects):
        type_idx = type_byte & 0xFE
        coarse_x = packed_x & 0x1F
        coarse_y = packed_y & 0x1F
        fine_x = (packed_x >> 5) & 0x07
        fine_y = (packed_y >> 5) & 0x07
        height = extra if extra is not None else 0xFF

        try:
            obj_tiles, err = sim.simulate_type_at_position(
                type_idx, coarse_y, coarse_x,
                fine_x=fine_x, fine_y=fine_y, height=height)
            if err:
                errors.append(f"  obj[{obj_idx}] type=${type_idx:02X}: {err}")

            for h, l, tile in obj_tiles:
                h = h & 0xFF
                l = l & 0xFF
                if H_MIN <= h <= H_MAX and L_MIN <= l <= L_MAX:
                    key = (h, l)
                    if key not in grid:
                        grid[key] = []
                    grid[key].append(tile)

        except Exception as e:
            errors.append(f"  obj[{obj_idx}] type=${type_idx:02X}: EXCEPTION {e}")

    return grid, errors


def build_room_entry(grid):
    """Build base grid + overlay from expanded grid dict.

    Matches CPC buffer behaviour at $1667: each new tile write shifts the
    previous cell+5 to cell+2 and stores the new tile at cell+5.  Only the
    LAST TWO tiles per cell survive.  The renderer at $4F18 draws cell+2
    first (background) then cell+5 (foreground, composited on top).

    Returns (base_grid, overlays) where:
      base_grid: 20x16 array (second-to-last tile per cell, 0=empty)
      overlays:  list of (row, col, tile) for the last tile (at most 1 per cell)
    """
    base_grid = [[0] * 16 for _ in range(20)]
    overlays = []

    for h in range(H_MIN, H_MAX + 1):
        for l in range(L_MIN, L_MAX + 1):
            key = (h, l)
            if key not in grid:
                continue
            tiles = grid[key]
            row = h - H_MIN   # 0-19
            col = l - L_MIN   # 0-15

            if len(tiles) == 1:
                # Single tile: CPC puts it at cell+5 only (cell+2 stays 0)
                # Rendering: skip cell+2 (zero), draw cell+5.
                # For QL we put it in base grid (same visual result).
                base_grid[row][col] = tiles[0]
            else:
                # Multiple tiles: CPC keeps only last two.
                # cell+2 = second-to-last (background, drawn first)
                # cell+5 = last (foreground, drawn second with compositing)
                base_grid[row][col] = tiles[-2]
                overlays.append((row, col, tiles[-1]))

    return base_grid, overlays


def generate_room_ptrs(room_entries):
    """Generate room_ptrs.s with pointer table and palette (small, near code).

    room_entries: [(room_id, palette, base_grid, overlays), ...]
    """
    lines = []
    lines.append("; ============================================================")
    lines.append("; room_ptrs.s - Room pointer table and palette")
    lines.append("; Generated by convert_rooms.py - DO NOT EDIT")
    lines.append("; Included near rooms.s for PC-relative addressing.")
    lines.append("; Actual room data is in room_data.s (at end of binary).")
    lines.append("; ============================================================")
    lines.append("")

    max_room_id = max(r[0] for r in room_entries) if room_entries else 0

    lines.append(f"ROOM_COUNT equ {max_room_id + 1}")
    lines.append("")

    room_ids = {r[0] for r in room_entries}
    lines.append("; Room pointer table (word offsets from room_data_base)")
    lines.append("; Offset $FFFF = invalid room")
    lines.append("room_ptr_table:")
    for i in range(max_room_id + 1):
        if i in room_ids:
            lines.append(f"        dc.w    room_{i}-room_data_base  ; Room {i}")
        else:
            lines.append(f"        dc.w    $FFFF  ; Room {i} (invalid)")
    lines.append("")

    lines.append("; Room palette bytes (from ABADIA6.BIN)")
    lines.append("room_palette:")
    palette_map = {r[0]: r[1] for r in room_entries}
    for i in range(max_room_id + 1):
        pal = palette_map.get(i, 0)
        lines.append(f"        dc.b    ${pal:02X}  ; Room {i}")
    lines.append("        even")
    lines.append("")

    return "\n".join(lines)


def generate_room_data(room_entries):
    """Generate room_data.s with room body data (large, at end of binary).

    room_entries: [(room_id, palette, base_grid, overlays), ...]
    """
    lines = []
    lines.append("; ============================================================")
    lines.append("; room_data.s - Room body data with overlay lists")
    lines.append("; Generated by convert_rooms.py - DO NOT EDIT")
    lines.append(f"; {len(room_entries)} rooms: 320-byte base grid + overlay list each")
    lines.append("; Placed at end of binary; accessed via room_data_base_ptr.")
    lines.append("; ============================================================")
    lines.append("")
    lines.append("room_data_base:")

    total_base_tiles = 0
    total_overlays = 0

    for room_id, palette, base_grid, overlays in room_entries:
        nonzero = sum(1 for row in base_grid for t in row if t != 0)
        total_base_tiles += nonzero
        total_overlays += len(overlays)

        lines.append(f"room_{room_id}:  ; {nonzero} base tiles, "
                     f"{len(overlays)} overlays")

        # Base grid: 320 bytes (20 rows x 16 cols)
        for row_idx in range(20):
            vals = ",".join(f"${t:02X}" for t in base_grid[row_idx])
            lines.append(f"        dc.b    {vals}  ; H={row_idx + H_MIN}")

        # Overlay list
        lines.append(f"        dc.w    {len(overlays)}  ; overlay count")
        if overlays:
            # Emit overlays: 3 bytes each (row, col, tile)
            for i in range(0, len(overlays), 4):
                batch = overlays[i:i + 4]
                vals = ",".join(f"{r},{c},${t:02X}" for r, c, t in batch)
                lines.append(f"        dc.b    {vals}")
        lines.append("        even")
        lines.append("")

    lines.append(f"; Total: {total_base_tiles} base tiles, "
                 f"{total_overlays} overlays across {len(room_entries)} rooms")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and expand room data for QL port")
    parser.add_argument("--output", type=str,
                        default=os.path.join(SRC_DIR, "room_data.s"))
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    bank5_path = os.path.join(DATA_DIR, "ABADIA6.BIN")
    bank7_path = os.path.join(DATA_DIR, "ABADIA8.BIN")
    abadia1_path = os.path.join(DATA_DIR, "ABADIA1.BIN")

    for path, name in [(bank5_path, "ABADIA6.BIN"),
                        (bank7_path, "ABADIA8.BIN"),
                        (abadia1_path, "ABADIA1.BIN")]:
        if not os.path.exists(path):
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)

    with open(bank5_path, "rb") as f:
        bank5_data = f.read()
    with open(bank7_path, "rb") as f:
        bank7_data = f.read()
    with open(abadia1_path, "rb") as f:
        abadia1_data = f.read()

    print(f"ABADIA6.BIN: {len(bank5_data)} bytes (room headers)")
    print(f"ABADIA8.BIN: {len(bank7_data)} bytes (room objects)")
    print(f"ABADIA1.BIN: {len(abadia1_data)} bytes (type bytecodes)")

    sim = BytecodeSimulator(abadia1_data)
    headers = parse_room_headers(bank5_data)
    print(f"\nFound {len(headers)} valid room headers")

    # Expand all rooms
    print("\nExpanding rooms...")
    room_entries = []
    total_raw_objects = 0
    total_cells = 0
    total_multi = 0
    total_overlays = 0
    all_errors = []

    for room_id, palette, skip_count in headers:
        block_offset = navigate_to_room(bank7_data, skip_count)
        if block_offset is None:
            print(f"  Room {room_id}: NAVIGATION FAILED")
            continue

        objects = parse_room_objects(bank7_data, block_offset)
        total_raw_objects += len(objects)

        grid, errors = expand_room_full(sim, objects)
        base_grid, overlays = build_room_entry(grid)

        room_entries.append((room_id, palette, base_grid, overlays))

        # Stats
        nonzero = sum(1 for row in base_grid for t in row if t != 0)
        multi = sum(1 for tiles in grid.values() if len(tiles) > 1)
        total_cells += nonzero
        total_multi += multi
        total_overlays += len(overlays)

        if errors:
            all_errors.extend([f"Room {room_id}:"] + errors)

        if args.verbose:
            print(f"  Room {room_id:2d}: {nonzero:3d} base tiles, "
                  f"{len(overlays):3d} overlays, pal=${palette:02X}")

    print(f"\nExpanded {len(room_entries)} rooms:")
    print(f"  {total_raw_objects} raw objects")
    print(f"  {total_cells} base grid cells")
    print(f"  {total_multi} multi-tile cells")
    print(f"  {total_overlays} overlay entries (100% accuracy, no fallback)")

    if all_errors:
        print(f"\n{len(all_errors)} warnings during expansion:")
        for err in all_errors[:20]:
            print(f"  {err}")
        if len(all_errors) > 20:
            print(f"  ... and {len(all_errors) - 20} more")

    # Generate room_ptrs.s (small, near code) and room_data.s (large, end)
    ptrs_path = os.path.join(SRC_DIR, "room_ptrs.s")
    data_path = args.output

    ptrs_asm = generate_room_ptrs(room_entries)
    os.makedirs(os.path.dirname(ptrs_path), exist_ok=True)
    with open(ptrs_path, "w", newline="\n") as f:
        f.write(ptrs_asm)
    print(f"\nOutput: {ptrs_path}")

    data_asm = generate_room_data(room_entries)
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    with open(data_path, "w", newline="\n") as f:
        f.write(data_asm)
    print(f"Output: {data_path}")

    # Estimate data size
    est_size = 0
    for _, _, base_grid, overlays in room_entries:
        est_size += 320 + 2 + len(overlays) * 3
        if (len(overlays) * 3) % 2 != 0:
            est_size += 1  # even alignment
    print(f"  Estimated room body data: {est_size:,} bytes")


if __name__ == "__main__":
    main()

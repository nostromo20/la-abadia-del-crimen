# CPC Rendering Pipeline - La Abadia del Crimen

## Overview

The CPC rendering uses a **multi-pass** system with a rectangular grid buffer
as the intermediary. Objects are placed into the grid by a bytecode VM, then
a separate screen pass reads the grid and draws tiles at **rectangular**
grid positions. The isometric visual appearance comes entirely from the
tile artwork — tiles contain diagonal lines at 2:1 slope that create the
illusion of depth when placed on a flat grid.

```
Room objects -> Bytecode VM -> Grid buffer (20x16, 6 bytes/cell)
                                    |
                          Screen rendering pass ($4F18)
                                    |
               pixel_x = col * 16,  pixel_y = row * 8
                                    |
                       CPC screen (320x200 Mode 1)
```

### Key Insight

The isometric projection routine at `$1FB8` computes E,D values that are
stored **per grid cell** for depth ordering (painter's algorithm), but the
actual screen pixel positions are derived from the **grid row/column indices**
directly — not from the stored E,D values. This was verified by disassembly
of the screen renderer at `$4F18` in ABADIA2.BIN.

---

## CPC Data Layout

### Binary Files
| File | CPC Address | Content |
|------|-------------|---------|
| ABADIA1.BIN | $0100-$3FFF | Main code + bytecode interpreter + type table |
| ABADIA2.BIN | $4000-$7FFF | Screen rendering code (bank 4) |
| ABADIA3.BIN | $0300+ | Tile graphics (256 tiles, 32 bytes each) |
| ABADIA6.BIN (bank 5) | $4000+ | Room header table at offset $0004 |
| ABADIA8.BIN (bank 7) | $4000+ | Room object lists (skip-byte linked) |

### Room Header Table (ABADIA6.BIN)
```
Offset $0004: 4 bytes per room entry
  [0] marker ($FF or $7F = valid, $00 = invalid)
  [1] palette index
  [2] marker ($FF)
  [3] skip_count (index into ABADIA8.BIN skip chain)
```

### Room Object Records (ABADIA8.BIN)
```
Navigation: start at offset 0, read skip bytes, advance N times.
Each room's object list follows its skip byte:
  [0] type_byte  ($FF = end of list)
        type_index = type_byte & $FE
        has_extra  = type_byte & $01
  [1] packed_X:  bits 0-4 = coarse_X (grid L), bits 5-7 = fine_X
  [2] packed_Y:  bits 0-4 = coarse_Y (grid H), bits 5-7 = fine_Y
  [3] extra byte (only if has_extra=1): height parameter
```

---

## Isometric Projection ($1FB8)

This routine maps grid coordinates to depth values for the painter's algorithm.
It is called once per object during setup (via the `$EC` bytecode handler).
**It does NOT determine screen pixel positions for tile rendering.**

### Z80 Disassembly (Verified)
```z80
$1FB8:  CP $FF          ; height == $FF?
        RET Z           ; yes -> no projection
        SRL A           ; A = height / 2
        ADD A,H         ; A = height/2 + H
        LD D,A          ; D = height/2 + H
        ADD A,L         ; A = height/2 + H + L
        SUB $0F         ; A = height/2 + H + L - 15
        LD E,A          ; E = H + L + height/2 - 15
        LD A,$10        ; A = 16
        ADD A,D         ; A = 16 + height/2 + H
        SUB L           ; A = 16 + height/2 + H - L
        LD D,A          ; D = H - L + height/2 + 16
        LD ($1FDE),DE   ; store projected coords
```

### Result
```
E = H + L + height/2 - 15     (depth axis: sum direction)
D = H - L + height/2 + 16     (depth axis: difference direction)
```

These E,D values are stored in the grid buffer cell alongside the tile ID.
They are used for **depth sorting** (painter's algorithm ordering) — NOT
for computing screen pixel coordinates. The screen renderer at `$4F18`
uses the grid buffer's row/column position directly.

---

## Grid Buffer ($8D80)

### Address Computation ($1633, Verified)
```z80
; Input: H=row, L=column, C=tile_id
$1633:  LD A,H / SUB 8 / CP 20 / RET NC    ; clip H to 8..27
        LD D,A                               ; D = row (0..19)
        LD A,L / SUB 8 / CP 16 / RET NC    ; clip L to 8..23
        LD E,A                               ; E = col (0..15)
        ; Compute: HL = row * 96 + col * 6
        ; (row*96 = row*64 + row*32, col*6 = col*4 + col*2)
        LD DE,$8D80
        ADD HL,DE
        ; HL = $8D80 + (H-8)*96 + (L-8)*6
```

### Buffer Layout
```
Base:    $8D80
Size:    1920 bytes (20 rows x 16 cols x 6 bytes)
Stride:  96 bytes per row (16 cols x 6 bytes)
End:     $94FF

Cell format (6 bytes):
  [0] depth_min    (painter's algorithm, from E value)
  [1] depth_max    (painter's algorithm, from E value)
  [2] prev_tile    (shifted from [5] on overwrite)
  [3] projected E  (from $1FDE — used for depth, not screen pos)
  [4] projected D  (from $1FDF — used for depth, not screen pos)
  [5] tile_id      (current tile index)
```

### Secondary Floor Buffer ($9500)
```
Base:    $9500 = $8D80 + $0780
Size:    320 bytes (20 x 16 x 1 byte per cell)
Format:  tile_id only (no depth or projection data)
```

The JP instruction at `$165D` is patched at runtime:
- Floor pass: JP `$1660` (write to $9500, 1 byte per cell)
- Object pass: JP `$1667` (write to $8D80, 6 bytes per cell)

---

## Rendering Phases

### Phase 1: Buffer Clear ($1A70)
- LDIR zeros 1920 bytes at $8D80
- Clear CPC screen lines ($C008, $40 bytes/line, $A0 lines)

### Phase 2: Floor Rendering
- JP at $165D patched to $1660 (floor mode)
- Floor objects placed via bytecodes into secondary buffer at $9500
- 1 byte per cell (tile ID only, no depth/projection)
- Floor tiles rendered first (bottom layer)

### Phase 3: Object Rendering
- JP at $165D patched to $1667 (object mode)
- For each room object:
  1. Parse type, position (H,L), fine coords, height
  2. Look up type in pointer table at $156D
  3. Load workspace data (12 bytes at ptr target)
  4. Run isometric projection ($1FB8) to compute E,D for depth
  5. Execute bytecodes: walk grid, place tiles
  6. Each tile stored with tile_id + depth + E,D per cell

### Phase 4: Screen Rendering (ABADIA2.BIN, $4EB2)
Verified from disassembly of ABADIA2.BIN:
- Entry at $4EB2: called from ABADIA1.BIN via JP Z,$4EB2
- Grid scanner at $4F18: walks the 20x16 grid buffer
- For each cell with a tile_id (non-zero byte at offset [5]):
  - **pixel_x = col * 4 bytes** (= col * 16 pixels in CPC Mode 1)
  - **pixel_y = row * 8 pixels** (8 scanlines per tile)
  - Screen address = base + row * 80 + col * 4
    (CPC screen stride = 80 bytes/line, 4 bytes = 16 pixels)
- Grid row stride = 96 bytes; screen row stride = 80 bytes
  (these differ because grid cells are 6 bytes, screen tiles are 4 bytes)

#### Tile Drawing ($4F3D)
```
Tile graphics at $6D00 + tile_id * 32  (256 tiles, 32 bytes each)
Mask tables at $9D00 and $9F00 (AND-masks for transparency)
Compositing: screen = (screen AND mask) OR tile
CPC Mode 1 interleave: alternates $C000 bank (even) and $4000 bank (odd)
  with $0800 stride between line pairs
```

#### Depth-Ordered Scan
The grid scanner at $4F18 starts from row 8, col 7 (approximately
grid centre) and scans outward. This provides depth ordering so that
tiles closer to the camera overdraw tiles further away. However, the
**screen positions are always rectangular** — only the scan order uses
the depth information.

---

## Bytecode Virtual Machine ($201E)

The bytecode VM executes rendering programs stored per object type.
IX = program counter, H/L = grid cursor.

### Bytecode Table
| Opcode | Handler | Description |
|--------|---------|-------------|
| $FF | $2032 | END - terminate, reset mirror state |
| $FE | $2091 | IF ext_6D != 0: begin loop block |
| $FD | $209E | IF ext_6E != 0: begin loop block |
| $FC | $20CF | PUSH HL (save grid position) |
| $FB | $20D3 | POP HL (restore grid position) |
| $FA | $20D7 | LOOP END - decrement counter, loop or continue |
| $F9 | $20E7 | DRAW tile + DEC H (step up) |
| $F8 | $20F5 | DRAW tile + INC/DEC L (self-modified step) |
| $F7 | $2141 | SET variable = expression |
| $F6 | $204F | INC H (step down, no draw) |
| $F5 | $2052 | INC/DEC L (self-modified, step right/left) |
| $F4 | $2055 | DEC H (step up, no draw) |
| $F3 | $2058 | DEC/INC L (self-modified, step left/right) |
| $F2 | $205B | H += expression |
| $F1 | $2066 | L += expression |
| $F0 | $2077 | INC ext_6D |
| $EF | $2071 | INC ext_6E |
| $EE | $2083 | DEC ext_6D |
| $ED | $207D | DEC ext_6E |
| $EC | $21B4 | CALL sub-object (save all state, new workspace) |
| $EB | $20EE | DRAW tile + DEC L (step left) |
| $EA | $21A1 | JUMP to inline address |
| $E9 | $218D | MIRROR mode on (swap L step directions) |
| $E4 | $21B4 | CALL sub-object (variant, same as $EC) |

### Draw Mechanism ($20FC)
Draw bytecodes ($F9, $F8, $EB) use a shared helper:
1. Read step opcode from inline data
2. Self-modify instruction at $211B (DEC H / INC L / DEC L)
3. Read tile ID via parameter reader
4. Call $1633 to store tile in grid buffer
5. Execute self-modified step instruction
6. Check for continuation bytes ($80=repeat with step, $81=draw without step)

### Parameter Reader ($2214)
| Range | Meaning |
|-------|---------|
| $00-$5F | Direct literal (tile ID or value) |
| $61-$6F | Variable from workspace ($1FCF + index) |
| $70-$7F | Variable with optional mirror XOR |
| $80 | Repeat marker |
| $81 | Draw-one-no-step |
| $82 | Extended literal (next byte is value) |
| $84 | Negate accumulator |
| $C8+ | End of expression (opcode territory) |

### Expression Evaluator ($2166)
Accumulates values: reads parameters and adds them together.
$84 negates the accumulator (for subtraction).
Stops when next byte >= $C8 (opcode territory).

---

## Source File Reference (QL Port)

### Assembly Source (`src/`)
| File | Purpose |
|------|---------|
| equates.s | Hardware constants, viewport dimensions, colour words |
| main.s | Entry point, MODE 8 setup, room switching UI, include order |
| screen.s | Screen clear, pixel plot, rectangle fill |
| text.s | Character/string rendering with nibble_to_mask LUT |
| font.s | 8x8 font bitmap data (CPC game font) |
| buffer.s | Offscreen buffer clear (fill with colour) and blit to screen |
| rooms.s | Room loading + rectangular grid rendering (CPC-accurate) |
| room_data.s | Generated 320-byte grids per room (20x16, tile IDs) |
| iso_data.s | M5 test room data + sort buffer workspace |
| iso.s | Rendering engine: render_tile_at, iso_project, sort, test_room |
| tile_data.s | Generated tile graphics + masks (256 tiles, 64 bytes each) |

### Python Tools (`tools/`)
| File | Purpose |
|------|---------|
| simulate_renderer.py | CPC bytecode VM simulator, generates object_types.s |
| convert_rooms.py | Expands rooms via simulator, pre-composites overlapping tiles |
| convert_tiles.py | CPC tile graphics -> QL Mode 8 format with masks |
| preview_iso.py | PNG preview renderer for rooms and M5 test scene |
| cpc_utils.py | CPC Mode 1 pixel decoding, palette mapping |
| disasm_cpc.py | Z80 disassembler for CPC binary analysis |
| diagnose_room.py | Room compositing diagnostics |
| diagnose_black_tiles.py | Tile transparency analysis |

---

## QL Port Implementation

### Rendering Approach (CPC-Accurate)
The QL port uses the same rectangular grid rendering as the CPC:
```
pixel_x = col * 16     (col = L - 8, range 0..15)
pixel_y = row * 8      (row = H - 8, range 0..19)
```

Grid fills viewport exactly:
- 16 cols * 16px = 256px wide = ISO_WIDTH
- 20 rows * 8px = 160px tall = ISO_HEIGHT

No sorting or depth ordering is needed because tiles at 16x8 spacing
on a 16x8 grid do not overlap. The depth-correct appearance is achieved
through the tile artwork itself.

### QL vs CPC Screen Differences
| Property | CPC Mode 1 | QL Mode 8 |
|----------|-----------|-----------|
| Width | 320 pixels | 256 pixels |
| Height | 200 pixels | 256 pixels |
| Tile width | 16px (4 bytes) | 16px (8 bytes/4 words) |
| Tile height | 8px | 8px |
| Colours | 4 from 27 | 8 fixed |
| Screen stride | 80 bytes/line | 128 bytes/line |
| Viewport | 256x160 centred | 256x160 top-justified |

The CPC viewport (256x160 tiles) maps directly to the QL viewport
(also 256x160). No scaling is needed.

### The room build on the QL: the CPC's spiral, on black (2026-10-05)
The CPC builds a lit room in three visible stages (0x19d8): the play area cleared to pen 0
(0x1a70), the tile buffer generated (0x1a0a: nothing new on the screen), then 0x4eb2 draws the
buffer from cell (column 7, row 8) outwards in strips: 4 down, 1 right, 5 up, 2 left, each two
longer every turn, until a strip down would be 20 long (320 cells, each once; 0x4f20 loop, tile 0
skipped, background tile then foreground tile). The fork had replaced the spiral by a row-by-row
loop (same final image).

The QL port again draws in the CPC's order (GeneradorPantallas::dibujaBufferTiles/dibujaTira),
with one change asked for by the author: the transition is black, not pen 0 (cyan by day, blue by
night), because the QL's generation takes ~0.5 s of the ~1 s room step:
- GeneradorPantallas::limpiaPantalla (lit rooms) and Juego::reiniciaPantalla (intro -> game,
  load, new game) clear the play area to QL black (`ql_play_black`, a movem clear; black is
  terrain pen 3 in the day and night palettes, which the host oracle fills);
- each cell is drawn straight to the screen as the spiral reaches it (`ql_play_cell`: the cell
  in pen 0, its background tile composed onto pen 0 without reading the screen, then its
  foreground tile through ql_play_tile's loop): the room grows from the centre on the black.
The finished screen is byte-identical to the old build (pen 0 fill, tiles row by row) for all
116 screens in the day and the night palettes; nothing else changes (the tile buffer, the
mixer, the logic). Dark rooms (pen 3, no tiles) and the day-start spiral (AccionesDia) are as
before. tools/spiraltest.py (in regress): the cell order against the CPC's own 0x4eb2 run on the
Z80, the 116 x 2 screens against the old build (dev header +30 bit 4), black where no cell has
been drawn; `--story` writes build/story/spiral_NN.png and spiral_strip.png (a frame every 40 ms
of modelled 68008 time). Cost: none (tools/roomtime.py, enter's 6 screen changes: 936 ms ->
928 ms a step in the cyclest model; Q-emuLator 77.0 -> 75.6 frames).

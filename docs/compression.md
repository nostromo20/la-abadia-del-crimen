# Fitting La Abadía on one microdrive cartridge

Investigation only (2026-10-04, at 484b247). No game code was changed. The numbers come from
the tools listed at the end and can be re-measured with them.

## Summary

- The embedded CPC data image (`rom_image`, `build/roms.bin`, 147,456 bytes) is mostly not needed.
  - **44,040 bytes are kept** under a conservative rule: everything the game reads, plus the
    full extent of every table it reads by address.
  - The rest can be zeroed in a release build. The layout does not change, so the code does not
    change.
  - LZMA of the data image goes from 53,756 to 26,666 bytes.
- **Verified:** an image with the trimmed data passes every hdiff run against the PC oracle,
  which uses the full data:
  - walk1 900 and 4000, enter 900, saveload 900, night, the mirror harness;
  - the intro, plus the early-skip and page-turn skip cases;
  - roomcmp on all 116 screens, sndtest on every sound and both tunes, and qrtest.
- **The release image** (trimmed data, plus the ~4.4 KB of harness-only code removed) compresses
  to:
  - 74,187 bytes with LZMA;
  - 76,158 with Shrinkler;
  - 84,766 with aPLib;
  - 87,190 with ZX0.
- **Recommendation:** one cartridge, trimmed release image, packed with **aPLib**. That is 188
  of a conservative 200 sectors (6 KB margin, 16 KB on a typical 220-sector cartridge), with
  about **5.2 s** of unpacking on a 68008, no extra RAM, and a 156-byte zlib-licensed 68000
  decoder.
  - ZX0 is faster (3.0 s) but leaves only a 3.5 KB margin at 200 sectors.
  - Shrinkler gives a 14 KB margin but takes 38 s to unpack.

## 1. CPC data usage map

`rom_image` is VIGASOCO's romsPtr: `roms = romsPtr + 0x4000`, which is the CPC address space
plus banks 4 to 7 above 0x10000.

**Dynamic map: `tools/romusage.py`.**
- A unicorn hook covers the whole rom_image range and records each byte's first access as a
  read (the content matters) or a write (the content is generated, so its initial value is
  dead).
- Runs covered:
  - walk1 4000, enter 900, saveload 900, speed_walk 900;
  - the whole intro with its page turns, then SPACE and play (3700 steps);
  - night (FORCE_NIGHT);
  - the mirror harness;
  - arch28 and the mirror staircases with Q+R (mirror opening and the trap);
  - the ending parchment (`Juego::enFinal` set, 3500 steps);
  - every screen 0x00–0x73 drawn;
  - every sound effect and both parchment tunes, each played to 12,000 polls.

**Static part: `tools/romtrim.py`.** Every reader of `roms` was enumerated:
- the C++ readers: GeneradorPantallas/Comandos, Logica, Marcador, MezcladorSprites,
  MotorGrafico, Pergamino, RejillaPantalla, Serializar, Sprite/SpriteMonje, Juego (the flips);
- `ql_sound.c`, `ql_game.cpp`;
- in the asm, only `build_tiles` and `ql_tile_rebuild` (the tile table).

The data-driven readers are each deterministic from fixed data, so the dynamic runs reach
everything they can reach. To be safe, their whole regions are kept, gaps included:
- the screen generator: its bytecode is reached from the screens' block data;
- the sound engine: from the effect table and the two tunes;
- the parchment strokes: from the character table, keeping every table pointer + 256 bytes.

Constant-address tables are kept to their full extent:
- panel numerals, time-of-day names, the font up to char 0x7f;
- all 256 tiles, all character/monk/door graphics;
- the height tables;
- the screens' block data up to screen 0x73;
- the panel graphics;
- both tune windows.

The C++ only ever forms addresses at or above 0x10000 from constants: the flips at 0x16xxx,
the height tables at 0x18a00+, and 0x1c000/0x1e328/0x1eb28. All 16-bit data pointers stay below
0x10000.

| romsPtr range | bank | size | kept | zeroed | class | LZMA saved |
|---|---|---:|---:|---:|---|---:|
| 00000-03fff | abadia0 (CPC title screen) | 16,384 | 0 | 16,384 | PROVABLY UNUSED: nothing addresses rom_image below +0x4000 | 5,135 |
| 04000-040ff | gap (CPC 0x0000-0x00ff) | 256 | 256 | 0 | UNCERTAIN: a zero pointer could reach it; kept | 0 |
| 04100-07fff | abadia1 (Z80 code + tables) | 16,128 | 4,776 | 11,352 | Z80 code: PROVABLY UNUSED (no reader reaches it) | 7,465 |
| 08000-0bfff | abadia2 (Z80 code + tables) | 16,384 | 6,110 | 10,274 | Z80 code: PROVABLY UNUSED | 6,813 |
| 0c000-0ffff | abadia3 (gfx, tiles, font) | 16,384 | 13,920 | 2,464 | PROVABLY UNUSED (past the font, gaps between graphics) | 1,513 |
| 10000-13fff | no bank (one fill value) | 16,384 | 0 | 16,384 | PROVABLY UNUSED (16-bit pointers cannot reach it) | 0 |
| 14000-17fff | abadia5 (CPC bank 4) | 16,384 | 0 | 16,384 | PROVABLY UNUSED: the CPC never pages bank 4, and nothing in the C++ points there | 4,335 |
| 18000-1bfff | abadia6 (CPC bank 5) | 16,384 | 0 | 16,384 | DEAD: the flipped graphics are written there at start-up before any read; the rest is unreferenced | 6,977 |
| 1c000-1ffff | abadia7 (heights) | 16,384 | 2,594 | 13,790 | PROVABLY UNUSED outside the height tables | 2,498 |
| 20000-23fff | abadia8 (screens, panel, ending tune) | 16,384 | 16,384 | 0 | USED | 0 |
| **total** | | **147,456** | **44,040** | **103,416** | | **27,090** |

LZMA (lc3 lp0 pb2) of the whole data image goes from 53,756 to 26,666 bytes. The verification
image is `build/tmp/trim_bin`: the game image with `build/roms_trim.bin` in place of
`rom_image`.

## 2. Release-build trims

| removable | bytes (raw) |
|---|---:|
| the C reference kernels kept for kerntest/the oracle (`c_*`) | 2,740 |
| `abadia_state`, `abadia_tilebuf`, `abadia_show_screen`, `abadia_game_over/ending` | 756 |
| the qltest hooks: autopilot, self-log, test_poll/flush | 500 |
| the heartbeat (`diag_draw`, colours) | 160 |
| the harness entry points, mirror harness, height-cache verifier (`ql_harness_*`, `qlHarnessAbreEspejo`, `hgFill/hgSame`) | 226 |
| **total** | **~4,400** |

That saves about 2.6 KB after LZMA. The BSS-only harness items (the 19 KB height cache, the
self-log buffer, `qlHarnessMirror`'s arrays) cost no file space. The measured release image
`build/codecs/rel_bin` is the trimmed image with these ranges zeroed, which approximates their
removal.

## 3. Codecs: compressed sizes in bytes

| codec (tool, version) | current image 269,848 | trimmed 269,848 | **release** 269,848 | code part only 122,392 | CPC data, trimmed 147,456 | loading screen 32,768 |
|---|---:|---:|---:|---:|---:|---:|
| LZMA1 lc3 lp0 pb2 (Python lzma, preset 9e) | 104,254 | 77,460 | 74,851 | 50,635 | 26,666 | 7,499 |
| LZMA1, best lc/lp/pb | 103,198 (lc0 lp0 pb1) | 76,756 | **74,187** (lc0 lp0 pb1) | 50,168 (lc0 lp1 pb1) | 26,329 | 7,405 |
| upkr -9 (upkr 0.2.3) | 104,976 | 78,534 | **75,864** | 52,607 | 25,758 | 7,552 |
| Shrinkler -d -9 (git 17cff11) | 106,408 | 78,804 | **76,158** | 51,992 | 26,527 | 7,067 |
| aPLib (apultra 1.4.8) | 116,887 | 87,633 | **84,766** | 58,688 | 28,837 | 9,189 |
| ZX0 v2 (salvador 1.4.2) | 127,664 | 90,052 | **87,190** | 58,502 | 28,683 | 9,108 |
| Exomizer 3 raw (git ba91318) | 128,845 | 91,303 | 88,388 | 59,465 | 29,142 | 8,389 |
| LZSA2 (lzsa 1.4.1) | — | — | 90,788 (in 64 KB raw blocks) | — | — | 9,557 |
| LZ4 -12, frame (lz4 1.10.0) | 162,635 | 116,529 | 113,163 | 78,279 | 35,160 | 11,673 |

Notes:
- **Not measured:** ZX7, because its repository is no longer public. nrv2b/ucl was skipped.
- **LZMA lc/lp/pb:** lc0 with pb1 (and lp1 for pure code) suits the 68000's 16-bit code. The gain
  over the default is only about 1%.
- **Hybrid:** the code part and the CPC data part are packed separately, and that is never
  better than the whole image. Shrinkler (data) + ZX0 (code) is 26,527 + 58,502 = 85,029 bytes,
  between aPLib and ZX0 on the whole release image.

## 4. Decoders on a 68008

**How decode times were measured:**
- `tools/codecrun.py` runs each 68000 decoder in unicorn on the real compressed release image
  and loading screen, and checks the output byte-identical (all OK).
- The time is cyclest's 68008 bus model at 7.5 MHz (8-bit bus, 4 clocks a byte, roughly ±30%).
  The game loads into RESPR, above the screen, so there is no display contention.
- The hand-written decoders were assembled with vasm (see `tools/codecs/asmdec.sh`).
- LZMA, upkr, Exomizer and LZSA2 have no 68000 decoder in their repositories, and none was
  found. For those, the authors' own C decoders were compiled with `m68k-linux-gnu-gcc -m68000
  -O2`: LZMA SDK `LzmaDec.c`, upkr `c_unpacker`, Exomizer `rawdecrs/exodecr.c` and LZSA2
  `expand_block_v2.c`. Their times are an upper bound; a hand-written decoder would typically be
  2–3 times faster and much smaller.

| decoder | licence | bytes | release image (s) | loading screen (s) | CPC data alone (s) | code alone (s) | RAM besides the buffers |
|---|---|---:|---:|---:|---:|---:|---|
| ZX0 v2, 68000 (E. Marty) | zlib | 88 | **3.00** | 0.40 | 1.10 | 1.89 | — |
| aPLib, 68000 (E. Marty) | zlib | 156 | **5.21** | 0.70 | 1.85 | 3.49 | — |
| LZ4 frame, smallest (A. Carré) | MIT | 122 | 1.84 | 0.27 | 0.83 | 1.01 | — |
| LZ4 frame, fastest (A. Carré) | MIT | 3,770 | 0.88 | 0.13 | 0.39 | 0.49 | — |
| Shrinkler, 68000 (A. S. Christensen) | free to use, any legal purpose | 190 | **38.2** | 4.75 | 13.2 | 26.5 | 3 KB stack |
| LZMA1, C LzmaDec (I. Pavlov) | public domain (LZMA SDK) | 9,916 | 93.3 | 8.95 | 32.8 | 63.7 | probabilities: 3.7 KB (lc0) to 16 KB (lc3) |
| upkr, C c_unpacker | Unlicense | 736 | 141.6 | 18.0 | 46.5 | 99.5 | 396 bytes |
| Exomizer 3 -b, C exodecr | zlib-style | 1,616 | 22.7 | 2.84 | 9.47 | 14.0 | 158 bytes |
| LZSA2, C expand_block_v2 | zlib | 1,036 | — | 0.54 | — | — | — |

Exomizer is measured with `raw -b` (backwards), which is what its C decoder reads; that is
88,436 bytes for the release image.

**Microdrive load time.** The figures assumed are a tape speed of 28 in/s, about 15 KB/s
(120 kbit/s) while data passes the head, and one loop revolution of about 7.5 s. Source: the
QL microdrive figures quoted in the QL forum / The Register / Wikipedia (links below).
- QDOS loads a file's blocks in the order they pass the head, so a file covering most of the
  tape loads in about one revolution once the directory is found.
- **Estimate:** 8–15 s for the main file (75–90 KB), 2–8 s for the screen file, and up to one
  revolution to find each.
- **About 15–30 s of loading for every one-cartridge option.** The codecs differ only in
  unpack time, from 3 s (ZX0) to 90+ s (C LZMA).

## 5. Cartridge capacity

**QDOS microdrive format:**
- 512-byte data sectors.
- At most 255 sector numbers. File numbers, block numbers and the map entries are bytes, and
  the driver is laid out for no more than 255 sectors.
- Sector 0 holds the map.
- The directory is file 0: a 64-byte header, then 64 bytes per file, so one sector for up to 7
  files.
- Every file's first block starts with its 64-byte header, so a file of n bytes takes
  ⌈(n+64)/512⌉ sectors.
- Q-emuLator MDV images hold up to 255 sectors of 528 bytes (header plus data). Real cartridges
  format to fewer: the spec says "at least 100 KB" (200 sectors), and new tapes give about
  220–225.

**Release layout:**
- BOOT: one sector.
- Loading screen: ZX0, 9,108 bytes + the 88-byte decoder, so 19 sectors.
- Main file: decoder + packed image.

| budget | good sectors | map + dir + BOOT + screen | **main file max** |
|---|---:|---:|---:|
| safe (a 100 KB cartridge, the spec minimum) | 200 | 22 | 178 sectors = **91,072 bytes** |
| typical (a new tape; the author's 110 KB note) | 220 | 22 | 198 sectors = 101,312 bytes |
| optimistic (Q-emuLator's 255) | 255 | 22 | 233 sectors = 119,232 bytes |

## 6. Options

All the one-cartridge options load the packed main file into the game's own BSS area, behind
where the image unpacks to:
- RESPR is 445,748 bytes, the image is 269,848, so 175,900 bytes are free at load time.
- So unpacking needs **no extra RAM** and no in-place overlap.

| option | main file (decoder + packed) | total sectors | fits 200? (margin) | fits 220? | unpack on a 68008 | load + unpack on a real QL | risk |
|---|---:|---:|---|---|---:|---:|---|
| **one cartridge, aPLib + trim** | 84,922 | 188 | **yes (12 sectors = 6,144 B)** | yes (16 KB) | **5.2 s** | ~20–35 s | low: zlib 68000 decoder, measured, byte-checked |
| one cartridge, ZX0 + trim | 87,278 | 193 | yes (7 = 3,584 B) | yes (14 KB) | 3.0 s | ~18–33 s | the margin is thin for future growth |
| one cartridge, Shrinkler + trim | 76,348 | 172 | yes (28 = 14,336 B) | yes (24 KB) | 38 s | ~50–65 s | slow; 3 KB stack |
| one cartridge, LZMA + trim (C decoder) | 84,103 | 187 | yes (13 = 6,656 B) | yes | 93 s (a hand 68000 LZMA decoder: an estimated 30–45 s, ~10 KB smaller: not found, unmeasured) | ~110 s | slowest; a large C decoder |
| one cartridge, hybrid (Shrinkler data + ZX0 code) | 85,307 | 189 | yes (11 = 5,632 B) | yes | 15.1 s | ~30–45 s | two decoders, two streams; no gain over aPLib |
| one cartridge, LZ4 + trim | 113,285 | 244 | no | no | 0.9–1.8 s | — | fits only a 255-sector (emulator) cartridge |
| two cartridges | ZX0 or raw | 2 × ≤255 | yes | yes | 0–3 s | ~40 s + a swap prompt | a cartridge swap; two media to duplicate |
| floppy / hard disk only | raw 269,848 + screen 32,768 | — | n/a | n/a | 0 | seconds | no microdrive release |

Without the trim, nothing fits a 200-sector cartridge. The current image needs 103 KB even
with LZMA.

## Recommendation

**One cartridge: the conservatively trimmed release image, packed with aPLib, the loading
screen packed with ZX0.**
- It fits a spec-minimum 200-sector cartridge with 6 KB to spare (16 KB on a typical one).
- It unpacks in about 5 s on a 68008, with a 156-byte zlib-licensed decoder, no extra RAM, and
  a byte-checked round trip.
- If a future version grows by more than ~6 KB packed, Shrinkler is the fallback: 14 KB more
  room, at ~38 s.

## Tools (committed)

- `tools/romusage.py`: the dynamic usage map → `build/romusage.bin`. It runs 11 game scenarios,
  plus all screens and all sounds; `--only` merges more runs.
- `tools/romtrim.py`: dynamic map ∪ static extents → `build/roms_trim.bin`, with the per-bank
  table.
- `tools/codecsize.py`: compressed sizes; LZMA in Python, the others in WSL.
- `tools/codecrun.py`: the 68000 decoders in unicorn, timed with cyclest's 68008 model, output
  checked.
- `tools/codecs/`:
  - `fetch.sh`, `fetch2.sh`: sources into `~/codecs` in WSL;
  - `buildall.sh`, `build2.sh`, `build3.sh`: build the compressors; upkr needs rustup;
  - `copydec.sh` and `asmdec.sh`: the vasm decoders;
  - `cdec.sh`, with `wrap.c` and `flat.ld`: the C decoders for the 68000;
  - `versions.sh`.

Sources for the microdrive figures:
[QL forum, Microdrive thread](https://qlforum.co.uk/viewtopic.php?t=1269&start=20),
[The Register, the ZX Microdrive story](https://www.theregister.com/Print/2013/03/13/feature_the_sinclair_zx_microdrive_story/),
[ZX Microdrive (Wikipedia)](https://en.wikipedia.org/wiki/ZX_Microdrive),
[MDV image file formats (dilwyn)](https://dilwyn.theqlforum.com/docs/formats/MDV%20image%20file%20formats.pdf),
[Microdrive data line format (QL forum)](https://www.theqlforum.com/viewtopic.php?p=4176).

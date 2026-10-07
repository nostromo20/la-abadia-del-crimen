# Release size budget (2026-10-05, HEAD cc5c944)

The release game file `abadia` = 336-byte stub + the aPLib-packed image. A file takes
ceil((bytes + 64) / 512) sectors. Today:
- packed image: 88,040 bytes (88,037 in the probe: the build id differs);
- file: 173 sectors;
- cartridge: 195 sectors, or 198 with a save and the settings file;
- headroom: about 139 packed bytes before a 174th sector.

So any further speed work needs space first. This document measures where that space could come
from. **Nothing in the game, the dev kit or the release was changed.**

## How it was measured

`tools/sizeprobe.py` makes each variant from a scratch copy of the sources
(`build/sizeprobe/<variant>/tree`). It builds the variant exactly as `build_release.sh` does:
- vasm `-DRELEASE`;
- g++ with `QL_RELEASE -ffunction-sections`;
- `ld --gc-sections`;
- `mkimage`;
- `apultra`.

It then reports the raw and packed sizes. Compression interacts with the rest of the image, so the
packed deltas are real repacks, not sums of raw bytes.

Code that is assembled into qlmain.o, which `--gc-sections` cannot drop, is costed with `cutpack`
instead: the byte range is removed from the built image and the image is repacked. These figures
are estimates within a few bytes.

Run it with:
- `python tools/sizeprobe.py` — every variant and cut;
- `python tools/sizeprobe.py base en_only` — selected variants.

## 1. Languages

**What is compiled in.**
- Only Spanish (0) and English (1): `QL_NUM_IDIOMAS 2`. The fork's eight-language table sits
  under `#if 0` and costs nothing.
- Per language:
  - the panel phrases, `GestorFrases::frases[2][57]`;
  - the start and end parchments, `PergaminoTextos.cpp`;
  - the five save/load messages, `Juego.cpp` `qlMensajes`.
- Shared between the two:
  - the strip texts (help, devices, "PRESS SPACE TO CONTINUE") are English only;
  - the panel's day and time names, the numerals and the font come from the CPC data.
- There are no accent or font tables per language: Ñ and ¿ are CPC font codes.

**How the language is chosen.**
- At build time: `IDIOMA` in `build_release.sh`, default 1 = English, becomes `-DQL_IDIOMA` and
  `Juego::idioma`.
- Nothing selects it at run time. The release is English, yet carries the Spanish texts too.
- Behaviour that depends on the language: Adso's question (Y/N or S/N) and the parchment selection.

**A finding: the Spanish parchments are stored twice.** The trimmed CPC data image (`rom_image`)
still holds the CPC's own Spanish parchment texts:
- at roms 0xB304, kept with bank abadia2's tables;
- at roms 0x22E59, kept with the whole abadia8 bank.

The game draws the parchment from `PergaminoTextos.cpp`, so the C++ copy compresses almost for
free against the ROM copy:
- removing only the C++ Spanish parchments makes the image **larger** by about 120 bytes;
- removing both copies saves about 2.1 KB.

`build/romusage.bin` (the dynamic usage map) records reads of those bytes as follows:
- the abadia8 copy: no reads;
- the abadia2 copy: 97 of its ~1.5 KB read. Those bytes have to be identified before trimming it.

| variant | raw delta | packed delta | abadia sectors | cartridge with a save |
|---|---:|---:|---:|---:|
| today: Spanish + English (b) | 0 | 0 | 173 | 198 |
| (a) English only: Spanish phrases, parchments and messages removed | −7,272 | **−1,395** | 171 | 196 |
| Spanish phrases only removed | −3,276 | **−1,491** | 170 | 195 |
| Spanish C++ parchments only removed | −3,920 | +120 | 173 | 198 |
| (a) plus the ROM copies of the Spanish parchments zeroed (romtrim) | −11,189 | **−3,647** | 166 | 191 |

(b), keeping English and Spanish, is what ships now, so it saves nothing. A Spanish release would
be the mirror image: a separate `IDIOMA=0` build without the English texts.

## 2. The intro → parchment transition

The transition is built from these parts:
- `QL_INTRO_DISSOLVE` in the C++: Pergamino's off-screen page path, and `ql_game.cpp`'s panel-flush
  discard;
- in the asm (screen.s): `ql_off_begin`, `ql_off_pixel`/`off_plot`, `ql_off_fill`,
  `ql_off_dissolve` and `dis_tab`, 442 bytes, always assembled;
- `platform_init`'s mode check, which keeps the loader's Mode 8 screen when the intro follows.

| part | raw | packed |
|---|---:|---:|
| the C++ side (no_dissolve variant: the plain path instead) | −260 | −113 |
| the asm side, cut from the no_dissolve image | −442 | −200 |
| **the dissolve in all** | **−702** | **−313** |
| `platform_init`'s mode check (~10 instructions) | ~−20 | ~−15 (estimate) |
| "PRESS SPACE TO CONTINUE" (`qlsIntro`: a 24-byte string + a call) | ~−50 | ~−35 (estimate) |
| B1, the panel-first ordering in `reiniciaPantalla` | 0 | 0 |

B1 is the same calls in a different order, so it has no measurable size.

The plain path that the dissolve replaced:
- clears the loading screen at start-up;
- draws each parchment page directly on the screen.

So the dissolve costs about 313 packed bytes, about 0.6 of a sector.

## 3. Other candidates

| candidate | raw | packed delta | cartridge with a save | impact | risk |
|---|---:|---:|---:|---|---|
| `QL_TILE_COMPOSE` off (composite tiles, 16 KB of patch and graphics data) | −17,144 | **−8,031** | 183 | **visual**: the holes where the CPC's two-layer tile buffer drops a third graphic come back ("two columns erase the background"); the CPC does the same | low (a define) |
| the AY sound engine (`ql_sound.o`; QSound music only) | −2,856 | −1,658 | 195 | **behaviour**: no music on QSound machines (the effects are on the beeper) | low–medium |
| the parchment's AY music (`qb_music_parchment`) | −1,370 | −498 | 197 | **behaviour**: no music under the intro and ending parchments on QSound | low |
| `abadia_state` (the state block for the release hdiff) | −620 | −424 | 197 | none for players; `tools/relverify.sh` could no longer hdiff the shipped binary itself (the unpacked image would still be checked against the pre-pack build) | low |
| the intro dissolve (section 2) | −702 | −313 | 198 | **visual**: the transition the author asked for | low |
| `QL_HGRID_CACHE` (the height-grid cache's code; its 19 KB are BSS) | −348 | −223 | 198 | **speed**: room fills recomputed | low |
| the zero runs left by romtrim in `rom_image` (103 KB of zeros) | −104,187 | −171 | 198 | none, but every `roms` offset would have to be remapped | high for 171 bytes |
| the 1 KB harness script area in the header (zeros) | −1,024 | +7 | 198 | none | not worth it |
| debug/test leftovers (`test_log/poll/flush`, `diag_draw`, `ql_debug`: `rts` stubs; `ql_phase` ~12 B) | ~−20 | ~−15 | 198 | none | not worth it |
| gated old paths (pre-spiral row-by-row, pre-CHARCOL asm, old page turn, C kernels `c_*`, `c_mem*`) | 0 | 0 | — | already absent from the release (`ifeq`/`ifnd RELEASE`/constant-false, `--gc-sections`) | — |
| fork features never called (menus, map, VGA paths) | 0 | 0 | — | already `#if 0` or dropped by `--gc-sections` | — |
| a different compressor: Shrinkler (docs/compression.md) | — | about −12 KB | about 175 | **load time**: unpacking 3 s → 38 s; 3 KB stack | medium |

Packed deltas do not quite add up across rows, because compression interacts. Combining candidates
needs its own probe run. The figures in this table are each measured against today's base.

## 4. Recommendation (best saving per impact)

1. **An English-only release, with the CPC's Spanish parchment copies trimmed.**
   - Saves 3,647 packed bytes: 191 sectors with a save, 9 free of 200. The game file drops to 166
     sectors, so about 3.8 KB packed can be added before it reaches today's 173.
   - Impact: none for an English release.
   - Steps:
     - drop the Spanish phrases, parchments and messages under a build-time language switch (keep
       `frases[0][0]`, the Latin phrase the parchment shows, or its English twin);
     - teach `tools/romtrim.py` the two ROM text ranges, after identifying the 97 read bytes in the
       abadia2 one.
   - A lower-risk first step: the Spanish phrases alone, −1,491 (195 with a save, 5 free).
2. **`abadia_state` out of the release.** −424, no player impact. Keep relverify on the unpacked
   image (identical to the pre-pack build), and hdiff the RELEASE objects in a harness build.
3. If more is needed, the **parchment music** (−498) is the next least-visible cut.
4. Keep the dissolve (−313), the height cache (−223) and above all `QL_TILE_COMPOSE` (−8 KB, but
   a visible regression) unless a much bigger feature needs room. If the release ever grows by more
   than ~10 KB, the documented fallback is Shrinkler (about 12 KB, but 38 s to unpack).

Steps 1 and 2 together come to about −4.0 KB packed. That is roughly 8 sectors, leaving the
release with a save at about 190 of 200, plenty for the speed work to come.

## Done: the English-only release (step 1, 2026-10-05)

`build_release.sh` with `IDIOMA=1`, the default, now builds the English-only release:
- the C++ gets `QL_SOLO_INGLES`, so the Spanish phrases go (except `frases[0][0]`, the Latin line
  the parchment shows), together with the Spanish parchments and the Spanish save/load messages;
- vasm gets `ENGLISH_ONLY`, which embeds `build/roms_trim_en.bin` (`romtrim.py --english`).

`romtrim.py --english` zeroes the CPC's two Spanish parchment texts:
- roms 0x7300–0x787a;
- roms 0x1ee58–0x1f7c0.

The tool asserts that no byte of either text is in the dynamic read map. The 97 "read" bytes near
the first copy were never part of the text: the text ends at 0x787a with its 0x1a terminator. The
bytes read from 0x788a on are the parchment border graphics (Pergamino::dibujaTriangulo/restaura*),
which are their own extent and stay untouched.

The dev build and the oracle keep both languages, so yntest's Spanish case still runs. The dev
image is byte-identical apart from its build id. `tools/relverify.sh` checks the trimmed English
release against the full-data oracle (reltest; hdiff walk1/enter/saveload/walk1 4000/intro/
intro → game) and everything is identical.

| | packed | abadia | cartridge | with a save + settings |
|---|---:|---:|---:|---:|
| before (cc5c944) | 88,040 | 173 | 195 | 198 (2 free of 200) |
| English-only | **84,356** | **166** | **188** | **191 (9 free of 200)** |

Packed headroom: 228 bytes before a 167th sector, and about 4.8 KB before the cartridge with a
save reaches 200 sectors.

## After the 2026-10-06 work (consistency fixes, room generator, drawing)

| step | commit | packed | abadia | cartridge with a save + settings |
|---|---|---:|---:|---:|
| English-only release | 0006aef | 84,356 | 166 | 191 (9 free) |
| 2a height-cache pre-warm, 2b a_bfs24 inline tests | 27827ea, 0a9c12b | 84,707 | 167 | 192 (8 free) |
| 3 room generator in asm | b3ea656 | 84,993 | 167 | 192 (8 free) |
| 4 drawing (one-pass cells, unrolled blits, register calls) | cd238bb, 2e8f974 | 85,098 | 167 | 192 (8 free) |
| characters 1: interleaved mixing buffer | 5979342 | 85,333 | 168 | 193 (7 free) |
| characters 2: per-sprite kernels | b154e73 | 85,362 | 168 | 193 (7 free) |

Headroom now: 254 packed bytes before a 169th sector; about 3.8 KB before the cartridge with a save
reaches 200 sectors.

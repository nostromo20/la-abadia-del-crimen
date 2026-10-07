# Notices and attribution

This repository combines the QL port's own work with code and data from others. Each part keeps
its own terms.

## The original game

*La Abadía del Crimen* — design and programming **Paco Menéndez**, graphics and cover **Juan
Delcán**, published by **Opera Soft** (1987). Inspired by Umberto Eco's *Il nome della rosa*.
The game, its graphics, maps, text and music are **© Opera Soft**. They are included here for
preservation and non-commercial use only, as in other public ports of the game; this project is
not endorsed by the rights holders.

| path | what | origin |
|---|---|---|
| `data/abadia.dsk` | the Amstrad CPC disk image the build reads (`tools/mkroms.py`) | original game, as shipped in Samuel85/Abbey |
| `data/ABADIA*.BIN`, `data/cpc_memory.bin` | the CPC game's files and a memory dump, used by the conversion and test tools | original game |
| `audio/dos/` | the PC (DOS) version's speaker sounds and tunes, extracted by `tools/dos_sound_extract.py` from its `ABADIA1.OVL` (not included), and their QL beeper versions | derived from the PC version |
| `loadscreen/` | the loading screen in QL Mode 8, converted from the CPC title screen | derived from the CPC version |

## The game logic: VIGASOCO

| path | origin | terms |
|---|---|---|
| `cpp/vigasoco/` | **Manuel Abadía**'s "La Abadía del Crimen" game driver for **VIGASOCO** (VIdeo GAmes SOurce COde, © 2003–2005 the VIGASOCO Project Team), as modernised by **Samuel Salinas** (Samuel85) in *Abbey* (github.com/Samuel85/Abbey), with the QL port's changes | VIGASOCO: free for **non-commercial** use, credit VIGASOCO and the driver author; no commercial use without written permission. See `LICENSES/VIGASOCO-readme.txt` |
| `cpp/port/Juego.cpp`, `cpp/port/cpc6128.cpp` and headers | rewritten from the fork's versions for the QL | as above (derived) |

The changes made to these sources are listed in `cpp/README.txt`; the scripts that made them are
`tools/import_vigasoco.py`, `tools/import_pergamino.py` and `tools/patch_*.py`. QL changes inside
the files are marked `QL:` and the replaced fork code is kept under `#if 0`.

The English texts are **Antonio Giner**'s translation, from the same sources. **Luzbel** wrote the
SDL version that *Abbey* descends from. Manuel Abadía's commented disassembly of the CPC game was
the reference for the timing and the sound engine.

## Third-party code

| path | author | licence |
|---|---|---|
| `src/release/unaplib_68000.s` | **Emmanuel Marty** (aPLib format by **Jørgen Ibsen**) | zlib (notice in the file) |
| `src/release/unzx0_68000.s` | **Emmanuel Marty** (ZX0 format by **Einar Saukas**) | zlib (notice in the file) |

The packers themselves (apultra, salvador; Emmanuel Marty) are fetched and built by
`tools/codecs/`, not included.

## The QL port

Everything else — the 68000 renderer and QL platform layer in `src/`, the rest of `cpp/port/`,
`cpp/host/`, the tools, tests, docs and the colour tool — is **© 2026 Jim McKay**, MIT licence
(`LICENSE`). Developed with the help of Claude (Anthropic) as a coding assistant.

Notes on two files of the port's own:
- `cpp/port/ql_sound.c` runs the CPC game's sound engine, translated from its Z80 code, on the
  QSound AY; the music data it plays is the original game's.
- `cpp/port/ql_rand.c` is a re-implementation of the method of glibc's `random()` (so the QL and the
  PC oracle draw the same numbers as the fork did); it contains no glibc code.

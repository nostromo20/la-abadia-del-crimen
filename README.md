# La Abadía del Crimen — Sinclair QL port (source)

The source of the Sinclair QL conversion of Opera Soft's *La Abadía del Crimen* (1987): the CPC
game's logic (Manuel Abadía's VIGASOCO driver) compiled for the 68008, with a hand-written 68000
renderer and QL platform layer, QSound and beeper sound, saving to any QL drive, and a microdrive
release.

**Playing it?** See [`release/README.md`](release/README.md): requirements, loading, keys.

## Credits

- **Original game:** Paco Menéndez (design, programming), Juan Delcán (graphics), Opera Soft (1987)
- **Reverse engineering and the VIGASOCO driver:** Manuel Abadía; VIGASOCO Project Team
- **SDL version:** Luzbel · **VGA graphics and English translation:** Antonio Giner
- **Abbey (the sources compiled here):** Samuel Salinas (Samuel85)
- **aPLib / ZX0 68000 decompressors:** Emmanuel Marty (formats by Jørgen Ibsen, Einar Saukas)
- **QL port:** Jim McKay

Licences and the origin of every part: [`NOTICE.md`](NOTICE.md). In short: the port's own code is
MIT; the game logic keeps VIGASOCO's non-commercial terms; the game data is © Opera Soft. **The
game may not be sold.**

## Layout

| path | contents |
|---|---|
| `src/` | 68000 assembler: start-up, QDOS layer, renderer, room generator, tile composer, sprite mixer, keyboard, saves, the release loader (`src/release/`) |
| `cpp/vigasoco/` | the game logic (VIGASOCO, via Abbey), with the QL changes |
| `cpp/port/` | the QL glue: platform interface, sound engine and beeper player, text strip, save format |
| `cpp/host/` | the PC "oracle": the same C++ on Linux, for the differential tests |
| `tools/` | build steps, converters, test harnesses, the colour tool, emulator automation |
| `tests/` | key scripts and saves for the tests |
| `docs/` | how things work and why: rendering pipeline, sound, speed against the CPC, sizes, the release |
| `data/`, `loadscreen/`, `audio/` | the original game's data and what was converted from it (© Opera Soft) |

## Building

The build runs on **Windows** with **WSL** (Ubuntu), from Git Bash:

| tool | where | for |
|---|---|---|
| vasm (`vasmm68k_mot.exe`, Motorola syntax) | Windows | the assembler parts |
| `g++-m68k-linux-gnu`, `binutils-m68k-linux-gnu` | WSL (`apt install`) | the C++ game logic for the 68000 |
| `g++` | WSL | the PC oracle (tests) |
| Python 3 with `pillow`; for the tests also `unicorn` and `z80` | Windows | tools, harness |
| apultra, salvador | WSL, `~/codecs` (`bash tools/codecs/get_packers.sh` in WSL) | release packing |

Set `PY` and `VASM` (environment, or `config.sh`), then:

```
bash build_hybrid.sh     # dev image: abadia_h_bin + boot_h_bas (LRUN win1_boot_h_bas)
bash build_release.sh    # release: release/abadia.mdv, abadia.win, mdv/ flp/ win/ folders
```

The dev image and the release are built from the same sources; the release leaves out the test
hooks and packs the game into one cartridge (docs/release.md).

## Testing

```
bash cpp/build_oracle.sh <this repo as a WSL path>   # in WSL: the PC oracle
bash tools/regress.sh                                # the whole suite (~15 min)
```

The suite runs the QL image in a 68000 emulator (unicorn) with a model of QDOS, and compares it
with the PC oracle frame by frame and with the **original CPC code** running on a Z80 emulator:
screens, the room generator, the sprite mixer, the sound engine, saves, timing, keys and more.
`tools/qemu_drive.py`, `tools/qltest.py` and `tools/wintest.py` drive real emulators
(Q-emuLator, QPC2, sQLux) — set their paths as in `tools/qlpaths.py`.

## The colour tool

`tools/colour_mapper.html` shows the game's scenes with the QL's eight colours and dithers and
lets you choose the mapping per scene, separately for the scenery, the characters and the panel.
Open it in a browser (Export JSON), or through `python tools/colour_server.py` to save straight to
`data/colour_mapping.json`; the next build uses it.

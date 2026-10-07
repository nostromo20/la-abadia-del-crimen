# Game data

The original game's files, read by the build and the tools. **© Opera Soft** — included for
preservation and non-commercial use only (see `../NOTICE.md`).

| file | used by |
|---|---|
| `abadia.dsk` | `tools/mkroms.py` builds `build/roms.bin` (VIGASOCO's layout of the CPC data) from it |
| `ABADIA0.BIN` … `ABADIA8.BIN` | the conversion and reference tools (loading screen, room and tile converters) |
| `cpc_memory.bin` | the CPC reference tools |
| `colour_mapping.json` | the port's colour choices (made with `tools/colour_mapper.html`); `tools/mkpalette.py` turns it into `src/palette_data.s` |

The PC (DOS) version's `ABADIA1.OVL` is **not** included: its sounds are already extracted in
`audio/dos/`. To re-extract them, put your own copy at `data/dos/ABADIA1.OVL` (or pass its path to
`tools/dos_sound_extract.py`).

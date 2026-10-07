# The microdrive release

This is the release package recommended in `docs/compression.md`:
- one cartridge;
- the trimmed release image, packed with aPLib;
- the loading screen, packed with ZX0.

The package is built by `build_release.sh`. It is separate from the dev build:
- `build_hybrid.sh`, `abadia_h_bin` and `boot_h_bas` are unchanged;
- the dev image is byte-identical apart from its build id.

## What is on the cartridge

| file | bytes | QDOS type | dataspace | sectors | what it is |
|---|---:|---|---:|---:|---|
| `BOOT` | 86 | 0 (BASIC) | — | 1 | sets `dev$`, `MODE 8`, `EXEC_W` the two jobs, `MODE 4` at the end |
| `abadia_title` | 9,242 | 1 (job) | 512 | 19 | ZX0 decoder (88 B) and the loading screen (A4S, 9,108 B) |
| `abadia` | 85,698 | 1 (job) | 351,728 | 168 | 336-byte stub with the aPLib decoder, and the packed game (85,362 B), English only (IDIOMA=1, docs/size_budget.md) |
| map + directory | | | | 2 | |
| **total** | | | | **190** | free: **10 of 200, 30 of 220, 65 of 255** (188 with the English-only release of 2026-10-05, then +2 for the 2026-10-06 consistency, speed and characters work; before that 195: 188 before the text strip and the save device; 193 before the speed work of docs/speed_vs_cpc.md; still 195 after option 6, whose ~400 packed bytes were offset by leaving the harness-only page-turn paths out of the release, and after the CPC's spiral room build, +252 packed bytes) |
| + a save (`abadia_sav`) and the settings file (`abadia_cfg`) | | | | **193** | free: **7 of 200, 27 of 220, 62 of 255** (the save counted at its 2-sector maximum; a typical ~430-byte save takes 1: 197, 3 free of 200) |

The BOOT program (LF line endings):

```
10 dev$="mdv1_"
20 MODE 8: EXEC_W dev$&"abadia_title": EXEC_W dev$&"abadia"
30 MODE 4
```

The game's job area is 437,426 bytes:
- the file, 85,698 bytes;
- plus the dataspace, 351,728 bytes.

That area holds:
- the stub;
- the unpacked image, 265,296 bytes (255,296 of code and data, plus a 10,000-byte relocation table);
- the BSS, up to 435,544 bytes from the image start;
- 1.5 KB of stack.

A 640 KB QL with TK2 and QSound has 598 KB free after booting (measured in Q-emuLator).

## Why two jobs

The loading screen has to be up while QDOS loads the 85 KB game file. That load takes most of a
tape revolution on a real drive.

**How it works.** A tiny first job unpacks the picture into the screen and removes itself. Then
BOOT starts the game job:
- QDOS loads the game file while the picture stays on screen, because nothing draws during an
  EXEC load;
- the game keeps the loading screen until its intro parchment dissolves it, as the dev loader
  does.

**Why not one file.** A single file could only show the picture after the whole file had loaded.
Loading the game from inside the first job would mean writing a job loader by hand: file
channels, MT.CJOB and an activation. Two EXEC_W calls get the same result with QDOS's own
loader.

## The game job (`src/release/rel_main.s`)

**Job header.**
- `bra.w start` at +0.
- `$4AFB` at +6.
- The name `ABADIA` at +8.
- A **settings block** at +16 (see below).

**What the stub does.** EXEC loads the file at the job's base, with its dataspace above it.
1. **Checks for room.** If the job area does not reach the end of the BSS plus 1 KB of stack, the
   stub calls MT.FRJOB with `out of memory` (-3) before writing anything.
2. **Moves the packed image up.** It goes to the end of where the BSS will be, copied backwards a
   long at a time because the regions overlap. An assembly-time check makes sure it lands past
   the end of the unpacked image.
3. **Unpacks it with aPLib** to just after the stub. The decoder is Emmanuel Marty's
   `unaplib_68000.s`, zlib licence, unchanged.
4. **Checks the result.** The unpacked image must carry the `ABQL` tag; if not, the stub exits
   with `bad parameter` (-15).
5. **Copies the settings into the image header:**
   - +28: sound;
   - +31: flags;
   - +1312: the save file name.
6. **Calls the image** with `JSR`, exactly as SuperBASIC's `CALL` does:
   - the image relocates itself, clears its BSS and runs on its own stack;
   - when ESC quits, it unlinks its poll routine, closes its channel, restores auto-repeat and
     returns.
7. **Removes the job** with MT.FRJOB (D1 = -1, D3 = 0). QDOS frees the whole area and anything
   the job still owns.

The image itself is the normal hybrid image, built with `RELEASE` / `QL_RELEASE`:
- **removed:** the qltest hooks (autopilot, self-log), the heartbeat, the harness entry points and
  sequences (night, mirror, height-cache verification), and the C reference kernels (`c_*`) and
  harness-only exports, which are no longer kept by the linker;
- **CPC data:** `build/roms_trim.bin` (`tools/romtrim.py`) in place of `build/roms.bin`;
- **kept:** `abadia_state`, 598 bytes, which only runs when the harness sets header bit 0. It lets
  the shipped binary itself be checked with hdiff. It costs about 300 bytes packed.

## File headers: microdrive, floppy, hard disk

**On the cartridge.** The QDOS header is in the directory and at the start of each file, as QDOS
writes it. Type 1 and the dataspace are stored there.

**Host folder version (`release/win/`).** The two jobs start with Q-emuLator's 30-byte
`]!QDOS File Header` prefix: the ID, 0, 15 words, then bytes 4–13 of the QDOS header.
- This prefix is documented in Q-emuLator's manual, Appendix II.
- The same ID string appears in QPC2.exe and in sQLux (which also reads `XTcc`).
- Copying the files to a real floppy or microdrive through any of these emulators keeps the type
  and dataspace.
- BOOT is plain text with no header.

**Hard-disk container (`release/abadia.win`).** `tools/mkwin.py` puts the same three files in a
2 MB QXL.WIN container (SMSQ/E's format: `QLWA` header, a word a group map chained over the first
groups, the root directory, 2 KB groups). The jobs' type and dataspace go into the directory
entries; the Q-emuLator prefix is stripped. The layout was checked against containers made by QPC2
and QL-SD, and `tools/wintest.py` boots a copy of it as WIN1_ in QPC2 (BOOT runs, the jobs start).

## Settings without rebuilding

Run `tools/relpatch.py TARGET [--sound detect|off|force] [--save NAME] [--intro on|off]`. Run it
without options to show the current settings.

TARGET can be:
- the `abadia` file, plain or with the header prefix;
- a whole `.mdv` image, whose sectors are rewritten with new checksums and the same layout.

It edits the job's settings block at fixed file offsets:

| file offset | contents | copied to |
|---|---|---|
| +16 | `ABCF` tag | — |
| +20 | sound: 0 detect QSound, 1 off (the beeper), 2 force | image header +28 |
| +21 | flags: bit 1 skips the intro | image header +31 |
| +22 | the start-up save device: word length, then up to 40 characters (its part up to the first `_`, e.g. `mdv2_abadia_sav` → MDV2_; empty = MDV1_) | image header +1312 |

These are the build-time defaults. On a QL without the host tools, the same bytes can be patched
with TK2's `BPUT #ch\position,byte` (the offsets in the table). The save device itself is
normally chosen in the game with F3 and remembered in a small settings file (next section).

The dev build sets the same header field from its loader (`boot_h_bas` line 147,
`win1_abadia_sav` → WIN1_).

## In the game: the text strip, the save device and the settings file

**The strip** is the 28 QL lines under the panel (lines 228–255). It shows up to three lines of
32 characters in the game's own font (the panel/scroll font, with three added glyphs `-` `/` `_`
in its style), in the panel's text colour of the current palette (red by day, white at night),
on black. It is drawn only when its text or the palette changes: the common game step only
tests four bytes.

| when | the strip |
|---|---|
| intro parchment, once the page has dissolved in | `PRESS SPACE TO CONTINUE` in red |
| gameplay | `F5-HELP` for the first ~5 s of play (after the intro, or a new game), then BLANK; F5 toggles the help: `F1-SAVE F2-LOAD F3-DEVICE:MDV1_` / `ARROW L/R-TURN UP-WALK DOWN-ADSO` / `SPACE-DROP ITEM F5-HIDE` (2026-10-05 wording; line 1 is 31 characters with any device) |
| F3 | `SAVE DEVICE: <DEV>` for ~2 s |
| F1 | `SAVING TO <DEV>...` (up BEFORE the drive starts), then `GAME SAVED`, or `<DEV> IS WRITE PROTECTED`, or `INSERT <DEV> SAVE CARTRIDGE` (a microdrive with no cartridge), or `SAVE FAILED: <DEV>` (anything else), ~2.6 s |
| F2 | `LOADING FROM <DEV>...`, then `GAME LOADED`, `NO SAVED GAME ON <DEV>`, `INSERT <DEV> SAVE CARTRIDGE` (a microdrive with no cartridge), or `LOAD FAILED` (corrupt, or an old text save: the game is put back as it was) |
| settings file not written | `<DEV> IS WRITE PROTECTED`, `INSERT <DEV> SAVE CARTRIDGE` (a microdrive with no cartridge) or `SETTING NOT SAVED` |
| end of the investigation, ending parchment | nothing |

**Adso's night question** ("SHALL WE SLEEP, MASTER? Y/N" in English): Y answers yes, N no; the
blinking answer prompt in the phrase area reads `Y:N`. The Spanish game keeps S/N and its phrase.
The `/` is an added glyph in the font's style (the phrase font, Marcador, and the strip).

When a message ends, or the help is hidden, the strip goes back to blank (to the help if it is
up). All the texts fit 32 characters; none had to be shortened.

Write-protected is QDOS error -20 ("read only"); a missing cartridge answers -7 ("not found"),
also to a directory open, which is how a microdrive with no cartridge is told apart. Checked in
Q-emuLator 4.0.3 (its microdrive driver, a read-only image file and an empty slot): -20, -7, -7.

**The save device.** F3 cycles MDV1_ → MDV2_ → FLP1_ → FLP2_ → WIN1_ → WIN2_ → RAM1_ → MDV1_.
The save file is `abadia_sav` on it; F1 overwrites it (no backup).

**The save file** is compact (cpp/port/ql_stream.h, 2026-10-05): `ABQS`, version 1, then every
value of the fork's Serializar as a zigzag base-128 integer, most of them one byte (the
comments, and the numbers inside them such as "// SPRITE 3", are not written). A save is ~430-440
bytes: 1 sector with its 64-byte QDOS header (2 if it ever passes 448 bytes; the old text saves
were ~7 KB, 14 sectors). A
file without that magic and version, such as an old text save, is rejected: LOAD FAILED, and the
game stays as it was. `tools/savefmt.py` converts text saves (tests/arch28_sav.txt is the text
source of tests/arch28_sav).

**The home drive.** At start-up, during the loading screen, the game looks for its own program
file — `abadia` in the release, `abadia_h_bin` in the dev build — on WIN1_, FLP1_, MDV1_, MDV2_,
in that order; the first where it exists is "home".

**The settings file `abadia_cfg`** (16 bytes: `ABDV`, a 32-bit generation counter, the device's
length and name):
- written once, ~2 s after the LAST F3 press, with the counter + 1;
- to MDV2_ when the device chosen is MDV2_, otherwise to the home drive (to the chosen device
  itself if no home was found);
- at start-up it is read from home AND from MDV2_; the one with the higher counter wins.

**The start-up device:** the settings file if there is one; otherwise the header's save-name
field (the dev loaders set `win1_abadia_sav`; empty in the release); otherwise MDV1_. The
selection always holds for the session, even when the settings file cannot be written.

**Failures never stop the game.** Every file call returns an error code; the channel is always
closed. A device that does not exist answers at once. On a real QL an EMPTY microdrive is slow
to answer: the drive runs until QDOS gives up (several seconds), so with no cartridge in MDV2_
the start-up probe for its settings file pauses for that long, and so do F1/F2 on an empty drive.

**The game cartridge with a save.** The release boots from MDV1_, which is also the default save
device and (on a real QL) the home drive, so the save and the settings file go on the game
cartridge: see the budget in "What is on the cartridge".

## Building

```
bash build_release.sh
python tools/reltest.py          # runs the jobs' own code in unicorn; writes build/rel/unpacked_bin
bash tools/relverify.sh          # reltest + hdiff of the unpacked release image vs the PC oracle
```

What it needs:
- **WSL:** `~/codecs/apultra/apultra` and `~/codecs/salvador/salvador` (`tools/codecs/`).
- **build/roms_trim.bin:** when it is missing, `tools/romtrim.py` regenerates it, and that needs
  `build/romusage.bin` (`tools/romusage.py`).
- **Outputs:**
  - `build/rel/`: objects, `abadia_r_bin`/`.sym`, the packed files and the two jobs;
  - `release/abadia.mdv`, `release/abadia.win`, and the host folders `release/win/`,
    `release/mdv/`, `release/flp/` (the same files; BOOT names win1_, mdv1_, flp1_). To make a real
    cartridge or floppy, copy the folder for that drive: BOOT loads from the drive it names.

`tools/mkmdv.py` writes the cartridge: QLay format, 255 × 686-byte sectors, as Q-emuLator mounts
it.
- It allocates sectors as QDOS does: the directory in the highest sector, then every 9th sector
  going down the tape.
- `--selftest` re-creates four existing cartridges byte for byte (Tiny Quest, Prince of Persia,
  Rick Dangerous, The Great Escape).
- `--list` shows any image.

## Verification (2026-10-04)

**The jobs in unicorn (`tools/reltest.py`).**
- The game job unpacks to an image **byte-identical to `build/rel/abadia_r_bin`**, the release
  build before packing.
- Moving and unpacking take **41.3 M cycles = 5.50 s on a 68008** (41.3 M before the save-format change; 40.2 M = 5.35 s before the strip), using cyclest's bus model at
  ±30%. The game area sits above the screen, so there is no display contention.
- With too little memory the job exits with -3 before writing anything.
- The title job puts exactly `loadscreen/A4S_scr` on the screen in **0.40 s**.

**hdiff against the PC oracle with the full CPC data (`tools/relverify.sh`).** The release image
as the job unpacks it was **identical** in every case:

| run | state | screens |
|---|---|---|
| walk1 900 | identical | 90, 0 differ |
| enter 900 | identical | 90, 0 differ |
| saveload 900 | identical | 90, 0 differ |
| walk1 4000 | identical | 40, 0 differ |
| intro 400 | identical | 10, 0 differ |
| intro → game: intro, early skip, page-turn skip | — | 40 each, 0 differ |

**Q-emuLator 4.0.3** (`tools/relshot.py --selfdrive`). The setup was a copy of a
Q-emuLator configuration (JS ROM, TK2, QSound, 640 KB), with slot 1 = `MDV:` plus a copy of the image and the
QDOS microdrive driver.
- No screen grabs or key input were possible in that session (a remote desktop). The test
  cartridge's BOOT drove the run itself:
  - it saved the QL's screen memory with `SBYTES`;
  - it started the game with `EXEC`;
  - it quit the game by putting an ESC in the keyboard queue (IO.QIN, 11 words of code in an
    `ALCHP` block);
  - it logged the free memory to `win2_`, in a NEW empty folder for every run (2026-10-05 fix: an
    old file of the same name made Toolkit II ask "OK to overwrite..Y or N?" over the loading
    screen; a test BOOT is never written where the author boots from).
- **After the title job and the moment the game file had loaded,** the screen was **identical to
  A4S**. So the picture was up through the whole load.
- **30 s into each run,** the intro parchment was running.
- **The game ran twice without a reset.** Free memory was the same after the first and second
  runs: 597,504 → 596,480 → 596,480 on the cartridge, and 594,944 twice from a folder. The first
  run's 1–2.5 KB is SuperBASIC's own growth (new variables, channel tables), not the job: a
  second 437 KB job could not have been created if the first were still there.
- **The folder version booted the same way** as `win1_` and as `flp1_`.
- The emulator's game-file load took 4–5 s. That is not a real-tape figure; `docs/compression.md`
  estimates 8–15 s on a real drive.

**Not verified:** real hardware (a real microdrive or floppy), QPC2 and sQLux. On real hardware
the screen job also writes into screen memory, which is slower there; `reltest` does not model
that.

## Installing and testing in Q-emuLator

1. Click slot 1, choose **Microdrive image**, and pick `release/abadia.mdv`. Use a copy if you do
   not want the image written to; the qcf line is `Slot1=MDV:<path>`.
2. Reset or start the QL and press F1. It boots `mdv1_BOOT`.
3. For saves, put a formatted cartridge image in slot 2 (`mdv2_`), or press F3 in the game to
   pick another device (F5 shows the keys); the choice is remembered in `abadia_cfg`.
4. For a hard-disk-style test, put the `release/win` folder in a slot as `win1_`, or mount
   `release/abadia.win` (a QXL.WIN container) as `win1_`; it boots on its own in QPC2.
5. To run from a floppy or a real cartridge, copy the three files of `release/flp/` or
   `release/mdv/` to it (their BOOT already names `flp1_` / `mdv1_`).

Settings for **Use QDOS driver for MDV images**:
- **on:** loading takes as long as a real tape, roughly;
- **off** (the default, Q-emuLator's own driver): loading is fast.

## Where it sits in memory (measured 2026-10-06)

Measured in Q-emuLator with the author's configuration: 640K, TK2 and the QSound ROM. Test BOOTs read
the QDOS job table and the RESPR area.

- **The release job** (EXEC from the cartridge) occupies 350,064–786,432 ($55770–$C0000), the top
  of RAM. Everything is inside it:
  - the stub, the unpacked code and data;
  - the BSS: the mixing buffer, the tile copies, the height cache, the heap and the game's own stack;
  - the QDOS user stack.
  
  Its lowest byte is 87,920 bytes above $40000, so none of it is in the 128 KB that the display
  contends.
- **The dev kit's RESPR block** occupies 319,904–786,424 ($4E1A0–$BFFF8), 57,760 bytes above $40000.
- **QDOS gives no control over placement.** Jobs and RESPR blocks are allocated from the top down,
  so only other resident extensions or jobs started first could push the game below $40000.
- **What always runs in contended memory:**
  - the screen ($20000–$27FFF);
  - the system variables and tables, and the supervisor stack from $28000: the 50 Hz poll and the
    QDOS traps for the keyboard, the IPC and files.

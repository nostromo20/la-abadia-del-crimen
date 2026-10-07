# DOS PC-speaker sound: analysis and QL beeper conversion

Source: the Spanish DOS release of *La Abadía del Crimen* (Opera Soft, 1988), in
`Documents\La-Abadia-del-Crimen_DOS_ES\la-abadia-del-crimen\`. The files are only read, never
modified, and nothing from them is copied into the port. This document covers data extraction
for interoperability: the sounds' notes and timings, re-expressed as QL IPC BEEP parameters.

**Status: analysis and renders only. No beeper player is in the game yet; the next step waits on
the author's listening test.**

## 1. Summary

The DOS game has **one** PC-speaker engine. It is a small bytecode interpreter driven by a
reprogrammed 300 Hz timer interrupt. It plays **2 looping tunes and 5 effects**, all
monophonic square waves on PIT channel 2:

| name | script | length | what it is | game event (DOS site) | CPC equivalent | confidence |
|---|---|---|---|---|---|---|
| music_parchment | DS:C1A8 | 135 notes, 74.7 s, loops | the CPC **ending** melody, an octave lower, melody only | both parchments: intro (0x1f0c) and ending (0x3436) | CPC END tune (61/61 notes match, one octave apart) | high |
| music_background | DS:C45F | 51 notes, 27.3 s, loops | CPC sound 0x1007's tune, at the same pitch | game start (0x1f97); restarts when the engine is idle, the player has been still for 50 loop passes and no phrase is on the scroll (0x608a) | CPC 0x1007 "inicia un sonido en el canal 1" (CPC 41AB, same routine) | high |
| open_door | DS:C176 | 400 ms | 18→23 Hz rising click train (a creak) | a door opens (0x1257) | CPC 0x101B OPEN (CPC 0DA6) | high |
| steps | DS:C180 | 40 ms | 49 Hz, two cycles (a thud) | Guillermo's footstep (0x2044) | CPC 0x1002 STEPS (CPC 2620) | high |
| get | DS:C18A | 300 ms | 1047→1604 Hz rising sweep | object picked up (0x53e5) | CPC 0x1025 GET (CPC 5090) | high |
| let | DS:C194 | 300 ms | 3964→1712 Hz falling sweep | object dropped (0x53de) | CPC 0x102F LET (CPC 508C) | high |
| speech | DS:C19E | 200 ms | 659 Hz with a slight vibrato | a phrase starts on the scroll (0x53a2); also 20 times when the demo's key buffer runs out (0x2cc5) | CPC 0x1020 "canal 3" voice (CPC 3B73 / 320B) | high |

**Silent on DOS.** These CPC sound calls exist in the DOS code, but each one calls a one-byte
`RET` stub:

| CPC sound | DOS call sites | stub |
|---|---|---|
| CLOSE door (0x1016) | 0x125e | 0x636f |
| BELLS (0x100C) | 0x4ad3, 0x4b2e, 0x4b60 | 0x636d |
| JINGLE / campanas (0x1011) | 0x4b2a, 0x4b5c, 0x4b70 | 0x636e |
| HIT, Severino's knocking (0x102A) | 0x502f | 0x6382 |
| MIRROR (0x0FFD) | 0x2e37 | 0x6360 |

The CPC intro tune (C minor, three voices) has **no DOS counterpart**: both DOS parchments play
the ending melody.

**No 1-bit digitised playback is reachable.** ABADIA1.OVL contains a PWM sample player, but it is
dead code (section 6). The keyboard handler at 0x4cb toggles port 61h bit 7; that is the
keyboard acknowledge, not sound.

## 2. Which files matter

- **ABADIA.EXE** is the loader, with code at file offset 0x200 (IP 0).
  - It shows the title (`abadia.pic`), then loads **`abadia1.ovl`** in 32 KB chunks at segment
    [0x677] (normally 0x1000) (routine 0x2f4 → file 0x4f4).
  - It relocates five segment words (0x37, 0xab, 0x47d, 0x4c4, 0x1ed2) by `seg-0x1000`, then
    does a far return to `seg:0000` (file 0x59e–0x5c3).
  - It hooks INT 13h (file 0x224). Only the read or write of track 0x1D, sector 1, head 0 is
    turned into a 0x5000-byte read or write of `abadia.dat`, which is the save game (file
    0x265–0x2c6).
- **ABADIA1.OVL** is the whole game. It is a raw image whose code segment is the load segment
  and whose data segment is load+0x800. So **data offset X is at file offset 0x8000+X**: the
  constant `mov ax,1800h` at 0x47c is one of the relocated words.
- **ABADIA2.OVL is not part of this game.**
  - It is never loaded. Its name sits only in a table of name pointers at loader 0x6cf, which
    nothing references.
  - ABADIA1 has no INT 21h. Its only real INT 13h calls are save/load (0xd5–0x11e) and the
    copy-protection check (0x6516, 0x6567); the other `CD 13` byte pairs are inline data.
  - Its strings are from another Opera Soft game ("BIENVENIDOS A ITALIA 90 … PARA CARGAR EL
    MUNDIAL PULSE FIRE", plus World Cup team names).
  - Its tone routine at 0xb3a–0xb6c belongs to that game, so it is ignored here.

## 3. The engine (ABADIA1.OVL; addresses are code offsets = file offsets)

### Timer

- 0x43d–0x470 installs the INT 8 handler 0x471 and sets PIT channel 0 to divisor **0x0F8A**, so
  the timer runs at **1193182/3978 = 299.945 Hz** (one tick = 3.3339 ms). 0x4df restores the
  same rate after the sample player.
- The handler calls the sound tick **0x57a on every interrupt** (0x4a0). It calls the game's
  0x281e only every other interrupt.

### Starting and ending a sound

- **0x553 starts a sound unconditionally**, with BX = the script. It:
  - clears the call stack ([0F20]=0F89);
  - resets the envelope to "hold" ([0F22]=0F1A, which holds 0x81; [0F24]=1);
  - sets the flags to active ([0F1B]=1);
  - turns the speaker gate on (`61h |= 3`) and sets PIT channel 2 to mode 3 (`43h ← B6h`).
- **0x543 starts a sound only if the engine is idle** (and [0F2D]=0, which is never set).
- **0x5fc stops**: gate off, flags=0.

### Engine state (data segment)

| address | meaning |
|---|---|
| F1B | flags: b0 active, b1 note sounding, b6 rest, b7 keep fetching |
| F1C | script pointer |
| F1E | ticks left in the current note |
| F20 | call-stack pointer |
| F22 | envelope table start |
| F25 | envelope table position |
| F24 | envelope period |
| F27 | envelope period counter |
| F28 | current divisor |

### Tick (0x57a)

- If no note is sounding, fetch and run opcodes until one stops the fetching.
- Otherwise, count the note down. When it reaches 0, fetch the next opcode **in the same tick**,
  so notes are gapless and legato.
- Otherwise, unless resting, count the envelope period down. When it reaches 0:
  - reload the period;
  - read the next envelope byte: 0x81 holds without advancing, 0x80 goes back to the table start;
  - sign-extend the byte, add it to the divisor, and write the result to port 42h.

### Opcodes

The jump table is at DS:0F0C (file 0x8F0C): `5FC 67F 6B7 628 608 66C 646`.

| op | bytes | handler | effect |
|---|---|---|---|
| 00 | `00` | 0x5fc | END: speaker gate off, engine idle |
| 02 | `02 dL dH nL nH` | 0x67f | NOTE: divisor d to port 42h, lasting n ticks; envelope restarts. The gate is **not** re-enabled |
| 04 | `04 nL nH` | 0x6b7 | REST n ticks: gate off. No script uses it |
| 06 | `06 aL aH` | 0x628 | CALL a. Unused |
| 08 | `08` | 0x608 | RET (END when the stack is empty). Unused |
| 0A | `0A aL aH` | 0x66c | JUMP a. Both tunes end with a JUMP to their own start, so they loop forever |
| 0C | `0C r aL aH` | 0x646 | ENVELOPE: every r ticks, add the next signed byte of table a to the divisor |

Frequency = 1193182 / divisor; a divisor of 0 means 65536.

### Scripts and envelope tables

| data offset | contents |
|---|---|
| C175 | `00`: bare END. 0x63a3 starts it with 0x543 to silence the speaker when the engine is idle |
| C176 | `0C 01 C45D` `02 0000 0078` `00`: divisor 65536, 120 ticks, divisor −114 every tick |
| C180 | `0C 02 C45B` `02 5F1E 000C` `00`: 49 Hz, 12 ticks, no envelope |
| C18A | `0C 02 C459` `02 0474 005A` `00`: 1046.6 Hz, 90 ticks, divisor −9 every 2 ticks |
| C194 | `0C 02 C457` `02 012D 005A` `00`: 3964 Hz, 90 ticks, divisor +9 every 2 ticks |
| C19E | `0C 04 C452` `02 0712 003C` `00`: 659 Hz, 60 ticks, vibrato every 4 ticks |
| C1A8 | `0C 08 C452`, then 135 `NOTE` ops (lengths 160/480/640), then `0A C1A8`. Parchment tune |
| C45F | `0C 08 C452`, then 51 `NOTE` ops (lengths 32–512), then `0A C45F`. Background tune |
| C452 | envelope `+9 −9 −9 +9 80h`: a ±9-divisor vibrato with a 4-step period (32 ticks ≈ 9.4 Hz in the tunes, 16 ticks in speech) |
| C457 | `+9 80h`: falling pitch |
| C459 | `−9 80h`: rising pitch |
| C45B | `81h`: hold |
| C45D | `−114 80h`: rising pitch |

The **sound-call stubs** are at 0x6360–0x63a6. They take the place of the CPC's sound jump
table (0x0FFD…0x102F):

| stub | does |
|---|---|
| 6361 | C180 |
| 6367 | C45F, only if idle |
| 6370 | C176 |
| 6376 | C19E |
| 637c | C18A |
| 6383 | C194 |
| 63a3 | C175, only if idle |
| 6360, 636d, 636e, 636f, 6382, 63a2 | `RET` |

## 4. How each sound was mapped to its event

The DOS code is a close transliteration of the CPC Z80 code, so each DOS call site lines up with
a CPC call in `Spannish_abadia_source/abadia.asm`. The CPC calls give the meaning:

- **Door, 0x124f.** DOS: `test [di+1],40h` / `je` / `call 6370` / `jne` / `call 636f`. CPC 0DA6:
  `call nz,101B` (open), `call z,1016` (close). So opening = C176, and closing is silent.
- **Steps, 0x2042.** DOS: `[BAF4]&1` / `call 6361`. This is the CPC 2620 `call nz,1002` (STEPS)
  in the same main-loop routine.
- **Get and drop, 0x53d5.** DOS: `and al,cl` / `jne +` / `call 6383` / `je +` / `call 637c`. CPC
  5088: `and c` / `call z,102F` (LET) / `call nz,1025` (GET). So LET = C194 and GET = C18A.
- **Phrase blip, 0x5370.** This is the phrase-start routine, CPC 502E: it sets [B85E]/[B85F]/[B85D]
  = CPC 2DA1/2DA2/2DA0 and skips to the phrase. It then calls C19E.
  - The CPC instead blips per character (3B73), at a per-phrase pitch taken from its table 5659.
  - DOS still stores that per-phrase byte at DS:C16D (0x537a), but nothing reads it, so the DOS
    blip is a fixed 659 Hz, once per phrase.
- **End of the demo, 0x2cb9.** DOS loops 20 times over `call 6376` + delay 0x7d0. This is CPC
  31FF–3215: 20 times `call 1020` + `call 490E`.
- **Background tune, 0x6060.** This is CPC 4186–41AB: the camera or idle counter. While the
  cursor keys are not pressed, [C004] (CPC 3C93) counts up to 50. After that, each pass calls
  CPC 1007, and DOS calls 6367 when [B85E]=0 (no phrase).
  - On DOS, the background tune therefore plays while the player stands still.
  - Any effect cuts it, because effects use 0x553.
  - It restarts **from the top** once the engine falls idle.
  - At game start, 0x1f97 starts it unconditionally.
- **Bells, jingle, hit, mirror.** The CPC sites at 5F48–5FC7 (bells and jingle in the
  canonical-hours routines), 635A (hit) and 335E–3361 (mirror) are matched at DOS
  0x4ad3–0x4b70, 0x502f and 0x2e37. All of them call `RET` stubs.
- **Parchments.** 0x6d7 clears the screen, starts C1A8 with 0x553 and prints the text in SI. It
  is called at 0x1f0c with SI=C966 ("Ya al final de mi vida de pecador…", the intro) and at 0x3436
  with SI=CF67 ("Desfigurado por la angustia…", the ending).
- **Melodies.** These were compared with the CPC AY streams (`build/snd/host_ay.txt`, the CPC
  engine oracle), after collapsing repeated pitches. Those streams hold AY periods already
  scaled x1.5 for the QSound clock (`ql_sound.c` QL_AY_NUM/DEN), so the real CPC frequency is
  1.5 MHz/(16·period):
  - DOS C1A8 matches the CPC ending tune's channel A on **all 61** CPC notes in its 30 s window,
    exactly one octave apart (the CPC is an octave higher).
  - It matches only 9/60 against the CPC intro tune.
  - DOS C45F matches the CPC 0x1007 tune (channel C) on all 9 notes in the stock 3 s window, at
    the same pitch. A 30 s CPC render (below) carries on as the same theme.

## 5. Verification of the extraction

`tools/dos_sound_extract.py` checks the engine in two independent ways, and they must agree:

1. **Static decoder.** A Python model of 0x553/0x57a, built from the disassembly above, runs every
   script tick by tick.
2. **Emulation.** Unicorn 2.1.4 runs the **real x86 code**:
   - the overlay is loaded at 1000:0000 with DS=1800;
   - 0x553 is called with BX = the script, then 0x57a is called once per tick;
   - IN and OUT are hooked, so writes to 42h, 43h and 61h are logged.

   The emulated PIT channel 2 latch and port 61h give the speaker's (gate, divisor) at the end of
   each tick.

The two per-tick traces are **identical for all 7 sounds**. The script asserts this, plus
signature checks on the timer divisor and the opcode table.

For a looping tune, one pass ends at the tick where the JUMP back to its own start runs.

## 6. The digitised player: present, but dead

0x6433 is an INT 8 handler that plays 8-bit samples by PWM:

- It sets PIT channel 2 to one-shot mode (43h ← B2h, then 90h). Each interrupt writes a byte
  through the `xlat` table DS:E577 to port 42h.
- It sets PIT channel 0 to divisor [E568]=0x4A, which is 16.1 kHz. Each sample is played twice,
  so the sample rate is about 8 kHz.
- The sample data are far pointers to absolute segments:
  - 2E44:0000, 0x1B18 paragraphs = 111 KB, via 0x6401;
  - 2D00:0000, 0x144 paragraphs = 5 KB, via 0x63d3.

  Neither is in any shipped file.

It is unreachable in this release:

- The setup routine is 0x6465, but every caller calls **0x6464, which is a bare `RET`**.
- The 0x6401 wait loop is patched to `RET`.
- Its only entry, 0x63a9, is reached from 0x5ab3 behind `mov al,0 / cmp al,6 / jne`, which never
  falls through.
- The 0x63d3 path is the copy-protection punishment: play the short sample 10 times at a rising
  rate, then `jmp FFFF:0`. Its check (0x6501–0x657a: CRC-error sectors on track 0x28) is NOPped
  out.

Even if it were live, the QL beeper cannot do PCM. That would need a different approach, such as
the 68008 bit-banging the speaker, which IPC BEEP cannot do.

## 7. Event-list format (`audio/dos/<name>.json`)

Each file has:

- `notes`: the score level, one entry per NOTE opcode, with `t_ms`, `dur_ms`, `tick`, `ticks`,
  `divisor`, `hz`, and `envelope{every_ticks, table, divisor_deltas}`;
- `segments`: the exact speaker output, one row per run of ticks with a constant (gate,
  divisor). The columns are given by `segment_fields`: `t_ms dur_ms tick ticks on divisor hz`.
  The envelope's vibrato and sweeps appear here;
- the trigger, the event, the CPC equivalent and the confidence, plus the tick rate and pass
  length.

`index.json` lists all of them, plus the silent-on-DOS sounds.

The DOS renders `build/snd/dos/<name>_dos.wav` are phase-continuous square waves at 44.1 kHz,
made from the segments. One pass of each tune is rendered.

## 8. QL IPC BEEP conversion (`tools/dos_sound_ql.py`)

### The beeper model

This is the model from the author's earlier QL sound work, matching sQLux's emulation of the
QL's sound:

- the tick is 22917 Hz;
- the half-cycle is `((p+255)%256)+10.6` ticks, so **f(p) = 22917/(2(p+9.6))**:
  - the ceiling is p=1, about **1081 Hz**;
  - the floor is p=255, about **43.3 Hz**;
  - p=0 is never emitted;
- interval and duration are 15-bit **little-endian**;
- the step is a signed nibble; positive = higher pitch number = lower frequency;
- wrap 0 = sweep once, then hold.

The Python synth is a direct port of synthQL. It renders `_ql_beep.wav` with each BEEP starting
at its onset and cut by the next one, because a new IPC sound replaces the current one.

### Tunes

- **One BEEP per note.** Each note is issued on the first 50 Hz frame at or after its DOS onset,
  using the q68 cumulative pacing, so there is no drift. The onset error is ≤ 19.9 ms.
- **No gaps.** Each BEEP lasts its note plus one frame, so the next BEEP cuts it. This keeps the
  DOS legato.
- **Long notes are re-issued** after 1.42 s, because the duration limit is 32767 ticks = 1.43 s:
  - parchment: the 1.6 s E5 and the 2.13 s final C5;
  - background: the two 1.71 s D6.
- **Whole-tune octave transposition, never per-note folds**, so the melodic contour survives.
  The **recommended** shift is the highest octave that meets all of these:
  - every note is in range;
  - no two different DOS pitches land on the same QL pitch;
  - the worst error is ≤ 35 cents.

  The `_alt` render is the neighbouring octave.
- **The DOS vibrato (±9 divisor, about ±5–15 cents) is dropped.** Near the ceiling the beeper's
  pitch step is 40–100 cents, so it cannot express it.

| tune | notes above 1081 Hz at DOS pitch | recommended | alt |
|---|---|---|---|
| music_parchment | 2 (notes 116 and 119, both D6 1174 Hz, at 62.9 s and 64.5 s) | **−1 octave**: QL pitches 10–56, RMS error 15 cents, worst 29.5 cents, no collisions | −2 octaves: RMS 7, worst 19 |
| music_background | 25 of 51 (notes 22–50, the whole second half, 1174–2093 Hz, from 10.2 s) | **−2 octaves**: pitches 12–56, RMS 14 cents, worst 27 cents | −1 octave: RMS 25, worst 56 cents, and A6/A#6 **collide** on p=3 |

**Tempo check (`tools/beepspeed.py`, 2026-10-07).**
- The table against the DOS notes: no onset early, the latest 19.8 ms late (one frame), every
  duration within 13.4 ms of the note + one frame, the loop 3734 frames = 74680.0 ms against the
  DOS pass of 74680.3 ms. The DOS engine tick is the INT 8 rate the game sets, 299.945 Hz.
- The game, in the harness without QSound: every BEEP at its table frame or one frame later,
  over 2.4 passes. The one-frame delay is the player's: it is stepped from the main loop.
- **Fixed then:** the tune's clock started at the music request, but the parchment's first step
  (the page composed off-screen and dissolved in) runs ~2.7 s without the main loop. Notes 2–4
  were lost and note 5 came in 0.5 s late. The clock now starts when the page is up
  (`ql_music_ready`, Pergamino.cpp), for both parchments. QSound's tune runs in the poll and is
  not affected.

**IPC rate.** The shortest note is 32 ticks = 107 ms (background). The closest BEEP onsets are
100 ms apart (background) and 180 ms (parchment). **No passage needs more than one BEEP per 20 ms
frame.** Every effect is a single BEEP.

### Effects

Each effect is one BEEP; the parameters are p1, p2, interval, duration, step, wrap, random, fuzz.

A DOS sweep is linear in divisor, which means linear in period. The QL pitch number is also linear
in period, so a DOS sweep becomes an exact p1→p2 ramp, with the interval taken from the DOS
slope. A sound outside 43–1081 Hz is shifted by the fewest octaves that bring it in range.

| sound | BEEP params | IPC bytes | notes |
|---|---|---|---|
| open_door | 148, 115, 279, 9169, −1, 0, 0, 0 | `94 73 17 01 D1 23 F0 00` | **+2 octaves**: the 18–23 Hz click train becomes a 73–92 Hz buzz ramp. The beeper's floor is 43 Hz, so the slow ratchet character is lost. This is the weakest conversion |
| steps | 224, 0, 0, 917, 0, 0, 0, 0 | `E0 00 00 00 95 03 00 00` | exact: 49.0 Hz, 40 ms |
| get | 12, 5, 884, 6876, −1, 0, 0, 0 | `0C 05 74 03 DC 1A F0 00` | −1 octave, 523→802 Hz. The ramp is only 7 steps, so it sounds a little stepped |
| let | 2, 17, 442, 6876, +1, 0, 0, 0 | `02 11 BA 01 DC 1A 10 00` | −2 octaves, 991→428 Hz, 15 steps |
| speech | 8, 0, 0, 4584, 0, 0, 0, 0 | `08 00 00 00 E8 11 00 00` | 651 Hz (−21 cents); the 9-cent vibrato is dropped |

All BEEP lists, with logical parameters and the 8 IPC bytes in order, are in
`audio/dos/<name>_ql.json`. Those bytes go after the `0A 08 AAAA0000` header (the 0x0000AAAA
mask, stored low byte first) and before the reply byte.

## 9. Output files

- `tools/dos_sound_extract.py`: decoder, x86 emulation cross-check, JSON, DOS WAVs. Usage:
  `[path/to/ABADIA1.OVL]`.
- `tools/dos_sound_ql.py`: BEEP fit, 8049 renders, CPC references. `--no-cpc-long` skips the
  30 s CPC 0x1007 render.
- `audio/dos/*.json`: event lists (`<name>.json`), BEEP lists (`<name>_ql.json`) and `index.json`.
- `build/snd/dos/` (untracked):
  - `<name>_dos.wav`: the DOS original;
  - `<name>_ql_beep.wav`: the recommended QL version;
  - `music_*_ql_beep_alt.wav`: the other octave choice;
  - `<name>_cpc.wav`: the CPC reference. For music_parchment it is the CPC ending tune,
    `music_parchment_cpc_intro.wav` is the CPC intro, and music_background is a 30 s render of
    CPC 0x1007 through the QL build's AY engine.

To regenerate: `python tools/dos_sound_extract.py && python tools/dos_sound_ql.py`.
`tools/sndtest.py --wav` must have been run first for the CPC copies.

## 10. Decisions (after the author's listening test)

- The DOS-derived beeper versions are accepted, open_door's buzz included.
- **Intro parchment:** reuse the DOS parchment tune at −1 octave (`music_parchment_ql.json`
  `beeps`), as DOS does.
- **In-game background music:** QSound only, so `music_background_ql.json` is not used.
- **close, bells, jingle, hit, mirror** are silent on DOS. They get CPC-derived beeper versions
  (section 11).

## 11. CPC-derived beeper versions (`tools/cpc_sound_ql.py`)

### Source

The QL port's own CPC engine (`cpp/port/ql_sound.c` in `abadia_h_bin`) is run headless with
`snd_play(entry)` and one `snd_poll()` per 50 Hz frame. Every `ql_ay_write` is logged until the
sound ends. The stock `sndtest` renders stop at 150 frames, which is too short for BELLS.

The first 150 frames are checked against the CPC oracle stream `build/snd/host_ay.txt`, and are
identical for all five. The periods are QSound-scaled (×1.5), so real frequency =
1.5 MHz/(16·period).

The VIGASOCO IDs and call sites come from `ql_sound.c`'s table and the CPC listing:

| name | CPC entry | VIGASOCO | game event |
|---|---|---|---|
| close | 0x1016 | CLOSE | a door closes |
| bells | 0x100C | BELLS | prima, sexta, vísperas |
| jingle | 0x1011 | JINGLE | tercia, completas (the CPC comment calls it "campanas") |
| hit | 0x102A | HIT | Severino knocking |
| mirror | 0x0FFD | MIRROR | the mirror opens |

### Fit rules

The beeper model is the one in section 8.

- **No volume on the beeper**, so each strike keeps only its *core*: the frames at ≥ 1/3 of
  that strike's peak volume. Fade-outs are dropped.
- **Range:** one octave shift for the whole sound. It is the highest octave in which every
  strike is in 43–1081 Hz and within 35 cents, so the intervals between strikes survive.
- **AY noise** mixed into a tone becomes BEEP **fuzz**.
- **Several strikes** become one BEEP per strike, at the CPC frame where it starts.
- **Two simultaneous tones** become a continuous bounce between them.

| sound | CPC | BEEP fit | length CPC → QL | weak points |
|---|---|---|---|---|
| close | 65.4 Hz tone+noise thud, decaying over 25 frames | 1 BEEP `166,0,0,9167,0,0,0,13`: 65.3 Hz, fuzz 13 | 500 → 400 ms | no decay. Fuzz only approximates the AY noise gating; tune by ear (11–14) |
| hit | three tone+noise knocks: 73.4, 73.4, 65.4 Hz at frames 0, 23, 46 | 3 BEEPs `146/146/166,0,0,9167,0,0,0,13` at frames 0, 23, 46 | 1420 → 1320 ms | 60 ms gaps between knocks stand in for the decays. Same fuzz caveat |
| bells | 5 "ding-dong" pairs over 8.8 s: tone A 496 Hz then 440 Hz, over a 312 Hz drone on B, each strike decaying 35–46 frames | 10 BEEPs, −1 octave: p37 (246 Hz) and p42 (222 Hz), 700 and 800 ms, at frames 0, 36, 87, 123, 175, 211, 262, 298, 350, 386 | 8780 → 8520 ms | monophonic, so the 312 Hz drone and the AY's slight detune shimmer are lost. One octave down because at CPC pitch the ding-dong whole tone would shrink to 1.4 semitones (p14/p16) |
| jingle | dyad 1995 + 2930 Hz, re-struck (volume) every ~5.4 frames for about 1 s | 1 BEEP `2,6,309,22459,+1,15,0,0`: continuous bounce p2↔p6 (988↔735 Hz), one up-down cycle per re-strike | 980 → 980 ms | both tones are folded (−1 and −2 octaves), so their interval inverts. The tremolo becomes a pitch warble |
| mirror | B: 65.6→87 Hz rising tone sweep. A: a 24 Hz tone+noise grind. Volume swells 1→15→1 over 79 frames | 1 BEEP `159,128,833,27042,−1,0,0,12`: sweep 68→83 Hz with fuzz 12, starting at frame 10 (200 ms, where the swell becomes audible) | 1580 → 1380 ms (ends at 1.38 s) | the swell is lost and the grind is only fuzz. It starts 200 ms after the trigger, like the CPC's swell |

### Outputs

- `audio/dos/<name>_ql.json`, for each of close, bells, jingle, hit and mirror.
- `audio/dos/index.json`, which gains a `cpc_derived` list (`dos_sound_extract.py` keeps it).
- `build/snd/dos/<name>_ql_beep.wav` and `<name>_cpc.wav`. The CPC file is a full-length render
  with sndtest's AY model.

To regenerate: `python tools/cpc_sound_ql.py`.

### For the player

Each JSON's `beeps[]` is the BEEP list.

- `ipc_bytes` are the 8 parameter bytes, in IPC order: p1, p2, interval LE, duration LE,
  step|wrap, random|fuzz.
- `params` are the same values, unpacked.
- Issue each BEEP at `frame` (or `t_ms`), counted from the trigger. One frame = 20 ms, the same
  50 Hz grid the CPC engine ran on.
- `dur_ms` is informative only: the duration is inside the bytes.
- Strikes are never less than 23 frames apart, so a multi-BEEP sound never needs more than one
  IPC transaction per frame.
- A new sound or BEEP replaces the current one. The DOS tunes' lists follow the same convention.

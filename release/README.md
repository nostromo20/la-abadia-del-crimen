# La Abadía del Crimen — Sinclair QL

*The Abbey of Crime*, Opera Soft's 1987 isometric mystery, now on the Sinclair QL.

> It is the year of our Lord 1327. Brother William of Baskerville and his young novice Adso
> arrive at a Benedictine abbey in northern Italy, where a monk has died in strange
> circumstances. You have seven days to find out what is going on — while keeping to the
> abbey's strict timetable of masses, meals and curfew, under the watchful eye of the Abbot.

This is a full conversion of the Amstrad CPC version: the whole abbey, all the monks and their
routines, the seven days, the intro and ending parchments, the original music (on QSound) and a
beeper soundtrack for every other QL.

---

## What you need

| | |
|---|---|
| **Machine** | Sinclair QL, or a compatible / emulator |
| **Memory** | **640 KB** (a QL with a 512 KB expansion). The game uses about 430 KB |
| **Display** | Mode 8 (256 × 256, 8 colours) |
| **Storage** | One microdrive cartridge (190 of 200 sectors), a floppy, or a hard disk |
| **Sound** | Works on any QL (IPC beeper). With a **QSound** card you also get the original AY music |

Faster machines are fine: the game paces itself on the QL's 50 Hz clock, so accelerated QLs,
QPC2 and fast emulators run it at the right speed.

**Tested on:** Q-emuLator (640 KB, QSound), QPC2 (from the WIN container), and a real QL with
QSound.

---


## Loading

- **Microdrive:** put `abadia.mdv` in `mdv1_` (or the cartridge in drive 1) and reset; press F1
  or F2 at the start-up screen. It boots by itself.

The loading screen stays up while the game loads (most of a turn of the tape on a real
microdrive), then the intro parchment fades in.

---

## Playing

You are **William**. Adso follows you.

| key | action |
|---|---|
| ← / → | turn left / right |
| ↑ | walk forward |
| ↓ | Adso steps forward, the way William faces (to move him along) |
| SPACE | drop the item you carry; skips the intro |
| Y / N | answer Adso's questions (yes / no) |
| F1 | save the game |
| F2 | load the game |
| F3 | choose the save drive: MDV1_ → MDV2_ → FLP1_ → FLP2_ → WIN1_ → WIN2_ → RAM1_ |
| F5 | show / hide the help line |
| ESC | quit to SuperBASIC |

**Hints from the abbey's rulebook**
- Keep close to the Abbot when he guides you — if you fall behind, he will not wait forever.
- Go to mass (morning and evening) and to the meal at midday. After compline, be in your cell.
- Your *obsequium* (the bar in the panel) is your standing with the Abbot. When it runs out,
  you are thrown out of the abbey.
- The box on the lower left of the panel shows the canonical hour: NOCHE, PRIMA, TERCIA, SEXTA,
  NONA, VÍSPERAS, COMPLETAS — night, morning mass, free time, meal, free time, evening mass,
  curfew.

**Saving.** F1 saves to `abadia_sav` on the chosen drive (the game's own drive by default). A
save is under 1 KB, so it fits on the game cartridge next to the game. The drive you pick with
F3 is remembered in a small settings file (`abadia_cfg`). Errors (no cartridge, write
protected, disk full) are shown in the line under the panel and never stop the game.

---

## About the port

### What it is

The game logic is the original's, rule for rule. It comes from Manuel Abadía's reverse
engineering of the CPC version (the VIGASOCO "La Abadía del Crimen" driver, through Samuel
Salinas's *Abbey* fork), compiled for the 68008 with GCC. Everything that touches the screen,
the keyboard, the sound and the drives is QL code, mostly hand-written 68000 assembler:

- **Graphics.** The CPC's 320 × 200 four-colour screen is shown in QL Mode 8. The 256-pixel
  play area maps one to one; the room builder, tile composer, sprite mixer and screen copy are
  in assembler. Colours were chosen per scene, with separate colours and dithers for the
  characters and the panel, and a night palette. Rooms build in the CPC's spiral, on black.
- A few things are deliberately better than the CPC: the arch-pillar flip, foreground columns
  that no longer erase the background behind them
- **Sound.**
  - *With QSound:* the CPC's own music, played by the CPC sound engine on the AY chip.
  - *Without QSound:* the intro and ending tune from the PC (DOS) version, which was written
    for a one-voice speaker, on the QL beeper at the original tempo.
  - *Sound effects* are on the beeper on every QL: the PC version's, plus beeper versions of
    the CPC's bells, doors and mirror where the PC was silent.
- **Text.** English throughout: the parchments, the scrolling phrases and the messages. The
  hour names in the panel are kept in the original Spanish, as on the CPC.
- **Size.** The game unpacks itself from an 86 KB file (aPLib), the loading screen , so the
   whole game fits on one cartridge with room for a save.

### Known limits

- The game has been played in its opening scenes and checked by automated tests (the ending
  included), but not yet played start to finish by a person on a real QL. Reports welcome!

---

## Credits

### The original game
- **Paco Menéndez** — design and programming
- **Juan Delcán** — graphics and cover art
- **Opera Soft** — published 1987 (© Opera Soft)

Inspired by Umberto Eco's novel *Il nome della rosa* (*The Name of the Rose*).

### The reverse engineering and the PC remakes this port builds on
- **Manuel Abadía** — reverse engineering of the CPC game, its commented disassembly, and the
  "La Abadía del Crimen" game driver for **VIGASOCO** (VIdeo GAmes SOurce COde, © 2003–2005
  the VIGASOCO Project Team)
- **Luzbel** — the SDL version
- **Antonio Giner** — VGA graphics and the English translation (used in this port)
- **Samuel Salinas** (Samuel85) — *Abbey*, the modernised VIGASOCO port whose sources this port
  compiles

### Third-party code
- **Emmanuel Marty** — the 68000 aPLib and ZX0 decompressors (zlib licence)
- **Jørgen Ibsen** — the aPLib compression format
- **Einar Saukas** — the ZX0 compression format

### Sinclair QL port
- **Jim McKay** — QL port: renderer, QL platform layer, colours and layout, sound, saving,
  packaging and testing

Developed with the help of Claude (Anthropic) as a coding assistant.

The full credits are also on the last pages of the intro parchment.

---

## Licence and rights

- *La Abadía del Crimen* — its design, graphics, music and text — is © Opera Soft. This port is
  a free, non-commercial fan conversion and is not endorsed by the rights holders.
- The game logic is derived from VIGASOCO. Its terms: free for **non-commercial** use, with
  VIGASOCO and the driver author (Manuel Abadía) credited; no commercial use without the
  author's written permission. Those terms apply to this port.
- The aPLib and ZX0 decompressors are under the zlib licence; their notices are kept in the
  source.

**This port may not be sold.** Share it freely, unchanged, with this README.

---

## Feedback

Bug reports, test results on real hardware (which QL, which expansions, which drive) and
suggestions are very welcome on [theqlforum.com](https://theqlforum.com).

*¡Que Dios os guarde, hermanos!*

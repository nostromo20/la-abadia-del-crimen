# Speed: the QL port against the Amstrad CPC

This is an evaluation only; no game code was changed (2026-10-05, HEAD 85d3c30). The author finds
the port generally slower than the CPC. In particular:
- the intro parchment's text;
- the phrase that scrolls in the panel during play.

## Summary

| item | CPC (measured) | QL (measured) | QL vs CPC | main cause |
|---|---:|---:|---:|---|
| panel phrase scroll | **150 ms** a character, independent of the game loop | **260 ms** a character (2 logic steps); 320 ms in monk rooms | **1.7–2.1× slower** | pacing model (the fork's) |
| intro page turn (wait + animation) | **4.3 s** | **14.4 s** (Q-emuLator, Speed=QL) | **3.4× slower** | QL CPU (the animation) |
| intro text, page 1 | 55.1 s | 58.7 s (Q-emuLator), 59.3 s (model) | 7–8% slower | pacing constants |
| whole intro (to the end of the text) | 400.7 s | ~480–500 s (estimate below) | ~20–25% slower | page turns, then the constants |
| game step, walking / idle (camera on Guillermo) | 120 ms (the CPU work is ~55 ms) | 130 ms (6.5 frames; 6.4–6.9 measured) | ~8% slower | the step length (the fork's 130 ms) |
| game step, monk rooms | 132 ms mean (the work, 105 ms mean, overruns 120 ms in 23% of steps) | ~160 ms (8.0 frames measured) | ~20% slower | QL CPU |
| no key for ~6.5 s, camera on another character, no phrase | **no wait at all: ~50 ms a step** | 130 ms | **2.6× slower** | a CPC rule the port lacks |

**What the author sees.** The phrase scroll and the page turns are the "much slower" parts:
- the phrase is a pacing-model error, fixable at no CPU cost;
- the page turns are a QL CPU problem, in one routine.

The parchment's handwriting itself is only ~8% slower.

## How the CPC was measured

`tools/cpctime.py` runs the **original CPC game**, from its entry point 0x249A:
- on the Z80 emulator (pip `z80`) already used by `tools/cpcref.py` and `tools/mixcheck.py`;
- with the memory and bank switching of `cpcref.py`;
- with the 300 Hz interrupt delivered to the game's own handler (0x2D48: music, speech and the
  phrase scroll, the main loop's counter);
- with the keyboard answered through the PPI;
- with the same key scripts as the QL tests (tests/walk1.txt and tests/enter.txt, one script step
  per main-loop pass).

**Timing model.**
- The Z80 runs at 4 MHz, but the gate array stretches every instruction to a whole number of
  microseconds: CPC time = ceil(T-states / 4) µs. A few instructions differ by at most 1 µs.
- Interrupts come every 52 HSYNCs = 3328 µs. They are held until EI. They are never delivered
  between a DD/FD prefix and its opcode: an earlier version of the tool did that and crashed the
  game.

**Validation.**
- **The delay loop.** The parchment's delay loop (0x67C6: nop / dec bc / ld a,b / or c / jr nz)
  costs 1 + 2 + 1 + 1 + 3 = 8 µs an iteration. That is the figure the CPC literature gives.
  Manuel Abadía's disassembly says "32 ciclos" for it, which is 8 µs. His "aprox. 10 µs" assumed
  3.2 MHz on top of the stretch, counting it twice, so his "8 ms / 30 ms / 600 ms / 655 ms" notes,
  which the port's constants copied, are about 20% long.
- **The interrupt rate** measured 299.5–300.3 Hz.
- **The phrase scroll** measured 148.8–150.6 ms a character, against 45 interrupts in the code
  (0x3B54).
- **The game.** The intro runs to its end, and the main loop runs ~1,000 passes of real play with
  the expected screens and wait thresholds.

**What paces the CPC.**
- **The main loop (0x25B7–0x2632):**
  - After the logic it busy-waits (0x2614) until the interrupt counter reaches the value at 0x2618,
    then resets the counter and draws the sprites. That value is 36 (from 0xBF49), so a pass takes
    at least 36/300 s = **120 ms**, or longer when the work overruns.
  - 0x41D6: when no cursor key has been pressed for 50 passes, the camera moves to another
    character. If no phrase is showing, the value becomes **0**, and the loop then runs as fast as
    the CPU allows.
- **The panel phrase:** the interrupt handler advances it, one character every 45 interrupts =
  **150 ms**, whatever the main loop is doing.
- **The parchment:** pure busy-wait delay loops (0x6725–0x6809). Strokes (one pixel each) take
  0x320 iterations, a space or the end of a character 0xBB8, a new line 0xEA60, and a page 3 ×
  0x10000, before the page-turn animation. The music interrupt steals ~12% of the time on top
  (stroke to stroke: 6.55 ms without interrupts, 7.44 ms with them).

**Where 130 ms came from.**
- VIGASOCO (Manuel Abadía's original) emulates the CPC's 300 Hz interrupt:
  - its `runSync` is that interrupt, and the phrase scroll advances every 45 calls;
  - its game thread waits on the same counter.
  It is CPC-true.
- The Samuel85 fork that this port follows replaced this with one frame every
  `GAME_FRAME_TIME` = 130 ms (`src/system.h`; `SCROLL_FRAME_TIME` 60 ms is defined but unused).
  It calls the phrase scroll once a frame, advancing a character every **2** calls (the comment
  says "45 … actualizado a 2"), so 260 ms a character.
- Neither 130 ms nor "2" is a CPC figure. The QL kept both.

## How the QL was measured

- **Real QL speed: Q-emuLator, Speed=QL**, running the dev image with the in-game self-log (frames
  per logic step).
  - It ran from a fresh folder and config (`build/qltest/speed_<time>`), whose BOOT was replaced by
    a REMark afterwards.
  - The intro run gives page 1 and the first page turn.
  - The game-step figures are the earlier Q-emuLator measurements (project notes, 2026-10-02/03):
    idle 6.35–7.1, walking 6.6–6.9, monk rooms ("enter") 8.0–8.1 frames a step.
- **The harness** (`tools/qlspeed.py`, `tools/cyclest.py`) gives:
  - per-step costs (cyclest's 68008 bus model, ±30%, **no display contention**);
  - the steps per character and page.
- The model under-reads the real QL in screen-heavy work: monk rooms modelled 6.8 frames, measured
  8.0. The page turn modelled 8.7 s, measured 14.4 s. Screen writes on a real QL wait for the
  display, and the model leaves that out.

## Detail

### Panel phrase

| | CPC | QL |
|---|---:|---:|
| per character | 150 ms (interrupt-driven) | 2 steps = 260 ms, 320 ms when steps take 8 frames |
| "SHALL WE SLEEP, MASTER? Y/N" (27 characters + 17 clearing spaces) | 6.6 s | 11.2 s (86 steps) |

The cause is the fork's pacing model; it costs no CPU. The game logic also waits for phrases (monks
don't start some actions while a phrase is showing), so the slow scroll makes some scripted scenes
slower too.

### Intro parchment

| | CPC | QL constant (Pergamino.cpp) | QL |
|---|---:|---:|---:|
| stroke (one pixel) | 7.44 ms | 8 ms | 8 ms (steps on time) |
| space / end of character | ~27 ms (24 ms + interrupts) | 30 ms | |
| new line | ~540 ms (480 ms + interrupts) | 600 ms | |
| page wait | ~1.76 s (3 × 524 ms + interrupts) | 1.985 s | |
| page-turn animation | ~2.5 s | — (one animation frame per logic step) | ~12 s (frames of 0.7–1.3 s) |
| page turn total (last line to the next page's first stroke) | **4.26–4.82 s** | | **14.4 s** |
| end of page 1 | 55.1 s | | 58.7 s |
| page turns at | 55.1, 107.6, 167.6, 226.2, 285.3, 337.8, 370.9 s | | model: 59.3, 117.3, 186.5, 256.8, 317.1, 378.3, 448.7 s |
| end of the text | **400.7 s** | | ~480 s modelled; ~500 s on a real QL (the page turns measured 14.4 s, not the modelled 8.7 s) |

- The handwriting runs at the QL's constant, so steps are on time (6.45 frames each in Q-emuLator),
  and it is 7–8% slower than the CPC because the constants are.
- **The page turns:**
  - The CPC draws the turning page flat out.
  - The QL draws one animation frame per logic step (15 frames).
  - Each frame costs 0.4–0.7 s of 68008 time in the model and 0.7–1.3 s on the emulated QL:
    `Pergamino::pasaPagina` and its `restaura*` routines go through `setMode1Pixel` /
    `ql_play_pixel` one pixel at a time, into screen memory.

### Game loop

| | CPC period (work) | QL period |
|---|---:|---:|
| idle at the start, camera on Guillermo | 119.8 ms (42–51 ms) | 130 ms (127–142 ms) |
| walking (walk1 steps 10–200) | 120.8 ms mean (56.7 ms mean, 89 ms p90; 6 of 191 over 120 ms) | 6.6–6.9 frames = 132–138 ms (model: 58 ms of work) |
| monk rooms (enter steps 400–900) | 132.5 ms mean (105 ms mean, 143 ms p90; 116 of 501 over 120 ms) | 8.0 frames = 160 ms (model: 95 ms of work, 6.8 frames) |
| no cursor key for 50 passes, no phrase (camera on another character) | ~50 ms (no wait) | 130 ms |

**The two CPUs compared.** Where the screen is not the bottleneck (walking, idle), the 68008 port
needs about as much time per step as the Z80 original (~55 ms modelled against 57 ms measured).
The QL loses in screen-heavy rooms, where display contention (not modelled) pushes the real steps to
8 frames, and to the fixed 130 ms against the CPC's 120 ms.

**Where the monk-room time goes** (cyclest, enter steps 400–900; harness-only `abadia_state` left
out):
- **drawing (about 35%):** `blit_packed` 10%, `a_tiles_prof` 7.5%, `a_sprite_blit_pm` 5.5%,
  `a_combina_tile_p` 4.9%;
- **routes (about 7%):** `a_bfs24` 4.8%, `generaAlternativa`, `a_puertas_ruta`;
- **the panel:** phrase drawing through `setMode1Pixel` / `imprimirCaracter`, 4.6%;
- **the mixer:** 3.4%.

## Options

| # | option | effect | CPU / memory | risk | changes timing vs the original? |
|---|---|---|---|---|---|
| 1 | **Pace the panel phrase by frames: 7.5 frames (150 ms) a character**, advanced in the main loop from the frame counter (one or two characters some steps) | phrase 1.7–2.1× faster, exactly CPC | ~0 (a counter; the scroll itself costs the same per character) | low; hdiff: the oracle needs the same rule with a nominal frame clock (6.5 frames a step) to stay comparable | **towards the CPC** (the fork's 260 ms was the deviation). Scenes that wait for a phrase end sooner, as on the CPC |
| 2 | **A faster page-turn animation**: span fills / word copies in asm instead of per-pixel calls; draw only the strip that changes per frame; then pace it by the CPC's own time (~2.5 s) rather than one frame per step | page turn 14.4 s → ~4–5 s; the intro ~70 s shorter | ~1–2 KB code; the CPU is spent only in the intro | medium (drawing code; checked with the existing intro hdiff/storyboard tools) | towards the CPC |
| 3 | **The parchment constants to the measured CPC values**: 7.44 / 27 / 540 / 1760 ms (or the CPC's iteration counts × 8 µs × 1.12) | handwriting ~8% faster; with 2, the intro ≈ CPC | 0 | very low | towards the CPC |
| 4 | **The step to the CPC's 120 ms (6 frames)** where the QL keeps up, still waiting only for what is left | walking/idle 8% faster; monk rooms unchanged (already over) | ~8% more CPU per second while walking; sound and the music engine are frame-based, so unaffected | low–medium: more steps over budget at the margin; the key auto-repeat is tuned for 130 ms | towards the CPC |
| 5 | **The CPC's "no wait while the camera is on another character and no phrase shows" rule** | the waiting-for-the-abbot scenes ~2.6× faster, as on the CPC | the CPU runs flat out then (as the CPC does) | low | **towards the CPC** (the port is slower than the original there) |
| 6 | **More CPU work for monk rooms**: the drawing path (blit_packed, tiles, sprite blits: ~35%), with display contention in mind (fewer screen writes, write whole words/longs once), the route search spikes | maybe 10–20% per step there (160 ms → ~135–145 ms), still above the CPC's 132 ms | effort high; memory small | medium; each kernel is covered by kerntest/hdiff | no (only speed) |

**Trade-off of 4 and 5.** A shorter step raises the CPU needed per second by ~8% (option 4), and
option 5 makes some idle stretches run flat out. Neither touches monk rooms, which already overrun
both on the QL and on the CPC (23% of the CPC's passes there exceed 120 ms). The overruns do not
get worse, the slack in light rooms is used. A faster tick only helps where there is slack:
walking, idle, the corridors.

## Recommendation

1. **Option 1 (the phrase by frames)** first: the biggest visible gap during play, no CPU cost, and
   it removes a deviation the fork introduced.
2. **Options 2 + 3 (the parchment):** the page-turn animation in asm plus the CPC constants. This
   brings the intro from ~500 s to about the CPC's 400 s.
3. **Options 4 + 5 (the CPC's loop rules: 120 ms, no wait when the camera is elsewhere):** cheap,
   CPC-true, and they only use slack the QL has.
4. **Option 6** only after 1–5, and only if monk rooms still feel slow: it is the expensive one,
   with ~10–20% realistically left.

1, 3, 4 and 5 are pacing changes with no CPU cost; 2 and 6 are CPU work.

## Tools (committed)

- `tools/cpctime.py`: the original CPC game timed on the Z80.
  - `intro`: strokes, lines and page turns, to the end of the text.
  - `loop --keys tests/X.txt --iters N`: the time of every main-loop pass, and its work before the
    wait.
- `tools/qlspeed.py`: the QL in the harness.
  - `intro`: page turns, with the cyclest-modelled step lengths.
  - `phrase`: steps per panel character.
- The Q-emuLator measurement: the dev image with the self-log, from a fresh config
  (`build/tmp/qemu_intro_speed.py`, not committed).

## After options 1–5 (2026-10-05)

The author approved options 1–5 (option 6, monk-room CPU work, was not approved). Commits:
- 38aca28: option 1, the panel phrase paced by frames;
- 43bbb2e: options 2 + 3, the page turn in asm and the CPC's parchment times;
- the next commit: options 4 + 5, the 120 ms step and the CPC's no-wait rule.

All figures below are from Q-emuLator (Speed=QL, the dev image with its self-log, fresh
configs), except where marked "harness".

| item | CPC | QL before | QL after |
|---|---:|---:|---:|
| panel phrase, a character | 150 ms | 260 ms (320 ms in monk rooms) | **150 ms** (frames; harness, real clock: 152 ms) |
| intro page turn (new line + wait + animation) | 4.8 s | 14.4 s | **4.9 s** |
| intro, end of page 1 | 54.6 s | 58.7 s | **54.7 s** |
| intro, page 7 turn (Spanish text, harness) | 370.9 s | — | 369.5 s |
| whole intro, end of the text | 400.7 s (Spanish) | ~480–500 s (English) | **411.8 s** (English); Spanish: an extra 8th page, see below |
| step, idle (camera on Guillermo) | 120 ms | 6.44 frames = 129 ms | **5.98 frames = 120 ms** |
| step, walking (walk1 10–200) | 120.8 ms | 6.54 frames = 131 ms | **6.23 frames = 125 ms** |
| step, monk rooms (enter 400–900) | 132 ms | 7.85 frames = 157 ms | 8.03 frames = 161 ms (option 6, not done) |
| waiting scene: no key for 50 steps, no phrase (walk1 252–300) | ~50 ms (no wait) | 6.46 frames = 129 ms | **3.67 frames = 73 ms** (no wait: the CPU's own pace) |

**How each was done:**
- **Option 1.** `ql_game.cpp` counts the frames each step took. A step that takes long releases its
  characters at once, as the CPC's interrupt would have scrolled them in the meantime.
- **Option 2.** `ql_play_triangle_inc` draws each animation frame from the previous one: only the
  ends of the lines that already hold the previous frame. The border restores are packed-byte
  blits. Across all 7 page turns (665 animation frames) the screen is identical at every frame to
  the old per-pixel paths (`tools/pagetest.py`). The 68008 time of the turns went from 46.1 s to
  8.9 s (cyclest model).
- **Option 3.** The parchment's costs are the measured CPC figures:
  - 7.44 ms a stroke;
  - 26.94 ms a space or the end of a character;
  - 535.32 ms a new line;
  - 1761.21 ms the page wait;
  - 26.57 ms per animation call.
  The budget is the frames each step took, so the parchment keeps CPC time even when a step
  overruns. A page ended by a new line now also pays the new line's delay, as the CPC does.
- **Option 4.** The step is exactly 6 frames. The timers tuned for 130 ms were retuned:
  - F5-HELP 42 steps (5.0 s);
  - save/load messages 22 steps (2.6 s);
  - SAVE DEVICE message and the settings-file delay 17 steps (2.0 s).
  The Q/R latch stays 4 steps (0.48 s). The auto-repeat (`ar_setup`) is in frames and unchanged.
- **Option 5.** `Logica::qlEspera` follows the CPC exactly:
  - no wait once no cursor key has been pressed for 50 passes and no phrase shows (0x41a1–0x41c2);
  - the wait comes back with a cursor key, or when the camera returns to Guillermo (0x41b7);
  - it starts each new game (0x2548).
  `tools/waittest.py` runs the original CPC code and the QL on walk1: both switch to no-wait at the
  same pass (QL step 250, CPC pass 249), with 50 no-wait steps each and no disagreements.

**hdiff.** The harness and the oracle share a nominal clock: 6 frames a step, header +30 bit 2 on
the QL. So the frame-based pacing is identical on both sides, and every hdiff case stays
identical: state and screens, the intro ones included. The real clock is checked separately by
`tools/phrasetest.py` (REALCLOCK=1).

**CPU per step.**
- Options 1, 3 and 5 cost nothing per step.
- Option 2 costs less than before.
- Option 4 runs 8% more steps per second wherever the QL was on time.
- The faster phrase scrolls 0.8 characters per step instead of 0.5. To offset that, the panel
  character is now written straight into the panel buffer (the same bytes, one dirty-area update
  instead of 64 `setMode1Pixel` calls). Net per-step work, enter 2–900, cyclest model: 88.0 ms
  before, 89.0 ms after. Where phrases run back to back (enter 160–400) it is about 5 ms more.

**Monk rooms** still overrun (8.0 frames against the CPC's 6.6). Option 6 (below) brought them to 7.46 frames (149 ms).

**Not speed: the fork's intro text.**
- Through page 7 the QL's Spanish text keeps the CPC's page times within 0.5–2 s.
- The fork's text then adds credit lines that the CPC's text does not have: "reingenieria inversa:
  Manuel Abadia", "version SDL: Luzbel", "Graficos VGA: Antonio Giner", "version Abbey: Samuel
  Salinas". They make an 8th page and about 30 s more.
- Trimming them would be a content decision for the author (CREDITS.txt).

## Option 6: monk-room CPU work (2026-10-05)

**Measured.** Q-emuLator (Speed=QL), the dev image's self-log every 2 steps (so p90, max and the
spike count are over 2-step averages), tests/enter.txt; the CPC figure is from the section above.

| enter steps | before (b8402ca) | after (fcde7a3) | CPC |
|---|---|---|---|
| 400–900 (monk rooms) | 7.82 frames = 156 ms; p90 10, max 43, 56 over 10 | 7.46 frames = 149 ms; p90 10, max 44, 30 over 10 | 132 ms |
| 100–400 | 8.65 frames = 173 ms; p90 12, max 14, 78 over 10 | 7.14 frames = 143 ms; p90 10, max 12, 24 over 10 | |
| 900–1100 | 9.36 frames = 187 ms; p90 11, max 62, 14 over 10 | 6.28 frames = 126 ms; p90 8, max 12, 6 over 10 | |

walk1 steps 20–600: 5.56 → 5.49 frames (the no-wait rule makes these shorter than 6 frames);
idle: 3.84 → 3.57 frames. Every Q-emuLator run of the same image gives the same numbers.

cyclest model, enter 400–900: 94.6 → 84.6 ms of work a step.

| part | commit | what | model ms/step | release size |
|---|---|---|---|---|
| 1 | e158eae | memcpy/memmove/memset in asm (16 bytes a dbra pass; the C copy took ~8 instructions a long); C references kept, `tools/memtest.py` | } 94.6 → 86.4 | } +~400 B packed, offset by leaving the harness-only page-turn paths out of the release: 195 sectors |
| 2 | 4df025a | phrase scroll: the screen's own words moved (`ql_panel_scroll`) when the screen already shows the panel, so only the new character is presented, not 128×8 pixels every 150 ms; the host presents the moved pens, so hdiff checks the moved words | } | } |
| 3 | fcde7a3 | `estaEnRejillaCentral` without its two calls (~30 calls a step) | 86.4 → 84.6 | +13 B packed |

The phrase work was most of the gain where phrases run (100–400, 900–1100). In the monk rooms
the rest of the time is spent drawing (blit_packed 11%, a_tiles_prof 8%, a_sprite_blit_pm 6%,
a_combina_tile_p 5%), on routes (a_bfs24 5%) and in the characters' logic. Each of these is already
an asm kernel or a small C function; what is left is a few per cent each (unrolling blit_packed,
a mask-offset table in its character-colour path, inlining Puerta::puedeAbrir), against the
release's 400 bytes of headroom at 173 sectors for the game file. The monk rooms stay ~13% slower
than the CPC (149 against 132 ms).

## Consistency fixes and options 4–5 (2026-10-06)

**Measured.** Q-emuLator (Speed=QL), with the dev image's self-log. The runs:
- walk1, enter and idle logged every 2 steps, so p90, max and "over 10" are over 2-step averages;
- room changes logged every step, on enter's first 5.

Every run of the same image gives the same figures. "Before" is the image of e42ff22, which is the
same as cc5c944.

| | before | after (2e8f974) | CPC |
|---|---|---|---|
| monk rooms, enter steps 400–900 | 7.43 frames = 149 ms; 26 over 10, max 44 | **7.00 frames = 140 ms**; 14 over 10, max 30 | 132 ms |
| enter steps 2–900: steps over 10 frames, max | 64, max 52 | **30**, max 40 | |
| walk1 steps 2–900 (first ~2 minutes) | 5.53 frames; 4 over 10, max 11 | 5.47 frames; **0 over 10**, max 10 | |
| idle | 3.58 frames | 3.48 frames | |
| a room change (enter's 5) | 75.6 frames = 1.51 s | **55.4 frames = 1.11 s** | |

**What was done:**
- **2a: the height-grid cache is pre-warmed in spare time.**
  - In `wait_tick`, while 3 or more frames are left to wait, the cache gets one window at a time:
    the window each character is in, and the window it faces.
  - Misses during steps (harness, 1,500 steps): walk1 32 → 19, enter 33 → 7, saveload 50 → 15.
  - hgridtest's overall hit rate went from 62% to 85%.
  - The work runs only in time the step would otherwise spend waiting. cyclest counts it as work
    (`ql_hg_prewarm` in its tables).
- **2b: `a_bfs24` tests the four neighbours inline.** Its share of a monk-room step fell from
  5.3% to 3.9% (2,275 → 1,828 ms over 500 steps).
- **3: the room generator runs in asm** (`src/gen.s`: the bytecode interpreter and its tile
  commands).
  - A room build (generation + spiral) went from 656 ms to 488 ms in the model.
  - On enter's room changes the model went from 920 to 715 ms, and the black time before the spiral
    from ~550 to ~340 ms.
- **4: the drawing routines.**
  - A cell with both tiles is now drawn in one pass, so a room build takes 452 ms.
  - The character-colour copy to the screen (`blit_packed`) does two words a loop, and gets
    mask × 512 by `ror #7`.
  - The tile combines take their arguments in registers.
  - Model, monk rooms: 93.3 → 92.0 ms a step.

Each part has a differential test against the C it replaces or the old path:
- kerntest, gentest, spiraltest and memtest;
- hdiff on every script;
- cpcref, roomcmp, tilecompose and mixcheck.

All are identical.

The monk rooms are now 6% slower than the CPC (140 against 132 ms), down from 13%. The rest is
spread over the drawing kernels (`blit_packed` 9.5%, `a_tiles_prof` 7.2%, `a_sprite_blit_pm`
5.7%, the combine 4.1%), the route search (4.0%) and the characters' logic. None of these offers
more than a per cent or two each.

## Several characters on screen (2026-10-06, characters steps 0–3)

**Measured.** Q-emuLator (Speed=QL, the dev image's self-log every 2 steps; "over 10" and max
are over 2-step averages). "Stress" is `tests/stress.txt`: the four monks of day 1 placed next to
Guillermo (`tests/stress_sav`), with 5–6 characters on screen. Before = 3559f8a, after = b154e73.

| | before | after | CPC |
|---|---|---|---|
| monk rooms, enter steps 400–900 | 7.00 frames = 140 ms; p90 9, max 30, 14 over 10 | **6.84 frames = 137 ms**; p90 8, max 30, 14 over 10 | 132 ms |
| enter steps 2–900, over 10 frames | 30 | 26 | |
| stress, steps 10–600 | 8.05 frames = 161 ms; max 15, 58 over 10 | 7.97 frames = 159 ms; max 14, **40 over 10** | |
| walk1 | 5.47 frames | 5.43 frames | |
| idle | 3.48 frames | 3.48 frames | |
| a room change (enter's 5) | 55.4 frames | 54.2 frames | |
| screen bytes written a step: enter / stress | 1,757 / 599 | 1,757 / 599 | |

Cyclest model, enter steps 400–900: 92.0 → 90.3 → 88.7 ms a step.

**Step 0: memory placement.** The release job and the dev kit's RESPR block both sit wholly above
$40000 (docs/release.md). No fix was needed.

**Step 1: the mixing buffer is interleaved.**
- Each element is a mask byte followed by the pens, so the screen copy reads one word and does one
  table lookup, with no mask test.
- `blit_packed`: 4,366 → 2,815 ms over 500 steps.

**Step 2: the per-sprite kernels.**
- The interleaved kernels use post-increment addressing.
- The mask bits of a drawn byte come from a table.
- `a_tiles_prof` tests its two layers inline.

**Step 3: fewer screen writes. Measured, not implemented.**
- In the monk rooms, 1,757 bytes a step reach the screen, and 50% of them write the value already
  there:
  - the sprite areas: 1,002 bytes, 63% unchanged;
  - the phrase scroll: 375 bytes, 56% unchanged;
  - room builds: about 330 bytes a step on average.
- Of the sprite areas' bytes, 20% are whole unchanged rows and 35% whole unchanged word columns.
- Skipping them needs the previous content: a shadow of the play area in fast RAM, or reading the
  screen.
- On the 68008 a skipped write saves its own ~8–12 cycles (plus any contention wait, a few cycles
  on a real QL). A compare costs ~20–24 cycles for every word, changed or not.
- So it would make the step slower on a real QL too. The areas are already the union of the old and
  new sprite boxes, so trimming by the boxes alone finds no rows or columns to drop.

**What the stress scene shows.** With 5–6 characters on screen, the cost moves from drawing to the
characters' logic (cyclest, stress steps 20–400):
- route search: `a_bfs24` 8.6%, `a_bfs16` 2.8%, `reconstruyeCamino` 3.4%;
- movement tests: `a_avance` 7.6%, `obtenerAlturaPosicionesAvance*` 5%;
- grid tests: `estaEnRejillaCentral` 4%, `marcaPosicion` 3%.

Those are the next targets for crowded scenes; the drawing kernels are now a few per cent each.

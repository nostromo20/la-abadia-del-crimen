#!/bin/bash
# Full regression set for the hybrid build: hdiff --realq (walk1/enter/saveload 900, walk1 4000),
# roomcmp, sndtest, kerntest (random seed), the QEMU_KEYS walk-and-turn check, and the beeper
# check (every MT.IPCOM BEEP against audio/dos/*_ql.json, QSound present and absent), and the COLOUR
# checks: hdiff compares colours (tools/colourmodel.py), also at night (--night) and on the intro
# parchment (--intro), and tools/colourcheck.py draws the colour tool's scenes through the real copy path.
cd "$(dirname "$0")/.." && . ./config.sh
mkdir -p build/tmp
grep -i "warn\|error" build/vasm.log | head -3
for t in walk1 enter saveload; do echo "== hdiff $t 900"; $PY tools/hdiff.py --script tests/$t.txt --ticks 900 --every 10 --realq --sv164 0xC1000 2>&1 | tail -2; done
echo "== hdiff walk1 4000"; $PY tools/hdiff.py --script tests/walk1.txt --ticks 4000 --every 100 --realq --sv164 0xC1000 2>&1 | tail -2
echo "== roomcmp"; $PY tools/roomcmp.py 2>&1 | grep SUMMARY
echo "== sndtest"; $PY tools/sndtest.py 2>&1 | tail -1
echo "== kerntest"; $PY tools/kerntest.py --cases 2400 --seed $RANDOM 2>&1 | grep -E "mismatches" | grep -v " 0 mismatches" ; echo "(kerntest: lines above = failures)"
echo "== QEMU_KEYS"; bash tools/keyswalk.sh | tail -2
echo "== beeptest"; $PY tools/mkbeeps.py --check; $PY tools/beeptest.py 2>&1 | grep -v "^ok"
echo "== hdiff enter 600 --night (colours, day -> night switch)"; $PY tools/hdiff.py --script tests/enter.txt --ticks 600 --every 25 --realq --sv164 0xC1000 --night 2>&1 | tail -2
echo "== hdiff intro 400 (parchment colours, dither)"; $PY tools/hdiff.py --script tests/idle.txt --ticks 400 --every 40 --realq --sv164 0xC1000 --intro 2>&1 | tail -2
echo "== colourcheck"; $PY tools/mkpalette.py --check | tail -1; $PY tools/colourcheck.py 2>&1 | grep -v "^ok"
echo "== hdiff walk1 300 --mirror (save, mirror opens, load; QL cache hits verified)"; $PY tools/hdiff.py --script tests/walk1.txt --ticks 300 --every 10 --realq --sv164 0xC1000 --mirror 2>&1 | tail -2
echo "== hgridtest (height-grid cache: verify on hit, height-table writers, mirror + save/load)"; $PY tools/hgridtest.py 2>&1 | grep -E "^(FAIL|HGRID)|NOT A KNOWN"
echo "== cpcref --tiles (every screen's tile buffer, QL_TILE_COMPOSE off, vs the CPC's own generator run on a Z80)"; mkdir -p build/tmp/tour_cpc; MSYS_NO_PATHCONV=1 wsl env NOCOMPOSE=1 $QLL/build/host/oracle --tour $QLL/build/roms.bin $QLL/build/tmp/tour_cpc 0 115; $PY tools/cpcref.py --tiles --dir build/tmp/tour_cpc 2>&1 | tail -1
echo "== tilecompose (data in sync; composed tile buffers (roomcmp's tour) = CPC + plan; every composed cell exact for every reachable sprite position, through the CPC's Z80 mixer)"; $PY tools/tilecompose.py --sync | tail -1; $PY tools/tilecompose.py --check build/roomcmp --z80 1 2>&1 | tail -1
echo "== mixcheck (the mixer vs the CPC's own Z80 mixer, and in-play tile buffers vs the CPC generator)"; for c in "tests/arch28.txt --ticks 45 --save tests/arch28_sav" "tests/enter.txt --ticks 900"; do $PY tools/mixcheck.py --script $c 2>&1 | tail -1; done
echo "== hdiff intro -> game (SPACE at step 200, during the first page, at a page turn: off-screen page, dissolve, tiles rebuilt)"; for s in intro intro_skip_early intro_skip_turn; do $PY tools/hdiff.py --script tests/$s.txt --ticks 400 --every 10 --realq --sv164 0xC1000 --intro 2>&1 | tail -1; done
echo "== qrtest (the mirror code: Q and R typed once each, up to 3 steps apart, on each staircase)"; $PY tools/qrtest.py 2>&1 | grep -E "^FAIL|^QR"
echo "== striptest (the strip under the panel: F5-HELP, help, F3 devices, save/load messages, settings file across runs, missing/write-protected drives, PRESS SPACE on the intro, nothing on the ending)"; $PY tools/striptest.py 2>&1 | grep -E "^FAIL|^STRIP"
echo "== yntest (Adso's night question: Y/N in English, S/N in Spanish; the phrase ends in Y/N)"; $PY tools/yntest.py 2>&1 | grep -E "^FAIL|^YN"
echo "== phrasetest (the panel phrase on the REAL frame clock: 7.5 frames = 150 ms a character, as the CPC)"; $PY tools/phrasetest.py 2>&1 | grep -E "^FAIL|^PHRASE|^ok"
echo "== pagetest (the parchment page turn: the fast span/blit paths against the old per-pixel ones, screen for screen at every animation frame)"; $PY tools/pagetest.py 2>&1 | grep -E "^FAIL|^PAGE|^ok"
echo "== waittest (the CPC no-wait rule: the QL flag against the original CPC code's [0x2618] on walk1)"; $PY tools/waittest.py 2>&1 | grep -E "^FAIL|^WAIT|^ok"
echo "== turntest (90-degree turns: a tap = 1 turn, held = 1 a step, on the KEYROW and the typed paths; no double count)"; $PY tools/turntest.py 2>&1 | grep -E "^FAIL|^TURN"
echo "== memtest (asm memcpy/memmove/memset vs the C references: overlaps, parities, lengths)"; $PY tools/memtest.py --seed $RANDOM 2>&1 | grep -E "^FAIL|^MEM"
echo "== spiraltest (room build: the CPC's spiral order vs its Z80 code; 116 screens day/night identical to the old build; black until drawn)"; $PY tools/spiraltest.py 2>&1 | grep -E "^FAIL|^SPIRAL"
echo "== gentest (the room generator in asm: every screen, day and night, tile buffers and screens = the C++)"; $PY tools/gentest.py 2>&1 | grep -E "^FAIL|^GEN"
echo "== inttest (the interleaved mixing buffer: the new kernels and screen copy against the plane ones, every palette)"; $PY tools/inttest.py --cases 3000 --seed $RANDOM 2>&1 | grep -E "^FAIL|^INT| [1-9][0-9]* differ"
echo "== qstest (QSound detection: QDOS any even vector, SMSQ/E only \$C0000-\$FFFFF; start-up silencing)"; $PY tools/qstest.py 2>&1 | grep -E "^FAIL|^QSTEST"
echo "== beepspeed (the beeper parchment tune: table = DOS tempo; in the game every note at its frame or one later)"; $PY tools/beepspeed.py 2>&1 | grep -E "^FAIL|^BEEPSPEED"

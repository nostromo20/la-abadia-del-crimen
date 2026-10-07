; ============================================================
; qlstart.s - entry, self-relocation, header, main loop (hybrid build)
; La Abadia del Crimen - QL Port
; ============================================================
; The hybrid image is linked at address 0 by m68k-linux-gnu-ld and loaded by
; LBYTES at whatever address RESPR returned. tools/mkimage.py appends a
; relocation table after the image:
;     dc.l  n                 ; number of entries
;     dc.l  off1,off2,...     ; image offsets of the longwords to relocate
; _start adds the load address to each one (once: reloc_done guards against a
; second CALL), then clears the BSS (which overlaps the table), runs the C++
; static constructors and enters the game loop on its own stack.
;
; Fixed header (read by the unicorn harness, tools/qlrun.py):
;   +0  bra.w _start_real
;   +4  'ABQL'           tag
;   +8  build id (long)
;   +12 fault word (long) - ql_fault() stores a code here and halts
;   +16 tick counter (long)
;   +20 50 Hz frame counter (long) - bumped by the poll routine
;   +24 heap high-water mark (long)
;   +28 harness flags (long): bit 0 fill the state block, bit 1 skip the intro
;       (byte +28 sound mode, +29 diagnostics, +30 test flags: see qltest.s;
;       byte +31: bit 0 state block, bit 1 skip the intro, diagnostics bit 2 no
;       BEEP IPC, bit 3 no KEYROW IPC, bit 4 no console drain)
;   +288 test script area (1024 bytes)
;   +32 state block, STATE_SIZE (256) bytes - filled by abadia_state()
; ============================================================

HDR_FAULT       equ 12
HDR_TICKS       equ 16
HDR_FRAMES      equ 20
HDR_HEAP        equ 24
HDR_STATE       equ 32
STATE_SIZE      equ 256

MT_LPOLL        equ $1C
MT_RPOLL        equ $1D
MT_IPCOM        equ $11
MT_INF          equ $00

GAME_STACK_SIZE equ 8192

; diagnostic phases (diag_phase); C++ stages use $10-$2F via ql_phase()
PH_WAIT         equ $01
PH_KEYS         equ $02
PH_TICK         equ $03
PH_SYNC         equ $04
PH_STATE        equ $05
PH_INIT         equ $06
POLL_STACK_SIZE equ 1024

        section .text.start,code

        xref    abadia_init,abadia_tick,abadia_sync,abadia_state
        xref    ql_heap_used,snd_poll,beep_tick,ql_hg_prewarm
        xref    __image_end,__bss_start,__bss_end
        xref    __init_array_start,__init_array_end
        xdef    _start,ql_fault,harness_tick_done,ql_hdr

_start:
ql_hdr:
        bra.w   _start_real
        dc.b    "ABQL"
        dc.l    BUILD_ID
hdr_fault:
        dc.l    0
hdr_ticks:
        dc.l    0
hdr_frames:
        dc.l    0
hdr_heap:
        dc.l    0
hdr_harness:
        dc.l    0                       ; nonzero: fill the state block every step
hdr_state:
        ds.b    STATE_SIZE
hdr_script:                             ; +288: test script area (qltest.s)
        ds.b    1024
hdr_savename:                           ; +1312: the start-up SAVE DEVICE, a QDOS string of up
        dc.w    0                       ; to 40 characters: its part up to the first _ (ql_strip.cpp),
        ds.b    40                      ; used when no settings file abadia_cfg is found. The loader
                                        ; may set it (POKE_W a+1312, length, characters from a+1314).
                                        ; Empty (the default since 2026-10-05): MDV1_
        xdef    hdr_savename

reloc_done:
        dc.w    0

_start_real:
        movem.l d1-d7/a0-a6,-(sp)

        ; ---- relocate (first CALL only) ----
        lea     _start(pc),a5               ; A5 = load address
        lea     reloc_done(pc),a0
        tst.w   (a0)
        bne.s   .relocated
        move.l  #__image_end,d0             ; link-time value = image size (linked at 0)
        lea     0(a5,d0.l),a0               ; A0 -> relocation table
        move.l  (a0)+,d1                    ; entry count
        move.l  a5,d2
        bra.s   .rl_next
.rl_loop:
        move.l  (a0)+,d0
        add.l   d2,0(a5,d0.l)
.rl_next:
        subq.l  #1,d1
        bpl.s   .rl_loop
        lea     reloc_done(pc),a0
        move.w  #1,(a0)
.relocated:

        ; ---- clear BSS (after relocation: it overlaps the table) ----
        move.l  #__bss_start,a0             ; relocated values from here on
        move.l  #__bss_end,a1
.bss_clr:
        cmp.l   a1,a0
        bhs.s   .bss_done
        clr.w   (a0)+
        bra.s   .bss_clr
.bss_done:

        ; ---- own stack ----
        move.l  sp,a0
        lea     game_stack_top,sp
        move.l  a0,-(sp)                    ; caller's SP, restored on exit

        ; ---- C++ static constructors ----
        move.l  #__init_array_start,a4
.ctor:
        cmp.l   #__init_array_end,a4
        bhs.s   .ctor_done
        move.l  (a4)+,a0
        jsr     (a0)
        bra.s   .ctor
.ctor_done:

        move.b  #PH_INIT,diag_phase
        bsr     platform_init
        moveq   #1,d0                   ; intro parchment ...
        move.l  hdr_harness(pc),d1
        btst    #1,d1                   ; ... unless the harness set bit 1 (skip intro)
        beq.s   .intro
        moveq   #0,d0
.intro:
        move.l  d0,-(sp)
        jsr     abadia_init
        addq.l  #4,sp
        bsr     platform_after_init

        ; ---- main loop: one logic step every 130 ms (6.5 frames) ----
main_loop:
        move.b  #PH_WAIT,diag_phase
        bsr     wait_tick
        move.b  #PH_KEYS,diag_phase
        bsr     scan_keyrows
        move.b  key_state+QK_ESC,d0
        bne.s   main_exit
        bsr     beep_step               ; after the keyboard read (see wait_tick)

        move.b  #PH_TICK,diag_phase
        jsr     abadia_tick
        move.b  #PH_SYNC,diag_phase
        jsr     abadia_sync
        move.b  #PH_STATE,diag_phase

        move.b  hdr_harness+3(pc),d0    ; state block only for the harness (bit 0;
        btst    #0,d0                   ; the loader may use byte +28 for sound)
        beq.s   .no_state
        lea     hdr_state(pc),a0
        move.l  a0,-(sp)
        jsr     abadia_state
        addq.l  #4,sp
.no_state:
        jsr     ql_heap_used
        lea     hdr_heap(pc),a0
        move.l  d0,(a0)
        lea     hdr_ticks(pc),a0
        addq.l  #1,(a0)
        bsr     test_log                ; qltest.s: self-log (header +30 bit 1)
harness_tick_done:
        nop
        bra.s   main_loop

main_exit:
        bsr     test_flush              ; qltest.s: last log records to the file
        bsr     platform_exit
        move.l  (sp)+,a0
        move.l  a0,sp
        movem.l (sp)+,d1-d7/a0-a6
        moveq   #0,d0
        rts

; ------------------------------------------------------------
; ql_fault(code) - stores the fault code in the header and halts
; ------------------------------------------------------------
ql_fault:
        move.l  4(sp),d0
        lea     hdr_fault(pc),a0
        move.l  d0,(a0)
.halt:
        bra.s   .halt

; ------------------------------------------------------------
; wait_tick - waits until the next step is due: STEP_FRAMES = 6 frames = 120 ms, the CPC's
; (its main loop waits for 36 interrupts of 300 Hz, CPC 0x2614; docs/speed_vs_cpc.md). The
; port's step was 130 ms before 2026-10-05 (6 and 7 frames alternately: STEP_130).
; No wait at all while ql_sin_espera is set (ql_game.cpp: the CPC sets its wait to 0 while
; no cursor key has been pressed for 50 passes and no phrase is showing, 0x41a8).
; next_tick advances by STEP_FRAMES; if the game is
; running late it does not try to catch up.
; ------------------------------------------------------------
STEP_FRAMES     equ 6
STEP_130        equ 0                       ; 1: the old 6/7-frame (130 ms) schedule
        xref    ql_sin_espera
wait_tick:
        tst.b   ql_sin_espera               ; the CPC's "no wait": go on at once, and
        beq.s   .wt_loop                    ; restart the schedule from now
        ; ... but no faster than the CPC's no-wait step (~50 ms: 2 and 3 frames
        ; alternately). A 68008 takes longer than that anyway (3.67 frames), so it
        ; never waits here; QPC2 / a fast emulator would otherwise run flat out.
        ; Only with the poll seen running (else the frames only move in .wt_loop).
.wt_nw:
        move.l  hdr_frames(pc),d0
        tst.b   poll_seen
        beq.s   .wt_nwgo
        move.l  nw_due(pc),d1
        sub.l   d0,d1
        ble.s   .wt_nwgo
.wt_nwspin:
        cmp.l   hdr_frames(pc),d0           ; wait for the poll's next frame
        beq.s   .wt_nwspin
        bra.s   .wt_nw
.wt_nwgo:
        lea     nw_phase(pc),a0
        eor.w   #1,(a0)
        moveq   #2,d1
        add.w   (a0),d1                     ; 2, 3, 2, 3 .. frames
        add.l   d0,d1
        lea     nw_due(pc),a0
        move.l  d1,(a0)
        addq.l  #STEP_FRAMES,d0
        lea     next_tick(pc),a0
        move.l  d0,(a0)
        rts
.wt_loop:
        move.l  hdr_frames(pc),d0
        move.l  next_tick(pc),d1
        sub.l   d0,d1                       ; frames still to wait
        ble.s   .wt_due
        ; Step the beeper (ql_beeper.c) only while 2 or more frames are still to
        ; wait, so a whole frame (20 ms) always separates a BEEP from the keyboard
        ; read: on Q-emuLator a KEYROW soon after a BEEP reads garbage (0x91 seen;
        ; a phantom ESC quits the game) or hangs. wait_tick may be entered late in
        ; a frame, so "a later frame" is not enough. main_loop also steps the
        ; beeper just after the keyboard read (beep_step there).
        cmp.l   #2,d1
        blt.s   .wt_nobeep
        bsr     beep_step
.wt_nobeep:
        ; QL_HGRID_CACHE: with 3 or more frames still to wait (60 ms, at least 40), fill one
        ; window the characters are likely to need into the height-grid cache (4-16 ms on the
        ; 68008); spare time only, never on a step's own time (RejillaPantalla.cpp)
        cmp.l   #3,d1
        blt.s   .wt_nowarm
        jsr     ql_hg_prewarm
        tst.l   d0
        bne     .wt_loop                    ; filled one: look at the clock again
.wt_nowarm:
        ; Busy-wait for the poll to count the next frame, as the author's
        ; other QL games do. NOT MT.SUSJB: with SuperBASIC's job suspended
        ; every frame, Q-emuLator delivered keys only on release, never showed
        ; them to KEYROW and never auto-repeated them (2026-10-02).
        move.l  hdr_frames(pc),d4
        move.l  #WT_SPIN,d2
.wt_spin:
        cmp.l   hdr_frames(pc),d4
        bne.s   .wt_polled
        subq.l  #1,d2
        bne.s   .wt_spin
        ; Fallback: no frame counted for ~0.8 s at QL speed, so the poll is not
        ; running: count the frame here (the game goes on, without sound) and
        ; flag it for the heartbeat (block C red). Only while the poll has never
        ; been seen: WT_SPIN is a 68008 figure, a few ms on QPC2 / a fast
        ; emulator, where this counted frames itself and the game ran flat out.
        tst.b   poll_seen
        beq.s   .wt_nopoll
        move.l  #WT_SPIN,d2
        bra.s   .wt_spin
.wt_nopoll:
        st      poll_dead
        lea     hdr_frames(pc),a0
        addq.l  #1,(a0)
.wt_polled:
        bra.s   .wt_loop
.wt_due:
        neg.l   d1                          ; frames late
        cmp.l   #STEP_FRAMES+1,d1           ; (7: as before)
        blo.s   .wt_ontime
        move.l  hdr_frames(pc),d0           ; late by a whole step: restart the clock
        lea     next_tick(pc),a0
        move.l  d0,(a0)
.wt_ontime:
        moveq   #STEP_FRAMES,d0
        if      STEP_130
        lea     tick_phase(pc),a0
        moveq   #6,d0
        eor.w   #1,(a0)
        beq.s   .wt_six
        moveq   #7,d0
.wt_six:
        endif
        lea     next_tick(pc),a0
        add.l   d0,(a0)
        rts

WT_SPIN         equ 100000                  ; ~40 frames of spinning at 7.5 MHz

next_tick:
        dc.l    0
nw_due:
        dc.l    0                           ; the earliest frame for the next no-wait step
nw_phase:
        dc.w    0

; beep_step: steps the beeper once per new 50 Hz frame (at most one IPC BEEP,
; in user mode). Trashes D0-D1/A0-A1.
beep_step:
        move.l  hdr_frames(pc),d0
        cmp.l   beep_frame(pc),d0
        beq.s   .bs_out
        lea     beep_frame(pc),a0
        move.l  d0,(a0)
        move.l  d0,-(sp)
        jsr     beep_tick
        addq.l  #4,sp
.bs_out:
        rts
beep_frame:                                 ; the frame the beeper was last stepped for
        dc.l    -1
tick_phase:
        dc.w    0

; ------------------------------------------------------------
; QDOS trap wrappers - the only trap sites in the hybrid build, so the
; harness can intercept them by address. Registers as for the trap.
; ------------------------------------------------------------
        xdef    do_trap1,do_trap2,do_trap3
do_trap1:
        trap    #1
        rts
do_trap2:
        trap    #2
        rts
do_trap3:
        trap    #3
        rts

; ------------------------------------------------------------
; 50 Hz poll routine: counts frames
; ------------------------------------------------------------
; Called by QDOS 50 times a second, in supervisor mode on the system stack,
; A3 = link block, A6 = system variables (preserved: C saves A2-A6).
; The sound engine runs on its own stack (POLL_STACK_SIZE bytes in the BSS)
; so the small system stack only holds the return address and two longs.
poll_routine:
        lea     hdr_frames(pc),a0
        addq.l  #1,(a0)
        st      poll_seen               ; the poll runs: wait_tick waits for it, however long
        bsr     test_poll               ; qltest.s: poll count, main-loop silence
        tst.b   ql_hdr+29               ; diagnostics on (loader: POKE a+29,1)?
        beq.s   .pr_nodiag
        bsr     diag_draw
.pr_nodiag:
        tst.b   poll_busy               ; never re-entered (no TAS: read-modify-write
        bne.s   .pr_out                 ; bus cycles are best avoided on the QL)
        st      poll_busy
        move.l  sp,a0
        lea     poll_stack_top,sp
        move.l  a0,-(sp)
        jsr     snd_poll                ; CPC sound engine: 6 x 300 Hz steps
        move.l  (sp)+,sp
        clr.b   poll_busy
.pr_out:
        rts

        even
poll_link:
        dc.l    0
        dc.l    0

platform_init:
        bsr     con_open                ; qlhooks.s: keyboard channel (as the author's other games)
        bsr     ar_setup                ; qlhooks.s: fast auto-repeat while running
        bsr     init_unpack_lut
        bsr     qsound_init
        btst    #1,ql_hdr+31            ; the intro follows: the loader's screen (already
        bne.s   .pi_clear               ; Mode 8) stays up until the parchment dissolves in
        moveq   #MT_DMODE,d0
        moveq   #-1,d1                  ; read the mode
        moveq   #-1,d2
        bsr     do_trap1
        cmp.b   #8,d1
        beq.s   .pi_keep
.pi_clear:
        moveq   #MT_DMODE,d0
        moveq   #8,d1
        moveq   #-1,d2
        bsr     do_trap1
        move.w  #COL_BLACK,d0
        bsr     clear_screen
.pi_keep:
        move.l  #2,-(sp)                ; day palette until the game sets one
        bsr     ql_set_palette
        addq.l  #4,sp
        lea     poll_link(pc),a0
        lea     poll_routine(pc),a1
        move.l  a1,4(a0)
        moveq   #MT_LPOLL,d0
        bsr     do_trap1
        move.l  hdr_frames(pc),d0
        lea     next_tick(pc),a0
        move.l  d0,(a0)
        rts

platform_after_init:
        rts

platform_exit:
        bsr     ar_restore              ; qlhooks.s: the QL's auto-repeat back
        bsr     con_close               ; qlhooks.s
        lea     poll_link(pc),a0
        moveq   #MT_RPOLL,d0
        bsr     do_trap1
        rts

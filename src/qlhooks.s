; ============================================================
; qlhooks.s - platform hooks called by the compiled C++ (see cpp/port/ql_port.h)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; C calling convention (m68k SVR4, GCC): arguments on the stack as longs,
; 4(sp) = first; result in D0; D0-D1/A0-A1 may be clobbered, everything else
; must be preserved.
;
; Screen geometry: CPC play area x 32..287, y 0..159 -> QL x 0..255,
; y PLAY_Y..PLAY_Y+159 (Mode 8, 1:1), panel CPC x 32..287 at PANEL_QL_Y.
; Layout A (chosen 2026-10-03): the CPC's 200 lines centred in the
; QL's 256, as on the CPC - 28 lines above, 28 below.
; ============================================================

PLAY_Y          equ 28              ; QL line of CPC line 0 (layout A: centred)
PANEL_QL_Y      equ 188             ; QL line of CPC panel line 160 (PLAY_Y + 160)

        ifnd    USE_KEYROW
USE_KEYROW      equ 1                   ; 1 = also read KEYROW row 1 (see con_open notes)
        endc
QK_UP           equ 0
QK_DOWN         equ 1
QK_LEFT         equ 2
QK_RIGHT        equ 3
QK_SPACE        equ 4
QK_Q            equ 5
QK_R            equ 6
; A typed Q or R counts as pressed for QR_STEPS steps (~0.5 s: 4 x 120 ms), every other typed key
; for one: the mirror code needs Q and R down in the same step (Logica::pulsadoQR, the
; only reader of QK_Q/QK_R), and neither is on a KEYROW row we read, so both come only
; as typed characters, one each (QDOS auto-repeats only the last key held). QR_STEPS 1 =
; the old behaviour.
QR_STEPS        equ 4
QK_S            equ 7
QK_N            equ 8
QK_ESC          equ 9
QK_F1           equ 10
QK_F2           equ 11
QK_F3           equ 12                  ; F3 cycles the save device (ql_strip.cpp)
QK_F5           equ 13                  ; F5 shows / hides the help strip
QK_Y            equ 14                  ; Y: yes to Adso's question in the English game (S in Spanish)
QK_COUNT        equ 15
; the keys KEYROW reads (key_map: row 1, and A/D/W on rows 4/5 as LEFT/RIGHT/UP)
KR_KEYS         equ (1<<QK_UP)|(1<<QK_DOWN)|(1<<QK_LEFT)|(1<<QK_RIGHT)|(1<<QK_SPACE)|(1<<QK_ESC)

        xdef    ql_key_down,ql_ay_write,ql_play_fill,ql_play_pixel
        xdef    ql_file_save,ql_file_load,ql_play_triangle
        xdef    ql_play_tile,ql_play_blit,ql_set_palette,ql_panel_present
        xdef    ql_play_blit_p
        xdef    ql_debug,ql_rom_image,scan_keyrows,key_state

; ------------------------------------------------------------
; keyboard: KEYROW via MT.IPCOM for rows 1,3,5,6,7
; key_state[QK_*] = 1 while held
; ------------------------------------------------------------
scan_keyrows:
        movem.l d2-d7/a2-a6,-(sp)
        bsr     autopilot_keys          ; qltest.s: keys from the script (header +30 bit 0)
        tst.w   d0
        bne     .sk_done
        ; A BEEP less than 2 frames ago (a late step: wait_tick did not wait):
        ; on Q-emuLator the KEYROW would read garbage, so keep last step's keys
        ; (held keys stay held) and only take the typed ones.
        move.l  ql_hdr+20,d0
        sub.l   beep_last,d0
        cmp.l   #2,d0
        blo     .sk_typed
        lea     key_state,a0        ; every key released until read below
        moveq   #QK_COUNT-1,d0
.sk_clr:
        clr.b   (a0)+
        dbra    d0,.sk_clr
        ifeq    USE_KEYROW
        bra     .sk_typed
        endc
        btst    #3,ql_hdr+31            ; diagnostics: header +31 bit 3 = no KEYROW IPC
        bne     .sk_typed
        ; KEYROW the usual way: A6 = system
        ; variables from MT.INF, D3 = 0, one IPC transaction per frame.
        moveq   #MT_INF,d0
        bsr     do_trap1
        move.l  a0,a6
        lea     key_map(pc),a4
.sk_next:
        moveq   #0,d4
        move.b  (a4)+,d4                ; row, $FF = end
        cmp.b   #$FF,d4
        beq.s   .sk_typed
        lea     kr_block(pc),a3
        move.b  d4,6(a3)                ; row number in the IPC command
        moveq   #MT_IPCOM,d0
        moveq   #0,d3
        bsr     do_trap1
        move.b  d1,d5                   ; row bits
        beq.s   .sk_key
        st      keyrow_alive            ; KEYROW works on this machine (a key seen)
.sk_key:
        moveq   #0,d6
        move.b  (a4)+,d6                ; bit, $FF = end of row
        cmp.b   #$FF,d6
        beq.s   .sk_next
        moveq   #0,d7
        move.b  (a4)+,d7                ; QK index
        btst    d6,d5
        beq.s   .sk_key
        lea     key_state,a0
        move.b  #1,0(a0,d7.w)           ; OR: W and UP both mean forward
        bra.s   .sk_key
.sk_typed:
        ; each key typed since the last step counts as pressed for this one
        ; step only (a time window spanned two steps: one tap turned twice);
        ; Q and R for QR_STEPS steps (key_typed holds the steps left)
        btst    #4,ql_hdr+31            ; diagnostics: header +31 bit 4 = no console drain
        bne.s   .sk_nodrain
        bsr     con_drain
.sk_nodrain:
        lea     key_typed,a0
        lea     key_state,a1
        moveq   #0,d2
.sk_t:
        tst.b   0(a0,d2.w)
        beq.s   .sk_tn
        subq.b  #1,0(a0,d2.w)
        ; once KEYROW has shown a key, the keys it reads come from it alone (held, as the CPC
        ; reads them once a pass): a typed character of the same key, arriving a step later
        ; (or an auto-repeat of a tap), would count the tap twice (two 90-degree turns)
        tst.b   keyrow_alive
        beq.s   .sk_tset
        move.w  #KR_KEYS,d3
        btst    d2,d3
        bne.s   .sk_tn
.sk_tset:
        move.b  #1,0(a1,d2.w)
.sk_tn:
        addq.w  #1,d2
        cmp.w   #QK_COUNT,d2
        blo.s   .sk_t
.sk_done:
        movem.l (sp)+,d2-d7/a2-a6
        rts

        even
kr_block:
        dc.b    9,1,0,0,0,0,0,2         ; KEYROW, row patched at +6

; row, then (bit, key) pairs, $FF ends a row; $FF row ends the table
; row 1: ENTER(0) LEFT(1) UP(2) ESC(3) RIGHT(4) \(5) SPACE(6) DOWN(7)
; row 3: S = bit 3     row 5: R = bit 4     row 6: Q = bit 3     row 7: N = bit 6
; Only row 1 is read (one IPC transaction per step, as in the QL PoP); the
; one-shot keys F1/F2/Q/R/S/N arrive as typed characters (con_drain).
; W/A/D duplicate UP/LEFT/RIGHT (2026-10-02 test: do letter keys reach the
; QL differently from the cursor keys under Q-emuLator?)
key_map:
        dc.b    1, 1,QK_LEFT, 2,QK_UP, 3,QK_ESC, 4,QK_RIGHT, 6,QK_SPACE, 7,QK_DOWN, $FF
        dc.b    4, 4,QK_LEFT, 6,QK_RIGHT, $FF           ; row 4: A = bit 4, D = bit 6
        dc.b    5, 1,QK_UP, $FF                         ; row 5: W = bit 1
        dc.b    $FF
        even

; ------------------------------------------------------------
; Typed keys: a console channel of our own, drained every step with IO.FBYTE
; (timeout 0) - as the author's other QL games do, which read held
; keys reliably in Q-emuLator. Each game key typed counts as pressed for
; the next step; the one-shot keys (F1/F2/Q/R/S/N, and ESC) come only from
; here, the arrows and SPACE also from KEYROW row 1 (true held state).
; History, 2026-10-02 in Q-emuLator: KEYROW returned no
; key at all (row 1 = 0 for a whole session, with and without QSound), and
; with A6/D3 set the call did not return while a key was held - the game
; stopped until release. Cause found by comparing with another QL game that reads
; KEYROW fine in the SAME Q-emuLator configuration: the game suspended
; SuperBASIC's job (MT.SUSJB) every frame; it now busy-waits instead.
; KEYROW row 1 gives the true held state; a held key also auto-repeats
; quickly (ar_setup, restored on exit) in case KEYROW shows nothing.
; ------------------------------------------------------------
SV_ARDEL        equ $8C                 ; sysvar: auto-repeat delay (frames)
SV_ARFRQ        equ $8E                 ; sysvar: auto-repeat interval (frames)
AR_DELAY        equ 15                  ; 300 ms: a tap types one key (8 = 160 ms before 2026-10-05:
                                        ; a ~200 ms tap typed two, two 90-degree turns)
AR_RATE         equ 2                   ; then a key every 40 ms: several per 120 ms step
CON_OPEN        equ $01                 ; trap #2 IO.OPEN
CON_CLOSE       equ $02                 ; trap #2 IO.CLOSE
CON_FBYTE       equ $01                 ; trap #3 IO.FBYTE

con_open:
        movem.l d1-d3/a0-a1,-(sp)
        lea     con_name(pc),a0
        moveq   #CON_OPEN,d0
        moveq   #-1,d1                  ; this job
        moveq   #0,d3                   ; open existing
        bsr     do_trap2
        tst.l   d0
        bmi.s   .co_fail
        move.l  a0,con_id
        bra.s   .co_out
.co_fail:
        clr.l   con_id
.co_out:
        movem.l (sp)+,d1-d3/a0-a1
        rts

con_close:
        movem.l d0-d3/a0-a1,-(sp)
        move.l  con_id,d0
        beq.s   .cc_out
        move.l  d0,a0
        moveq   #CON_CLOSE,d0
        bsr     do_trap2
        clr.l   con_id
.cc_out:
        movem.l (sp)+,d0-d3/a0-a1
        rts

; ar_setup / ar_restore - a held key repeats quickly while the game runs;
; the QL's own auto-repeat settings come back on exit.
ar_setup:
        movem.l d0-d3/a0-a1,-(sp)
        moveq   #MT_INF,d0
        bsr     do_trap1                ; A0 = system variables
        move.l  a0,ar_sysvars
        move.w  SV_ARDEL(a0),ar_saved
        move.w  SV_ARFRQ(a0),ar_saved+2
        move.w  #AR_DELAY,SV_ARDEL(a0)
        move.w  #AR_RATE,SV_ARFRQ(a0)
        movem.l (sp)+,d0-d3/a0-a1
        rts

ar_restore:
        move.l  a0,-(sp)
        move.l  ar_sysvars,d0
        beq.s   .ar_out
        move.l  d0,a0
        move.w  ar_saved,SV_ARDEL(a0)
        move.w  ar_saved+2,SV_ARFRQ(a0)
.ar_out:
        move.l  (sp)+,a0
        rts

; con_drain - read every waiting character and flag the game keys among them
; (kq_mark). Called by scan_keyrows (D2-D7/A2-A6 saved there).
con_drain:
.cd_next:
        move.l  con_id,d0
        beq.s   .cd_out
        move.l  d0,a0
        moveq   #CON_FBYTE,d0
        moveq   #0,d3                   ; poll only, never wait
        bsr     do_trap3
        tst.l   d0
        bne.s   .cd_out                 ; nothing waiting (or an error)
        bsr.s   kq_mark
        bra.s   .cd_next
.cd_out:
        rts

; kq_mark - D1.B = QL key code: if it is a game key, flag it as typed.
; Uses D0/A2.
kq_mark:
        lea     kq_codes(pc),a2
.km_find:
        move.b  (a2)+,d0
        beq.s   .km_out                 ; not a game key
        cmp.b   d0,d1
        beq.s   .km_hit
        addq.l  #1,a2
        bra.s   .km_find
.km_hit:
        moveq   #0,d0
        move.b  (a2),d0
        lea     key_typed,a2
        cmp.b   #QK_Q,d0
        beq.s   .km_qr
        cmp.b   #QK_R,d0
        beq.s   .km_qr
        move.b  #1,0(a2,d0.w)           ; this step only
        rts
.km_qr:
        move.b  #QR_STEPS,0(a2,d0.w)    ; Q, R: QR_STEPS steps (typed again: from now)
.km_out:
        rts

con_name:
        dc.w    4
        dc.b    'con_'
        even

; QL key code, game key; 0 ends the table
kq_codes:
        dc.b    $D0,QK_UP, $D8,QK_DOWN, $C0,QK_LEFT, $C8,QK_RIGHT
        dc.b    $20,QK_SPACE, $1B,QK_ESC, $E8,QK_F1, $EC,QK_F2, $F0,QK_F3, $F8,QK_F5
        dc.b    'Q',QK_Q, 'q',QK_Q, 'R',QK_R, 'r',QK_R
        dc.b    'S',QK_S, 's',QK_S, 'N',QK_N, 'n',QK_N, 'Y',QK_Y, 'y',QK_Y
        dc.b    'W',QK_UP, 'w',QK_UP, 'A',QK_LEFT, 'a',QK_LEFT, 'D',QK_RIGHT, 'd',QK_RIGHT
        dc.b    0
        even

; int ql_key_down(int key)
ql_key_down:
        move.l  4(sp),d1
        moveq   #0,d0
        cmp.l   #QK_COUNT,d1
        bhs.s   .kd_out
        lea     key_state,a0
        move.b  0(a0,d1.l),d0
.kd_out:
        rts

; ------------------------------------------------------------
; sound: stubs until step 7
; ------------------------------------------------------------
ql_debug:
        rts

; ------------------------------------------------------------
; QSound AY (step 7). Present when QDOS has SV.AYJMP (sysvar +$164) set;
; found by qsound_init at start-up. Register write as in the author's
; earlier QSound driver: latch the register number, then write the value.
; ------------------------------------------------------------
AY_DATA_PORT    equ $000C2000
AY_CTRL_PORT    equ $000C2002

; ------------------------------------------------------------
; QL_BEEPER (cpp/port/ql_beeper.c). Called from the main loop's frame wait
; (USER mode), never from the poll: one MT.IPCOM BEEP, as the author's
; other QL games send it (A6 = system variables, D3 = 0). The block's
; last byte is the reply spec and MUST be 0: BEEP sends nothing back, and a
; reply spec makes QDOS wait for a nibble that never comes (Q-emuLator hangs).
; void ql_beep_ipc(const u8 *p8)  - the 8 parameter bytes
; ------------------------------------------------------------
        xdef    ql_beep_ipc,ql_qsound,beep_count
ql_beep_ipc:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes saved -> arg at 48
        btst    #2,ql_hdr+31            ; diagnostics: header +31 bit 2 = no BEEP IPC
        bne.s   .bp_out                 ; (the sequencer still runs)
        move.l  ar_sysvars,d0
        beq.s   .bp_out                 ; not set up yet: silent
        move.l  d0,a6
        move.l  48(sp),a0
        lea     beep_block+6,a1
        moveq   #7,d0
.bp_cp:
        move.b  (a0)+,(a1)+
        dbra    d0,.bp_cp
        lea     beep_block,a3
        moveq   #MT_IPCOM,d0
        moveq   #0,d3
        bsr     do_trap1
        addq.l  #1,beep_count           ; for the self-log (qltest.s)
        move.l  ql_hdr+20,beep_last     ; scan_keyrows keeps 2 frames away from it
        ; Q-emuLator: a KEYROW in the same frame as a BEEP reads garbage (0x91,
        ; probe 2026-10-03) or hangs, so the caller (qlstart.s beep_step) never
        ; issues a BEEP on a frame that is followed by the keyboard read.
.bp_out:
        movem.l (sp)+,d2-d7/a2-a6
        rts

        ifnd    RELEASE                 ; (a release build has no harness: ql_game.cpp, RejillaPantalla.cpp)
; int ql_harness_mirror(void) - header +31 bit 6 (harness: the mirror / save-load
; sequence at tick 3, ql_game.cpp); int ql_harness_hgverify(void) - bit 7 (every
; height-grid cache hit verified against a fresh fill)
        xdef    ql_harness_mirror,ql_harness_hgverify
ql_harness_mirror:
        moveq   #0,d0
        btst    #6,ql_hdr+31
        beq.s   .hm_out
        moveq   #1,d0
.hm_out:
        rts
ql_harness_hgverify:
        moveq   #0,d0
        btst    #7,ql_hdr+31
        beq.s   .hv_out
        moveq   #1,d0
.hv_out:
        rts

; int ql_harness_night(void) - header +31 bit 5 (test harness: night from tick 2)
        xdef    ql_harness_night
ql_harness_night:
        moveq   #0,d0
        btst    #5,ql_hdr+31
        beq.s   .hn_out
        moveq   #1,d0
.hn_out:
        rts
        endif                           ; RELEASE

; int ql_frames_real(void) - the 50 Hz frame counter (header +20), or -1 when the harness asks
; for the nominal clock (header +30 bit 2: the step schedule, as the PC oracle; ql_game.cpp)
; int ql_pagina_vieja(void) - header +30 bit 3: the parchment's page turn by the old per-pixel
; paths (the harness's differential check, tools/pagetest.py; Pergamino.cpp)
; (not in the release: no harness there, Pergamino.cpp's old paths are left out with it)
        ifnd    RELEASE
        xdef    ql_pagina_vieja
ql_pagina_vieja:
        moveq   #0,d0
        btst    #3,ql_hdr+30
        beq.s   .pv_out
        moveq   #1,d0
.pv_out:
        rts
; int ql_gen_viejo(void) - header +30 bit 5: the room generator's tile commands in C, not
; a_tile_mueve (tools/gentest.py; Comandos.cpp, ql_port.h ql_gen_asm)
        xdef    ql_gen_viejo
ql_gen_viejo:
        moveq   #0,d0
        btst    #5,ql_hdr+30
        beq.s   .gv_out
        moveq   #1,d0
.gv_out:
        rts
; int ql_espiral_vieja(void) - header +30 bit 4: the room build as before 2026-10-05 (pen 0
; fill, row by row) for tools/spiraltest.py (GeneradorPantallas.cpp, ql_port.h ql_espiral)
        xdef    ql_espiral_vieja
ql_espiral_vieja:
        moveq   #0,d0
        btst    #4,ql_hdr+30
        beq.s   .ev_out
        moveq   #1,d0
.ev_out:
        rts
        endif

        xdef    ql_frames_real
ql_frames_real:
        moveq   #-1,d0
        btst    #2,ql_hdr+30
        bne.s   .fr_nom
        move.l  ql_hdr+20,d0
.fr_nom:
        rts


; int ql_qsound(void) - 1 when the AY (QSound) is in use
ql_qsound:
        moveq   #0,d0
        move.b  qs_present,d0
        rts

; void ql_ay_write(int reg, int val) - called from the 50 Hz poll (snd_poll)
ql_ay_write:
        tst.b   qs_present
        beq.s   .ay_none
        move.l  4(sp),d0
        move.l  8(sp),d1
        lea     AY_DATA_PORT,a0
        lea     AY_CTRL_PORT,a1
        move.b  d0,(a0)                 ; register number
        move.b  #$0F,(a1)               ; latch address
        move.b  #$0A,(a1)               ; inactive
        move.b  d1,(a0)                 ; value
        move.b  #$0E,(a1)               ; write
        move.b  #$0A,(a1)               ; inactive
.ay_none:
        rts

; QSound detection. Header byte +28 (POKEd by the loader): 1 = never use
; QSound, 2 = use it without checking, 0 = detect. The QSound vector
; (SV.AYJMP, system variable +$164) must be set and even. Under QDOS (JS,
; Minerva: MT.INF version "1.xx") any such vector means QSound, as the author's
; other QSound games decide it: on real hardware the QSound ROM may sit in
; the ROM port ($0C000) or be copied to RAM by a Gold Card, so the old test
; "vector in $C0000-$FFFFF" missed it (2026-10-07: no QSound on a real QL).
; Under SMSQ/E (version 2.xx and up: QPC2 ...) the old test stays: QPC2 uses
; that slot for its own AY emulation and $C2000 may be plain RAM there.
; AY.INIT through the vector is only called where it was tested (Q-emuLator,
; vector in $C0000-$FFFFF); elsewhere the chip is silenced through the ports
; (the author's other QSound games never call it).
qsound_init:
        movem.l d3-d4,-(sp)
        move.b  ql_hdr+28,d3
        cmp.b   #1,d3
        beq.s   .qi_none
        moveq   #MT_INF,d0
        bsr     do_trap1                ; A0 = system variables, D2 = version
        move.l  $164(a0),d0             ; SV.AYJMP
        cmp.b   #2,d3
        beq.s   .qi_yes                 ; forced
        tst.l   d0
        beq.s   .qi_none
        btst    #0,d0
        bne.s   .qi_none                ; odd: not code
        rol.l   #8,d2                   ; the version's first character
        cmp.b   #'2',d2
        blo.s   .qi_yes                 ; QDOS: any vector
        bsr.s   .qi_range               ; SMSQ/E: only in the expansion area
        bne.s   .qi_none
.qi_yes:
        move.b  #1,qs_present
        bsr.s   .qi_range
        bne.s   .qi_quiet
        move.l  d0,a0
        moveq   #0,d0                   ; AY.INIT
        jsr     (a0)
        bra.s   .qi_none
.qi_quiet:
        lea     AY_DATA_PORT,a0         ; mixer: all off, volumes 0
        lea     AY_CTRL_PORT,a1
        moveq   #7,d3
        move.b  #$3F,d4
.qi_reg:
        move.b  d3,(a0)
        move.b  #$0F,(a1)
        move.b  #$0A,(a1)
        move.b  d4,(a0)
        move.b  #$0E,(a1)
        move.b  #$0A,(a1)
        moveq   #0,d4
        addq.b  #1,d3
        cmp.b   #11,d3
        blo.s   .qi_reg
.qi_none:
        movem.l (sp)+,d3-d4
        rts
; Z set when D0 lies in the expansion area $C0000-$FFFFF
.qi_range:
        cmp.l   #$C0000,d0
        blo.s   .qr_no
        cmp.l   #$100000,d0
        bhs.s   .qr_no
        cmp.b   d0,d0                   ; Z
        rts
.qr_no:
        moveq   #1,d1                   ; NZ (D1 is free here)
        rts

; ------------------------------------------------------------
; save/load files (QDOS). The name is the QDOS string in the header at
; +1312 (hdr_savename, qlstart.s): mdv2_abadia_sav unless the loader sets it.
; ------------------------------------------------------------
IO_DELET        equ $04
IO_FSTRG        equ $03
IO_SSTRG        equ $07

; int ql_file_save(const char *buf, int len)  -> bytes written or -1
ql_file_save:
        movem.l d2-d4/a2-a5,-(sp)       ; 28 bytes -> args at 32
        move.l  32(sp),a4               ; buffer
        move.l  36(sp),d4               ; length
        moveq   #IO_DELET,d0            ; delete any old file (error ignored)
        moveq   #-1,d1
        lea     hdr_savename,a0
        bsr     do_trap2
        moveq   #IO_OPEN,d0
        moveq   #-1,d1
        moveq   #2,d3                   ; new file
        lea     hdr_savename,a0
        bsr     do_trap2
        tst.l   d0
        bne.s   .fs_err
        move.l  a0,a5                   ; channel (QDOS keeps only D4-D7/A4-A6)
        moveq   #IO_SSTRG,d0
        move.l  d4,d2
        moveq   #-1,d3
        move.l  a4,a1
        bsr     do_trap3
        move.l  d1,d4                   ; bytes written
        tst.l   d0
        beq.s   .fs_wok
        moveq   #-1,d4                  ; a write error (full, write-protected...)
.fs_wok:
        move.l  a5,a0
        moveq   #IO_CLOSE,d0
        bsr     do_trap2
        move.l  d4,d0
        bra.s   .fs_out
.fs_err:
        moveq   #-1,d0
.fs_out:
        movem.l (sp)+,d2-d4/a2-a5
        rts

; int ql_file_load(char *buf, int cap)  -> bytes read or -1
ql_file_load:
        movem.l d2-d4/a2-a5,-(sp)       ; 28 bytes -> args at 32
        move.l  32(sp),a4
        move.l  36(sp),d4
        moveq   #IO_OPEN,d0
        moveq   #-1,d1
        moveq   #1,d3                   ; old file, shared
        lea     hdr_savename,a0
        bsr     do_trap2
        tst.l   d0
        bne.s   .fl_err
        move.l  a0,a5                   ; channel (QDOS keeps only D4-D7/A4-A6)
        moveq   #IO_FSTRG,d0
        move.l  d4,d2
        moveq   #-1,d3
        move.l  a4,a1
        bsr     do_trap3                ; end of file may be reported with D1 > 0
        move.l  d1,d4
        move.l  a5,a0
        moveq   #IO_CLOSE,d0
        bsr     do_trap2
        move.l  d4,d0
        bra.s   .fl_out
.fl_err:
        moveq   #-1,d0
.fl_out:
        movem.l (sp)+,d2-d4/a2-a5
        rts

        ifne    0                       ; (the name before the header field, kept for reference)
save_name:
        dc.w    15
        dc.b    "win1_abadia_sav"
        even
        endc

; unsigned char *ql_rom_image(void)
ql_rom_image:
        move.l  #rom_image,d0
        move.l  d0,a0
        rts

        ifeq    CHARCOL                 ; pre-CHARCOL version (one colour per pen): colour.s replaces it
; ------------------------------------------------------------
; palette: CPC ink (0-3) -> Mode 8 colour word
; ------------------------------------------------------------
; void ql_set_palette(int pal)
; The QL has no colour palette: the screen holds colours, not pens. So:
;  - palette 0 (the CPC's all-black palette, used to hide drawing) blanks the
;    screen and keeps the current colours for what is drawn next;
;  - any other change rebuilds the tables and RECOLOURS what is on the screen
;    (old pen -> new colour), which is what a CPC palette change does.
ql_set_palette:
        move.l  4(sp),d0
        and.w   #3,d0
        bne.s   .sp_real
        clr.w   cur_pal_p1              ; blank: nothing to recolour at the next palette
        move.w  #COL_BLACK,d0           ; black palette: blank the screen
        bra     clear_screen            ; (screen.s; D0-D1/A0 only)
.sp_real:
        move.w  d0,d1
        addq.w  #1,d1                   ; palette+1 (BSS 0 = none built yet)
        cmp.w   cur_pal_p1,d1
        beq     .sp_same                ; tiles already built for it
        move.w  cur_pal_p1,old_pal_p1
        move.w  d1,cur_pal_p1
        lea     ink_words,a1
        lea     old_ink,a0
        move.l  (a1),(a0)+              ; keep the old colours for the recolour
        move.l  4(a1),(a0)
        lsl.w   #3,d0                   ; 4 words per palette
        lea     palettes(pc),a0
        adda.w  d0,a0
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        ; rebuild the per-pixel table: ink_px[pixel*4+ink] = ink_word & pixel mask
        lea     ink_words,a0
        lea     ink_px,a1
        movem.l d2-d3/a2,-(sp)
        lea     pixel_masks(pc),a2      ; pixel_masks is in screen.s
        moveq   #3,d2                   ; pixel
.sp_px:
        move.w  (a2)+,d3
        moveq   #3,d1                   ; ink
        lea     ink_words,a0
.sp_ink:
        move.w  (a0)+,d0
        and.w   d3,d0
        move.w  d0,(a1)+
        dbra    d1,.sp_ink
        dbra    d2,.sp_px
        ; ink_quad[p0<<6|p1<<4|p2<<2|p3] = OR of the four ink_px entries
        lea     ink_quad,a1
        lea     ink_px,a2
        moveq   #0,d2
.sp_quad:
        move.w  d2,d0
        lsr.w   #6,d0
        add.w   d0,d0
        move.w  0(a2,d0.w),d3           ; pixel 0
        move.w  d2,d0
        lsr.w   #4,d0
        and.w   #3,d0
        add.w   d0,d0
        or.w    8(a2,d0.w),d3           ; pixel 1
        move.w  d2,d0
        lsr.w   #2,d0
        and.w   #3,d0
        add.w   d0,d0
        or.w    16(a2,d0.w),d3          ; pixel 2
        move.w  d2,d0
        and.w   #3,d0
        add.w   d0,d0
        or.w    24(a2,d0.w),d3          ; pixel 3
        move.w  d3,(a1)+
        addq.w  #1,d2
        cmp.w   #256,d2
        blt.s   .sp_quad
        ; ink_cpc[b] = ink_quad[p0<<6|p1<<4|p2<<2|p3] for CPC byte b (packed buffer)
        lea     ink_cpc,a1
        lea     unpack_lut,a2
        moveq   #0,d2
.sp_cpc:
        moveq   #0,d0
        moveq   #3,d1
.sp_cpk:
        lsl.w   #2,d0
        or.b    (a2)+,d0
        dbra    d1,.sp_cpk
        add.w   d0,d0
        lea     ink_quad,a0
        move.w  0(a0,d0.w),(a1)+
        addq.w  #1,d2
        cmp.w   #256,d2
        blt.s   .sp_cpc
        movem.l (sp)+,d2-d3/a2
        tst.w   old_pal_p1
        beq.s   .sp_first               ; nothing on screen in the old colours yet
        bsr     recolour_screen
.sp_first:
        cmp.w   #2,cur_pal_p1           ; palette 1 (a parchment) draws no tiles (its tile
        beq.s   .sp_same                ; area holds the off-screen page, ql_off_*)
        bra     build_tiles
.sp_same:
        rts

; ------------------------------------------------------------
; recolour_screen - maps every pixel of QL lines 0..RECOLOUR_LINES-1 from
; the old palette (old_ink) to the current one (ink_words): colour c ->
; pen p with old_ink[p] = c -> ink_words[p]; colours not in the old palette
; stay. A 256-word table handles two pixels at a time: index = high-byte
; nibble << 4 | low-byte nibble (G,F,G,F / R,B,R,B of two pixels).
; ------------------------------------------------------------
RECOLOUR_LINES  equ 200                 ; the CPC screen (play area + panel, or the parchment)

recolour_screen:
        movem.l d2-d7/a2-a3,-(sp)
        ; colour map: cmap[c] for the 8 colour indices (G*4+R*2+B)
        lea     cmap,a0
        moveq   #7,d0
.rc_id:
        move.b  d0,0(a0,d0.w)           ; identity
        dbra    d0,.rc_id
        lea     old_ink,a1
        lea     ink_words,a2
        moveq   #3,d2                   ; pen
.rc_pen:
        move.w  (a1)+,d0
        bsr     .rc_index               ; d1 = colour index of word d0
        move.w  (a2)+,d0
        move.w  d1,d3
        bsr     .rc_index
        move.b  d1,0(a0,d3.w)           ; old colour -> new colour
        dbra    d2,.rc_pen
        ; pair table: rtab[hi nibble << 4 | lo nibble] = new hi nibble << 8 | new lo nibble
        lea     rtab,a1
        moveq   #0,d2                   ; index
.rc_tab:
        moveq   #0,d4                   ; result
        moveq   #1,d5                   ; pixel: 1 = left (bits 3,2), 0 = right (bits 1,0)
.rc_pix:
        move.w  d5,d6
        add.w   d6,d6                   ; shift for this pixel: 2 or 0
        move.w  d2,d0
        lsr.w   #4,d0                   ; hi nibble
        lsr.w   d6,d0
        moveq   #2,d7
        and.w   d0,d7                   ; G bit (of G,F)
        add.w   d7,d7                   ; G*4
        move.w  d2,d0
        lsr.w   d6,d0
        and.w   #3,d0                   ; R,B
        or.w    d0,d7                   ; colour index
        moveq   #0,d1
        move.b  0(a0,d7.w),d1           ; new colour
        move.w  d1,d0
        and.w   #4,d0                   ; new G
        lsr.w   #1,d0                   ; to the G position of the pair (bit 1)
        lsl.w   d6,d0
        lsl.w   #8,d0
        or.w    d0,d4
        and.w   #3,d1                   ; new R,B
        lsl.w   d6,d1
        or.w    d1,d4
        dbra    d5,.rc_pix
        move.w  d4,(a1)+
        addq.w  #1,d2
        cmp.w   #256,d2
        blt.s   .rc_tab
        ; the screen: each word = two pixel pairs (high nibbles, low nibbles)
        lea     SCREEN_BASE,a2
        lea     rtab,a1
        move.w  #RECOLOUR_LINES*64-1,d7
.rc_word:
        move.w  (a2),d0
        move.w  d0,d1
        lsr.w   #8,d1                   ; high byte
        move.w  d1,d2
        and.w   #$F0,d2                 ; hi nibble (pixels 0,1) << 4
        move.w  d0,d3
        lsr.w   #4,d3
        and.w   #$0F,d3                 ; lo nibble (pixels 0,1)
        or.w    d3,d2
        add.w   d2,d2
        move.w  0(a1,d2.w),d4           ; new nibbles for pixels 0,1
        lsl.w   #4,d4                   ; to the upper nibbles of both bytes
        and.w   #$0F,d1                 ; hi nibble (pixels 2,3)
        lsl.w   #4,d1
        move.w  d0,d3
        and.w   #$0F,d3
        or.w    d3,d1
        add.w   d1,d1
        or.w    0(a1,d1.w),d4           ; pixels 2,3 in the lower nibbles
        move.w  d4,(a2)+
        dbra    d7,.rc_word
        movem.l (sp)+,d2-d7/a2-a3
        rts

; colour index (G*4 + R*2 + B) of pixel 0 of the Mode 8 word d0 -> d1
.rc_index:
        moveq   #0,d1
        btst    #15,d0                  ; G of pixel 0
        beq.s   .ri_g
        moveq   #4,d1
.ri_g:
        btst    #7,d0                   ; R
        beq.s   .ri_r
        addq.w  #2,d1
.ri_r:
        btst    #6,d0                   ; B
        beq.s   .ri_b
        addq.w  #1,d1
.ri_b:
        rts

; void ql_tile_rebuild(int id) - QL_TILE_COMPOSE: pre-CHARCOL, all tiles again
        xdef    ql_tile_rebuild
ql_tile_rebuild:
        bra     build_tiles

; ------------------------------------------------------------
; build_tiles - Mode 8 tile graphics + masks from the CPC tiles (roms 0x8300)
; through the current palette (ink_quad). Same result as the tile data that
; tools/convert_tiles.py produced for the day palette, for any palette.
; Pen 2 is transparent for tiles 0x00-0x7f, pen 1 for 0x80-0xff (CPC tables
; at 0x9d00/0x9f00). tile_gfx: 256 x 64 bytes, tile_msk the same after it.
; ------------------------------------------------------------
build_tiles:
        movem.l d2-d7/a2-a4,-(sp)
        move.l  #rom_image+$4000+$8300,a0
        lea     tile_gfx,a1
        lea     unpack_lut,a2
        lea     ink_quad,a3
        lea     pixel_masks(pc),a4
        moveq   #0,d7                   ; tile number
.bt_tile:
        moveq   #2,d6                   ; transparent pen
        tst.b   d7
        bpl.s   .bt_t
        moveq   #1,d6
.bt_t:
        moveq   #31,d5                  ; 32 bytes = 32 Mode 8 words
.bt_byte:
        moveq   #0,d0
        move.b  (a0)+,d0
        add.w   d0,d0
        add.w   d0,d0                   ; unpack_lut index
        moveq   #0,d1                   ; ink_quad index
        moveq   #0,d2                   ; mask
        moveq   #0,d4                   ; pixel
.bt_pix:
        lsl.w   #2,d1
        move.b  0(a2,d0.w),d3           ; pen of this pixel
        addq.w  #1,d0
        cmp.b   d6,d3
        bne.s   .bt_op
        move.w  d4,d3
        add.w   d3,d3
        or.w    0(a4,d3.w),d2           ; transparent: mask bits set, pen 0 in the index
        bra.s   .bt_np
.bt_op:
        or.b    d3,d1
.bt_np:
        addq.w  #1,d4
        cmp.w   #4,d4
        blt.s   .bt_pix
        add.w   d1,d1
        move.w  0(a3,d1.w),d1           ; colour word
        move.w  d2,d3
        not.w   d3
        and.w   d3,d1                   ; transparent pixels are 0 in the graphic
        move.w  d2,TILE_DATA_SIZE(a1)   ; mask
        move.w  d1,(a1)+
        dbra    d5,.bt_byte
        addq.w  #1,d7
        cmp.w   #256,d7
        blt.s   .bt_tile
        movem.l (sp)+,d2-d7/a2-a4
        rts

        endc                            ; CHARCOL

; CPC palettes 0 black, 1 parchment, 2 day, 3 night -> QL colours.
; Day matches tools/convert_tiles.py, whose decoder numbers pens with the two
; nibbles swapped: true pen 1 -> yellow, pen 2 -> red (cyan, yellow, red, black).
; Night/parchment are provisional (colour scheme = step 6 decision).
; Since 2026-10-03 the table is GENERATED from data/colour_mapping.json
; (tools/colour_mapper.html -> tools/mkpalette.py -> palette_data.s); the
; hand-written table it replaced is kept below, out of the build.
        if 0
palettes:
        dc.w    COL_BLACK,COL_BLACK,COL_BLACK,COL_BLACK
        dc.w    COL_WHITE,COL_MAGENTA,COL_BLACK,COL_RED  ; parchment (provisional)
        dc.w    COL_CYAN,COL_YELLOW,COL_RED,COL_BLACK
        dc.w    COL_BLUE,COL_MAGENTA,COL_WHITE,COL_BLACK
        endc
        include "palette_data.s"

        ifeq    CHARCOL                 ; pre-CHARCOL version (one colour per pen): colour.s replaces it
; ------------------------------------------------------------
; void ql_play_fill(int x, int y, int w, int h, int ink)  (CPC coords)
; ------------------------------------------------------------
ql_play_fill:
        movem.l d2-d7,-(sp)
        movem.l 28(sp),d0-d4            ; x y w h ink
        sub.l   #32,d0                  ; QL x
        bge.s   .pf_x0
        add.l   d0,d2                   ; clip left
        moveq   #0,d0
.pf_x0:
        move.l  d0,d5
        add.l   d2,d5
        cmp.l   #256,d5
        ble.s   .pf_x1
        move.l  #256,d2
        sub.l   d0,d2                   ; clip right
.pf_x1:
        tst.l   d2
        ble.s   .pf_out
        tst.l   d3
        ble.s   .pf_out
        add.w   #PLAY_Y,d1
        and.w   #3,d4
        add.w   d4,d4
        lea     ink_words,a0
        move.w  0(a0,d4.w),d4
        moveq   #4,d5                   ; fast path: one aligned word wide
        cmp.l   d5,d2                   ; (the day-start spiral's 4x2 blocks)
        bne.s   .pf_gen
        moveq   #3,d5
        and.w   d0,d5
        bne.s   .pf_gen
        lea     SCREEN_BASE,a0
        lsl.w   #7,d1
        adda.w  d1,a0
        lsr.w   #1,d0
        adda.w  d0,a0
        subq.w  #1,d3
.pf_w:
        move.w  d4,(a0)
        lea     SCREEN_STRIDE(a0),a0
        dbra    d3,.pf_w
        bra.s   .pf_out
.pf_gen:
        bsr     fill_rect               ; screen.s: D0 x D1 y D2 w D3 h D4 colour
.pf_out:
        movem.l (sp)+,d2-d7
        rts

; ------------------------------------------------------------
; void ql_play_triangle(int x, int y, int lado, int c1, int c2)  (CPC coords)
; The parchment's page-turn triangle (Pergamino::dibujaTriangulo): for each
; line j < lado: pixels x..x+j in pen c1, then x+j+1..x+j+4 in pen c2.
; Lines outside CPC y 0..199 are skipped, x is clipped to the play area.
; ------------------------------------------------------------
ql_play_triangle:
        movem.l d2-d7/a2,-(sp)          ; 28 bytes -> args at 32
        lea     ink_words,a1
        move.l  44(sp),d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d6           ; colour 1
        move.l  48(sp),d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d7           ; colour 2
        moveq   #0,d5                   ; j
.tr_line:
        cmp.l   40(sp),d5
        bge.s   .tr_done
        move.l  36(sp),d1
        add.l   d5,d1                   ; CPC y
        bmi.s   .tr_next
        cmp.l   #200,d1
        bge.s   .tr_next
        add.w   #PLAY_Y,d1
        move.l  32(sp),d0
        sub.l   #32,d0                  ; QL x
        move.l  d5,d2
        addq.l  #1,d2                   ; j+1 pixels
        move.w  d6,d4
        movem.l d0-d2,-(sp)
        bsr     hline
        movem.l (sp)+,d0-d2
        add.l   d2,d0                   ; x+j+1
        moveq   #4,d2
        move.w  d7,d4
        bsr     hline
.tr_next:
        addq.l  #1,d5
        bra.s   .tr_line
.tr_done:
        movem.l (sp)+,d2-d7/a2
        rts

        endc                            ; CHARCOL

; hline: D0.L QL x (any), D1.W QL line, D2.L width, D4.W colour word.
; Clips x to 0..255. Trashes D0-D3, A0, A2.
hline:
        tst.l   d0
        bge.s   .hl_x0
        add.l   d0,d2                   ; clip left
        moveq   #0,d0
.hl_x0:
        move.l  d0,d3
        add.l   d2,d3
        cmp.l   #256,d3
        ble.s   .hl_x1
        move.l  #256,d2
        sub.l   d0,d2                   ; clip right
.hl_x1:
        tst.l   d2
        ble.s   .hl_out
        move.l  d0,d3
        add.l   d2,d3
        subq.l  #1,d3                   ; last pixel x
        lea     SCREEN_BASE,a0
        lsl.w   #7,d1
        adda.w  d1,a0
        move.w  d0,d1
        lsr.w   #2,d1
        add.w   d1,d1
        adda.w  d1,a0                   ; first word
        lea     hl_masks(pc),a2
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a2,d0.w),d0           ; left mask (pixels x&3 .. 3)
        move.w  d3,d1
        and.w   #3,d1
        add.w   d1,d1
        move.w  8(a2,d1.w),d1           ; right mask (pixels 0 .. last&3)
        lsr.w   #2,d3                   ; last word index
        move.l  a0,d2
        sub.l   #SCREEN_BASE,d2
        and.w   #127,d2
        lsr.w   #1,d2                   ; first word index
        sub.w   d2,d3                   ; words after the first
        bne.s   .hl_multi
        and.w   d1,d0                   ; one word: both masks
        move.w  (a0),d2
        move.w  d0,d3
        not.w   d3
        and.w   d3,d2
        and.w   d4,d0
        or.w    d0,d2
        move.w  d2,(a0)
.hl_out:
        rts
.hl_multi:
        move.w  (a0),d2                 ; first word
        move.w  d0,-(sp)
        not.w   d0
        and.w   d0,d2
        move.w  (sp)+,d0
        and.w   d4,d0
        or.w    d0,d2
        move.w  d2,(a0)+
        subq.w  #2,d3                   ; full words between
        bmi.s   .hl_last
.hl_full:
        move.w  d4,(a0)+
        dbra    d3,.hl_full
.hl_last:
        move.w  (a0),d2
        move.w  d1,d0
        not.w   d0
        and.w   d0,d2
        and.w   d4,d1
        or.w    d1,d2
        move.w  d2,(a0)
        rts

hl_masks:
        dc.w    $FFFF,$3F3F,$0F0F,$0303 ; left: pixels p..3
        dc.w    $C0C0,$F0F0,$FCFC,$FFFF ; right: pixels 0..p

; ------------------------------------------------------------
; Diagnostic heartbeat, drawn by the 50 Hz poll at QL lines 248-255 (below the
; CPC screen: nothing else draws or recolours there). Header byte +29 = 1.
;   lines 248-251, 8 px blocks from x = 0:
;     A  frame counter colour   - changes every 50 Hz frame: interrupt alive
;     B  logic step colour      - changes every 130 ms step: main loop alive
;     C  white if the poll's busy flag was set (sound engine re-entered/stuck);
;        red if the poll stopped running for a while (wait_tick counted frames)
;     D  phase colour (phase & 7), then the 8 phase bits (white = 1), MSB first
;   lines 252-255: the 32 bits of the fault word (white = 1), MSB first
; ------------------------------------------------------------
        xdef    diag_draw,ql_phase,diag_phase,poll_dead,poll_seen
        ifd     RELEASE
diag_draw:                              ; release build: no heartbeat
        rts
        else
diag_draw:
        lea     SCREEN_BASE+248*SCREEN_STRIDE,a0
        lea     diag_cols(pc),a1
        move.l  ql_hdr+20,d0            ; frames
        bsr.s   .dg_block
        move.l  ql_hdr+16,d0            ; logic steps
        bsr.s   .dg_block
        moveq   #0,d0                   ; black ...
        tst.b   poll_busy
        beq.s   .dg_nb
        moveq   #7,d0                   ; ... white if busy
.dg_nb:
        tst.b   poll_dead
        beq.s   .dg_nd
        moveq   #2,d0                   ; red: the poll stopped for a while (main loop counted frames)
.dg_nd:
        bsr.s   .dg_block
        moveq   #0,d0
        move.b  diag_phase,d0
        move.w  d0,-(sp)
        bsr.s   .dg_block
        move.w  (sp)+,d1
        moveq   #7,d2                   ; 8 phase bits, one word (4 px) each
.dg_pb:
        moveq   #0,d0
        btst    d2,d1
        beq.s   .dg_p0
        moveq   #7,d0
.dg_p0:
        bsr.s   .dg_word
        dbra    d2,.dg_pb
        ; fault word bits on lines 252-255
        lea     SCREEN_BASE+252*SCREEN_STRIDE,a0
        move.l  ql_hdr+12,d1
        moveq   #31,d2
.dg_fb:
        moveq   #0,d0
        btst    d2,d1
        beq.s   .dg_f0
        moveq   #7,d0
.dg_f0:
        bsr.s   .dg_word
        dbra    d2,.dg_fb
        rts
; .dg_block: 8 px (2 words) x 4 lines in colour d0 & 7, a0 advances 4 bytes
.dg_block:
        move.w  d0,-(sp)
        bsr.s   .dg_word
        move.w  (sp)+,d0
; .dg_word: 4 px x 4 lines in colour d0 & 7, a0 advances 2 bytes
.dg_word:
        and.w   #7,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d0
        move.w  d0,(a0)
        move.w  d0,SCREEN_STRIDE(a0)
        move.w  d0,2*SCREEN_STRIDE(a0)
        move.w  d0,3*SCREEN_STRIDE(a0)
        addq.l  #2,a0
        rts
diag_cols:
        dc.w    COL_BLACK,COL_BLUE,COL_RED,COL_MAGENTA,COL_GREEN,COL_CYAN,COL_YELLOW,COL_WHITE
        endif                           ; RELEASE

; void ql_phase(int phase) - breadcrumb from the C++ (see Juego::run)
ql_phase:
        move.l  4(sp),d0
        move.b  d0,diag_phase
        rts

        ifeq    CHARCOL                 ; pre-CHARCOL version (one colour per pen): colour.s replaces it
; void ql_play_pixel(int x, int y, int ink)
ql_play_pixel:
        movem.l d2-d4,-(sp)
        movem.l 16(sp),d0-d2
        sub.l   #32,d0
        bmi.s   .pp_out
        cmp.l   #256,d0
        bge.s   .pp_out
        add.w   #PLAY_Y,d1
        and.w   #3,d2
        add.w   d2,d2
        lea     ink_words,a0
        move.w  0(a0,d2.w),d2
        bsr     plot_pixel              ; screen.s: D0 x D1 y D2 colour
.pp_out:
        movem.l (sp)+,d2-d4
        rts

        endc                            ; CHARCOL

; ------------------------------------------------------------
; void ql_play_tile(int x, int y, int tile)
; 16x8 tile, x multiple of 16 in CPC coords; tile_data/tile_masks are the
; Mode 8 conversions made by tools/convert_tiles.py (day palette)
; ------------------------------------------------------------
ql_play_tile:
        movem.l d2-d7/a2,-(sp)
        movem.l 32(sp),d0-d2
        sub.l   #32,d0
        bmi.s   pt_out
        cmp.l   #256-16,d0
        bgt.s   pt_out
        tst.l   d1
        bmi.s   pt_out
        cmp.l   #160-8,d1
        bgt.s   pt_out
        add.w   #PLAY_Y,d1
        and.w   #$FF,d2
        lsl.w   #6,d2
        lea     tile_gfx,a1             ; built by build_tiles for the current palette
        lea     TILE_DATA_SIZE(a1),a2   ; tile_msk follows
        adda.w  d2,a1
        adda.w  d2,a2
        lea     SCREEN_BASE,a0
        lsl.w   #7,d1
        adda.w  d1,a0
        lsr.w   #1,d0                   ; x/4*2
        and.w   #$FFFE,d0
        adda.w  d0,a0
        moveq   #7,d5
pt_rows:                                ; (ql_play_cell's second tile comes in here: A0 screen,
.pt_row:                                ; A1 graphic, A2 mask, D5 7, D2-D7/A2 saved as here)
        rept    4
        move.w  (a0),d7
        and.w   (a2)+,d7
        or.w    (a1)+,d7
        move.w  d7,(a0)+
        endr
        lea     SCREEN_STRIDE-8(a0),a0
        dbra    d5,.pt_row
pt_out:
        movem.l (sp)+,d2-d7/a2
        rts

; ------------------------------------------------------------
; void ql_play_cell(int x, int y, int t0, int t1)   (2026-10-05, the CPC's spiral room build)
; one 16x8 cell of GeneradorPantallas::dibujaBufferTiles: pen 0 (the CPC's cleared
; background), then tile t0 and tile t1 on it (0 = none, as the CPC skips tile 0). The play
; area is black until its cell is drawn; the cell's pixels are those of the old build (the
; whole area in pen 0, then every tile ANDed/ORed onto the screen): the first pass makes them
; from the pen 0 words without reading the screen. x multiple of 16 (CPC coords).
; ------------------------------------------------------------
; void ql_play_black(void) - the whole play area (QL lines PLAY_Y..PLAY_Y+159, full width)
; QL black, before a lit room is built from the centre (GeneradorPantallas::limpiaPantalla;
; QL black is pen 3 of the terrain in the day and night palettes, what the host fills)
        xdef    ql_play_black
ql_play_black:
        movem.l d2-d7,-(sp)
        lea     SCREEN_BASE+(PLAY_Y+160)*SCREEN_STRIDE,a0
        moveq   #0,d0
        moveq   #0,d2
        moveq   #0,d3
        moveq   #0,d4
        moveq   #0,d5
        moveq   #0,d6
        moveq   #0,d7
        suba.l  a1,a1
        move.w  #160*SCREEN_STRIDE/32-1,d1
.pb_l:
        movem.l d0/d2-d7/a1,-(a0)       ; 32 bytes of 0
        dbra    d1,.pb_l
        movem.l (sp)+,d2-d7
        rts

; CELL_ONEPASS (2026-10-06): a cell with both tiles made in one pass (pen 0 & mask0 | tile0
; & mask1 | tile1, one screen write a word) instead of the second tile read back from the
; screen; a cell with only the foreground tile in one pass with it. The same words (spiraltest:
; 116 screens x day/night against the old build). 0 = the two passes.
CELL_ONEPASS    equ     1
        xdef    ql_play_cell
ql_play_cell:
        movem.l d2-d7/a2,-(sp)          ; 28 bytes -> args at 32
        movem.l 32(sp),d0-d3            ; x y t0 t1
        sub.l   #32,d0
        bmi     .pc_out
        cmp.l   #256-16,d0
        bgt     .pc_out
        tst.l   d1
        bmi     .pc_out
        cmp.l   #160-8,d1
        bgt     .pc_out
        add.w   #PLAY_Y,d1
        lea     ink_words,a0
        move.w  (a0),d4                 ; pen 0, even lines
        move.w  8(a0),d6                ; pen 0, odd lines
        btst    #0,d1
        beq.s   .pc_par
        exg     d4,d6
.pc_par:
        lea     SCREEN_BASE,a0
        lsl.w   #7,d1
        adda.w  d1,a0
        lsr.w   #1,d0
        and.w   #$FFFE,d0
        adda.w  d0,a0
        move.l  a0,-(sp)                ; (the second tile starts here again)
        moveq   #7,d5
        if      CELL_ONEPASS
        and.w   #$FF,d3
        beq.s   .pc_one                 ; no foreground tile: as before
        and.w   #$FF,d2
        bne.s   .pc_two
        move.w  d3,d2                   ; only the foreground tile: one pass with it
        moveq   #0,d3
        bra.s   .pc_one
.pc_two:                                ; both tiles composed in one pass, one write a word
        movem.l a3-a4,-(sp)
        lsl.w   #6,d2
        lea     tile_gfx,a1
        lea     TILE_DATA_SIZE(a1),a2
        adda.w  d2,a1
        adda.w  d2,a2
        lsl.w   #6,d3
        lea     tile_gfx,a3
        lea     TILE_DATA_SIZE(a3),a4
        adda.w  d3,a3
        adda.w  d3,a4
.pc_row2:
        rept    4
        move.w  d4,d7
        and.w   (a2)+,d7
        or.w    (a1)+,d7
        and.w   (a4)+,d7
        or.w    (a3)+,d7
        move.w  d7,(a0)+
        endr
        lea     SCREEN_STRIDE-8(a0),a0
        exg     d4,d6
        dbra    d5,.pc_row2
        movem.l (sp)+,a3-a4
        addq.l  #4,sp                   ; (the saved screen address)
        bra     .pc_out
.pc_one:
        endif
        and.w   #$FF,d2
        beq.s   .pc_fill
        lsl.w   #6,d2
        lea     tile_gfx,a1
        lea     TILE_DATA_SIZE(a1),a2
        adda.w  d2,a1
        adda.w  d2,a2
.pc_row0:
        rept    4
        move.w  d4,d7
        and.w   (a2)+,d7
        or.w    (a1)+,d7
        move.w  d7,(a0)+
        endr
        lea     SCREEN_STRIDE-8(a0),a0
        exg     d4,d6
        dbra    d5,.pc_row0
        bra.s   .pc_t1
.pc_fill:
        rept    4
        move.w  d4,(a0)+
        endr
        lea     SCREEN_STRIDE-8(a0),a0
        exg     d4,d6
        dbra    d5,.pc_fill
.pc_t1:
        move.l  (sp)+,a0
        and.w   #$FF,d3
        beq.s   .pc_out
        lsl.w   #6,d3
        lea     tile_gfx,a1
        lea     TILE_DATA_SIZE(a1),a2
        adda.w  d3,a1
        adda.w  d3,a2
        moveq   #7,d5
        bra     pt_rows                 ; ql_play_tile's own loop and return
.pc_out:
        movem.l (sp)+,d2-d7/a2
        rts

        ifeq    CHARCOL                 ; pre-CHARCOL version (one colour per pen): colour.s replaces it
; ------------------------------------------------------------
; void ql_play_blit(int x, int y, int w, int h, const u8 *src, int stride)
; byte-per-pixel inks -> play area. x and w multiples of 4 (CPC coords).
; ------------------------------------------------------------
ql_play_blit:
        movem.l d2-d7/a2-a4,-(sp)
        movem.l 40(sp),d0-d3/a1         ; x y w h src
        move.l  60(sp),d7               ; stride
        sub.l   #32,d0
        add.w   #PLAY_Y,d1
        bsr     blit_inks
        movem.l (sp)+,d2-d7/a2-a4
        rts

; blit_inks: D0 QL x (multiple of 4, may be clipped), D1 QL y, D2 w, D3 h,
; A1 src, D7 src stride. Pixels outside x 0..255 are skipped.
; Trashes D0-D6/A0-A4
blit_inks:
        tst.l   d2
        ble     .bi_out
        tst.l   d3
        ble     .bi_out
        ; clip left
        tst.l   d0
        bge.s   .bi_l
        sub.l   d0,a1                   ; skip -x source pixels
        add.l   d0,d2
        moveq   #0,d0
.bi_l:
        move.l  d0,d4
        add.l   d2,d4
        cmp.l   #256,d4
        ble.s   .bi_r
        move.l  #256,d2
        sub.l   d0,d2
.bi_r:
        tst.l   d2
        ble     .bi_out
        lsr.l   #2,d2                   ; words per line
        subq.l  #1,d2
        bmi     .bi_out
        lea     SCREEN_BASE,a0
        move.l  d1,d4
        lsl.l   #7,d4
        adda.l  d4,a0
        lsr.w   #1,d0
        and.w   #$FFFE,d0
        adda.w  d0,a0
        lea     ink_quad,a2             ; 256 words: 4 pens -> Mode 8 word
        subq.l  #1,d3
.bi_line:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d2,d6
.bi_word:
        moveq   #0,d4                   ; index = p0<<6 | p1<<4 | p2<<2 | p3 (pens 0-3)
        move.b  (a4)+,d4
        lsl.b   #2,d4
        or.b    (a4)+,d4
        lsl.b   #2,d4
        or.b    (a4)+,d4
        lsl.b   #2,d4
        or.b    (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bi_word
        lea     SCREEN_STRIDE(a0),a0
        adda.l  d7,a1
        dbra    d3,.bi_line
.bi_out:
        rts

; ------------------------------------------------------------
; void ql_play_blit_p(int x, int y, int w, int h, const u8 *src, int stride)
; packed mixing buffer (CPC bytes, 4 pixels each) -> play area.
; x and w in pixels (multiples of 4, CPC coords), stride in bytes.
; ------------------------------------------------------------
ql_play_blit_p:
        movem.l d2-d7/a2-a4,-(sp)
        movem.l 40(sp),d0-d3/a1         ; x y w h src
        move.l  60(sp),d7               ; stride (bytes)
        sub.l   #32,d0
        add.w   #PLAY_Y,d1
        bsr.s   blit_packed
        movem.l (sp)+,d2-d7/a2-a4
        rts

; blit_packed: as blit_inks, but A1 = packed CPC bytes, D7 stride in bytes.
; One source byte = one Mode 8 word (ink_cpc). Trashes D0-D6/A0-A4
blit_packed:
        tst.l   d2
        ble     .bp_out
        tst.l   d3
        ble     .bp_out
        tst.l   d0                      ; clip left
        bge.s   .bp_l
        move.l  d0,d4
        asr.l   #2,d4
        sub.l   d4,a1                   ; skip -x/4 source bytes
        add.l   d0,d2
        moveq   #0,d0
.bp_l:
        move.l  d0,d4
        add.l   d2,d4
        cmp.l   #256,d4
        ble.s   .bp_r
        move.l  #256,d2
        sub.l   d0,d2
.bp_r:
        tst.l   d2
        ble     .bp_out
        lsr.l   #2,d2                   ; words per line
        subq.l  #1,d2
        bmi     .bp_out
        lea     SCREEN_BASE,a0
        move.l  d1,d4
        lsl.l   #7,d4
        adda.l  d4,a0
        lsr.w   #1,d0
        and.w   #$FFFE,d0
        adda.w  d0,a0
        lea     ink_cpc,a2              ; 256 words: CPC byte -> Mode 8 word
        subq.l  #1,d3
.bp_line:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d2,d6
.bp_word:
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bp_word
        lea     SCREEN_STRIDE(a0),a0
        adda.l  d7,a1
        dbra    d3,.bp_line
.bp_out:
        rts

; ------------------------------------------------------------
; void ql_panel_present(int x, int y, int w, int h, const u8 *panel)
; panel = 320x40 inks (CPC y 160..199). PROVISIONAL layout: the CPC
; panel's x 32..287 shown 1:1 at QL line PANEL_QL_Y.
; ------------------------------------------------------------
ql_panel_present:
        movem.l d2-d7/a2-a4,-(sp)
        movem.l 40(sp),d0-d3/a1         ; x y w h panel
        ; round x down / w up to multiples of 4
        move.l  d0,d4
        and.l   #3,d4
        sub.l   d4,d0
        add.l   d4,d2
        addq.l  #3,d2
        and.l   #-4,d2
        ; source = panel + y*320 + x
        move.l  d1,d4
        mulu    #320,d4
        add.l   d0,d4
        adda.l  d4,a1
        sub.l   #32,d0
        add.l   #PANEL_QL_Y,d1
        move.l  #320,d7
        bsr     blit_inks
        movem.l (sp)+,d2-d7/a2-a4
        rts

        endc                            ; CHARCOL

; ------------------------------------------------------------
; void ql_panel_scroll(int x, int y, int w, int h, int dx, const u8 *panel)   (speed option 6;
; panel unused here: the host presents the pens instead, for hdiff)
; the panel's on-screen pixels of CPC x..x+w-1, panel lines y..y+h-1, moved dx pixels left:
; what CPC6128::scrollPanelLeft does to the pens, done to the screen (the panel colours depend on
; the line only, so the moved words are what a present of the moved pens would draw). x, w and
; dx multiples of 4, x-dx >= 32 and x+w <= 288 (cpc6128.cpp checks); destination below source.
; ------------------------------------------------------------
        xdef    ql_panel_scroll
ql_panel_scroll:
        movem.l d2-d3,-(sp)
        movem.l 12(sp),d0-d3            ; x y w h
        add.l   #PANEL_QL_Y,d1
        lsl.l   #7,d1                   ; * SCREEN_STRIDE
        sub.l   #32,d0
        lsr.l   #1,d0                   ; source byte offset in the line
        add.l   d1,d0
        lea     SCREEN_BASE,a0
        adda.l  d0,a0                   ; source
        move.l  28(sp),d0               ; dx
        lsr.l   #1,d0
        move.l  a0,a1
        suba.l  d0,a1                   ; destination
        lsr.l   #2,d2                   ; words a line
        subq.l  #1,d3
        bmi.s   .ps_out
.ps_line:
        move.l  a0,-(sp)
        move.l  a1,-(sp)
        move.w  d2,d1
        lsr.w   #1,d1                   ; longs
        bra.s   .ps_lc
.ps_l:
        move.l  (a0)+,(a1)+
.ps_lc:
        dbra    d1,.ps_l
        btst    #0,d2
        beq.s   .ps_ln
        move.w  (a0)+,(a1)+
.ps_ln:
        move.l  (sp)+,a1
        move.l  (sp)+,a0
        lea     SCREEN_STRIDE(a0),a0
        lea     SCREEN_STRIDE(a1),a1
        dbra    d3,.ps_line
.ps_out:
        movem.l (sp)+,d2-d3
        rts

; ------------------------------------------------------------
        section .bss,bss
        xdef    game_stack_top
key_state:
        ds.b    16
keyrow_alive:                           ; nonzero once KEYROW has returned a key bit (scan_keyrows)
        ds.w    1
key_typed:                              ; con_drain: steps a typed key still counts as pressed
        ds.b    16
con_id:                                 ; our keyboard console channel (0 = none)
        ds.l    1
ar_sysvars:                             ; ar_setup: system variables (0 = not set up)
        ds.l    1
ar_saved:                               ; the QL's SV_ARDEL, SV_ARFRQ
        ds.w    2
qs_present:
        ds.b    2
ink_words:                              ; terrain colours: 4 even-line words, 4 odd-line (CHARCOL)
        ds.w    8
ink_px:
        ds.w    16
ink_quad:
        ds.w    256
ink_cpc:                                ; packed mixing buffer: CPC byte -> Mode 8 word
        ds.w    256
beep_count:                             ; IPC BEEPs issued (ql_beep_ipc)
        ds.l    1
beep_last:                              ; frame of the last BEEP (0 = none yet)
        ds.l    1
        section .data,data
        cnop    0,2
beep_block:                             ; IPC SOUND: command, 8 bytes, mask, params, reply
        dc.b    $0A,8
        dc.b    $00,$00,$AA,$AA         ; $0000AAAA: each parameter sent as 8 bits
        ds.b    8
        dc.b    0                       ; no reply
        even
        section .bss,bss
cur_pal_p1:
        ds.w    1
old_pal_p1:
        ds.w    1
old_ink:
        ds.w    8
cmap:
        ds.b    8
rtab:
        ds.w    256
tile_gfx:
        ds.b    TILE_DATA_SIZE          ; tile graphics for the current palette
tile_msk:
        ds.b    TILE_DATA_SIZE          ; tile masks (must follow tile_gfx)
        cnop    0,4
game_stack:
        ds.b    GAME_STACK_SIZE
game_stack_top:
        ds.l    1
        xdef    poll_stack,poll_stack_top
poll_stack:
        ds.b    POLL_STACK_SIZE
poll_stack_top:
        ds.l    1
poll_busy:
        ds.w    1
diag_phase:
        ds.w    1
poll_misses:
        ds.w    1                       ; (byte used; word slot keeps the next label even)
poll_dead:
        ds.w    1                       ; set once the main loop had to count frames itself
poll_seen:
        ds.w    1                       ; set by the poll: it runs, wait_tick never counts frames

        section .text.start,code

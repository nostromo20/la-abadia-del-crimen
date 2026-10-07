; ============================================================
; input.s - Non-blocking keyboard input system
; La Abadia del Crimen - QL Port (M10a)
; ============================================================
; Provides per-frame keyboard scanning with hold counters
; and edge detection. Uses persistent con_ channel with
; non-blocking IO.FBYTE (D3=0).
;
; Call init_input once at startup, close_input at shutdown.
; Call scan_keys once per frame, then use check_key_held
; or check_key_edge to query key states.
;
; Register convention: D7 holds channel ID across trap calls
; (traps clobber D0-D3/A0-A3; only D4-D7/A4-A6 are safe).
; ============================================================

; ============================================================
; init_input - Open persistent con_ channel, clear state
; Trashes: D0-D3, D7, A0-A3
; ============================================================
init_input:
        ; Open "con_" channel
        lea     .inp_con_name(pc),a0
        moveq   #IO_OPEN,d0
        moveq   #-1,d1              ; this job
        moveq   #0,d3               ; exclusive access
        trap    #2
        tst.l   d0
        bmi.s   .ii_fail

        ; A0 = channel ID from IO.OPEN
        move.l  a0,d7               ; save in safe register
        lea     con_channel(pc),a0
        move.l  d7,(a0)

        ; Clear hold counters
        lea     key_hold(pc),a0
        moveq   #KEY_COUNT-1,d0
.ii_clr:
        clr.b   (a0)+
        dbf     d0,.ii_clr

        ; Clear bitmaps and raw key
        lea     key_held(pc),a0
        clr.w   (a0)
        lea     key_edge(pc),a0
        clr.w   (a0)
        lea     key_prev(pc),a0
        clr.w   (a0)
        lea     last_raw_key(pc),a0
        clr.b   (a0)

.ii_fail:
        rts

.inp_con_name:
        dc.w    4
        dc.b    "con_"
        even

; ============================================================
; close_input - Close persistent con_ channel
; Trashes: D0-D3/A0-A3
; ============================================================
close_input:
        move.l  con_channel(pc),d0
        beq.s   .ci_done
        move.l  d0,a0
        moveq   #IO_CLOSE,d0
        trap    #2
        lea     con_channel(pc),a0
        clr.l   (a0)
.ci_done:
        rts

; ============================================================
; scan_keys - Per-frame keyboard scan
; Drains QDOS key buffer, updates hold counters & bitmaps.
; After return, use check_key_held / check_key_edge or read
; last_raw_key for non-mapped keys (+/-/T in room viewer).
; Trashes: D0-D7/A0-A3
; ============================================================
scan_keys:
        ; Save key_held -> key_prev
        move.w  key_held(pc),d0
        lea     key_prev(pc),a0
        move.w  d0,(a0)

        ; Clear last_raw_key for this frame
        lea     last_raw_key(pc),a0
        clr.b   (a0)

        ; Load channel ID into D7 (safe across traps)
        move.l  con_channel(pc),d7
        beq     .sk_done            ; no channel open

        ; --- Drain all pending keys from QDOS buffer ---
.sk_drain:
        move.l  d7,a0               ; channel ID (reload; trap clobbers A0)
        moveq   #IO_FBYTE,d0
        moveq   #0,d3               ; non-blocking (D3=0)
        trap    #3
        tst.l   d0
        bmi.s   .sk_drain_done      ; D0<0 = no key pending

        ; Save raw key code (D1.B from IO.FBYTE)
        lea     last_raw_key(pc),a0
        move.b  d1,(a0)

        ; Map to game key index: D1.B -> D0.W
        bsr     map_key_code
        tst.w   d0
        bmi.s   .sk_drain           ; unmapped key, keep draining

        ; Reset hold counter for this key
        lea     key_hold(pc),a0
        move.b  #HOLD_FRAMES,(a0,d0.w)
        bra.s   .sk_drain

.sk_drain_done:
        ; --- Walk hold counters, build held bitmap ---
        moveq   #0,d6               ; D6 = new held bitmap
        lea     key_hold(pc),a0     ; (no trap between here and end)
        moveq   #0,d5               ; D5 = bit position (ascending)
        moveq   #KEY_COUNT-1,d4     ; D4 = loop counter

.sk_cnt_loop:
        move.b  (a0),d0
        beq.s   .sk_cnt_next        ; counter already 0
        subq.b  #1,d0
        move.b  d0,(a0)             ; write back decremented
        bset    d5,d6               ; set bit in held bitmap

.sk_cnt_next:
        addq.l  #1,a0               ; next counter byte
        addq.w  #1,d5               ; next bit position
        dbf     d4,.sk_cnt_loop

        ; Store new held bitmap
        lea     key_held(pc),a0
        move.w  d6,(a0)

        ; Compute edge = held AND NOT prev
        move.w  key_prev(pc),d0
        not.w   d0
        and.w   d6,d0
        lea     key_edge(pc),a0
        move.w  d0,(a0)

.sk_done:
        rts

; ============================================================
; map_key_code - Map raw QDOS key code to game key index
; Entry: D1.B = raw key code
; Exit:  D0.W = key index (0-9) or -1 if unmapped
; Trashes: D0, D1, A0
; ============================================================
map_key_code:
        ; Force lowercase for uppercase letter range ($41-$5A)
        move.b  d1,d0
        cmp.b   #$41,d0
        blt.s   .mk_scan
        cmp.b   #$5A,d0
        bgt.s   .mk_scan
        or.b    #$20,d0             ; A-Z -> a-z
.mk_scan:
        lea     key_code_table(pc),a0
        moveq   #0,d1               ; index counter
.mk_loop:
        cmp.b   (a0)+,d0
        beq.s   .mk_found
        addq.w  #1,d1
        cmp.w   #KEY_COUNT,d1
        blt.s   .mk_loop
        ; Not found
        moveq   #-1,d0
        rts
.mk_found:
        move.w  d1,d0
        rts

; ============================================================
; check_key_held - Test if key is currently held
; Entry: D0.W = key index (0-9)
; Exit:  Z flag clear if held, set if not held
; Trashes: D1
; ============================================================
check_key_held:
        move.w  key_held(pc),d1
        btst    d0,d1
        rts

; ============================================================
; check_key_edge - Test if key was newly pressed this frame
; Entry: D0.W = key index (0-9)
; Exit:  Z flag clear if newly pressed, set if not
; Trashes: D1
; ============================================================
check_key_edge:
        move.w  key_edge(pc),d1
        btst    d0,d1
        rts

; ============================================================
; Key code lookup table (order matches KEY_* constants)
; ============================================================
key_code_table:
        dc.b    QL_KEY_UP       ; 0 = KEY_UP    ($D0)
        dc.b    QL_KEY_DOWN     ; 1 = KEY_DOWN  ($D8)
        dc.b    QL_KEY_LEFT     ; 2 = KEY_LEFT  ($C0)
        dc.b    QL_KEY_RIGHT    ; 3 = KEY_RIGHT ($C8)
        dc.b    $20             ; 4 = KEY_SPACE
        dc.b    'n'             ; 5 = KEY_N     (lowercase)
        dc.b    $1B             ; 6 = KEY_ESC
        dc.b    'q'             ; 7 = KEY_Q     (lowercase)
        dc.b    'r'             ; 8 = KEY_R     (lowercase)
        dc.b    $0D             ; 9 = KEY_ENTER
        even

; ============================================================
; Input state data
; ============================================================
con_channel:    dc.l    0               ; persistent con_ channel ID
key_hold:       dc.b    0,0,0,0,0,0,0,0,0,0  ; per-key hold counters (KEY_COUNT)
key_held:       dc.w    0               ; bitmap: bit N = key N currently held
key_edge:       dc.w    0               ; bitmap: bit N = key N newly pressed
key_prev:       dc.w    0               ; previous frame's held bitmap
last_raw_key:   dc.b    0               ; last raw QDOS key code this frame
        even

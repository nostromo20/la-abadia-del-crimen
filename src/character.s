; ============================================================
; character.s - Character data and movement logic
; La Abadia del Crimen - QL Port (M8e: Screen Change)
; ============================================================
; Routines: init_guillermo, process_guillermo_input, draw_char_marker
;
; Guillermo moves on the 16x20 tile grid using arrow keys:
;   Left/Right arrows (edge): rotate orientation +-90 degrees
;   Up arrow (held): advance 1 grid cell in facing direction
;
; Movement is rate-limited to 1 step every MOVE_DELAY frames.
; Collision: movement rejected if out of bounds, height 0,
; or height difference > 1 (via check_can_move in height.s).
;
; draw_char_marker renders a magenta block with white direction
; indicator directly on SCREEN_BASE (after buffer blit).
; ============================================================

; ============================================================
; Guillermo character data (15 bytes, CPC-compatible layout)
; ============================================================
guillermo:
        dc.b    0               ; +0  animation counter
        dc.b    0               ; +1  orientation (0-3)
        dc.b    8               ; +2  position X (col)
        dc.b    10              ; +3  position Y (row)
        dc.b    0               ; +4  height
        dc.b    0               ; +5  movement flags
        dc.b    0               ; +6  flip state
        dc.b    0,0             ; +7  sprite X offset (future)
        dc.b    0,0             ; +9  sprite Y offset (future)
        dc.b    0               ; +11 command state (future NPC)
        dc.b    0               ; +12 current command byte (future)
        dc.b    0,0             ; +13 command data ptr (future)
        even

; Movement state
move_timer:     dc.b    0       ; frames until next advance allowed
char_moved:     dc.b    0       ; non-zero = position changed, needs redraw
        even

; Movement delta tables (indexed by orientation 0-3)
move_dx:        dc.b     1, 0,-1, 0     ; per orientation
move_dy:        dc.b     0,-1, 0, 1     ; per orientation
        even

; Direction label strings for HUD
dir_labels:
        dc.b    'R',0          ; ORIENT_PX = right
        dc.b    'U',0          ; ORIENT_MY = up
        dc.b    'L',0          ; ORIENT_MX = left
        dc.b    'D',0          ; ORIENT_PY = down
        even

; ============================================================
; init_guillermo - Set starting position
; Trashes: A0
; ============================================================
init_guillermo:
        lea     guillermo(pc),a0
        clr.b   CHR_ANIM(a0)           ; animation = 0
        clr.b   CHR_ORIENT(a0)          ; face +X (right)
        move.b  #8,CHR_X(a0)           ; col 8 (centre-ish)
        move.b  #10,CHR_Y(a0)          ; row 10 (centre)
        move.b  #HEIGHT_UNSET,CHR_HEIGHT(a0)
        clr.b   CHR_FLAGS(a0)

        lea     move_timer(pc),a0
        clr.b   (a0)

        lea     char_moved(pc),a0
        move.b  #1,(a0)                 ; force initial draw
        rts

; ============================================================
; process_guillermo_input - Per-frame input handler
; Call after scan_keys. Checks left/right edge for turning,
; up held for advancing. Sets char_moved flag on change.
; Trashes: D0-D3/A0
; ============================================================
process_guillermo_input:
        ; --- Left arrow (edge): rotate +90 (orientation + 1) ---
        moveq   #KEY_LEFT,d0
        bsr     check_key_edge
        beq.s   .pgi_no_left

        lea     guillermo(pc),a0
        move.b  CHR_ORIENT(a0),d0
        addq.b  #1,d0
        and.b   #3,d0
        move.b  d0,CHR_ORIENT(a0)

        lea     char_moved(pc),a0
        move.b  #1,(a0)

.pgi_no_left:
        ; --- Right arrow (edge): rotate -90 (orientation - 1) ---
        moveq   #KEY_RIGHT,d0
        bsr     check_key_edge
        beq.s   .pgi_no_right

        lea     guillermo(pc),a0
        move.b  CHR_ORIENT(a0),d0
        subq.b  #1,d0
        and.b   #3,d0
        move.b  d0,CHR_ORIENT(a0)

        lea     char_moved(pc),a0
        move.b  #1,(a0)

.pgi_no_right:
        ; --- Up arrow (held): advance in facing direction ---
        moveq   #KEY_UP,d0
        bsr     check_key_held
        beq     .pgi_no_up

        ; Rate limit: decrement timer, only move when it hits 0
        lea     move_timer(pc),a0
        move.b  (a0),d0
        beq.s   .pgi_do_move
        subq.b  #1,d0
        move.b  d0,(a0)
        bra     .pgi_no_up

.pgi_do_move:
        ; Reset timer
        lea     move_timer(pc),a0
        move.b  #MOVE_DELAY,(a0)

        ; Get orientation and look up deltas
        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_ORIENT(a0),d0       ; d0 = orientation 0-3

        lea     move_dx(pc),a0
        move.b  0(a0,d0.w),d1           ; d1.b = dx (signed)
        lea     move_dy(pc),a0
        move.b  0(a0,d0.w),d2           ; d2.b = dy (signed)

        ; Compute destination
        lea     guillermo(pc),a0
        move.b  CHR_X(a0),d3
        ext.w   d3
        ext.w   d1
        add.w   d1,d3                   ; d3 = dest_col (may be -1 or 16)

        move.b  CHR_Y(a0),d0
        ext.w   d0
        ext.w   d2
        add.w   d2,d0                   ; d0 = dest_row (may be -1 or 20)

        ; D3 = dest_col, D0 = dest_row
        exg     d0,d3                   ; D0 = dest_col, D3 = dest_row
        move.w  d3,d1                   ; D1 = dest_row

        ; Bounds check - if OOB, try screen change
        tst.w   d0
        bmi.s   .pgi_try_screen
        cmp.w   #15,d0
        bgt.s   .pgi_try_screen
        tst.w   d1
        bmi.s   .pgi_try_screen
        cmp.w   #19,d1
        bgt.s   .pgi_try_screen

        ; In bounds - check height collision
        bsr     check_can_move
        bne.s   .pgi_no_up              ; blocked

        ; Move accepted - update position
        lea     guillermo(pc),a0
        move.b  d0,CHR_X(a0)           ; dest_col
        move.b  d1,CHR_Y(a0)           ; dest_row

        ; Increment animation counter
        move.b  CHR_ANIM(a0),d0
        addq.b  #1,d0
        and.b   #3,d0
        move.b  d0,CHR_ANIM(a0)

        ; Flag redraw
        lea     char_moved(pc),a0
        move.b  #1,(a0)
        bra.s   .pgi_no_up

.pgi_try_screen:
        ; Out of bounds - attempt room transition
        bsr     try_screen_change
        ; Result doesn't matter: if success, screen_changed flag set
        ; If fail, character stays put

.pgi_no_up:
        ; --- Down arrow (held): reverse (advance opposite direction) ---
        moveq   #KEY_DOWN,d0
        bsr     check_key_held
        beq     .pgi_done

        ; Rate limit: reuse same timer (shared with up)
        lea     move_timer(pc),a0
        move.b  (a0),d0
        beq.s   .pgi_do_reverse
        ; Timer already decremented by up-arrow check if up was held,
        ; but if up wasn't held the timer hasn't been touched yet
        subq.b  #1,d0
        move.b  d0,(a0)
        bra.s   .pgi_done

.pgi_do_reverse:
        lea     move_timer(pc),a0
        move.b  #MOVE_DELAY,(a0)

        ; Get orientation, reverse it (+2 mod 4)
        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_ORIENT(a0),d0
        addq.b  #2,d0
        and.b   #3,d0                   ; reversed orientation

        lea     move_dx(pc),a0
        move.b  0(a0,d0.w),d1
        lea     move_dy(pc),a0
        move.b  0(a0,d0.w),d2

        ; Compute destination
        lea     guillermo(pc),a0
        move.b  CHR_X(a0),d3
        ext.w   d3
        ext.w   d1
        add.w   d1,d3                   ; d3 = dest_col

        move.b  CHR_Y(a0),d0
        ext.w   d0
        ext.w   d2
        add.w   d2,d0                   ; d0 = dest_row

        ; D3 = dest_col, D0 = dest_row
        exg     d0,d3                   ; D0 = dest_col, D3 = dest_row
        move.w  d3,d1                   ; D1 = dest_row

        ; Bounds check - if OOB, try screen change
        tst.w   d0
        bmi.s   .pgi_try_screen_rev
        cmp.w   #15,d0
        bgt.s   .pgi_try_screen_rev
        tst.w   d1
        bmi.s   .pgi_try_screen_rev
        cmp.w   #19,d1
        bgt.s   .pgi_try_screen_rev

        ; In bounds - check height collision
        bsr     check_can_move
        bne.s   .pgi_done               ; blocked

        ; Move accepted - update position
        lea     guillermo(pc),a0
        move.b  d0,CHR_X(a0)
        move.b  d1,CHR_Y(a0)

        lea     char_moved(pc),a0
        move.b  #1,(a0)
        bra.s   .pgi_done

.pgi_try_screen_rev:
        ; Out of bounds - attempt room transition
        bsr     try_screen_change

.pgi_done:
        rts

; ============================================================
; draw_char_marker - Draw orientation-aware marker at grid pos
; Draws a 16x8 magenta block with 4x2 white direction indicator
; on the leading edge. Operates on SCREEN_BASE (after blit).
;
; Position: x = col*16, y = row*8 + VP_Y
; Trashes: D0-D7/A0-A1
; ============================================================
draw_char_marker:
        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_X(a0),d0
        lsl.w   #4,d0                   ; d0 = col * 16 = pixel X
        moveq   #0,d1
        move.b  CHR_Y(a0),d1
        lsl.w   #3,d1                   ; d1 = row * 8 = pixel Y
        add.w   #VP_Y,d1                ; offset into viewport area

        ; Save base position for indicator
        move.w  d0,d5                   ; d5 = base X
        move.w  d1,d6                   ; d6 = base Y

        ; Draw 16x8 magenta block
        moveq   #16,d2                  ; width
        moveq   #8,d3                   ; height
        move.w  #COL_MAGENTA,d4         ; colour
        bsr     fill_rect

        ; Now draw 4x2 white indicator on leading edge
        ; Position depends on orientation
        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_ORIENT(a0),d0

        ; Branch by orientation
        tst.b   d0
        beq.s   .dcm_right              ; 0 = +X
        cmp.b   #1,d0
        beq.s   .dcm_up                 ; 1 = -Y
        cmp.b   #2,d0
        beq.s   .dcm_left               ; 2 = -X
        ; else 3 = +Y
        bra.s   .dcm_down

.dcm_right:
        ; Right edge: x+12, y+3
        move.w  d5,d0
        add.w   #12,d0
        move.w  d6,d1
        add.w   #3,d1
        bra.s   .dcm_draw_ind

.dcm_up:
        ; Top edge: x+6, y+0
        move.w  d5,d0
        add.w   #6,d0
        move.w  d6,d1
        bra.s   .dcm_draw_ind

.dcm_left:
        ; Left edge: x+0, y+3
        move.w  d5,d0
        move.w  d6,d1
        add.w   #3,d1
        bra.s   .dcm_draw_ind

.dcm_down:
        ; Bottom edge: x+6, y+6
        move.w  d5,d0
        add.w   #6,d0
        move.w  d6,d1
        add.w   #6,d1

.dcm_draw_ind:
        ; Draw 4x2 white indicator
        moveq   #4,d2                   ; width
        moveq   #2,d3                   ; height
        move.w  #COL_WHITE,d4           ; colour
        bsr     fill_rect
        rts

; ============================================================
; draw_dir_hud - Show "DIR:X" text in HUD area
; Trashes: D0-D7/A0-A4
; ============================================================
draw_dir_hud:
        ; Draw "DIR:" label
        lea     str_dir(pc),a0
        move.w  #144,d0
        move.w  #16,d1
        move.w  #COL_GREEN,d2
        bsr     draw_string

        ; Get current orientation and select label
        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_ORIENT(a0),d0
        add.w   d0,d0                   ; *2 (each label is 2 bytes: char + null)
        lea     dir_labels(pc),a0
        adda.w  d0,a0                   ; A0 -> direction char string

        move.w  #176,d0                 ; X position (after "DIR:")
        move.w  #16,d1
        move.w  #COL_WHITE,d2
        bsr     draw_string
        rts

str_dir:
        dc.b    "DIR:",0
        even

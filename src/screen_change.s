; ============================================================
; screen_change.s - Room transition when walking off screen edge
; La Abadia del Crimen - QL Port (M8e: Camera & Screen Change)
; ============================================================
; Routines: update_room_position, try_screen_change
;
; When Guillermo walks off the 16x20 grid edge, this module
; looks up the adjacent room in the ground floor table and
; loads it, wrapping the character's coordinates to the
; opposite edge.
;
; Grid spacing: 16 cols x 16 rows between room origins.
; Display: 16 cols x 20 rows (4-row vertical overlap).
; Wrapping: col -1->15, col 16->0, row -1->15, row 20->4.
; ============================================================

; ============================================================
; Room position state
; ============================================================
current_room_tx:
        dc.b    0               ; floor table X (0-15)
current_room_ty:
        dc.b    0               ; floor table Y (0-10)
        even

; Screen change flag (checked by main loop for full redraw)
screen_changed:
        dc.b    0
        even

; ============================================================
; Ground floor table (CPC $2265): 16x11 grid of room IDs.
; 0 = no room. IDs >= ROOM_COUNT (59) replaced with 0.
; Rooms 1, 13 kept as-is (load_room rejects via $FFFF ptr).
; ============================================================
ground_floor_table:
        ; Y=0
        dc.b     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        ; Y=1
        dc.b     0, 0, 0, 0, 0, 0, 0, 0,39, 0, 0, 0, 0, 0, 0, 0
        ; Y=2
        dc.b     0,10, 9, 0, 7, 8,42,40,38,41,55,56,57, 0, 0, 0
        ; Y=3
        dc.b     0, 0, 2, 1, 0,13,14,36,35,37,43,44,45, 0, 0, 0
        ; Y=4
        dc.b     0, 0, 3, 0,31, 0, 0, 0,34, 0,46,47,48, 0, 0, 0
        ; Y=5
        dc.b     0, 0, 4,29,30, 0, 0, 0,33, 0,49,50,51, 0, 0, 0
        ; Y=6
        dc.b     0,12,11,28, 5, 6, 0, 0,32, 0,52,53,54, 0, 0, 0
        ; Y=7
        dc.b     0, 0, 0,15,16,17,18, 0,27, 0,26,58, 0, 0, 0, 0
        ; Y=8
        dc.b     0, 0, 0, 0, 0, 0,19,20,21,24,25, 0, 0, 0, 0, 0
        ; Y=9
        dc.b     0, 0, 0, 0, 0, 0, 0, 0,22, 0, 0, 0, 0, 0, 0, 0
        ; Y=10
        dc.b     0, 0, 0, 0, 0, 0, 0, 0,23, 0, 0, 0, 0, 0, 0, 0
        even

; ============================================================
; Inverse map: room_id -> (tx, ty). Built from ground_floor_table.
; Only valid rooms (present in table) have meaningful values.
; ============================================================
room_to_tx:
        ;       R0  R1  R2  R3  R4  R5  R6  R7  R8  R9
        dc.b     0,  3,  2,  2,  2,  4,  5,  4,  5,  2
        ;       R10 R11 R12 R13 R14 R15 R16 R17 R18 R19
        dc.b     1,  2,  1,  5,  6,  3,  4,  5,  6,  6
        ;       R20 R21 R22 R23 R24 R25 R26 R27 R28 R29
        dc.b     7,  8,  8,  8,  9, 10, 10,  8,  3,  3
        ;       R30 R31 R32 R33 R34 R35 R36 R37 R38 R39
        dc.b     4,  4,  8,  8,  8,  8,  7,  9,  8,  8
        ;       R40 R41 R42 R43 R44 R45 R46 R47 R48 R49
        dc.b     7,  9,  6, 10, 11, 12, 10, 11, 12, 10
        ;       R50 R51 R52 R53 R54 R55 R56 R57 R58
        dc.b    11, 12, 10, 11,  0, 10, 11, 12, 11
        even

room_to_ty:
        ;       R0  R1  R2  R3  R4  R5  R6  R7  R8  R9
        dc.b     0,  3,  3,  4,  5,  6,  6,  2,  2,  2
        ;       R10 R11 R12 R13 R14 R15 R16 R17 R18 R19
        dc.b     2,  6,  6,  3,  3,  7,  7,  7,  7,  8
        ;       R20 R21 R22 R23 R24 R25 R26 R27 R28 R29
        dc.b     8,  8,  9, 10,  8,  8,  7,  7,  6,  5
        ;       R30 R31 R32 R33 R34 R35 R36 R37 R38 R39
        dc.b     5,  4,  6,  5,  4,  3,  3,  3,  2,  1
        ;       R40 R41 R42 R43 R44 R45 R46 R47 R48 R49
        dc.b     2,  2,  2,  3,  3,  3,  4,  4,  4,  5
        ;       R50 R51 R52 R53 R54 R55 R56 R57 R58
        dc.b     5,  5,  6,  6,  0,  2,  2,  2,  7
        even

; ============================================================
; update_room_position - Set tx/ty from current_room_id
; Call after every load_room.
; Trashes: D0/A0-A1
; ============================================================
update_room_position:
        move.w  current_room_id(pc),d0
        bmi.s   .urp_none               ; test room (-1)
        cmp.w   #ROOM_COUNT,d0
        bge.s   .urp_none

        lea     room_to_tx(pc),a0
        lea     current_room_tx(pc),a1
        move.b  0(a0,d0.w),(a1)

        lea     room_to_ty(pc),a0
        lea     current_room_ty(pc),a1
        move.b  0(a0,d0.w),(a1)
        rts

.urp_none:
        lea     current_room_tx(pc),a1
        clr.b   (a1)
        lea     current_room_ty(pc),a1
        clr.b   (a1)
        rts

; ============================================================
; try_screen_change - Attempt room transition for OOB move
; Entry: D0.W = dest_col (may be -1 or 16)
;         D1.W = dest_row (may be -1 or 20)
; Exit:  Z set = transition succeeded (room loaded, coords set)
;        NZ = no valid adjacent room (movement blocked)
; On success: loads new room + height data, sets character
;             position, sets CHR_HEIGHT = HEIGHT_UNSET (set on
;             next move by check_can_move).
; Trashes: D0-D7/A0-A5
; ============================================================
try_screen_change:
        ; Save dest coords
        move.w  d0,d4                   ; d4 = dest_col
        move.w  d1,d5                   ; d5 = dest_row

        ; Get current floor table position
        moveq   #0,d6                   ; d6 = new tx
        moveq   #0,d7                   ; d7 = new ty
        move.b  current_room_tx(pc),d6
        move.b  current_room_ty(pc),d7

        ; Check which edge was crossed
        tst.w   d4
        bmi.s   .tsc_left               ; col < 0: exit left
        cmp.w   #16,d4
        bge.s   .tsc_right              ; col >= 16: exit right
        tst.w   d5
        bmi.s   .tsc_up                 ; row < 0: exit up
        cmp.w   #20,d5
        bge.s   .tsc_down               ; row >= 20: exit down
        bra     .tsc_fail               ; not actually OOB

.tsc_left:
        subq.w  #1,d6                   ; tx - 1
        bmi     .tsc_fail               ; off left edge of floor table
        move.w  #15,d4                  ; wrap col to 15
        bra.s   .tsc_lookup

.tsc_right:
        addq.w  #1,d6                   ; tx + 1
        cmp.w   #16,d6
        bge     .tsc_fail               ; off right edge
        moveq   #0,d4                   ; wrap col to 0
        bra.s   .tsc_lookup

.tsc_up:
        subq.w  #1,d7                   ; ty - 1
        bmi.s   .tsc_fail               ; off top edge
        move.w  #15,d5                  ; wrap row to 15
        bra.s   .tsc_lookup

.tsc_down:
        addq.w  #1,d7                   ; ty + 1
        cmp.w   #11,d7
        bge.s   .tsc_fail               ; off bottom edge
        move.w  #4,d5                   ; wrap row to 4 (20 - 16 = 4)
        ; fall through to lookup

.tsc_lookup:
        ; Look up room_id at (d6, d7) in ground_floor_table
        ; Index = ty * 16 + tx
        move.w  d7,d0
        lsl.w   #4,d0                   ; ty * 16
        add.w   d6,d0                   ; + tx
        lea     ground_floor_table(pc),a0
        moveq   #0,d2
        move.b  0(a0,d0.w),d2           ; d2 = room_id

        ; Check if valid room
        tst.b   d2
        beq.s   .tsc_fail               ; 0 = no room
        cmp.w   #ROOM_COUNT,d2
        bge.s   .tsc_fail               ; >= ROOM_COUNT = invalid

        ; Try to load the room
        move.w  d2,d0
        bsr     load_room
        bcs.s   .tsc_fail               ; load failed (invalid room data)

        ; Room loaded - update position and height data
        bsr     update_room_position
        bsr     load_height_data

        ; Set character position to wrapped coords
        lea     guillermo(pc),a0
        move.b  d4,CHR_X(a0)
        move.b  d5,CHR_Y(a0)

        ; Mark height unknown so check_can_move accepts the next
        ; move and takes its height from the destination cell
        move.b  #HEIGHT_UNSET,CHR_HEIGHT(a0)

        ; Flag redraws
        lea     char_moved(pc),a0
        move.b  #1,(a0)
        lea     screen_changed(pc),a0
        move.b  #1,(a0)

        ; Return Z = success
        moveq   #0,d0
        rts

.tsc_fail:
        ; Return NZ = blocked
        moveq   #1,d0
        rts

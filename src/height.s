; ============================================================
; height.s - Height buffer and collision detection
; La Abadia del Crimen - QL Port (M8a: Collision)
; ============================================================
; Routines: init_height_data, load_height_data, check_can_move
;
; Pre-computed 16x20 height grids (from convert_heights.py) are
; stored in height_data.s at end of binary. This module provides
; collision checking: |current - dest| > 1 = blocked. Walls are
; just cells too high to step onto; height 0 is ground-level floor
; (CPC / VIGASOCO Personaje::trataDeAvanzar have no "no floor" rule).
;
; Both height_ptr_table and height_data_base are >32KB away,
; so we use stored absolute pointers (same pattern as rooms.s).
; ============================================================

; ============================================================
; Height state variables
; ============================================================
current_height_ptr:
        dc.l    0               ; -> current room's 320-byte grid (0=none)
height_ptr_table_ptr:
        dc.l    0               ; absolute address of height_ptr_table
height_data_base_ptr:
        dc.l    0               ; absolute address of height_data_base

; ============================================================
; init_height_data - Compute absolute addresses of height tables
; Same indirect-pointer pattern as init_room_data in rooms.s.
; Must be called once at startup.
; Trashes: A0-A1
; ============================================================
init_height_data:
        lea     .ihd_ref(pc),a0
        ; Store height_ptr_table address
        movea.l a0,a1
        adda.l  #height_ptr_table-.ihd_ref,a1
        lea     height_ptr_table_ptr(pc),a0
        move.l  a1,(a0)
        ; Store height_data_base address
        lea     .ihd_ref(pc),a0
        movea.l a0,a1
        adda.l  #height_data_base-.ihd_ref,a1
        lea     height_data_base_ptr(pc),a0
        move.l  a1,(a0)
        rts
.ihd_ref:

; ============================================================
; load_height_data - Set current_height_ptr for current room
; Must be called after load_room (uses current_room_id).
; Trashes: D0-D1/A0-A1
; ============================================================
load_height_data:
        move.w  current_room_id(pc),d0
        bmi.s   .lhd_none           ; test room (-1) = no height data

        cmp.w   #ROOM_COUNT,d0
        bge.s   .lhd_none

        ; Index into height_ptr_table (word entries) via stored pointer
        add.w   d0,d0               ; D0 = room_id * 2
        movea.l height_ptr_table_ptr(pc),a0
        moveq   #0,d1
        move.w  0(a0,d0.w),d1       ; D1 = word offset
        cmp.w   #$FFFF,d1
        beq.s   .lhd_none           ; no height data for this room

        ; Compute absolute pointer via stored height_data_base
        movea.l height_data_base_ptr(pc),a0
        adda.l  d1,a0               ; A0 = room height grid

        lea     current_height_ptr(pc),a1
        move.l  a0,(a1)
        rts

.lhd_none:
        lea     current_height_ptr(pc),a1
        clr.l   (a1)                ; NULL = free movement
        rts

; ============================================================
; check_can_move - Test if Guillermo can move to dest cell
; Entry: D0.B = dest_col (0-15), D1.B = dest_row (0-19)
; Exit:  Z flag set = allowed, NZ = blocked
; On success, updates CHR_HEIGHT to dest height.
; Trashes: D0-D3/A0
; ============================================================
check_can_move:
        move.l  current_height_ptr(pc),d2
        beq.s   .ccm_allow          ; no height data = free movement

        movea.l d2,a0               ; A0 = height grid base

        ; Read dest height: grid[dest_row * 16 + dest_col]
        moveq   #0,d2
        move.b  d1,d2               ; d2 = dest_row
        lsl.w   #4,d2               ; d2 = dest_row * 16
        moveq   #0,d3
        move.b  d0,d3
        add.w   d3,d2               ; d2 = dest_row * 16 + dest_col
        move.b  0(a0,d2.w),d3       ; d3 = dest height (0 = ground-level floor)

        ; Read current height from guillermo struct
        lea     guillermo(pc),a0
        moveq   #0,d2
        move.b  CHR_HEIGHT(a0),d2   ; d2 = current height

        ; If current height is not yet known, allow and set
        cmp.b   #HEIGHT_UNSET,d2
        beq.s   .ccm_set_height

        ; Check |current - dest| <= 1
        sub.b   d3,d2               ; d2 = current - dest (signed)
        bpl.s   .ccm_pos
        neg.b   d2                  ; d2 = |current - dest|
.ccm_pos:
        cmp.b   #1,d2
        bgt.s   .ccm_block          ; difference > 1: blocked

.ccm_set_height:
        ; Update character height
        lea     guillermo(pc),a0
        move.b  d3,CHR_HEIGHT(a0)

.ccm_allow:
        ; Return Z=1 (allowed) - use D2 to preserve D0/D1 (dest coords)
        moveq   #0,d2
        rts

.ccm_block:
        ; Return NZ (blocked) - use D2 to preserve D0/D1 (dest coords)
        moveq   #1,d2
        rts

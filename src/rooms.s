; ============================================================
; rooms.s - Room loading and rendering for QL port
; La Abadia del Crimen - Milestone 6
; ============================================================
; Routines: load_room, render_room, load_test_room
;
; Room data format (per room):
;   1. Base grid: 320 bytes (20 rows x 16 cols, first tile per cell)
;   2. Overlay count: 1 word (dc.w N)
;   3. Overlay entries: N x 3 bytes (row, col, tile_index)
;   4. Even alignment padding
;
; The renderer draws the base grid first, then iterates the
; overlay list to composite subsequent tiles using AND-mask/OR-tile.
; This matches CPC behaviour: multiple tiles per cell are drawn
; in order, with transparency allowing earlier tiles to show through.
;
; CPC rendering (verified from ABADIA2.BIN $4F18):
;   pixel_x = col * 16   (col = L - 8, range 0..15)
;   pixel_y = row * 8    (row = H - 8, range 0..19)
;   Grid fills viewport: 16*16=256 wide, 20*8=160 tall.

; ============================================================
; init_room_data - Compute and store room_data_base address
; Must be called once at startup before any load_room calls.
; Uses PC-relative trick to get absolute address of room_data_base
; which may be >32KB away (placed at end of binary).
; Trashes: A0-A1
; ============================================================
init_room_data:
        lea     .ird_ref(pc),a0     ; A0 = absolute address of .ird_ref
        adda.l  #room_data_base-.ird_ref,a0  ; add offset to reach room_data_base
        lea     room_data_base_ptr(pc),a1
        move.l  a0,(a1)
        rts
.ird_ref:

; ============================================================
; load_room - Load a room by ID
; Entry: D0.W = room_id (0 to ROOM_COUNT-1)
; Exit:  current_room_id set, current_room_ptr set
;        Carry set if invalid room
; Trashes: D0-D1/A0-A1
; ============================================================
load_room:
        ; Bounds check
        cmp.w   #ROOM_COUNT,d0
        bge.s   .lr_invalid

        ; Save room ID
        lea     current_room_id(pc),a0
        move.w  d0,(a0)

        ; Index into room_ptr_table (word entries, unsigned offsets)
        add.w   d0,d0               ; D0 = room_id * 2 (word index)
        lea     room_ptr_table(pc),a0
        moveq   #0,d1
        move.w  0(a0,d0.w),d1       ; D1.L = unsigned word offset
        cmp.w   #$FFFF,d1           ; $FFFF = invalid room marker
        beq.s   .lr_invalid

        ; Compute absolute pointer via stored room_data_base address
        movea.l room_data_base_ptr(pc),a0
        adda.l  d1,a0               ; A0 = room data start
        lea     current_room_ptr(pc),a1
        move.l  a0,(a1)

        ; Success
        and     #$FE,ccr            ; clear carry
        rts

.lr_invalid:
        or      #$01,ccr            ; set carry
        rts

; ============================================================
; render_room - Two-pass room renderer
;
; Pass 1: Render base grid (320 bytes, first tile per cell)
; Pass 2: Iterate overlay list, compositing subsequent tiles
;
; This matches CPC rendering: multi-tile cells are drawn in order,
; with AND-mask/OR-tile compositing allowing earlier tiles to show
; through transparent areas of later tiles.
;
; A5 = data pointer (safe: render_tile_at trashes D0-D7/A0-A3 only)
; D4/D5 = pixel coords, D7 = tile count — saved on stack
;
; Trashes: D0-D7/A0-A3
; ============================================================
render_room:
        move.l  current_room_ptr(pc),d0
        beq     .rr_done            ; no room loaded
        movea.l d0,a5               ; A5 = room data start

        ; === Pass 1: Base grid (320 bytes) ===
        moveq   #0,d7               ; D7 = tile count
        moveq   #0,d4               ; D4 = pixel_y (0, 8, 16, ..152)

.rr_row:
        moveq   #0,d5               ; D5 = pixel_x (0, 16, 32, ..240)

.rr_col:
        moveq   #0,d2
        move.b  (a5)+,d2            ; tile index from grid
        beq.s   .rr_skip            ; 0 = empty cell

        ; Set up render_tile_at args: D0=x, D1=y, D2=tile
        move.w  d5,d0               ; pixel_x
        move.w  d4,d1               ; pixel_y

        ; Save loop state (render_tile_at trashes D0-D7)
        movem.l d4-d5/d7,-(sp)
        bsr     render_tile_at
        movem.l (sp)+,d4-d5/d7

        addq.w  #1,d7               ; tile count++

.rr_skip:
        add.w   #16,d5              ; next column (+16 pixels)
        cmp.w   #ISO_WIDTH,d5       ; 256 = 16 cols * 16px
        blt.s   .rr_col

        addq.w  #8,d4              ; next row (+8 pixels)
        cmp.w   #ISO_HEIGHT,d4     ; 160 = 20 rows * 8px
        blt.s   .rr_row

        ; === Pass 2: Overlay list ===
        ; A5 now points past the 320-byte base grid
        move.w  (a5)+,d4            ; D4 = overlay count
        beq.s   .rr_save_count      ; no overlays
        subq.w  #1,d4               ; adjust for dbra

.rr_overlay:
        ; Read overlay entry: row (0-19), col (0-15), tile (1-255)
        moveq   #0,d1
        move.b  (a5)+,d1            ; row
        moveq   #0,d0
        move.b  (a5)+,d0            ; col
        moveq   #0,d2
        move.b  (a5)+,d2            ; tile index

        ; Convert grid position to pixel coordinates
        lsl.w   #3,d1               ; row * 8 = pixel_y
        lsl.w   #4,d0               ; col * 16 = pixel_x

        ; D0=pixel_x, D1=pixel_y, D2=tile_index
        move.w  d4,-(sp)            ; save overlay counter
        bsr     render_tile_at
        move.w  (sp)+,d4

        addq.w  #1,d7               ; tile count++
        dbra    d4,.rr_overlay

.rr_save_count:
        ; Store total tile count for diagnostic display
        lea     last_tile_count(pc),a0
        move.w  d7,(a0)

.rr_done:
        rts

; ============================================================
; load_test_room - Load the diagnostic test pattern
; Sets current_room_ptr to test_room_grid, room ID to -1
; Trashes: A0-A1
; ============================================================
load_test_room:
        lea     current_room_id(pc),a0
        move.w  #$FFFF,(a0)         ; -1 = test room
        lea     test_room_grid(pc),a0
        lea     current_room_ptr(pc),a1
        move.l  a0,(a1)
        rts

; ============================================================
; Room state variables
; ============================================================
current_room_id:
        dc.w    0
current_room_ptr:
        dc.l    0
room_data_base_ptr:
        dc.l    0               ; set by init_room_data at startup
last_tile_count:
        dc.w    0

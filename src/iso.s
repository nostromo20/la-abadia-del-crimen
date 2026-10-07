; ============================================================
; iso.s - Tile rendering engine
; La Abadia del Crimen - QL Port
; ============================================================
; Routines:
;   init_iso_engine   - Placeholder for future init
;   render_iso_view   - Main entry: clear buffer, render, blit
;   render_tile_at    - Draw one 16x8 tile into offscreen buffer
;   iso_project       - 3D->2D projection (M5 test scene only)
;   render_test_room  - Render hardcoded M5 test objects
;   sort_objects       - Bubble sort by depth (M5 test scene only)
;
; render_tile_at is the core tile blitter used by both:
;   - render_room (rooms.s) for CPC room data
;   - render_test_room for the M5 isometric test scene
;
; CPC tile format: 256 tiles, 8 rows, 4 words/row = 64 bytes.
; AND-mask compositing: screen = (screen AND mask) OR tile.
; Mask $FFFF = fully transparent, $0000 = fully opaque.
; Tile graphics at tile_data, masks at tile_data + TILE_DATA_SIZE.

; ============================================================
; init_iso_engine - Initialise isometric engine state
; Trashes: nothing
; ============================================================
init_iso_engine:
        rts

; ============================================================
; render_iso_view - Main entry: clear buffer, render, blit
; Called from main.s after load_room or load_test_room.
; 1. Clears ISO_BUFFER to background colour
; 2. Calls render_room (rooms.s) to draw tiles into buffer
; 3. Calls copy_buffer_to_screen to blit to display
; Trashes: everything
; ============================================================
render_iso_view:
        ; Background colour depends on room type:
        ; Normal rooms: cyan = CPC paper colour (ink 0).
        ;   CPC clears screen to ink 0 before rendering; transparent
        ;   tile pixels (mask=$FFFF) show background through.
        ; Test room: blue + green stripes for transparency testing.
        move.w  current_room_id(pc),d0
        bpl.s   .riv_paper              ; normal room (ID >= 0)

        ; Test room: blue clear then green stripes (transparency test)
        move.w  #COL_BLUE,d0
        bsr     clear_iso_buffer
        bsr     fill_test_stripes
        bra.s   .riv_render

.riv_paper:
        move.w  #COL_CYAN,d0            ; ink 0 = CPC paper (Cyan)
        bsr     clear_iso_buffer

.riv_render:
        ; Render all tiles into buffer
        bsr     render_room

        ; Draw character sprite into buffer (depth-sorted)
        bsr     draw_guillermo_to_buffer

        ; Re-draw front tiles using render-order comparison
        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_X(a0),d0           ; D0 = chr_col
        moveq   #0,d1
        move.b  CHR_Y(a0),d1           ; D1 = chr_row

        ; Extra overlap rows from height offset
        moveq   #0,d2
        move.b  CHR_HEIGHT(a0),d2
        cmp.b   #HEIGHT_UNSET,d2
        beq.s   .riv_no_hext            ; height not yet known
        sub.w   #HEIGHT_BASE,d2
        ble.s   .riv_no_hext
        mulu    #HEIGHT_PX_STEP,d2
        addq.w  #7,d2
        lsr.w   #3,d2                   ; ceil(offset/8) = extra rows
        bra.s   .riv_call_rft
.riv_no_hext:
        moveq   #0,d2
.riv_call_rft:
        bsr     render_front_tiles

        ; Copy buffer to screen
        bsr     copy_buffer_to_screen
        rts

; ============================================================
; fill_test_stripes - Pre-fill even tile-rows with green
; Alternates green/blue 8-pixel-high bands for transparency test.
; Even tile-rows (0,2,4..18) = green, odd (1,3,5..19) = blue.
; Tiles drawn on top: opaque areas hide stripes, transparent
; areas show green or blue through (proving mask works).
; Trashes: D4-D5/A0
; ============================================================
fill_test_stripes:
        lea     ISO_BUFFER,a0
        moveq   #9,d5               ; 10 green bands
.fts_band:
        ; Fill 8 scanlines (one tile height) with green
        move.w  #(64*8)-1,d4        ; 64 words/line * 8 lines - 1
.fts_fill:
        move.w  #COL_GREEN,(a0)+
        dbra    d4,.fts_fill
        ; Skip 8 scanlines (stay blue from clear)
        lea     1024(a0),a0          ; 8 * ISO_STRIDE = 1024
        dbra    d5,.fts_band
        rts

; ============================================================
; iso_project - Isometric 3D to 2D projection (M5 test only)
; Entry: D0.W = x3d, D1.W = y3d, D2.W = z3d
; Exit:  D0.W = screen_x (pixel), D1.W = screen_y (pixel)
; Formula:
;   screen_x = (x3d - z3d) * 2 - iso_center_x + ISO_WIDTH/2
;   screen_y = (x3d + z3d) - y3d - iso_center_y + ISO_HEIGHT/2
;
; This is used ONLY by render_test_room for the M5 hardcoded
; test scene. Room rendering (rooms.s) uses rectangular grid
; positions instead — the CPC also renders at rectangular
; positions (verified from ABADIA2.BIN $4F18).
;
; Auto-centering offsets iso_center_x/y are set before calling.
; Trashes: D0-D3
; ============================================================
iso_project:
        move.w  d0,d3               ; save x3d
        ; screen_x = (x3d - z3d) * 2 - center_x + viewport_center
        sub.w   d2,d0               ; x3d - z3d
        add.w   d0,d0               ; * 2
        sub.w   iso_center_x(pc),d0 ; - centering offset
        add.w   #ISO_WIDTH/2,d0     ; + viewport centre (96)
        ; screen_y = (x3d + z3d) - y3d - center_y + viewport_center
        add.w   d2,d3               ; x3d + z3d
        sub.w   d1,d3               ; - y3d
        sub.w   iso_center_y(pc),d3 ; - centering offset
        add.w   #ISO_HEIGHT/2,d3    ; + viewport centre (80)
        move.w  d3,d1               ; screen_y
        rts

; ============================================================
; Centering offsets (used by iso_project for M5 test scene)
; ============================================================
iso_center_x:
        dc.w    0
iso_center_y:
        dc.w    0

; ============================================================
; render_tile_at - Draw one 16x8 tile into offscreen buffer
; Entry: D0.W = buffer_x (pixel, must be multiple of 4)
;        D1.W = buffer_y (pixel)
;        D2.W = tile_index (0-255)
; Trashes: D0-D7/A0-A3
;
; AND-mask compositing (same as CPC at $4F3D):
;   for each word: buffer = (buffer AND mask) OR tile
; This allows transparent pixels (mask bits = 1) to preserve
; the background, while opaque pixels (mask bits = 0) are
; replaced with tile data.
;
; Buffer layout: ISO_BUFFER, ISO_STRIDE bytes per row.
; Each tile row = 4 words (8 bytes) = 16 pixels.
; Tiles that would extend outside the viewport are skipped.
; ============================================================
render_tile_at:
        ; Bounds check: tile must fit entirely within buffer
        tst.w   d0
        bmi.s   .rta_skip           ; X < 0
        cmp.w   #ISO_WIDTH-16,d0
        bgt.s   .rta_skip           ; X+16 > width
        tst.w   d1
        bmi.s   .rta_skip           ; Y < 0
        cmp.w   #ISO_HEIGHT-8,d1
        bgt.s   .rta_skip           ; Y+8 > height

        ; Tile/mask data offset = tile_index * 64
        ; Full tile_index (0-255) used directly, no bit 7 stripping
        move.w  d2,d4
        and.w   #$FF,d4             ; clamp to 0-255
        lsl.w   #6,d4               ; * 64
        lea     tile_data(pc),a1
        lea     TILE_DATA_SIZE(a1),a2   ; A2 = start of tile_masks
        adda.w  d4,a1               ; A1 = tile graphics
        adda.w  d4,a2               ; A2 = tile masks

        ; Buffer address = ISO_BUFFER + Y*ISO_STRIDE + (X/4)*2
        lea     ISO_BUFFER,a0
        mulu    #ISO_STRIDE,d1
        adda.l  d1,a0
        move.w  d0,d1
        lsr.w   #2,d1               ; X / 4
        add.w   d1,d1               ; * 2 (word offset)
        adda.w  d1,a0               ; A0 = buffer destination

        ; 8 rows x 4 words per row
        moveq   #7,d5               ; row counter
.rta_row:
        moveq   #3,d6               ; word counter
.rta_word:
        move.w  (a0),d7             ; read buffer word
        and.w   (a2)+,d7            ; AND with mask (keep transparent)
        or.w    (a1)+,d7            ; OR with tile (draw opaque)
        move.w  d7,(a0)+            ; write back
        dbra    d6,.rta_word
        ; Advance to next buffer row (stride - 8 bytes already advanced)
        lea     ISO_STRIDE-8(a0),a0
        dbra    d5,.rta_row
.rta_skip:
        rts

; ============================================================
; render_front_tiles - Re-draw tiles rendered after sprite
; Uses render-order comparison matching CPC's row-major
; painter's algorithm: tiles at higher row, or same row +
; higher col, are in front and re-drawn over the sprite.
; Entry: D0.W = chr_col, D1.W = chr_row, D2.W = extra_rows
; Trashes: D0-D7/A0-A5
; ============================================================
render_front_tiles:
        move.w  d2,d3                   ; D3 = extra_height_rows
        move.l  current_room_ptr(pc),d2
        beq     .rft_done
        movea.l d2,a5

        ; Save character position for render-order comparison
        move.w  d1,d7                   ; D7 = chr_row
        move.w  d0,a4                   ; A4 = chr_col (safe across bsr)

        ; Sprite depth for overlay comparison
        move.w  d0,d6
        add.w   d1,d6                   ; D6 = sprite_depth = chr_row + chr_col

        ; Start row = max(0, chr_row - 4 - extra_height_rows)
        move.w  d1,d4
        subq.w  #4,d4
        sub.w   d3,d4
        bge.s   .rft_start_ok
        moveq   #0,d4
.rft_start_ok:
        move.w  d4,d2
        lsl.w   #4,d2                   ; * 16 bytes per row
        adda.w  d2,a5

        ; === Base grid: re-draw tiles rendered AFTER sprite ===
.rft_row:
        moveq   #0,d5
.rft_col:
        moveq   #0,d2
        move.b  (a5)+,d2                ; tile index
        beq.s   .rft_skip               ; empty cell

        ; Render-order check: tile rendered after character?
        cmp.w   d7,d4                   ; tile_row vs chr_row
        bgt.s   .rft_draw               ; higher row = in front
        blt.s   .rft_skip               ; lower row = behind
        ; Same row: higher col = in front
        cmp.w   a4,d5                   ; tile_col vs chr_col
        ble.s   .rft_skip               ; col <= chr_col = behind or same

.rft_draw:
        move.w  d5,d0
        lsl.w   #4,d0                   ; pixel_x
        move.w  d4,d1
        lsl.w   #3,d1                   ; pixel_y

        movem.l d4-d7,-(sp)
        bsr     render_tile_at
        movem.l (sp)+,d4-d7

.rft_skip:
        addq.w  #1,d5
        cmp.w   #16,d5
        blt.s   .rft_col

        addq.w  #1,d4
        cmp.w   #20,d4
        blt.s   .rft_row

.rft_overlays:
        ; Overlays: use render-order (includes same-depth)
        movea.l current_room_ptr(pc),a5
        lea     320(a5),a5
        move.w  (a5)+,d4                ; overlay count
        beq.s   .rft_done
        subq.w  #1,d4

.rft_ov:
        moveq   #0,d1
        move.b  (a5)+,d1                ; row
        moveq   #0,d0
        move.b  (a5)+,d0                ; col
        moveq   #0,d2
        move.b  (a5)+,d2                ; tile index

        ; Render-order: overlay row > chr_row, or same row + col > chr_col
        cmp.w   d7,d1                   ; overlay_row vs chr_row
        bgt.s   .rft_ov_draw
        blt.s   .rft_ov_skip
        cmp.w   a4,d0                   ; overlay_col vs chr_col
        ble.s   .rft_ov_skip

.rft_ov_draw:
        lsl.w   #3,d1                   ; pixel_y
        lsl.w   #4,d0                   ; pixel_x

        movem.l d4-d7,-(sp)
        bsr     render_tile_at
        movem.l (sp)+,d4-d7

.rft_ov_skip:
        dbra    d4,.rft_ov

.rft_done:
        rts

; ============================================================
; render_test_room - Render the hardcoded M5 test scene
; Copies test_room_objects to sort_buffer, sorts by depth
; (x3d + z3d ascending = back-to-front), then renders each
; object through iso_project + render_tile_at.
; This is a separate pipeline from the CPC room renderer —
; it uses true 3D isometric projection, not grid positions.
; Trashes: everything
; ============================================================
render_test_room:
        ; Copy test objects to sort buffer
        lea     test_room_objects(pc),a0
        lea     sort_buffer(pc),a1
        moveq   #0,d0               ; count
.rtr_copy:
        move.w  (a0),d1
        cmp.w   #$FFFF,d1
        beq.s   .rtr_copied
        move.l  (a0)+,(a1)+         ; x3d, y3d
        move.l  (a0)+,(a1)+         ; z3d, tile_index
        addq.w  #1,d0
        bra.s   .rtr_copy
.rtr_copied:
        tst.w   d0
        beq.s   .rtr_done           ; no objects

        move.w  d0,-(sp)            ; save count

        ; Sort by depth (back-to-front)
        lea     sort_buffer(pc),a0
        bsr     sort_objects

        ; Render sorted objects
        move.w  (sp)+,d0            ; restore count
        subq.w  #1,d0               ; dbra counter
        lea     sort_buffer(pc),a5
.rtr_render:
        move.w  d0,-(sp)            ; save loop counter

        ; Load 3D coords and tile index
        move.w  (a5)+,d0            ; x3d
        move.w  (a5)+,d1            ; y3d
        move.w  (a5)+,d2            ; z3d
        move.w  (a5)+,d3            ; tile_index
        move.w  d3,a4               ; save tile_index (A4 safe)

        ; Project 3D -> 2D
        bsr     iso_project         ; D0=screen_x, D1=screen_y

        ; Render tile at projected position
        move.w  a4,d2               ; tile_index
        bsr     render_tile_at

        move.w  (sp)+,d0            ; restore counter
        dbra    d0,.rtr_render
.rtr_done:
        rts

; ============================================================
; sort_objects - Bubble sort objects by isometric depth
; Entry: A0 = object list (8 bytes per entry: x,y,z,tile)
;        D0.W = count
; Sort key = x3d + z3d (ascending = back-to-front)
; Used only by render_test_room (M5 test scene).
; Room rendering (rooms.s) does not need sorting because
; tiles are placed at non-overlapping rectangular positions.
; Trashes: D0-D6/A0-A1
; ============================================================
sort_objects:
        subq.w  #1,d0               ; need at least 2 elements
        ble.s   .so_done
.so_outer:
        move.w  d0,d1               ; inner counter
        subq.w  #1,d1
        blt.s   .so_done
        movea.l a0,a1               ; reset to list start
        clr.w   d4                  ; swapped flag
.so_inner:
        ; Compute depth[j] = x3d + z3d
        move.w  (a1),d2             ; x3d of element j
        add.w   4(a1),d2            ; + z3d = depth[j]
        ; Compute depth[j+1]
        move.w  8(a1),d3            ; x3d of element j+1
        add.w   12(a1),d3           ; + z3d = depth[j+1]
        ; Compare: want ascending order (back first)
        cmp.w   d3,d2
        ble.s   .so_no_swap
        ; Swap 8 bytes (two longword swaps)
        move.l  (a1),d5
        move.l  8(a1),d6
        move.l  d6,(a1)
        move.l  d5,8(a1)
        move.l  4(a1),d5
        move.l  12(a1),d6
        move.l  d6,4(a1)
        move.l  d5,12(a1)
        moveq   #1,d4               ; swapped = true
.so_no_swap:
        addq.l  #8,a1               ; next element pair
        dbra    d1,.so_inner
        tst.w   d4
        beq.s   .so_done            ; no swaps -> sorted
        subq.w  #1,d0               ; reduce range
        bgt.s   .so_outer
.so_done:
        rts

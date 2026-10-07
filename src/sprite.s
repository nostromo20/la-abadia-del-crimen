; ============================================================
; sprite.s - Sprite renderer with AND/OR masking
; La Abadia del Crimen - QL Port (M7d: Sprite Renderer)
; ============================================================
; Routines: draw_sprite, draw_guillermo_sprite
;
; Renders sprites to SCREEN_BASE using AND-mask/OR-gfx
; compositing. Clips to game viewport (VP_Y to VP_Y+ISO_HEIGHT).
;
; Screen address: SCREEN_BASE + y*128 + (x/4)*2
; Each word = 4 pixels. Sprites must be word-aligned (x mod 4 = 0).
; ============================================================

; ============================================================
; draw_guillermo_sprite - Draw Guillermo at his grid position
; Uses current orientation to select frame.
; Position: x = col*16, y = row*8 + VP_Y - (GUIL_HEIGHT - 8)
; Trashes: D0-D7/A0-A3
; ============================================================
draw_guillermo_sprite:
        lea     guillermo(pc),a0

        ; Calculate screen X from grid col
        moveq   #0,d0
        move.b  CHR_X(a0),d0
        lsl.w   #4,d0                   ; x = col * 16

        ; Calculate screen Y from grid row
        moveq   #0,d1
        move.b  CHR_Y(a0),d1
        lsl.w   #3,d1                   ; row * 8
        add.w   #VP_Y,d1                ; + viewport offset
        sub.w   #GUIL_HEIGHT-8,d1       ; align sprite bottom to cell bottom

        ; Select frame from orientation (0-3)
        moveq   #0,d2
        move.b  CHR_ORIENT(a0),d2       ; d2 = orientation 0-3

        ; Calculate frame offset: orient * GUIL_FRAME_SIZE
        move.w  d2,d3
        mulu    #GUIL_FRAME_SIZE,d3     ; d3 = byte offset into gfx/mask

        ; Set up gfx and mask pointers
        lea     guillermo_gfx(pc),a0
        adda.l  d3,a0                   ; A0 = frame gfx data
        lea     guillermo_mask(pc),a1
        adda.l  d3,a1                   ; A1 = frame mask data

        ; Sprite dimensions
        move.w  #GUIL_WIDTH,d2          ; width in words
        move.w  #GUIL_HEIGHT,d3         ; height in rows

        bra     draw_sprite             ; tail-call

; ============================================================
; draw_sprite - Generic sprite renderer with viewport clipping
; Entry: D0.W = x (pixels, must be word-aligned: x mod 4 = 0)
;        D1.W = y (pixels, screen coordinates)
;        D2.W = width (words)
;        D3.W = height (rows)
;        A0 = sprite graphics data
;        A1 = sprite mask data
; Draws to SCREEN_BASE using AND-mask/OR-gfx compositing.
; Clips to viewport: y in [VP_Y .. VP_Y+ISO_HEIGHT-1],
;                     x in [0 .. SCREEN_WIDTH-1]
; Trashes: D0-D7/A0-A3
; ============================================================
draw_sprite:
        ; --- Top clip ---
        cmp.w   #VP_Y,d1
        bge.s   .no_top_clip

        ; y < VP_Y: skip rows at top of sprite
        move.w  #VP_Y,d4
        sub.w   d1,d4                   ; d4 = rows to skip
        cmp.w   d3,d4
        bge     .ds_done                ; entirely above viewport
        sub.w   d4,d3                   ; reduce height

        ; Advance source pointers past skipped rows
        move.w  d2,d5
        mulu    d4,d5                   ; d5 = words to skip
        add.w   d5,d5                   ; bytes to skip
        adda.w  d5,a0                   ; skip gfx data
        adda.w  d5,a1                   ; skip mask data
        move.w  #VP_Y,d1               ; start at viewport top

.no_top_clip:
        ; --- Bottom clip ---
        move.w  d1,d4
        add.w   d3,d4                   ; d4 = y + height
        cmp.w   #VP_Y+ISO_HEIGHT,d4
        ble.s   .no_bottom_clip

        move.w  #VP_Y+ISO_HEIGHT,d4
        sub.w   d1,d4                   ; d4 = visible height
        move.w  d4,d3
        ble     .ds_done                ; entirely below viewport

.no_bottom_clip:
        ; --- Right clip ---
        moveq   #0,d6                   ; d6 = source skip (words per row)
        move.w  d0,d4
        move.w  d2,d5
        lsl.w   #2,d5                   ; d5 = width in pixels
        add.w   d4,d5                   ; d5 = right edge (pixels)
        cmp.w   #SCREEN_WIDTH,d5
        ble.s   .no_right_clip

        ; Right edge exceeds screen: reduce visible width
        move.w  #SCREEN_WIDTH,d5
        sub.w   d0,d5                   ; d5 = visible pixels
        lsr.w   #2,d5                   ; d5 = visible words
        move.w  d2,d6
        sub.w   d5,d6                   ; d6 = words to skip per row
        move.w  d5,d2                   ; use clipped width
        tst.w   d2
        ble     .ds_done

.no_right_clip:
        ; --- Calculate screen address ---
        ; addr = SCREEN_BASE + y * SCREEN_STRIDE + (x / 4) * 2
        move.w  d1,d4
        mulu    #SCREEN_STRIDE,d4       ; d4 = y * 128
        move.w  d0,d5
        lsr.w   #2,d5                   ; d5 = x / 4 (word index)
        add.w   d5,d5                   ; d5 = byte offset
        add.l   d5,d4                   ; d4 = total offset from SCREEN_BASE
        movea.l #SCREEN_BASE,a2
        adda.l  d4,a2                   ; A2 = screen address

        ; Source skip bytes per row (for right clipping)
        add.w   d6,d6                   ; d6 = skip bytes per row

        ; Screen row stride: SCREEN_STRIDE - visible_width_bytes
        move.w  d2,d7
        add.w   d7,d7                   ; d7 = visible width in bytes
        neg.w   d7
        add.w   #SCREEN_STRIDE,d7       ; d7 = stride adjustment

        ; --- Render loop ---
        subq.w  #1,d3                   ; adjust height for dbra

.ds_row_loop:
        move.w  d2,d4
        subq.w  #1,d4                   ; adjust width for dbra

.ds_word_loop:
        move.w  (a1)+,d5                ; read mask word
        and.w   d5,(a2)                 ; clear sprite area on screen
        move.w  (a0)+,d5                ; read gfx word
        or.w    d5,(a2)+                ; draw sprite pixels
        dbra    d4,.ds_word_loop

        ; Skip clipped source words (right clip)
        adda.w  d6,a0
        adda.w  d6,a1

        ; Advance to next screen row
        adda.w  d7,a2
        dbra    d3,.ds_row_loop

.ds_done:
        rts

; ============================================================
; draw_guillermo_to_buffer - Draw Guillermo into ISO_BUFFER
; Uses buffer-relative coordinates for depth-sorted rendering.
; Called by render_iso_view between tile passes.
; Trashes: D0-D7/A0-A3
; ============================================================
draw_guillermo_to_buffer:
        lea     guillermo(pc),a0

        ; Buffer X = col * 16
        moveq   #0,d0
        move.b  CHR_X(a0),d0
        lsl.w   #4,d0                   ; x = col * 16

        ; Buffer Y = row * 8 - (GUIL_HEIGHT - 8)
        moveq   #0,d1
        move.b  CHR_Y(a0),d1
        lsl.w   #3,d1                   ; row * 8
        sub.w   #GUIL_HEIGHT-8,d1       ; align sprite bottom to cell bottom

        ; Height visual offset: (CHR_HEIGHT - HEIGHT_BASE) * HEIGHT_PX_STEP
        moveq   #0,d2
        move.b  CHR_HEIGHT(a0),d2
        cmp.b   #HEIGHT_UNSET,d2
        beq.s   .dgb_no_hoff            ; height not yet known, skip
        sub.w   #HEIGHT_BASE,d2
        muls    #HEIGHT_PX_STEP,d2       ; signed: below base = push down
        sub.w   d2,d1                    ; higher = further up screen
.dgb_no_hoff:

        ; Select frame from orientation (0-3)
        moveq   #0,d2
        move.b  CHR_ORIENT(a0),d2
        move.w  d2,d3
        mulu    #GUIL_FRAME_SIZE,d3

        ; Set up gfx and mask pointers
        lea     guillermo_gfx(pc),a0
        adda.l  d3,a0
        lea     guillermo_mask(pc),a1
        adda.l  d3,a1

        move.w  #GUIL_WIDTH,d2
        move.w  #GUIL_HEIGHT,d3

        bra     draw_sprite_to_buffer   ; tail-call

; ============================================================
; draw_sprite_to_buffer - Sprite renderer targeting ISO_BUFFER
; Same AND/OR compositing as draw_sprite but renders to the
; offscreen buffer for depth-sorted rendering.
; Entry: D0.W = x (pixels, word-aligned: x mod 4 = 0)
;        D1.W = y (buffer pixels)
;        D2.W = width (words)
;        D3.W = height (rows)
;        A0 = sprite graphics data
;        A1 = sprite mask data
; Clips to [0..ISO_WIDTH-1] x [0..ISO_HEIGHT-1]
; Trashes: D0-D7/A0-A3
; ============================================================
draw_sprite_to_buffer:
        ; --- Top clip ---
        tst.w   d1
        bge.s   .dsb_no_top

        ; y < 0: skip rows at top of sprite
        move.w  d1,d4
        neg.w   d4                       ; d4 = rows to skip
        cmp.w   d3,d4
        bge     .dsb_done                ; entirely above buffer
        sub.w   d4,d3                    ; reduce height

        ; Advance source past skipped rows
        move.w  d2,d5
        mulu    d4,d5
        add.w   d5,d5                    ; bytes to skip
        adda.w  d5,a0
        adda.w  d5,a1
        moveq   #0,d1                    ; start at buffer top

.dsb_no_top:
        ; --- Bottom clip ---
        move.w  d1,d4
        add.w   d3,d4                    ; d4 = y + height
        cmp.w   #ISO_HEIGHT,d4
        ble.s   .dsb_no_bottom

        move.w  #ISO_HEIGHT,d4
        sub.w   d1,d4                    ; d4 = visible height
        move.w  d4,d3
        ble     .dsb_done

.dsb_no_bottom:
        ; --- Right clip ---
        moveq   #0,d6                    ; d6 = source skip (words)
        move.w  d0,d4
        move.w  d2,d5
        lsl.w   #2,d5                    ; width in pixels
        add.w   d4,d5                    ; right edge
        cmp.w   #ISO_WIDTH,d5
        ble.s   .dsb_no_right

        move.w  #ISO_WIDTH,d5
        sub.w   d0,d5                    ; visible pixels
        lsr.w   #2,d5                    ; visible words
        move.w  d2,d6
        sub.w   d5,d6                    ; words to skip
        move.w  d5,d2
        tst.w   d2
        ble     .dsb_done

.dsb_no_right:
        ; --- Calculate buffer address ---
        ; addr = ISO_BUFFER + y * ISO_STRIDE + (x / 4) * 2
        move.w  d1,d4
        mulu    #ISO_STRIDE,d4
        move.w  d0,d5
        lsr.w   #2,d5
        add.w   d5,d5
        add.l   d5,d4
        lea     ISO_BUFFER,a2
        adda.l  d4,a2

        ; Source skip bytes (right clip)
        add.w   d6,d6

        ; Buffer row stride adjustment
        move.w  d2,d7
        add.w   d7,d7                    ; visible width in bytes
        neg.w   d7
        add.w   #ISO_STRIDE,d7

        ; --- Render loop ---
        subq.w  #1,d3

.dsb_row:
        move.w  d2,d4
        subq.w  #1,d4

.dsb_word:
        move.w  (a1)+,d5                 ; read mask
        and.w   d5,(a2)                  ; clear sprite area
        move.w  (a0)+,d5                 ; read gfx
        or.w    d5,(a2)+                 ; draw sprite pixels
        dbra    d4,.dsb_word

        adda.w  d6,a0                    ; skip clipped source (right)
        adda.w  d6,a1
        adda.w  d7,a2                    ; next buffer row
        dbra    d3,.dsb_row

.dsb_done:
        rts

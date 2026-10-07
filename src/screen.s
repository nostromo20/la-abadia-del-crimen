; ============================================================
; screen.s - Screen primitives for QL Mode 8
; La Abadia del Crimen - QL Port
; ============================================================
; Routines: clear_screen, plot_pixel, fill_rect
;
; These operate directly on SCREEN_BASE ($20000), not on the
; offscreen ISO_BUFFER. Used for UI elements (title, room ID,
; prompts) that are drawn after the buffer blit.
;
; Screen address for pixel (X,Y):
;   word_addr = SCREEN_BASE + Y * SCREEN_STRIDE + (X / 4) * 2
; Each word contains 4 pixels; use pixel_masks LUT to isolate
; a single pixel position within the word.

; ============================================================
; pixel_masks - Per-pixel white mask LUT (4 words)
; Index by (X AND 3) to get the mask for that pixel position.
; ============================================================
pixel_masks:
        dc.w    PMASK_PX0           ; pixel 0: $C0C0
        dc.w    PMASK_PX1           ; pixel 1: $3030
        dc.w    PMASK_PX2           ; pixel 2: $0C0C
        dc.w    PMASK_PX3           ; pixel 3: $0303

; ============================================================
; clear_screen - Fill entire screen with a solid colour
; Entry: D0.W = colour word (e.g. COL_BLACK)
; Trashes: D0-D1/A0
; ============================================================
clear_screen:
        move.w  d0,d1
        swap    d1
        move.w  d0,d1               ; D1.L = colour | colour
        lea     SCREEN_BASE,a0
        move.w  #(SCREEN_SIZE/4)-1,d0
.loop:
        move.l  d1,(a0)+
        dbra    d0,.loop
        rts

; ============================================================
; plot_pixel - Plot a single pixel
; Entry: D0.W = X (0-255), D1.W = Y (0-255), D2.W = colour
; Trashes: D0-D4/A0-A1
; ============================================================
plot_pixel:
        ; Calculate screen address: SCREEN_BASE + Y*128 + (X/4)*2
        lea     SCREEN_BASE,a0
        move.w  d1,d3
        lsl.w   #7,d3               ; D3 = Y * 128
        adda.w  d3,a0               ; A0 += Y * 128

        move.w  d0,d3
        lsr.w   #2,d3               ; D3 = X / 4
        add.w   d3,d3               ; D3 = (X/4) * 2 (word offset)
        adda.w  d3,a0               ; A0 = screen word address

        ; Get pixel mask from LUT
        move.w  d0,d3
        and.w   #3,d3               ; D3 = X AND 3 (pixel index)
        add.w   d3,d3               ; word offset into LUT
        lea     pixel_masks(pc),a1
        move.w  0(a1,d3.w),d4       ; D4 = pixel white mask

        ; Read-modify-write
        move.w  (a0),d3             ; read screen word
        not.w   d4
        and.w   d4,d3               ; clear pixel bits
        not.w   d4                   ; restore mask
        move.w  d2,d1
        and.w   d4,d1               ; mask colour to pixel position
        or.w    d1,d3               ; merge colour
        move.w  d3,(a0)             ; write back
        rts

; ============================================================
; fill_rect - Fill a rectangle with a solid colour
; Entry: D0.W = X, D1.W = Y, D2.W = W, D3.W = H, D4.W = colour
; Trashes: D0-D7/A0-A1
;
; Handles sub-word alignment at left and right edges using
; read-modify-write with pixel masks. Middle full words are
; written directly. Operates on the physical screen.
;
; Uses 12-byte stack frame for loop state:
;   0(SP) = FR_LOFF    (word) left edge byte offset from row start
;   2(SP) = FR_LMASK   (word) left edge pixel mask
;   4(SP) = FR_RMASK   (word) right edge pixel mask
;   6(SP) = FR_FCOUNT  (word) full middle words to write per line
;   8(SP) = FR_COLOUR  (word) colour word
;  10(SP) = FR_Y       (word) remaining scanlines (dbra counter)
; ============================================================
FR_LOFF         equ 0
FR_LMASK        equ 2
FR_RMASK        equ 4
FR_FCOUNT       equ 6
FR_COLOUR       equ 8
FR_Y            equ 10
FR_SIZE         equ 12

fill_rect:
        subq.w  #1,d3               ; H-1 for dbra
        bmi     .done               ; H <= 0, nothing to do
        tst.w   d2
        ble     .done               ; W <= 0, nothing to do

        sub.w   #FR_SIZE,sp         ; allocate stack frame
        move.w  d4,FR_COLOUR(sp)
        move.w  d3,FR_Y(sp)

        ; --- Compute left edge byte offset ---
        move.w  d0,d5
        lsr.w   #2,d5               ; D5 = X / 4 (word index)
        add.w   d5,d5               ; D5 = byte offset of left word
        move.w  d5,FR_LOFF(sp)

        ; --- Compute right-end pixel index ---
        move.w  d0,d6
        add.w   d2,d6
        subq.w  #1,d6               ; D6 = X + W - 1 (last pixel X)
        move.w  d6,d7
        lsr.w   #2,d7               ; D7 = last pixel word index

        ; --- Check single-word case ---
        cmp.w   d5,d7               ; left word index (D5/2) vs right word index (D7)
        ; D5 is byte offset = word_index*2, D7 is word_index
        move.w  d5,d3
        lsr.w   #1,d3               ; D3 = left word index
        cmp.w   d3,d7
        bne.s   .multi_word

        ; --- Single word: build combined mask ---
        lea     pixel_masks(pc),a1
        moveq   #0,d4               ; accumulate mask
        move.w  d0,d3
        and.w   #3,d3               ; start pixel within word
        move.w  d6,d5
        and.w   #3,d5               ; end pixel within word
.single_mask_loop:
        move.w  d3,d7
        add.w   d7,d7
        or.w    0(a1,d7.w),d4       ; OR in this pixel's mask
        cmp.w   d5,d3
        beq.s   .single_mask_done
        addq.w  #1,d3
        bra.s   .single_mask_loop
.single_mask_done:
        move.w  d4,FR_LMASK(sp)
        clr.w   FR_RMASK(sp)
        clr.w   FR_FCOUNT(sp)
        bra.s   .render

        ; --- Multi-word case ---
.multi_word:
        lea     pixel_masks(pc),a1

        ; Build left edge mask (pixels from X%4 to 3)
        moveq   #0,d4
        move.w  d0,d3
        and.w   #3,d3               ; start pixel
.left_mask_loop:
        move.w  d3,d7
        add.w   d7,d7
        or.w    0(a1,d7.w),d4
        cmp.w   #3,d3
        beq.s   .left_mask_done
        addq.w  #1,d3
        bra.s   .left_mask_loop
.left_mask_done:
        move.w  d4,FR_LMASK(sp)

        ; Build right edge mask (pixels from 0 to (X+W-1)%4)
        moveq   #0,d4
        move.w  d6,d5
        and.w   #3,d5               ; end pixel
        moveq   #0,d3
.right_mask_loop:
        move.w  d3,d7
        add.w   d7,d7
        or.w    0(a1,d7.w),d4
        cmp.w   d5,d3
        beq.s   .right_mask_done
        addq.w  #1,d3
        bra.s   .right_mask_loop
.right_mask_done:
        move.w  d4,FR_RMASK(sp)

        ; Count full middle words
        ; Left word index = FR_LOFF/2, right word index = D6>>2
        move.w  FR_LOFF(sp),d3
        lsr.w   #1,d3               ; left word index
        move.w  d6,d4
        lsr.w   #2,d4               ; right word index
        move.w  d4,d5
        sub.w   d3,d5
        subq.w  #1,d5               ; full words = right - left - 1
        bpl.s   .fcount_ok
        moveq   #0,d5               ; clamp to 0
.fcount_ok:
        move.w  d5,FR_FCOUNT(sp)

        ; --- Render scanlines ---
.render:
        lea     SCREEN_BASE,a0
        move.w  d1,d3
        lsl.w   #7,d3               ; Y * 128
        adda.w  d3,a0               ; A0 = screen row base + Y offset
        adda.w  FR_LOFF(sp),a0      ; A0 = first word to touch

.scanline:
        movea.l a0,a1               ; A1 = working pointer for this row

        ; -- Left edge (read-modify-write) --
        move.w  FR_LMASK(sp),d4
        beq.s   .skip_left
        move.w  (a1),d3
        move.w  d4,d5
        not.w   d5
        and.w   d5,d3               ; clear masked pixels
        move.w  FR_COLOUR(sp),d5
        and.w   d4,d5               ; colour masked to pixel positions
        or.w    d5,d3
        move.w  d3,(a1)
.skip_left:
        addq.l  #2,a1               ; advance past left word

        ; -- Full middle words --
        move.w  FR_FCOUNT(sp),d5
        beq.s   .skip_middle
        subq.w  #1,d5
        move.w  FR_COLOUR(sp),d4
.middle_loop:
        move.w  d4,(a1)+
        dbra    d5,.middle_loop
.skip_middle:

        ; -- Right edge (read-modify-write) --
        move.w  FR_RMASK(sp),d4
        beq.s   .skip_right
        move.w  (a1),d3
        move.w  d4,d5
        not.w   d5
        and.w   d5,d3
        move.w  FR_COLOUR(sp),d5
        and.w   d4,d5
        or.w    d5,d3
        move.w  d3,(a1)
.skip_right:

        ; Advance to next scanline
        adda.w  #SCREEN_STRIDE,a0
        subq.w  #1,FR_Y(sp)
        bpl.s   .scanline

        add.w   #FR_SIZE,sp
.done:
        rts

; ============================================================
; QL_INTRO_DISSOLVE (Pergamino.cpp): a parchment page composed OFF-SCREEN
; in tile_gfx/tile_msk (32 KB, the screen's layout; unused while a parchment
; is up, as the parchment palette builds no tiles), then dissolved onto the
; screen in a 2x2 pattern (pixel pairs x line parity), 4 phases of ~3-4
; frames each. The screen keeps what it showed (the loading screen) until then.
; ============================================================
        xdef    ql_off_begin,ql_off_fill,ql_off_pixel,ql_off_dissolve

; void ql_off_begin(void) - the page black; as palette 0, nothing on screen
; is left to recolour at the next palette
ql_off_begin:
        clr.w   cur_pal_p1
        move.w  #COL_BLACK,d0
        move.w  d0,d1
        swap    d1
        move.w  d0,d1
        lea     tile_gfx,a0
        move.w  #(SCREEN_SIZE/4)-1,d0
.ob_l:
        move.l  d1,(a0)+
        dbra    d0,.ob_l
        rts

; void ql_off_pixel(int x, int y, int ink) - as ql_play_pixel, into the page
ql_off_pixel:
        movem.l d2-d4,-(sp)
        movem.l 16(sp),d0-d2
        sub.l   #32,d0
        bmi.s   .op_out
        cmp.l   #256,d0
        bge.s   .op_out
        add.w   #PLAY_Y,d1
        bsr.s   off_plot
.op_out:
        movem.l (sp)+,d2-d4
        rts

; off_plot: D0.W QL x (0-255), D1.W QL y, D2 pen -> the page (the terrain
; colours, odd lines their own). Trashes D2-D4/A0-A1
off_plot:
        and.w   #3,d2
        add.w   d2,d2
        lea     ink_words,a0
        btst    #0,d1
        beq.s   .pl_e
        addq.l  #8,a0
.pl_e:
        move.w  0(a0,d2.w),d2           ; colour word
        lea     tile_gfx,a0
        move.w  d1,d3
        lsl.w   #7,d3
        adda.w  d3,a0
        move.w  d0,d3
        lsr.w   #2,d3
        add.w   d3,d3
        adda.w  d3,a0
        move.w  d0,d3
        and.w   #3,d3
        add.w   d3,d3
        lea     pixel_masks(pc),a1
        move.w  0(a1,d3.w),d4
        and.w   d4,d2
        not.w   d4
        and.w   d4,(a0)
        or.w    d2,(a0)
        rts

; void ql_off_fill(int x, int y, int w, int h, int ink) - as ql_play_fill,
; into the page: whole words where aligned, pixels at the edges
ql_off_fill:
        movem.l d2-d7,-(sp)
        movem.l 28(sp),d0-d4            ; x y w h ink
        sub.l   #32,d0                  ; QL x
        bge.s   .of_x0
        add.l   d0,d2                   ; clip left
        moveq   #0,d0
.of_x0:
        move.l  d0,d5
        add.l   d2,d5
        cmp.l   #256,d5
        ble.s   .of_x1
        move.l  #256,d2
        sub.l   d0,d2                   ; clip right
.of_x1:
        tst.l   d2
        ble     .of_out
        tst.l   d3
        ble     .of_out
        add.w   #PLAY_Y,d1
.of_row:
        move.w  d0,d5                   ; x
        move.w  d2,d6                   ; pixels left on this line
.of_px:
        move.w  d5,d7
        and.w   #3,d7
        bne.s   .of_one
        cmp.w   #4,d6
        blt.s   .of_one
        lea     tile_gfx,a1             ; a whole word
        move.w  d1,d7
        lsl.w   #7,d7
        adda.w  d7,a1
        move.w  d5,d7
        lsr.w   #1,d7                   ; (x/4)*2
        adda.w  d7,a1
        move.w  d4,d7
        and.w   #3,d7
        add.w   d7,d7
        lea     ink_words,a0
        btst    #0,d1
        beq.s   .of_we
        addq.l  #8,a0
.of_we:
        move.w  0(a0,d7.w),(a1)
        addq.w  #4,d5
        subq.w  #4,d6
        bra.s   .of_next
.of_one:
        movem.l d0-d6,-(sp)
        move.w  d5,d0
        move.l  d4,d2
        bsr     off_plot
        movem.l (sp)+,d0-d6
        addq.w  #1,d5
        subq.w  #1,d6
.of_next:
        tst.w   d6
        bgt.s   .of_px
        addq.w  #1,d1
        subq.l  #1,d3
        bne.s   .of_row
.of_out:
        movem.l (sp)+,d2-d7
        rts

; void ql_off_dissolve(void) - the page onto the screen, 2x2 pattern
ql_off_dissolve:
        movem.l d2-d6/a2,-(sp)
        lea     dis_tab(pc),a2
        moveq   #3,d6
.od_ph:
        move.w  (a2)+,d2                ; the pixels of this phase
        move.w  d2,d4
        swap    d2
        move.w  d4,d2                   ; (in both words of a long)
        move.l  d2,d4
        not.l   d4
        move.w  (a2)+,d3                ; first line (0 even, 1 odd)
        lea     SCREEN_BASE,a0
        lea     tile_gfx,a1
        lsl.w   #7,d3
        adda.w  d3,a0
        adda.w  d3,a1
        move.w  #(256/2)-1,d1
.od_ln:
        moveq   #(SCREEN_STRIDE/16)-1,d0
.od_wd:
        rept    4                       ; a line: 8 x 4 longs
        move.l  (a1)+,d3
        and.l   d2,d3
        move.l  (a0),d5
        and.l   d4,d5
        or.l    d3,d5
        move.l  d5,(a0)+
        endr
        dbra    d0,.od_wd
        lea     SCREEN_STRIDE(a0),a0    ; the other parity's line
        lea     SCREEN_STRIDE(a1),a1
        dbra    d1,.od_ln
        dbra    d6,.od_ph                ; (a phase takes ~3-4 frames: no wait between)
        movem.l (sp)+,d2-d6/a2
        rts

dis_tab:
        dc.w    $F0F0,0                 ; pixels 0-1 of each word, even lines
        dc.w    $0F0F,1                 ; pixels 2-3, odd lines
        dc.w    $0F0F,0
        dc.w    $F0F0,1
        even

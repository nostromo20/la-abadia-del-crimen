; ============================================================
; colour.s - CHARCOL: colours per pixel source and 2x2 dithers
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; The author's colour mapping (data/colour_mapping.json, made with
; tools/colour_mapper.html; tools/mkpalette.py -> palette_data.s pal_table)
; gives, per CPC palette, the QL colour of each pen for:
;   terrain    - tiles, fills, the parchment: everything not below
;   characters - the pixels the sprite mixer draws FROM A SPRITE (monks,
;                Guillermo, Adso, objects, doors, reflections)
;   panel      - the HUD under the play area
; and any colour may be a 2x2 checker dither: pixel (x, y) of the QL screen
; shows a when x + y is even, b when odd. Each table therefore exists for
; even and for odd QL lines (equal when nothing is dithered).
;
; Characters: the mixer keeps a 1-bit-per-pixel SPRITE MASK beside the packed
; buffer (MASK_OFF bytes after it, in the free part of the shared 8 KB
; buffer): one byte per buffer byte, bit 3-k = pixel k drawn by a sprite.
; The sprite kernel sets it, the tile combine clears it under tiles drawn in
; front, the clear of a sprite's area clears it, the lamp clears it.
; blit_packed then reads one combined table, cmb[mask nibble][CPC byte], with
; a fast path for bytes without sprite pixels. All of it only runs while the
; palette's characters row differs from its terrain row (char_sep): otherwise
; the pre-CHARCOL path, at no cost.
;
; Palette changes: terrain is recoloured on the screen (old pen -> new
; colour, dither aware); the panel and the sprites are REDRAWN by the C++
; (ql_palette_repaint), since their old colours cannot be told apart from
; the terrain's.
; The routines here replace the qlhooks.s versions kept under ifeq CHARCOL.
; ============================================================

        ifne    CHARCOL

        xdef    char_sep,cmb_e,cmb_odd_ptr,ink_cpc_o,ink_quad_o,pq_e,pq_o,ql_blit_plain
        xdef    ql_tile_rebuild

        if      PLAY_Y&1
        fail    "colour.s: tiles assume they start on even QL lines (PLAY_Y even)"
        endc

; ------------------------------------------------------------
; void ql_set_palette(int pal)
;  - palette 0 (the CPC's all-black palette, used to hide drawing) blanks the
;    screen and keeps the current colours for what is drawn next;
;  - any other change rebuilds the tables, recolours the terrain on the
;    screen and rebuilds the tile graphics.
; ------------------------------------------------------------
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
        beq     .sp_same
        movem.l d2-d7/a2-a6,-(sp)
        move.w  cur_pal_p1,old_pal_p1
        move.w  d1,cur_pal_p1
        lea     ink_words,a0            ; keep the old terrain colours (both parities)
        lea     old_ink,a1
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        lsl.w   #6,d0                   ; 64 bytes a palette
        lea     pal_table(pc),a2
        adda.w  d0,a2
        lea     ink_words,a1            ; terrain: even words, then odd words
        move.l  (a2),(a1)+
        move.l  4(a2),(a1)+
        move.l  8(a2),(a1)+
        move.l  12(a2),(a1)+
        lea     ink_words,a0
        lea     ink_quad,a1
        bsr     pal_quad
        lea     ink_words+8,a0
        lea     ink_quad_o,a1
        bsr     pal_quad
        lea     ink_quad,a0
        lea     ink_cpc,a1
        bsr     pal_cpc
        lea     ink_quad_o,a0
        lea     ink_cpc_o,a1
        bsr     pal_cpc
        lea     32(a2),a0               ; panel
        lea     pq_e,a1
        bsr     pal_quad
        lea     40(a2),a0
        lea     pq_o,a1
        bsr     pal_quad
        moveq   #1,d0
        and.w   48(a2),d0               ; characters row differs from terrain?
        move.b  d0,char_sep
        beq     .sp_nochar
        lea     16(a2),a0
        lea     quad_tmp,a1
        bsr     pal_quad
        lea     quad_tmp,a0
        lea     cc_e,a1
        bsr     pal_cpc
        lea     24(a2),a0
        lea     quad_tmp,a1
        bsr     pal_quad
        lea     quad_tmp,a0
        lea     cc_o,a1
        bsr     pal_cpc
        lea     cc_e,a0
        lea     ink_cpc,a1
        lea     cmb_e,a3
        bsr     pal_cmb
        lea     cmb_e,a3                ; odd lines: the same table ...
        move.l  (a2),d0                 ; ... unless some row differs by parity
        cmp.l   8(a2),d0
        bne.s   .sp_odd
        move.l  4(a2),d0
        cmp.l   12(a2),d0
        bne.s   .sp_odd
        move.l  16(a2),d0
        cmp.l   24(a2),d0
        bne.s   .sp_odd
        move.l  20(a2),d0
        cmp.l   28(a2),d0
        beq.s   .sp_one
.sp_odd:
        lea     cc_o,a0
        lea     ink_cpc_o,a1
        lea     cmb_o,a3
        bsr     pal_cmb
        lea     cmb_o,a3
.sp_one:
        move.l  a3,cmb_odd_ptr
.sp_nochar:
        tst.w   old_pal_p1
        beq.s   .sp_first               ; nothing on screen in the old colours yet
        bsr     recolour_screen
.sp_first:
        cmp.w   #2,cur_pal_p1           ; palette 1 (a parchment) draws no tiles, and its
        beq.s   .sp_notiles             ; tile area holds the off-screen page (ql_off_*)
        bsr     build_tiles
.sp_notiles:
        movem.l (sp)+,d2-d7/a2-a6
.sp_same:
        rts

; pal_quad: A0 = 4 colour words (pens 0-3), A1 = 256-word table:
; [p0<<6 | p1<<4 | p2<<2 | p3] = pixel 0..3 in pens p0..p3. Trashes D0-D1/A1.
pal_quad:
        movem.l d2-d4/a3,-(sp)
        lea     pixel_masks(pc),a3
        moveq   #0,d2
.pq_loop:
        move.w  d2,d0
        lsr.w   #6,d0
        add.w   d0,d0
        move.w  0(a0,d0.w),d4
        and.w   (a3),d4                 ; pixel 0
        move.w  d2,d0
        lsr.w   #4,d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a0,d0.w),d1
        and.w   2(a3),d1                ; pixel 1
        or.w    d1,d4
        move.w  d2,d0
        lsr.w   #2,d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a0,d0.w),d1
        and.w   4(a3),d1                ; pixel 2
        or.w    d1,d4
        move.w  d2,d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a0,d0.w),d1
        and.w   6(a3),d1                ; pixel 3
        or.w    d1,d4
        move.w  d4,(a1)+
        addq.w  #1,d2
        cmp.w   #256,d2
        blt.s   .pq_loop
        movem.l (sp)+,d2-d4/a3
        rts

; pal_cpc: A0 = a pal_quad table, A1 = 256-word table indexed by CPC byte.
; Trashes D0-D1/A1.
pal_cpc:
        movem.l d2/a2,-(sp)
        lea     unpack_lut,a2
        moveq   #0,d2
.pc_loop:
        moveq   #0,d0
        moveq   #3,d1
.pc_k:
        lsl.w   #2,d0
        or.b    (a2)+,d0
        dbra    d1,.pc_k
        add.w   d0,d0
        move.w  0(a0,d0.w),(a1)+
        addq.w  #1,d2
        cmp.w   #256,d2
        blt.s   .pc_loop
        movem.l (sp)+,d2/a2
        rts

; pal_cmb: A0 = characters table, A1 = terrain table (both by CPC byte),
; A3 = 16 x 256 words: [m][b] = the characters' colour on the pixels whose
; bit 3-k is set in mask nibble m, the terrain's elsewhere. Trashes D0/A3.
pal_cmb:
        movem.l d2-d6/a4,-(sp)
        lea     pixel_masks(pc),a4
        moveq   #0,d2                   ; m
.cm_m:
        moveq   #0,d5                   ; word mask of the sprite pixels
        moveq   #0,d3                   ; pixel k
.cm_k:
        moveq   #3,d4
        sub.w   d3,d4
        btst    d4,d2
        beq.s   .cm_kn
        move.w  d3,d4
        add.w   d4,d4
        or.w    0(a4,d4.w),d5
.cm_kn:
        addq.w  #1,d3
        cmp.w   #4,d3
        blt.s   .cm_k
        move.w  d5,d6
        not.w   d6
        moveq   #0,d3                   ; byte * 2
.cm_b:
        move.w  0(a0,d3.w),d4
        and.w   d5,d4
        move.w  0(a1,d3.w),d0
        and.w   d6,d0
        or.w    d0,d4
        move.w  d4,(a3)+
        addq.w  #2,d3
        cmp.w   #512,d3
        blt.s   .cm_b
        addq.w  #1,d2
        cmp.w   #16,d2
        blt.s   .cm_m
        movem.l (sp)+,d2-d6/a4
        rts

; ------------------------------------------------------------
; recolour_screen - the 200 lines of the CPC screen (QL lines PLAY_Y ..):
; colour c -> pen p of the old terrain colours (either line parity) -> the
; new terrain colour of p for this pixel's position (dither aware); colours
; not in the old palette stay. Two pixels at a time, a table per line parity:
; index = high-byte nibble << 4 | low-byte nibble (G,F,G,F / R,B,R,B).
; ------------------------------------------------------------
RC_LINES        equ 200                 ; the CPC screen: play area + panel, or the parchment
recolour_screen:
        movem.l d2-d7/a2-a3,-(sp)
        lea     rc_inv,a0               ; colour -> old pen, $FF = none
        moveq   #7,d0
.ri0:
        st      0(a0,d0.w)
        dbra    d0,.ri0
        lea     old_ink,a1              ; 4 even words, then 4 odd words
        moveq   #0,d2
.ri1:
        move.w  (a1)+,d0
        moveq   #3,d3
        and.w   d2,d3                   ; pen
        bsr     rc_index0
        tst.b   0(a0,d1.w)
        bpl.s   .ri2
        move.b  d3,0(a0,d1.w)
.ri2:
        bsr     rc_index1
        tst.b   0(a0,d1.w)
        bpl.s   .ri3
        move.b  d3,0(a0,d1.w)
.ri3:
        addq.w  #1,d2
        cmp.w   #8,d2
        blt.s   .ri1
        ; rc_map[parity*16 + pos*8 + c] = new colour (pos 0 = left pixel, 1 = right)
        lea     rc_map,a2
        moveq   #0,d4                   ; parity
.rm_par:
        moveq   #0,d5                   ; pos
.rm_pos:
        moveq   #0,d6                   ; c
.rm_c:
        moveq   #0,d1
        move.b  0(a0,d6.w),d1
        bmi.s   .rm_id                  ; not an old colour: stays
        move.w  d4,d0
        lsl.w   #2,d0
        add.w   d1,d0
        add.w   d0,d0
        lea     ink_words,a1
        move.w  0(a1,d0.w),d0           ; the pen's new word for this parity
        tst.w   d5
        bne.s   .rm_p1
        bsr     rc_index0
        bra.s   .rm_st
.rm_p1:
        bsr     rc_index1
.rm_st:
        move.b  d1,(a2)+
        bra.s   .rm_n
.rm_id:
        move.b  d6,(a2)+
.rm_n:
        addq.w  #1,d6
        cmp.w   #8,d6
        blt.s   .rm_c
        addq.w  #1,d5
        cmp.w   #2,d5
        blt.s   .rm_pos
        addq.w  #1,d4
        cmp.w   #2,d4
        blt.s   .rm_par
        ; pair tables, rtab_e then rtab_o (256 words each)
        lea     rtab_e,a1
        lea     rc_map,a2
        moveq   #0,d4                   ; parity
.rt_par:
        moveq   #0,d2                   ; index
.rt_tab:
        moveq   #0,d3                   ; result
        moveq   #1,d5                   ; pixel: 1 = left (bits 3,2), 0 = right (bits 1,0)
.rt_pix:
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
        move.w  d4,d0
        lsl.w   #4,d0
        add.w   d7,d0
        tst.w   d5
        bne.s   .rt_left
        addq.w  #8,d0                   ; right pixel: pos 1
.rt_left:
        moveq   #0,d1
        move.b  0(a2,d0.w),d1           ; new colour
        move.w  d1,d0
        and.w   #4,d0                   ; new G
        lsr.w   #1,d0                   ; to the G position of the pair (bit 1)
        lsl.w   d6,d0
        lsl.w   #8,d0
        or.w    d0,d3
        and.w   #3,d1                   ; new R,B
        lsl.w   d6,d1
        or.w    d1,d3
        dbra    d5,.rt_pix
        move.w  d3,(a1)+
        addq.w  #1,d2
        cmp.w   #256,d2
        blt.s   .rt_tab
        addq.w  #1,d4
        cmp.w   #2,d4
        blt     .rt_par
        ; the screen: each word = two pixel pairs (high nibbles, low nibbles)
        lea     SCREEN_BASE+PLAY_Y*SCREEN_STRIDE,a2
        move.w  #RC_LINES-1,d5
        moveq   #PLAY_Y&1,d6            ; parity of the line
.rc_line:
        lea     rtab_e,a1
        tst.w   d6
        beq.s   .rc_even
        lea     rtab_o,a1
.rc_even:
        moveq   #63,d7
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
        eor.w   #1,d6
        dbra    d5,.rc_line
        movem.l (sp)+,d2-d7/a2-a3
        rts

; colour index (G*4 + R*2 + B) of pixel 0 / pixel 1 of the Mode 8 word d0 -> d1
rc_index0:
        moveq   #0,d1
        btst    #15,d0
        beq.s   .r0g
        moveq   #4,d1
.r0g:
        btst    #7,d0
        beq.s   .r0r
        addq.w  #2,d1
.r0r:
        btst    #6,d0
        beq.s   .r0b
        addq.w  #1,d1
.r0b:
        rts
rc_index1:
        moveq   #0,d1
        btst    #13,d0
        beq.s   .r1g
        moveq   #4,d1
.r1g:
        btst    #5,d0
        beq.s   .r1r
        addq.w  #2,d1
.r1r:
        btst    #4,d0
        beq.s   .r1b
        addq.w  #1,d1
.r1b:
        rts

; ------------------------------------------------------------
; build_tiles - Mode 8 tile graphics + masks from the CPC tiles (roms 0x8300)
; through the current terrain colours. A tile always starts on an even QL
; line (PLAY_Y even, tiles on 8-line rows), so its rows 1, 3, 5, 7 take the
; odd-line colours: dithered tiles need no second tile set.
; ------------------------------------------------------------
build_tiles:
        movem.l d2-d7/a2-a4,-(sp)
        move.l  #rom_image+$4000+$8300,a0
        lea     tile_gfx,a1
        moveq   #0,d7                   ; tile number
.bt_next:
        bsr.s   bt_one
        addq.w  #1,d7
        cmp.w   #256,d7
        blt.s   .bt_next
        movem.l (sp)+,d2-d7/a2-a4
        rts

; ------------------------------------------------------------
; void ql_tile_rebuild(int id) - QL_TILE_COMPOSE (GeneradorPantallas::qlCompone):
; tile id's graphic in the tile table changed; rebuild its Mode 8 copy
; ------------------------------------------------------------
ql_tile_rebuild:
        movem.l d2-d7/a2-a4,-(sp)
        move.l  40(sp),d7
        and.l   #$FF,d7
        move.l  d7,d0
        lsl.l   #5,d0                   ; id*32
        move.l  #rom_image+$4000+$8300,a0
        adda.l  d0,a0
        lea     tile_gfx,a1
        add.l   d0,d0                   ; id*64
        adda.l  d0,a1
        bsr.s   bt_one
        movem.l (sp)+,d2-d7/a2-a4
        rts

; bt_one: tile D7 (its 32 CPC bytes at A0) -> 32 Mode 8 words at A1 and its
; mask TILE_DATA_SIZE after; A0 and A1 advance past it. Trashes D0-D6/A2-A4
bt_one:
        lea     unpack_lut,a2
        lea     pixel_masks(pc),a4
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
        lea     ink_quad,a3             ; row (31 - d5) / 4: even rows ...
        btst    #2,d5
        bne.s   .bt_even
        lea     ink_quad_o,a3           ; ... odd rows
.bt_even:
        move.w  0(a3,d1.w),d1           ; colour word
        move.w  d2,d3
        not.w   d3
        and.w   d3,d1                   ; transparent pixels are 0 in the graphic
        move.w  d2,TILE_DATA_SIZE(a1)   ; mask
        move.w  d1,(a1)+
        dbra    d5,.bt_byte
        rts

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
        ble     .pf_out
        tst.l   d3
        ble     .pf_out
        add.w   #PLAY_Y,d1
        and.w   #3,d4
        add.w   d4,d4
        lea     ink_words,a0
        move.w  8(a0,d4.w),d5           ; odd-line colour
        move.w  0(a0,d4.w),d4           ; even-line colour
        cmp.w   d4,d5
        bne.s   .pf_dith
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
        bra.s   .pf_out
.pf_dith:                               ; a dithered pen: line by line
        movem.l d0-d5,-(sp)
        btst    #0,d1
        beq.s   .pf_de
        move.w  d5,d4
.pf_de:
        moveq   #1,d3
        bsr     fill_rect
        movem.l (sp)+,d0-d5
        addq.w  #1,d1
        subq.l  #1,d3
        bne.s   .pf_dith
.pf_out:
        movem.l (sp)+,d2-d7
        rts

; ------------------------------------------------------------
; void ql_play_triangle(int x, int y, int lado, int c1, int c2)  (CPC coords)
; The parchment's page-turn triangle (Pergamino::dibujaTriangulo): for each
; line j < lado: pixels x..x+j in pen c1, then x+j+1..x+j+4 in pen c2.
; ------------------------------------------------------------
; ------------------------------------------------------------
; void ql_play_triangle(int x, int y, int lado, int c1, int c2) - the parchment's page turn
; (Pergamino::dibujaTriangulo): for j = 0 .. lado-1, CPC line y+j: pixels x .. x+j in colour c1,
; then the 4 pixels after them in c2 (terrain colours, the line's parity). The same pixels as
; ql_play_triangle_old (two hline calls a line), as two span fills a line with whole words and
; longs in between (docs/speed_vs_cpc.md: the page turn).
; ------------------------------------------------------------
ql_play_triangle:                       ; the whole triangle: no line from the previous frame
        clr.l   -(sp)                   ; incTo
        clr.l   -(sp)                   ; incFrom
        move.l  28(sp),-(sp)            ; c2, c1, lado, y, x again
        move.l  28(sp),-(sp)
        move.l  28(sp),-(sp)
        move.l  28(sp),-(sp)
        move.l  28(sp),-(sp)
        bsr.s   ql_play_triangle_inc
        lea     28(sp),sp
        rts

; void ql_play_triangle_inc(int x, int y, int lado, int c1, int c2, int incFrom, int incTo)
; as ql_play_triangle, but the lines j in incFrom .. incTo-1 are known to hold the previous
; animation frame's triangle (Pergamino.cpp says which): of their c1 run only the first word and
; the last whole word are written (the rest is c1 already), then the word where c1 ends and c2's
; 4 pixels, as always. The screen ends up the same (tools/pagetest.py), with ~8 pixels a line.
        xdef    ql_play_triangle_inc
ql_play_triangle_inc:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes -> args at 44
        lea     ink_words,a1
        move.l  56(sp),d0               ; c1
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d6           ; c1: even lines (low word) ...
        swap    d6
        move.w  8(a1,d0.w),d6           ; ... odd lines
        swap    d6                      ; (low = even, high = odd)
        move.l  60(sp),d0               ; c2
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d7
        swap    d7
        move.w  8(a1,d0.w),d7
        swap    d7
        move.l  44(sp),a3
        suba.w  #32,a3                  ; A3 = QL x of pixel j = 0
        moveq   #0,d5                   ; j
        ; the page turn's own case (every call): x on a word, every line on the screen and
        ; inside the CPC screen: one loop with everything in registers
        move.l  a3,d0
        moveq   #3,d1
        and.l   d0,d1
        bne     .nt_line
        tst.l   d0
        bmi     .nt_line
        move.l  52(sp),d1               ; lado
        ble     .nt_line
        add.l   d1,d0
        addq.l  #4,d0
        cmp.l   #256,d0
        bgt     .nt_line
        move.l  48(sp),d0               ; y
        bmi     .nt_line
        add.l   d1,d0
        cmp.l   #200,d0
        bgt     .nt_line
        move.l  a6,-(sp)                ; (A6: one register more)
        move.l  d1,a6                   ; A6 = lado
        move.l  68(sp),a4               ; incFrom (args 4 bytes further now)
        move.l  72(sp),a5               ; incTo
        move.l  52(sp),d0               ; y
        add.w   #PLAY_Y,d0
        btst    #0,d0
        beq.s   .ft_par
        swap    d6                      ; an odd first line: the odd colours in the low words
        swap    d7
.ft_par:
        lea     SCREEN_BASE,a0
        lsl.w   #7,d0
        adda.w  d0,a0                   ; A0 = the first line
        move.l  a3,d0
        lsr.w   #1,d0
        move.w  d0,a3                   ; A3 = x/2: the first word's offset in a line
        lea     sp_right(pc),a1
.ft_row:
        move.w  d6,d4                   ; c1, c2 for this line
        move.w  d7,d3
        lea     0(a0,a3.w),a2
        move.w  d5,d2
        addq.w  #1,d2                   ; n = j+1 pixels of c1
        move.w  d2,d1
        lsr.w   #2,d2                   ; whole words of c1
        beq.s   .ft_part
        cmp.l   a4,d5                   ; a line kept from the previous frame?
        blt.s   .ft_full
        cmp.l   a5,d5
        bge.s   .ft_full
        move.w  d4,(a2)                 ; yes: its first word and its last whole word
        add.w   d2,d2
        move.w  d4,-2(a2,d2.w)
        adda.w  d2,a2
        bra.s   .ft_part
.ft_full:
        move.w  d4,d0
        swap    d0
        move.w  d4,d0
        lsr.w   #1,d2
        bcc.s   .ft_l
        move.w  d4,(a2)+
.ft_l:
        subq.w  #1,d2
        bmi.s   .ft_part
.ft_ll:
        move.l  d0,(a2)+
        dbra    d2,.ft_ll
.ft_part:
        and.w   #3,d1                   ; c1 pixels in the next word (0-3)
        beq.s   .ft_c2w
        add.w   d1,d1
        move.w  -2(a1,d1.w),d0          ; their mask
        move.w  d0,d2
        and.w   d4,d0
        not.w   d2
        move.w  d3,d1
        and.w   d2,d1
        or.w    d1,d0
        move.w  d0,(a2)+
        not.w   d2
        move.w  d2,d0
        and.w   d3,d0
        not.w   d2
        and.w   (a2),d2
        or.w    d2,d0
        move.w  d0,(a2)
        bra.s   .ft_next
.ft_c2w:
        move.w  d3,(a2)
.ft_next:
        lea     SCREEN_STRIDE(a0),a0
        swap    d6                      ; the other parity
        swap    d7
        addq.l  #1,d5
        cmp.l   a6,d5
        blt.s   .ft_row
        move.l  (sp)+,a6
        bra     .nt_done
.nt_line:
        cmp.l   52(sp),d5
        bge     .nt_done
        move.l  48(sp),d1
        add.l   d5,d1                   ; CPC y
        bmi     .nt_next
        cmp.l   #200,d1
        bge     .nt_next
        add.w   #PLAY_Y,d1
        lea     SCREEN_BASE,a0
        move.w  d1,d2
        lsl.w   #7,d2
        adda.w  d2,a0                   ; A0 = the line
        move.w  d6,d4                   ; c1 for this line's parity
        move.w  d7,d3                   ; c2
        btst    #0,d1
        beq.s   .nt_even
        swap    d6
        move.w  d6,d4
        swap    d6
        swap    d7
        move.w  d7,d3
        swap    d7
.nt_even:
        move.l  a3,d0                   ; from x
        move.l  d0,d1
        add.l   d5,d1
        addq.l  #1,d1                   ; to x+j+1 (exclusive)
        ; the page turn's own case (every call): x on a word, the whole line on the screen.
        ; c1 is then whole words, and the word where c1 stops takes c2 in its other pixels
        ; (and the next one the rest of c2's 4 pixels)
        moveq   #3,d2
        and.l   d0,d2
        bne     .nt_gen
        tst.l   d0
        bmi     .nt_gen
        move.l  d1,d2
        addq.l  #4,d2
        cmp.l   #256,d2
        bgt     .nt_gen
        lsr.w   #1,d0                   ; x/4 words = x/2 bytes
        lea     0(a0,d0.w),a2
        move.w  d5,d2
        addq.w  #1,d2                   ; n = j+1 pixels of c1
        move.w  d2,d1
        lsr.w   #2,d2                   ; whole words of c1
        beq.s   .nt_part
        cmp.l   64(sp),d5               ; a line kept from the previous frame?
        blt.s   .nt_full
        cmp.l   68(sp),d5
        bge.s   .nt_full
        move.w  d4,(a2)                 ; yes: its first word ...
        add.w   d2,d2
        move.w  d4,-2(a2,d2.w)          ; ... and its last whole word of c1
        adda.w  d2,a2
        bra.s   .nt_part
.nt_full:
        move.w  d4,d0
        swap    d0
        move.w  d4,d0                   ; c1 in both words
        lsr.w   #1,d2                   ; longs (carry: a word more)
        bcc.s   .nt_l
        move.w  d4,(a2)+
.nt_l:
        subq.w  #1,d2
        bmi.s   .nt_part
.nt_ll:
        move.l  d0,(a2)+
        dbra    d2,.nt_ll
.nt_part:
        and.w   #3,d1                   ; c1 pixels in the next word (0-3)
        add.w   d1,d1
        lea     sp_right(pc),a4
        tst.w   d1
        beq.s   .nt_c2w                 ; none: that word is all c2
        move.w  -2(a4,d1.w),d0          ; the mask of those c1 pixels (from the left)
        move.w  d0,d2
        and.w   d4,d0                   ; c1 there ...
        not.w   d2
        move.w  d3,d1
        and.w   d2,d1                   ; ... c2 in the rest
        or.w    d1,d0
        move.w  d0,(a2)+
        not.w   d2                      ; c2 goes on into the next word, as many pixels as c1 had there
        move.w  d2,d0
        and.w   d3,d0
        not.w   d2
        and.w   (a2),d2
        or.w    d2,d0
        move.w  d0,(a2)
        bra.s   .nt_next
.nt_c2w:
        move.w  d3,(a2)                 ; c1 ended on a word: the 4 pixels of c2 are the next word
        bra.s   .nt_next
.nt_gen:
        movem.l d1/d3,-(sp)
        bsr     span
        movem.l (sp)+,d0/d4             ; c2 from x+j+1 ...
        move.l  d0,d1
        addq.l  #4,d1                   ; ... 4 pixels
        bsr     span
.nt_next:
        addq.l  #1,d5
        bra     .nt_line
.nt_done:
        movem.l (sp)+,d2-d7/a2-a5
        rts

; span: the QL pixels D0 .. D1-1 of the line at A0 in the colour word D4 (clipped to 0..255).
; Trashes D0-D2, A2, A4.
span:
        tst.l   d0
        bge.s   .sp_a
        moveq   #0,d0
.sp_a:
        cmp.l   #256,d1
        ble.s   .sp_b
        move.l  #256,d1
.sp_b:
        cmp.l   d1,d0
        bge.s   .sp_out
        subq.l  #1,d1                   ; the last pixel
        move.w  d0,d2
        lsr.w   #2,d2
        add.w   d2,d2
        lea     0(a0,d2.w),a2           ; the first word
        lea     sp_left(pc),a4
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a4,d0.w),d0           ; its mask (pixels from the first on)
        move.w  d1,d2
        lsr.w   #2,d2
        add.w   d2,d2
        lea     0(a0,d2.w),a4           ; the last word
        lea     sp_right(pc),a5
        and.w   #3,d1
        add.w   d1,d1
        move.w  0(a5,d1.w),d1           ; its mask (pixels up to the last)
        cmpa.l  a2,a4
        bne.s   .sp_two
        and.w   d1,d0                   ; one word
        move.w  d0,d1
        not.w   d1
        and.w   (a2),d1
        and.w   d4,d0
        or.w    d0,d1
        move.w  d1,(a2)
.sp_out:
        rts
.sp_two:
        move.w  d0,d2                   ; the first word
        not.w   d2
        and.w   (a2),d2
        and.w   d4,d0
        or.w    d0,d2
        move.w  d2,(a2)+
        move.l  a4,d2                   ; whole words between
        sub.l   a2,d2
        lsr.l   #1,d2                   ; words
        beq.s   .sp_last
        move.w  d4,d0
        swap    d0
        move.w  d4,d0                   ; the colour in both words of a long
        lsr.l   #1,d2                   ; longs (the carry: one word more)
        bcc.s   .sp_l
        move.w  d4,(a2)+
.sp_l:
        subq.l  #1,d2
        bmi.s   .sp_last
.sp_ll:
        move.l  d0,(a2)+
        dbra    d2,.sp_ll
.sp_last:
        move.w  d1,d2                   ; the last word
        not.w   d2
        and.w   (a4),d2
        and.w   d4,d1
        or.w    d1,d2
        move.w  d2,(a4)
        rts

sp_left:
        dc.w    $FFFF,$3F3F,$0F0F,$0303
sp_right:
        dc.w    $C0C0,$F0F0,$FCFC,$FFFF

; the version before 2026-10-05 (two hline calls a line): kept for the harness's differential
; check of the page turn (header +30 bit 3, Pergamino.cpp), same arguments; not in the release
        ifnd    RELEASE
        xdef    ql_play_triangle_old
ql_play_triangle_old:
        movem.l d2-d7/a2,-(sp)          ; 28 bytes -> args at 32
        lea     ink_words,a1
        move.l  44(sp),d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d6           ; colour 1 (even lines)
        move.w  8(a1,d0.w),tri_o1       ; (odd lines)
        move.l  48(sp),d0
        and.w   #3,d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d7           ; colour 2
        move.w  8(a1,d0.w),tri_o2
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
        btst    #0,d1
        beq.s   .tr_e1
        move.w  tri_o1,d4
.tr_e1:
        movem.l d0-d2,-(sp)
        bsr     hline
        movem.l (sp)+,d0-d2
        add.l   d2,d0                   ; x+j+1
        moveq   #4,d2
        move.w  d7,d4
        btst    #0,d1
        beq.s   .tr_e2
        move.w  tri_o2,d4
.tr_e2:
        bsr     hline
.tr_next:
        addq.l  #1,d5
        bra.s   .tr_line
.tr_done:
        movem.l (sp)+,d2-d7/a2
        rts
        endif                           ; RELEASE

; ------------------------------------------------------------
; void ql_play_pixel(int x, int y, int ink)
; ------------------------------------------------------------
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
        btst    #0,d1
        beq.s   .pp_e
        addq.l  #8,a0                   ; odd line
.pp_e:
        move.w  0(a0,d2.w),d2
        bsr     plot_pixel              ; screen.s: D0 x D1 y D2 colour
.pp_out:
        movem.l (sp)+,d2-d4
        rts

; ------------------------------------------------------------
; void ql_play_blit(int x, int y, int w, int h, const u8 *src, int stride)
; byte-per-pixel inks -> play area (terrain colours)
; ------------------------------------------------------------
ql_play_blit:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes -> args at 44
        movem.l 44(sp),d0-d3/a1         ; x y w h src
        move.l  64(sp),d7               ; stride
        sub.l   #32,d0
        add.w   #PLAY_Y,d1
        lea     ink_quad,a2
        lea     ink_quad_o,a5
        bsr     blit_inks
        movem.l (sp)+,d2-d7/a2-a5
        rts

; blit_inks: D0 QL x (multiple of 4, may be clipped), D1 QL y, D2 w, D3 h,
; A1 src (one pen a byte), D7 src stride, A2/A5 the colour tables (pal_quad)
; for even/odd QL lines. Trashes D0-D6/A0-A5
blit_inks:
        tst.l   d2
        ble     .bi_out
        tst.l   d3
        ble     .bi_out
        tst.l   d0                      ; clip left
        bge.s   .bi_l
        sub.l   d0,a1
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
        btst    #0,d1
        beq.s   .bi_par
        exg     a2,a5                   ; the first line is odd
.bi_par:
        lea     SCREEN_BASE,a0
        move.l  d1,d4
        lsl.l   #7,d4
        adda.l  d4,a0
        lsr.w   #1,d0
        and.w   #$FFFE,d0
        adda.w  d0,a0
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
        exg     a2,a5
        dbra    d3,.bi_line
.bi_out:
        rts

; ------------------------------------------------------------
; void ql_play_blit_p(int x, int y, int w, int h, const u8 *src, int stride)
; packed mixing buffer (CPC bytes, 4 pixels each) -> play area.
; x and w in pixels (multiples of 4, CPC coords), stride in bytes. With
; separate character colours (char_sep) the sprite mask at src + MASK_OFF
; picks the characters' colours.
; ------------------------------------------------------------
ql_play_blit_p:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes -> args at 48
        movem.l 48(sp),d0-d3/a1         ; x y w h src
        move.l  68(sp),d7               ; stride (bytes)
        sub.l   #32,d0
        add.w   #PLAY_Y,d1
        bsr     blit_packed
        movem.l (sp)+,d2-d7/a2-a6
        rts

; void ql_play_blit_pi(int x, int y, int w, int h, const u8 *src, int stride)   (INTERLEAVE)
; ql_play_blit_p on the interleaved mixing buffer: src = the first element (mask byte, then the
; pens), stride in elements. The character-colour path reads the whole word: mask * 256 + pens
; indexes cmb[mask][pens] directly (the mask is never above 15)
        xdef    ql_play_blit_pi
ql_play_blit_pi:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes -> args at 48
        movem.l 48(sp),d0-d3/a1         ; x y w h src
        move.l  68(sp),d7               ; stride (elements)
        add.l   d7,d7                   ; (bytes)
        sub.l   #32,d0
        add.w   #PLAY_Y,d1
        bsr.s   blit_packed_i
        movem.l (sp)+,d2-d7/a2-a6
        rts

blit_packed_i:
        tst.l   d2
        ble     .bi2_out
        tst.l   d3
        ble     .bi2_out
        tst.l   d0                      ; clip left
        bge.s   .bi2_l
        move.l  d0,d4
        asr.l   #1,d4
        and.w   #$FFFE,d4               ; (-x/4 elements of 2 bytes)
        sub.l   d4,a1
        add.l   d0,d2
        moveq   #0,d0
.bi2_l:
        move.l  d0,d4
        add.l   d2,d4
        cmp.l   #256,d4
        ble.s   .bi2_r
        move.l  #256,d2
        sub.l   d0,d2
.bi2_r:
        tst.l   d2
        ble     .bi2_out
        lsr.l   #2,d2                   ; words per line
        subq.l  #1,d2
        bmi     .bi2_out
        lea     SCREEN_BASE,a0
        move.l  d1,d4
        lsl.l   #7,d4
        adda.l  d4,a0
        lsr.w   #1,d0
        and.w   #$FFFE,d0
        adda.w  d0,a0
        subq.l  #1,d3
        tst.b   char_sep
        beq.s   .bi2_plain
        tst.b   ql_blit_plain           ; an area without sprites: the plain copy
        beq.s   .bi2_m
.bi2_plain:
        lea     ink_cpc,a2              ; 256 words: CPC byte -> Mode 8 word
        lea     ink_cpc_o,a5
        btst    #0,d1
        beq.s   .bi2_line
        exg     a2,a5
.bi2_line:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d2,d6
.bi2_word:
        moveq   #0,d4
        move.b  1(a4),d4                ; the pens
        addq.l  #2,a4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bi2_word
        lea     SCREEN_STRIDE(a0),a0
        adda.l  d7,a1
        exg     a2,a5
        dbra    d3,.bi2_line
.bi2_out:
        rts
.bi2_m:                                 ; separate character colours: one word, one lookup
        lea     cmb_e,a2                ; cmb[mask nibble][CPC byte]
        move.l  cmb_odd_ptr,a5
        btst    #0,d1
        beq.s   .bi2_mline
        exg     a2,a5
.bi2_mline:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d2,d6
        lsr.w   #1,d6                   ; two words a dbra (an odd word first)
        btst    #0,d2
        bne.s   .bi2_pair
        move.w  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        subq.w  #1,d6
        bmi.s   .bi2_meol
.bi2_pair:
        move.w  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        move.w  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bi2_pair
.bi2_meol:
        lea     SCREEN_STRIDE(a0),a0
        adda.l  d7,a1
        exg     a2,a5
        dbra    d3,.bi2_mline
        rts

; BP_UNROLL (2026-10-06): the plain copy and the character-colour path two words a dbra
; (kerntest x_blit_p / blit_pm, colourcheck, hdiff). 0 = one.
BP_UNROLL       equ     1

; BMWORD: one word of the character-colour path: cmb[mask nibble][CPC byte] (A2), source A4,
; mask A6, screen A3; D4/D5 trashed
BMWORD  macro
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.b  (a6)+,d5
        beq.s   .t\@                    ; no sprite pixel: row 0 = terrain
        and.w   #$0F,d5
        ror.w   #7,d5                   ; mask * 512
        add.w   d5,d4
.t\@:
        move.w  0(a2,d4.w),(a3)+
        endm
; blit_packed: D0 QL x, D1 QL y, D2 w, D3 h, A1 packed CPC bytes, D7 stride
; in bytes. One source byte = one Mode 8 word. Trashes D0-D6/A0-A6
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
        subq.l  #1,d3
        tst.b   char_sep
        beq.s   .bp_plain
        tst.b   ql_blit_plain           ; an area without sprites: the plain copy
        beq.s   .bm
.bp_plain:
        lea     ink_cpc,a2              ; 256 words: CPC byte -> Mode 8 word
        lea     ink_cpc_o,a5
        btst    #0,d1
        beq.s   .bp_line
        exg     a2,a5
.bp_line:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d2,d6
        if      BP_UNROLL
        ; (2026-10-06) two words a dbra: an odd word first, then pairs
        lsr.w   #1,d6                   ; pairs - 1 (an even count), or the pairs after the odd word
        btst    #0,d2
        bne.s   .bp_pair                ; an even number of words
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        subq.w  #1,d6
        bmi.s   .bp_eol                 ; just the one
.bp_pair:
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bp_pair
.bp_eol:
        else
.bp_word:
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bp_word
        endif
        lea     SCREEN_STRIDE(a0),a0
        adda.l  d7,a1
        exg     a2,a5
        dbra    d3,.bp_line
.bp_out:
        rts
.bm:                                    ; separate character colours
        lea     cmb_e,a2                ; cmb[mask nibble][CPC byte]
        move.l  cmb_odd_ptr,a5
        btst    #0,d1
        beq.s   .bm_line
        exg     a2,a5
.bm_line:
        move.l  a0,a3
        move.l  a1,a4
        lea     MASK_OFF(a1),a6         ; the sprite mask
        move.w  d2,d6
        if      BP_UNROLL
        ; (2026-10-06) two words a dbra (an odd word first); the mask nibble times 512 by
        ; ror #7 instead of lsl #8 + add
        lsr.w   #1,d6
        btst    #0,d2
        bne.s   .bm_pair
        BMWORD
        subq.w  #1,d6
        bmi.s   .bm_eol
.bm_pair:
        BMWORD
        BMWORD
        dbra    d6,.bm_pair
        bra.s   .bm_eol
        endif
.bm_word:
        moveq   #0,d4
        move.b  (a4)+,d4
        add.w   d4,d4
        move.b  (a6)+,d5
        bne.s   .bm_spr
        move.w  0(a2,d4.w),(a3)+        ; no sprite pixel: row 0 = terrain
        dbra    d6,.bm_word
        bra.s   .bm_eol
.bm_spr:
        and.w   #$0F,d5
        lsl.w   #8,d5
        add.w   d5,d5                   ; mask * 512
        add.w   d5,d4
        move.w  0(a2,d4.w),(a3)+
        dbra    d6,.bm_word
.bm_eol:
        lea     SCREEN_STRIDE(a0),a0
        adda.l  d7,a1
        exg     a2,a5
        dbra    d3,.bm_line
        rts

; ------------------------------------------------------------
; void ql_panel_present(int x, int y, int w, int h, const u8 *panel)
; panel = 320x40 inks (CPC y 160..199), shown at QL line PANEL_QL_Y with the
; panel colours.
; ------------------------------------------------------------
ql_panel_present:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes -> args at 44
        movem.l 44(sp),d0-d3/a1         ; x y w h panel
        move.l  d0,d4                   ; round x down / w up to multiples of 4
        and.l   #3,d4
        sub.l   d4,d0
        add.l   d4,d2
        addq.l  #3,d2
        and.l   #-4,d2
        move.l  d1,d4                   ; source = panel + y*320 + x
        mulu    #320,d4
        add.l   d0,d4
        adda.l  d4,a1
        sub.l   #32,d0
        add.l   #PANEL_QL_Y,d1
        move.l  #320,d7
        lea     pq_e,a2
        lea     pq_o,a5
        bsr     blit_inks
        movem.l (sp)+,d2-d7/a2-a5
        rts

; ------------------------------------------------------------
        section .bss,bss
        cnop    0,4
char_sep:                               ; 1 while the palette has separate character colours
        ds.b    2                       ; (even: every symbol on an even address)
ql_blit_plain:                          ; set by the C++ before ql_play_blit_p: 1 = no sprite in the area
        ds.b    2
cmb_odd_ptr:                            ; cmb_o, or cmb_e when no row is dithered
        ds.l    1
tri_o1:
        ds.w    1
tri_o2:
        ds.w    1
rc_inv:
        ds.b    8
rc_map:
        ds.b    32
ink_quad_o:
        ds.w    256
ink_cpc_o:
        ds.w    256
pq_e:                                   ; panel colours, even / odd lines
        ds.w    256
pq_o:
        ds.w    256
quad_tmp:
        ds.w    256
cc_e:                                   ; characters' colours by CPC byte, even / odd
        ds.w    256
cc_o:
        ds.w    256
rtab_e:
        ds.w    256
rtab_o:
        ds.w    256
cmb_e:                                  ; 16 x 256 words each
        ds.w    4096
cmb_o:
        ds.w    4096
        section .text.start,code

        endc

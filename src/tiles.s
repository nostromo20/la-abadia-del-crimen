; ============================================================
; tiles.s - asm twin of the mixer's tile depth pass (QL_ASM_TILES)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; a_tiles_prof must give exactly the results of c_tiles_prof (cpp/port/
; ql_kernels.c), the line-by-line C copy of MezcladorSprites::
; dibujaTilesEntreProfundidades on the packed buffer; tools/kerntest.py runs
; both on random tile buffers, and hdiff compares the game with the oracle.
; ============================================================

        xdef    a_tiles_prof

; TP_REGS (2026-10-06): the tile combines called with their arguments in registers. 0 = on
; the stack, as a C call
TP_REGS equ     1

; parameter block (ints), see ql_kernels.h
TP_BT   equ     0
TP_BX   equ     4
TP_BY   equ     8
TP_NX   equ     12
TP_NY   equ     16
TP_MINX equ     20
TP_MINY equ     24
TP_MAXX equ     28
TP_MAXY equ     32
TP_MIX  equ     36
TP_DESP equ     40
TP_ANCH equ     44
TP_ULT  equ     48
TP_GFX  equ     52
TP_MASK equ     56                      ; CHARCOL: bit 0 = keep the sprite mask (a_combina_tile_pm),
                                        ; bit 1 = the interleaved buffer (INTERLEAVE, a_combina_tile_p*i)

; TP_INLINE (2026-10-06): the layer test written out for each of the two layers (TPLAYER), the
; last-pass flag in D4 (read once), the depth tests branching straight to the end: the same
; tests and order (kerntest tiles_prof, inttest). 0 = the bsr version (.tp_layer, kept).
TP_INLINE       equ     1

; TPLAYER: one depth layer of the cell at A4 ((A4) profX, 2(A4) profY, 4(A4) tile)
TPLAYER macro
        moveq   #0,d0
        move.b  4(a4),d0                ; tile
        beq.s   .c\@                     ; tile 0 is never drawn
        moveq   #0,d1
        move.b  (a4),d1                 ; profX
        tst.b   d5
        beq.s   .k\@
        btst    #7,d1
        beq.s   .k\@
        bsr     .tp_comb                ; drawn in this call already: combine it again
        bra.s   .c\@
.k\@:
        moveq   #0,d2
        move.b  2(a4),d2                ; profY
        cmp.l   TP_MINX(a5),d1
        bge.s   .m\@
        cmp.l   TP_MINY(a5),d2
        blt.s   .c\@                     ; behind the lower limit in x and y
.m\@:
        cmp.l   TP_MAXY(a5),d2
        bge.s   .c\@
        cmp.l   TP_MAXX(a5),d1
        bge.s   .c\@
        btst    #7,(a4)
        bne.s   .c\@                     ; already drawn
        bset    #7,(a4)
        moveq   #1,d5                   ; haPintado
        bsr     .tp_comb
.c\@:
        tst.b   d4
        beq.s   .o\@
        bclr    #7,(a4)                 ; last pass: clear the drawn mark
.o\@:
        endm

; ------------------------------------------------------------
; void a_tiles_prof(const int *p)
; A5 p, A6 desp of this tile row, A3 despX, A2 this row of bufferTiles,
; A4 the TileInfo (+k for layer k), D7 j, D6 i, D5 haPintado, D4 visible.
; ------------------------------------------------------------
a_tiles_prof:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes saved -> arg at 48
        move.l  48(sp),a5
        move.l  TP_DESP(a5),a6
        if      TP_INLINE
        tst.l   TP_ULT(a5)
        sne     d4                      ; the last pass (D4 survives the combines)
        endif
        moveq   #0,d7                   ; j
.tp_row:
        cmp.l   TP_NY(a5),d7
        bge     .tp_done
        move.l  TP_BY(a5),d0
        add.l   d7,d0                   ; bufTilesPosY + j
        cmp.l   #20,d0
        bhs     .tp_rnext               ; outside the tile buffer: the whole row
        mulu    #16*6,d0
        move.l  TP_BT(a5),a2
        adda.l  d0,a2                   ; row of bufferTiles
        move.l  a6,a3                   ; despX = desp
        moveq   #0,d6                   ; i
.tp_col:
        cmp.l   TP_NX(a5),d6
        bge     .tp_rnext
        move.l  TP_BX(a5),d1
        add.l   d6,d1                   ; bufTilesPosX + i
        cmp.l   #16,d1
        bhs     .tp_cnext
        add.w   d1,d1
        move.w  d1,d0
        add.w   d1,d1
        add.w   d0,d1                   ; x*6
        lea     0(a2,d1.w),a4           ; ti
        moveq   #0,d5                   ; haPintado = false
        if      TP_INLINE
        TPLAYER                         ; k = 0
        addq.l  #1,a4
        TPLAYER                         ; k = 1
        else
        bsr     .tp_layer               ; k = 0
        addq.l  #1,a4
        bsr     .tp_layer               ; k = 1
        endif
.tp_cnext:
        lea     16(a3),a3               ; despX += 16
        addq.l  #1,d6
        bra     .tp_col
.tp_rnext:
        move.l  TP_ANCH(a5),d0
        lsl.l   #5,d0                   ; anchoFinal*4*8
        adda.l  d0,a6
        addq.l  #1,d7
        bra     .tp_row
.tp_done:
        movem.l (sp)+,d2-d7/a2-a6
        rts

; one depth layer: (A4) profX, 2(A4) profY, 4(A4) tile
.tp_layer:
        moveq   #0,d0
        move.b  4(a4),d0                ; tile
        beq.s   .tp_clear               ; tile 0 is never drawn
        moveq   #1,d4                   ; visible
        moveq   #0,d1
        move.b  (a4),d1                 ; profX
        tst.b   d5
        beq.s   .tp_chk
        btst    #7,d1
        beq.s   .tp_chk
        bsr.s   .tp_comb                ; drawn in this call already: combine it again
        bra.s   .tp_clear
.tp_chk:
        moveq   #0,d2
        move.b  2(a4),d2                ; profY
        cmp.l   TP_MINX(a5),d1
        bge.s   .tp_max
        cmp.l   TP_MINY(a5),d2
        blt.s   .tp_inv                 ; behind the lower limit in x and y
.tp_max:
        cmp.l   TP_MAXY(a5),d2
        bge.s   .tp_inv
        cmp.l   TP_MAXX(a5),d1
        blt.s   .tp_vis
.tp_inv:
        moveq   #0,d4
.tp_vis:
        tst.b   d4
        beq.s   .tp_clear
        btst    #7,(a4)
        bne.s   .tp_clear               ; already drawn
        bset    #7,(a4)
        moveq   #1,d5                   ; haPintado
        bsr.s   .tp_comb
.tp_clear:
        tst.l   TP_ULT(a5)
        beq.s   .tp_lout
        bclr    #7,(a4)                 ; last pass: clear the drawn mark
.tp_lout:
        rts

; combinaTile(tile D0, despX A3) through a_combina_tile_p (kernels.s)
.tp_comb:
        moveq   #-1,d1                  ; tiles < 0x0b are opaque
        cmp.w   #$0B,d0
        blo.s   .tp_tr
        moveq   #2,d1                   ; pen 2 transparent for 0x0b-0x7f
        tst.b   d0
        bpl.s   .tp_tr
        moveq   #1,d1                   ; pen 1 for 0x80-0xff
.tp_tr:
        if      TP_REGS
        ; (2026-10-06) the arguments in registers (combina_p_regs / combina_pm_regs): no
        ; stack frame to build and read back for each tile
        move.l  d1,d2                   ; transparent pen
        lsl.w   #5,d0
        move.l  TP_GFX(a5),a1
        adda.w  d0,a1                   ; tile graphic (tile*32 < 8 KB)
        move.l  TP_ANCH(a5),d1          ; stride in bytes = anchoFinal
        move.l  a3,d0
        asr.l   #2,d0
        btst    #1,TP_MASK+3(a5)        ; bit 1: the interleaved buffer (one word an element)
        bne.s   .tp_ci
        add.l   TP_MIX(a5),d0
        move.l  d0,a0                   ; dest = bufferMezclas + despX/4
        btst    #0,TP_MASK+3(a5)
        bne     combina_pm_regs         ; (its rts returns from .tp_comb)
        bra     combina_p_regs
.tp_ci:
        add.l   d0,d0
        add.l   TP_MIX(a5),d0
        move.l  d0,a0                   ; dest = bufferMezclas + 2 * despX/4
        btst    #0,TP_MASK+3(a5)
        bne     combina_pmi_regs
        bra     combina_pi_regs
        else
        move.l  d1,-(sp)                ; transp
        lsl.w   #5,d0
        move.l  TP_GFX(a5),a0
        pea     0(a0,d0.w)              ; tile graphic (tile*32 < 8 KB)
        move.l  TP_ANCH(a5),-(sp)       ; stride in bytes = anchoFinal
        move.l  a3,d0
        asr.l   #2,d0
        add.l   TP_MIX(a5),d0
        move.l  d0,-(sp)                ; dest = bufferMezclas + despX/4
        tst.l   TP_MASK(a5)
        bne.s   .tp_cm
        bsr     a_combina_tile_p
        lea     16(sp),sp
        rts
.tp_cm:
        bsr     a_combina_tile_pm
        lea     16(sp),sp
        rts
        endif

; ============================================================
; kernels.s - asm twins of the mixer kernels (cpp/port/ql_kernels.h)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; Each routine must give byte-identical results to its C reference
; (cpp/port/ql_kernels.c); tools/kerntest.py runs both on the same inputs.
; C calling convention: args on the stack, D0-D1/A0-A1 scratch.
;
; unpack_lut: 256 x 4 bytes, the pens of the 4 pixels of a CPC Mode 1 byte
; (pixel k pen = bit(3-k)*2 + bit(7-k)), built once by init_unpack_lut.
; ============================================================

        xdef    a_combina_tile,a_sprite_blit,a_fill,a_and_mask,init_unpack_lut
        xdef    a_combina_tile_p,a_sprite_blit_p,combina_p_regs

init_unpack_lut:
        movem.l d2-d4,-(sp)
        lea     unpack_lut,a0
        moveq   #0,d0                   ; byte value
.ul_byte:
        moveq   #7,d2                   ; bit holding pen bit 0 (7-k)
.ul_pix:
        moveq   #0,d3
        btst    d2,d0
        beq.s   .ul_b0
        moveq   #1,d3
.ul_b0:
        move.w  d2,d4
        subq.w  #4,d4                   ; bit holding pen bit 1 (3-k)
        btst    d4,d0
        beq.s   .ul_b1
        addq.b  #2,d3
.ul_b1:
        move.b  d3,(a0)+
        subq.w  #1,d2
        cmp.w   #3,d2
        bgt.s   .ul_pix
        addq.w  #1,d0
        cmp.w   #256,d0
        blt.s   .ul_byte
        ; AND/OR tables for transparent pen 1 and pen 2 (as the CPC's at 0x9d00):
        ; per pixel, and = $FF/or = 0 if the pen is transparent, else and = 0/or = pen
        lea     unpack_lut,a0
        lea     ct_tables,a1            ; and1, or1, and2, or2 (1 KB each)
        moveq   #1,d2                   ; transparent pen
.ul_tab:
        move.w  #1023,d3
.ul_tb:
        move.b  (a0)+,d0
        cmp.b   d2,d0
        bne.s   .ul_op
        st      (a1)
        clr.b   1024(a1)
        bra.s   .ul_nx
.ul_op:
        clr.b   (a1)
        move.b  d0,1024(a1)
.ul_nx:
        addq.l  #1,a1
        dbra    d3,.ul_tb
        lea     -1024(a0),a0
        lea     1024(a1),a1
        addq.w  #1,d2
        cmp.w   #3,d2
        blt.s   .ul_tab
        ; pm_tabs (packed buffer): 4 x 256 bytes, pm_tabs[t*256+b] = the bits of
        ; the pixels of CPC byte b whose pen is t (pixel k: mask $88 >> k)
        lea     pm_tabs,a1
        moveq   #0,d2                   ; pen t
.ul_pt:
        lea     unpack_lut,a0
        move.w  #255,d3
.ul_pb:
        moveq   #0,d0                   ; mask
        moveq   #-$78,d4                ; $88: pixel 0
        moveq   #3,d1
.ul_pk:
        cmp.b   (a0)+,d2
        bne.s   .ul_pn
        or.b    d4,d0
.ul_pn:
        lsr.b   #1,d4
        dbra    d1,.ul_pk
        move.b  d0,(a1)+
        dbra    d3,.ul_pb
        addq.w  #1,d2
        cmp.w   #4,d2
        blt.s   .ul_pt
        lea     pm_tabs,a0              ; (2026-10-06) mb_tab: the drawn pixels' mask bits
        lea     mb_tab,a1               ; for a sprite byte (pen 0 transparent)
        move.w  #255,d3
.ul_mb:
        move.b  (a0)+,d0
        not.b   d0
        and.b   #$0F,d0
        move.b  d0,(a1)+
        dbra    d3,.ul_mb
        movem.l (sp)+,d2-d4
        rts

; ------------------------------------------------------------
; void a_combina_tile_p(u8 *dest, int destStride, const u8 *tile, int transp)
; packed buffer (4 pixels a byte, strides in bytes): per byte
; dest = ((dest ^ s) & m) ^ s, m = the transparent pixels' bits of s
; ------------------------------------------------------------
a_combina_tile_p:
        movem.l d2-d4/a2,-(sp)          ; 16 bytes saved -> args at 20
        move.l  20(sp),a0               ; dest
        move.l  24(sp),d1               ; dest stride
        move.l  28(sp),a1               ; tile (32 bytes)
        move.l  32(sp),d2               ; transparent pen, -1 = none
        bra.s   cp_go
; (2026-10-06) the same with the arguments in registers, for a_tiles_prof: A0 dest, D1 dest
; stride, A1 tile, D2 transparent pen; D0-D1/A0-A1 trashed, as for a C call
combina_p_regs:
        movem.l d2-d4/a2,-(sp)
cp_go:
        subq.l  #4,d1
        moveq   #7,d4
        tst.l   d2
        bmi.s   .cp_opaque
        lsl.w   #8,d2
        lea     pm_tabs,a2
        adda.w  d2,a2                   ; mask table of the transparent pen
        moveq   #0,d0
.cp_row:
        rept    4
        move.b  (a1)+,d0
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   0(a2,d0.w),d3
        eor.b   d0,d3
        move.b  d3,(a0)+
        endr
        add.l   d1,a0
        dbra    d4,.cp_row
        bra.s   .cp_done
.cp_opaque:
        move.b  (a1)+,(a0)+             ; byte moves: dest may be odd
        move.b  (a1)+,(a0)+
        move.b  (a1)+,(a0)+
        move.b  (a1)+,(a0)+
        add.l   d1,a0
        dbra    d4,.cp_opaque
.cp_done:
        movem.l (sp)+,d2-d4/a2
        rts

; ------------------------------------------------------------
; void a_sprite_blit_p(u8 *dest, int destStride, const u8 *src, int srcStride,
;                      int w, int h)    packed buffer, pen 0 transparent
; ------------------------------------------------------------
a_sprite_blit_p:
        movem.l d2-d6/a2-a4,-(sp)       ; 32 bytes saved -> args at 36
        move.l  52(sp),d4               ; w
        ble.s   .sq_done
        move.l  56(sp),d5               ; h
        ble.s   .sq_done
        subq.l  #1,d4
        subq.l  #1,d5
        move.l  36(sp),a0               ; dest
        move.l  40(sp),d2               ; dest stride
        move.l  44(sp),a1               ; src
        move.l  48(sp),d3               ; src stride
        lea     pm_tabs,a2              ; pen 0 masks
        moveq   #0,d0
.sq_row:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d4,d6
.sq_byte:
        move.b  (a4)+,d0
        beq.s   .sq_skip                ; four transparent pixels
        move.b  0(a2,d0.w),d1
        beq.s   .sq_opq                 ; no transparent pixel
        and.b   d1,(a3)
        or.b    d0,(a3)+
        dbra    d6,.sq_byte
        bra.s   .sq_eol
.sq_opq:
        move.b  d0,(a3)+
        dbra    d6,.sq_byte
        bra.s   .sq_eol
.sq_skip:
        addq.l  #1,a3
        dbra    d6,.sq_byte
.sq_eol:
        add.l   d2,a0
        add.l   d3,a1
        dbra    d5,.sq_row
.sq_done:
        movem.l (sp)+,d2-d6/a2-a4
        rts

; ------------------------------------------------------------
; void a_combina_tile(u8 *dest, int destStride, const u8 *tile, int transp)
; ------------------------------------------------------------
a_combina_tile:
        movem.l d2-d5/a2-a3,-(sp)       ; 24 bytes saved -> args at 28
        move.l  28(sp),a0               ; dest
        move.l  32(sp),d1               ; dest stride
        move.l  36(sp),a1               ; tile (32 bytes)
        move.l  40(sp),d2               ; transparent pen, -1 = none
        sub.l   #16,d1                  ; stride after a 16-pixel row
        lea     unpack_lut,a2
        moveq   #7,d5
        tst.l   d2
        bmi     .ct_opaque
        move.l  a0,d0
        btst    #0,d0
        bne.s   .ct_row                 ; odd dest: byte loop
        moveq   #1,d0
        cmp.l   d0,d2
        beq.s   .ct_t1
        moveq   #2,d0
        cmp.l   d0,d2
        bne.s   .ct_row                 ; other pens: byte loop
        lea     ct_tables+2048,a3       ; and2
        bra.s   .ct_tab
.ct_t1:
        lea     ct_tables,a3            ; and1
.ct_tab:
        lea     1024(a3),a2             ; or table
.ct_trow:
        moveq   #3,d4
.ct_tbyte:
        moveq   #0,d0
        move.b  (a1)+,d0
        add.w   d0,d0
        add.w   d0,d0
        move.l  (a0),d3
        and.l   0(a3,d0.w),d3
        or.l    0(a2,d0.w),d3
        move.l  d3,(a0)+
        dbra    d4,.ct_tbyte
        add.l   d1,a0
        dbra    d5,.ct_trow
        bra     .ct_done
.ct_row:
        moveq   #3,d4
.ct_byte:
        moveq   #0,d0
        move.b  (a1)+,d0
        add.w   d0,d0
        add.w   d0,d0
        lea     0(a2,d0.w),a3
        move.b  (a3)+,d3
        cmp.b   d2,d3
        beq.s   .ct_s0
        move.b  d3,(a0)
.ct_s0:
        move.b  (a3)+,d3
        cmp.b   d2,d3
        beq.s   .ct_s1
        move.b  d3,1(a0)
.ct_s1:
        move.b  (a3)+,d3
        cmp.b   d2,d3
        beq.s   .ct_s2
        move.b  d3,2(a0)
.ct_s2:
        move.b  (a3),d3
        cmp.b   d2,d3
        beq.s   .ct_s3
        move.b  d3,3(a0)
.ct_s3:
        addq.l  #4,a0
        dbra    d4,.ct_byte
        add.l   d1,a0
        dbra    d5,.ct_row
        bra.s   .ct_done
.ct_opaque:
        moveq   #3,d4
.ct_obyte:
        moveq   #0,d0
        move.b  (a1)+,d0
        add.w   d0,d0
        add.w   d0,d0
        move.b  0(a2,d0.w),(a0)+        ; byte moves: dest may be only word aligned
        move.b  1(a2,d0.w),(a0)+
        move.b  2(a2,d0.w),(a0)+
        move.b  3(a2,d0.w),(a0)+
        dbra    d4,.ct_obyte
        add.l   d1,a0
        dbra    d5,.ct_opaque
.ct_done:
        movem.l (sp)+,d2-d5/a2-a3
        rts

; ------------------------------------------------------------
; void a_sprite_blit(u8 *dest, int destStride, const u8 *src, int srcStride,
;                    int w, int h)      pen 0 transparent, w in CPC bytes
; ------------------------------------------------------------
a_sprite_blit:
        movem.l d2-d6/a2-a4,-(sp)       ; 32 bytes saved -> args at 36
        move.l  52(sp),d4               ; w
        ble.s   .sb_done
        move.l  56(sp),d5               ; h
        ble.s   .sb_done
        subq.l  #1,d4
        subq.l  #1,d5
        move.l  36(sp),a0               ; dest
        move.l  44(sp),a1               ; src
        lea     unpack_lut,a2
.sb_row:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d4,d6
.sb_byte:
        moveq   #0,d0
        move.b  (a4)+,d0
        beq.s   .sb_empty               ; four transparent pixels
        add.w   d0,d0
        add.w   d0,d0
        move.b  0(a2,d0.w),d1
        beq.s   .sb_p1
        move.b  d1,(a3)
.sb_p1:
        move.b  1(a2,d0.w),d1
        beq.s   .sb_p2
        move.b  d1,1(a3)
.sb_p2:
        move.b  2(a2,d0.w),d1
        beq.s   .sb_p3
        move.b  d1,2(a3)
.sb_p3:
        move.b  3(a2,d0.w),d1
        beq.s   .sb_empty
        move.b  d1,3(a3)
.sb_empty:
        addq.l  #4,a3
        dbra    d6,.sb_byte
        add.l   40(sp),a0               ; dest stride
        add.l   48(sp),a1               ; src stride
        dbra    d5,.sb_row
.sb_done:
        movem.l (sp)+,d2-d6/a2-a4
        rts

; ------------------------------------------------------------
; void a_fill(u8 *dest, int value, int n)
; ------------------------------------------------------------
a_fill:
        move.l  4(sp),a0
        move.l  8(sp),d0
        move.l  12(sp),d1
        ble.s   .fl_done
        btst    #0,7(sp)                ; odd dest (low byte of the argument): one byte first
        beq.s   .fl_even
        move.b  d0,(a0)+
        subq.l  #1,d1
        beq.s   .fl_done
.fl_even:
        and.w   #$FF,d0
        move.w  d0,a1
        lsl.w   #8,d0
        add.w   a1,d0                   ; value in both bytes
        move.w  d0,a1
        swap    d0
        move.w  a1,d0                   ; value in all four bytes
        move.l  d1,a1                   ; remaining count
        lsr.l   #2,d1
        bra.s   .fl_lnext
.fl_long:
        move.l  d0,(a0)+
.fl_lnext:
        subq.l  #1,d1
        bpl.s   .fl_long
        move.l  a1,d1
        and.w   #3,d1
        bra.s   .fl_bnext
.fl_byte:
        move.b  d0,(a0)+
.fl_bnext:
        dbra    d1,.fl_byte
.fl_done:
        rts

; ------------------------------------------------------------
; void a_and_mask(u8 *dest, int mask, int n)
; ------------------------------------------------------------
a_and_mask:
        move.l  4(sp),a0
        move.l  8(sp),d0
        move.l  12(sp),d1
        ble.s   .am_done
        btst    #0,7(sp)                ; odd dest: one byte first
        beq.s   .am_even
        and.b   d0,(a0)+
        subq.l  #1,d1
        beq.s   .am_done
.am_even:
        and.w   #$FF,d0
        move.w  d0,a1
        lsl.w   #8,d0
        add.w   a1,d0
        move.w  d0,a1
        swap    d0
        move.w  a1,d0                   ; mask in all four bytes
        move.l  d1,a1
        lsr.l   #2,d1
        bra.s   .am_lnext
.am_long:
        and.l   d0,(a0)+
.am_lnext:
        subq.l  #1,d1
        bpl.s   .am_long
        move.l  a1,d1
        and.w   #3,d1
        bra.s   .am_bnext
.am_byte:
        and.b   d0,(a0)+
.am_bnext:
        dbra    d1,.am_byte
.am_done:
        rts

        section .bss,bss
unpack_lut:
        ds.b    1024
ct_tables:
        ds.b    4096
pm_tabs:
        ds.b    1024
mb_tab:                                 ; ~pm_tabs[b] & $0F (init_unpack_lut)
        ds.b    256
        section .text.start,code

; ============================================================
; INTERLEAVE (2026-10-06): the same kernels on the INTERLEAVED mixing buffer: one word an
; element (4 pixels), the sprite-mask byte first (even address), the packed pens second, so
; the screen copy reads one word (mask * 256 + pens: one table lookup, no mask test). dest is
; the element's address, strides are in elements. The old kernels (separate planes, mask at
; +MASK_OFF) stay for the old layout and kerntest; tools/inttest.py runs both on the same
; contents (the planes interleaved for the new ones) and compares.
; ============================================================
        xdef    a_combina_tile_pi,a_combina_tile_pmi,a_sprite_blit_pi,a_sprite_blit_pmi
        xdef    combina_pi_regs,combina_pmi_regs

; void a_combina_tile_pi(u8 *dest, int destStride, const u8 *tile, int transp)   pens only
a_combina_tile_pi:
        movem.l d2-d4/a2,-(sp)          ; 16 bytes saved -> args at 20
        move.l  20(sp),a0
        move.l  24(sp),d1
        move.l  28(sp),a1
        move.l  32(sp),d2
        bra.s   cpi_go
combina_pi_regs:                        ; A0 dest, D1 stride, A1 tile, D2 transparent pen
        movem.l d2-d4/a2,-(sp)
cpi_go:
        add.l   d1,d1                   ; stride in bytes
        subq.l  #8,d1                   ; (less the 4 elements a row)
        addq.l  #1,a0                   ; at the pens byte
        moveq   #7,d4
        tst.l   d2
        bmi.s   .ci_opaque
        lsl.w   #8,d2
        lea     pm_tabs,a2
        adda.w  d2,a2
        moveq   #0,d0
.ci_row:
        move.b  (a1)+,d0
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   0(a2,d0.w),d3
        eor.b   d0,d3
        move.b  d3,(a0)
        addq.l  #2,a0
        move.b  (a1)+,d0
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   0(a2,d0.w),d3
        eor.b   d0,d3
        move.b  d3,(a0)
        addq.l  #2,a0
        move.b  (a1)+,d0
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   0(a2,d0.w),d3
        eor.b   d0,d3
        move.b  d3,(a0)
        addq.l  #2,a0
        move.b  (a1)+,d0
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   0(a2,d0.w),d3
        eor.b   d0,d3
        move.b  d3,(a0)
        addq.l  #2,a0
        add.l   d1,a0
        dbra    d4,.ci_row
        bra.s   .ci_done
.ci_opaque:
        move.b  (a1)+,(a0)
        move.b  (a1)+,2(a0)
        move.b  (a1)+,4(a0)
        move.b  (a1)+,6(a0)
        addq.l  #8,a0
        add.l   d1,a0
        dbra    d4,.ci_opaque
.ci_done:
        movem.l (sp)+,d2-d4/a2
        rts

; void a_combina_tile_pmi(u8 *dest, int destStride, const u8 *tile, int transp)
; as a_combina_tile_pm: the tile's drawn pixels clear their mask bits
a_combina_tile_pmi:
        movem.l d2-d4/a2,-(sp)          ; 16 bytes saved -> args at 20
        move.l  20(sp),a0
        move.l  24(sp),d1
        move.l  28(sp),a1
        move.l  32(sp),d2
        bra.s   cmi_go
combina_pmi_regs:                       ; A0 dest, D1 stride, A1 tile, D2 transparent pen
        movem.l d2-d4/a2,-(sp)
cmi_go:
        add.l   d1,d1
        subq.l  #8,d1
        moveq   #7,d4
        tst.l   d2
        bmi.s   .cn_opaque
        lsl.w   #8,d2
        lea     pm_tabs,a2
        adda.w  d2,a2
        moveq   #0,d0
.cn_row:
        move.b  (a1)+,d0
        move.b  0(a2,d0.w),d2           ; bits of the transparent pixels
        and.b   d2,(a0)+                ; drawn pixels: not a sprite any more
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   d2,d3
        eor.b   d0,d3
        move.b  d3,(a0)+
        move.b  (a1)+,d0
        move.b  0(a2,d0.w),d2           ; bits of the transparent pixels
        and.b   d2,(a0)+                ; drawn pixels: not a sprite any more
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   d2,d3
        eor.b   d0,d3
        move.b  d3,(a0)+
        move.b  (a1)+,d0
        move.b  0(a2,d0.w),d2           ; bits of the transparent pixels
        and.b   d2,(a0)+                ; drawn pixels: not a sprite any more
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   d2,d3
        eor.b   d0,d3
        move.b  d3,(a0)+
        move.b  (a1)+,d0
        move.b  0(a2,d0.w),d2           ; bits of the transparent pixels
        and.b   d2,(a0)+                ; drawn pixels: not a sprite any more
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   d2,d3
        eor.b   d0,d3
        move.b  d3,(a0)+
        add.l   d1,a0
        dbra    d4,.cn_row
        bra.s   .cn_done
.cn_opaque:
        clr.b   (a0)+
        move.b  (a1)+,(a0)+
        clr.b   (a0)+
        move.b  (a1)+,(a0)+
        clr.b   (a0)+
        move.b  (a1)+,(a0)+
        clr.b   (a0)+
        move.b  (a1)+,(a0)+
        add.l   d1,a0
        dbra    d4,.cn_opaque
.cn_done:
        movem.l (sp)+,d2-d4/a2
        rts

; void a_sprite_blit_pi(u8 *dest, int destStride, const u8 *src, int srcStride, int w, int h)
; pen 0 transparent; pens only
a_sprite_blit_pi:
        movem.l d2-d6/a2-a4,-(sp)       ; 32 bytes saved -> args at 36
        move.l  52(sp),d4               ; w
        ble.s   .si_done
        move.l  56(sp),d5               ; h
        ble.s   .si_done
        subq.l  #1,d4
        subq.l  #1,d5
        move.l  36(sp),a0
        addq.l  #1,a0                   ; at the pens byte
        move.l  40(sp),d2
        add.l   d2,d2                   ; dest stride in bytes
        move.l  44(sp),a1
        move.l  48(sp),d3
        lea     pm_tabs,a2              ; pen 0 masks
        moveq   #0,d0
.si_row:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d4,d6
.si_byte:
        move.b  (a4)+,d0
        beq.s   .si_skip                ; four transparent pixels
        move.b  0(a2,d0.w),d1
        beq.s   .si_opq                 ; no transparent pixel
        and.b   d1,(a3)
        or.b    d0,(a3)
        addq.l  #2,a3
        dbra    d6,.si_byte
        bra.s   .si_eol
.si_opq:
        move.b  d0,(a3)
.si_skip:
        addq.l  #2,a3
        dbra    d6,.si_byte
.si_eol:
        add.l   d2,a0
        add.l   d3,a1
        dbra    d5,.si_row
.si_done:
        movem.l (sp)+,d2-d6/a2-a4
        rts

; void a_sprite_blit_pmi(...)    as a_sprite_blit_pm: drawn pixels set their mask bits
; (mb_tab: the bits of a source byte's drawn pixels, one lookup)
a_sprite_blit_pmi:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes saved -> args at 44
        move.l  60(sp),d4
        ble.s   .sn_done
        move.l  64(sp),d5
        ble.s   .sn_done
        subq.l  #1,d4
        subq.l  #1,d5
        move.l  44(sp),a0
        move.l  48(sp),d2
        add.l   d2,d2
        move.l  52(sp),a1
        move.l  56(sp),d3
        lea     pm_tabs,a2
        lea     mb_tab,a5
        moveq   #0,d0
.sn_row:
        move.l  a0,a3
        move.l  a1,a4
        move.w  d4,d6
.sn_byte:
        move.b  (a4)+,d0
        beq.s   .sn_skip
        move.b  0(a2,d0.w),d1
        beq.s   .sn_opq
        move.b  0(a5,d0.w),d7
        or.b    d7,(a3)+                ; the drawn pixels' mask bits
        and.b   d1,(a3)
        or.b    d0,(a3)+
        dbra    d6,.sn_byte
        bra.s   .sn_eol
.sn_opq:
        or.b    #$0F,(a3)+
        move.b  d0,(a3)+
        dbra    d6,.sn_byte
        bra.s   .sn_eol
.sn_skip:
        addq.l  #2,a3
        dbra    d6,.sn_byte
.sn_eol:
        add.l   d2,a0
        add.l   d3,a1
        dbra    d5,.sn_row
.sn_done:
        movem.l (sp)+,d2-d7/a2-a5
        rts

; ============================================================
; CHARCOL: the packed kernels with the SPRITE MASK (colour.s): one mask byte
; per buffer byte at dest + MASK_OFF, bit 3-k = pixel k drawn by a sprite.
; Used only while the palette has separate character colours (char_sep).
; ============================================================
        xdef    a_combina_tile_pm,a_sprite_blit_pm,combina_pm_regs

; void a_combina_tile_pm(u8 *dest, int destStride, const u8 *tile, int transp)
; as a_combina_tile_p; the tile's drawn pixels clear their mask bits
a_combina_tile_pm:
        movem.l d2-d4/a2/a5,-(sp)       ; 20 bytes saved -> args at 24
        move.l  24(sp),a0               ; dest
        move.l  28(sp),d1               ; dest stride
        move.l  32(sp),a1               ; tile (32 bytes)
        move.l  36(sp),d2               ; transparent pen, -1 = none
        bra.s   cm_go
; (2026-10-06) the same with the arguments in registers, for a_tiles_prof (as combina_p_regs)
combina_pm_regs:
        movem.l d2-d4/a2/a5,-(sp)
cm_go:
        subq.l  #4,d1
        lea     MASK_OFF(a0),a5         ; the mask
        moveq   #7,d4
        tst.l   d2
        bmi.s   .cm_opaque
        lsl.w   #8,d2
        lea     pm_tabs,a2
        adda.w  d2,a2                   ; mask table of the transparent pen
        moveq   #0,d0
.cm_row:
        rept    4
        move.b  (a1)+,d0
        move.b  0(a2,d0.w),d2           ; bits of the transparent pixels
        move.b  (a0),d3
        eor.b   d0,d3
        and.b   d2,d3
        eor.b   d0,d3
        move.b  d3,(a0)+
        and.b   d2,(a5)+                ; drawn pixels: not a sprite any more
        endr
        add.l   d1,a0
        add.l   d1,a5
        dbra    d4,.cm_row
        bra.s   .cm_done
.cm_opaque:
        move.b  (a1)+,(a0)+
        move.b  (a1)+,(a0)+
        move.b  (a1)+,(a0)+
        move.b  (a1)+,(a0)+
        clr.b   (a5)+
        clr.b   (a5)+
        clr.b   (a5)+
        clr.b   (a5)+
        add.l   d1,a0
        add.l   d1,a5
        dbra    d4,.cm_opaque
.cm_done:
        movem.l (sp)+,d2-d4/a2/a5
        rts

; void a_sprite_blit_pm(u8 *dest, int destStride, const u8 *src, int srcStride,
;                       int w, int h)   as a_sprite_blit_p; drawn pixels set their mask bits
a_sprite_blit_pm:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes saved -> args at 44
        move.l  60(sp),d4               ; w
        ble.s   .sm_done
        move.l  64(sp),d5               ; h
        ble.s   .sm_done
        subq.l  #1,d4
        subq.l  #1,d5
        move.l  44(sp),a0               ; dest
        move.l  48(sp),d2               ; dest stride
        move.l  52(sp),a1               ; src
        move.l  56(sp),d3               ; src stride
        lea     pm_tabs,a2              ; pen 0 masks
        moveq   #0,d0
.sm_row:
        move.l  a0,a3
        move.l  a1,a4
        lea     MASK_OFF(a0),a5
        move.w  d4,d6
.sm_byte:
        move.b  (a4)+,d0
        beq.s   .sm_skip                ; four transparent pixels
        move.b  0(a2,d0.w),d1
        beq.s   .sm_opq                 ; no transparent pixel
        and.b   d1,(a3)
        or.b    d0,(a3)+
        not.b   d1
        and.b   #$0F,d1                 ; the drawn pixels' mask bits
        or.b    d1,(a5)+
        dbra    d6,.sm_byte
        bra.s   .sm_eol
.sm_opq:
        move.b  d0,(a3)+
        or.b    #$0F,(a5)+
        dbra    d6,.sm_byte
        bra.s   .sm_eol
.sm_skip:
        addq.l  #1,a3
        addq.l  #1,a5
        dbra    d6,.sm_byte
.sm_eol:
        add.l   d2,a0
        add.l   d3,a1
        dbra    d5,.sm_row
.sm_done:
        movem.l (sp)+,d2-d7/a2-a5
        rts

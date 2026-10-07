; ============================================================
; grid.s - asm twins of the height-grid hot spots (QL_ASM_GRID)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; Must give exactly the results of the C transcriptions in cpp/port/ql_kernels.c,
; which follow RejillaPantalla.cpp line by line; tools/kerntest.py runs both on
; random inputs, and hdiff compares the game with the PC oracle (original C++).
; C calling convention: args on the stack, D0-D1/A0-A1 scratch.
; ============================================================

        xdef    a_rellena_alturas,a_avance,a_copy576

; ------------------------------------------------------------
; void a_copy576(u8 *dst, const u8 *src) - one 24x24 height grid (the
; height-grid cache, RejillaPantalla.cpp): longs when both are even, else bytes
; ------------------------------------------------------------
a_copy576:
        move.l  4(sp),a0
        move.l  8(sp),a1
        move.l  a0,d0
        move.l  a1,d1
        or.w    d1,d0
        btst    #0,d0
        bne.s   .c5_b
        moveq   #576/16-1,d0
.c5_l:
        move.l  (a1)+,(a0)+
        move.l  (a1)+,(a0)+
        move.l  (a1)+,(a0)+
        move.l  (a1)+,(a0)+
        dbra    d0,.c5_l
        rts
.c5_b:
        move.w  #576-1,d0
.c5_bl:
        move.b  (a1)+,(a0)+
        dbra    d0,.c5_bl
        rts

; ------------------------------------------------------------
; void a_rellena_alturas(u8 *buf, const u8 *datos, int minPosX, int minPosY)
; A0 grid, A1 data. Per block: D0 altura, D2 lgtudX, D3 lgtudY, D4 distX,
; D5 distY. minPosX/minPosY stay on the stack. Only the low byte of altura
; is ever stored, so word arithmetic on it is exact.
; ------------------------------------------------------------
RA_MINX equ     52+2                    ; low words of the int arguments
RA_MINY equ     56+2
a_rellena_alturas:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes saved -> args at 44
        move.l  44(sp),a0               ; grid
        move.l  48(sp),a1               ; datos
        ; clear the 24x24 grid
        move.l  a0,a2
        move.w  #576-1,d0
        move.l  a0,d1
        btst    #0,d1
        bne.s   .ra_cb
        move.w  #576/4-1,d0
.ra_cl:
        clr.l   (a2)+
        dbra    d0,.ra_cl
        bra.s   .ra_next
.ra_cb:
        clr.b   (a2)+
        dbra    d0,.ra_cb
.ra_next:
        move.w  RA_MINX(sp),d6          ; the window, kept in D6/D7 while scanning
        move.w  RA_MINY(sp),d7
.ra_scan:
        moveq   #0,d0
        move.b  (a1),d0                 ; tipoBloque
        cmp.b   #$FF,d0
        beq     .ra_done
        moveq   #7,d1
        and.b   d0,d1                   ; tipoBloque & 7
        beq     .ra_done
        cmp.b   #6,d1
        bhs     .ra_done
        moveq   #0,d4
        move.b  1(a1),d4                ; posX
        sub.w   d6,d4                   ; distX
        bmi.s   .ra_dec
        cmp.w   #24,d4
        blt.s   .ra_dec
        btst    #3,d0                   ; starts right of the window: next entry
        beq.s   .ra_skip4
        addq.l  #1,a1
.ra_skip4:
        addq.l  #4,a1
        bra.s   .ra_scan
.ra_dec:
        moveq   #0,d2
        move.b  3(a1),d2                ; lgtudX
        moveq   #0,d3
        move.b  4(a1),d3                ; lgtudY
        moveq   #0,d5
        move.b  2(a1),d5                ; posY
        btst    #3,d0
        bne.s   .ra_five
        move.w  d2,d3
        and.w   #$0F,d3                 ; 4-byte entry: lengths in nibbles
        lsr.w   #4,d2
        addq.l  #4,a1
        bra.s   .ra_len
.ra_five:
        addq.l  #5,a1
.ra_len:
        addq.w  #1,d2
        addq.w  #1,d3
        lsr.b   #4,d0                   ; altura = (tipoBloque >> 4) & 15
        tst.w   d4                      ; distX (>= 24 was skipped above)
        bpl.s   .ra_y
        add.w   d2,d4                   ; -distX >= lgtudX <=> distX + lgtudX <= 0:
        ble.s   .ra_scan                ; ends before the window
        sub.w   d2,d4
.ra_y:
        sub.w   d7,d5                   ; distY
        bpl.s   .ra_yp
        add.w   d3,d5
        ble.s   .ra_scan
        sub.w   d3,d5
        bra.s   .ra_vis
.ra_yp:
        cmp.w   #24,d5
        bge.s   .ra_scan
.ra_vis:
        cmp.b   #5,d1
        beq     .ra_flat
        ; ---- types 1-4: altura changes by incX (D6) along x, by incY (D7) per row ----
        moveq   #0,d6
        moveq   #0,d7
        subq.b  #1,d1
        bne.s   .ra_t2
        moveq   #1,d6                   ; type 1: +1 along x
        bra.s   .ra_inc
.ra_t2:
        subq.b  #1,d1
        bne.s   .ra_t3
        moveq   #-1,d7                  ; type 2: -1 per row
        bra.s   .ra_inc
.ra_t3:
        subq.b  #1,d1
        bne.s   .ra_t4
        moveq   #-1,d6                  ; type 3: -1 along x
        bra.s   .ra_inc
.ra_t4:
        moveq   #1,d7                   ; type 4: +1 per row
.ra_inc:
        ; cells i = 0..lgtudX-1 land at x = distX + i; the visible ones are
        ; iS = max(0, -distX) .. iE = min(lgtudX, 24 - distX) (exclusive)
        moveq   #0,d1                   ; iS
        tst.w   d4
        bpl.s   .ra_is
        move.w  d4,d1
        neg.w   d1
.ra_is:
        move.w  d4,a4
        adda.w  d1,a4                   ; A4 = first visible column
        neg.w   d4
        add.w   #24,d4                  ; 24 - distX
        cmp.w   d2,d4
        ble.s   .ra_ie
        move.w  d2,d4                   ; iE
.ra_ie:
        move.w  d4,a3
        suba.w  d1,a3                   ; A3 = visible cells per row (may be <= 0)
        suba.l  a5,a5                   ; A5 = altura step to iS = iS * incX
        tst.w   d6
        beq.s   .ra_a5
        bpl.s   .ra_a5p
        neg.w   d1
.ra_a5p:
        move.w  d1,a5
.ra_a5:
        subq.w  #1,d3                   ; rows - 1 for dbra
.ra_row:
        tst.w   d5
        bmi.s   .ra_rskip               ; row above the window
        cmp.w   #24,d5
        bge.s   .ra_rskip               ; below it
        move.l  a3,d2
        ble.s   .ra_rskip               ; no visible cell
        move.w  d5,d1
        lsl.w   #3,d1                   ; y*8
        move.w  d1,d4
        add.w   d1,d1
        add.w   d4,d1                   ; y*24
        lea     0(a0,d1.w),a2
        adda.l  a4,a2                   ; first visible cell
        move.w  a5,d1
        add.w   d0,d1                   ; altura at iS
        subq.w  #1,d2
.ra_cell:
        move.b  d1,(a2)+
        add.w   d6,d1
        dbra    d2,.ra_cell
.ra_rskip:
        add.w   d7,d0                   ; next row's altura
        addq.w  #1,d5
        dbra    d3,.ra_row
        bra     .ra_next
        ; ---- type 5: a flat block, clipped as the C++ does ----
.ra_flat:
        move.w  d4,d1
        add.w   d2,d1                   ; distX + lgtudX
        tst.w   d4
        bpl.s   .ra_fxp
        moveq   #0,d4                   ; posX = 0
        move.w  d1,d2                   ; lgtudX + distX ...
        cmp.w   #24,d1
        ble.s   .ra_fy
        moveq   #24,d2                  ; ... or 24
        bra.s   .ra_fy
.ra_fxp:
        cmp.w   #24,d1
        ble.s   .ra_fy
        moveq   #24,d2
        sub.w   d4,d2                   ; lgtudX - (distX + lgtudX - 24)
.ra_fy:
        move.w  d5,d1
        add.w   d3,d1
        tst.w   d5
        bpl.s   .ra_fyp
        moveq   #0,d5
        move.w  d1,d3
        cmp.w   #24,d1
        ble.s   .ra_ff
        moveq   #24,d3
        bra.s   .ra_ff
.ra_fyp:
        cmp.w   #24,d1
        ble.s   .ra_ff
        moveq   #24,d3
        sub.w   d5,d3
.ra_ff:
        move.w  d5,d1
        lsl.w   #3,d1
        move.w  d1,d6
        add.w   d1,d1
        add.w   d6,d1                   ; posY*24
        add.w   d4,d1
        lea     0(a0,d1.w),a2           ; first cell
        subq.w  #1,d3
        bmi     .ra_next
        subq.w  #1,d2
        bmi     .ra_next
.ra_frow:
        move.l  a2,a3
        move.w  d2,d6
.ra_fcell:
        move.b  d0,(a3)+
        dbra    d6,.ra_fcell
        lea     24(a2),a2
        dbra    d3,.ra_frow
        bra     .ra_next
.ra_done:
        movem.l (sp)+,d2-d7/a2-a5
        rts

; ------------------------------------------------------------
; void a_avance(const u8 *grid, int *calc, int x, int y, const int *tab,
;               int enDesnivel, int alturaLocal, int *dif)
; A2 walks the grid: one step along a row = tab[0] + 24*tab[1] (D7),
; next row = tab[2] + 24*tab[3] (A3); the coordinates are never checked,
; as in the C++ (the 20x20 centre and the table keep them in the grid).
; ------------------------------------------------------------
a_avance:
        movem.l d2-d7/a2-a4,-(sp)       ; 36 bytes saved -> args at 40
        move.l  56(sp),a4               ; tab
        moveq   #16,d0                  ; despIni 4 (bytes)
        tst.l   60(sp)                  ; enDesnivel
        beq.s   .av_d
        moveq   #24,d0                  ; despIni 6
.av_d:
        move.l  48(sp),d1               ; x
        add.l   0(a4,d0.w),d1
        move.l  52(sp),d2               ; y
        add.l   4(a4,d0.w),d2
        bsr.s   .av_mul24               ; D2 = y*24
        add.l   d1,d2
        move.l  40(sp),a2
        adda.l  d2,a2                   ; first cell
        move.l  4(a4),d2
        bsr.s   .av_mul24
        add.l   (a4),d2
        move.l  d2,d7                   ; step along a row
        move.l  12(a4),d2
        bsr.s   .av_mul24
        add.l   8(a4),d2
        move.l  d2,a3                   ; step to the next row
        move.l  44(sp),a1               ; calc
        move.l  64(sp),d3               ; alturaLocal
        moveq   #3,d4
.av_row:
        move.l  a2,a0
        moveq   #3,d5
.av_cell:
        moveq   #0,d6
        move.b  (a0),d6
        cmp.w   #$10,d6
        bhs.s   .av_ch
        sub.l   d3,d6                   ; no character: height relative to him
        bra.s   .av_st
.av_ch:
        and.w   #$30,d6                 ; a character there
.av_st:
        move.l  d6,(a1)+
        adda.l  d7,a0
        dbra    d5,.av_cell
        adda.l  a3,a2
        dbra    d4,.av_row
        move.l  68(sp),a0               ; dif
        move.l  44(sp),a1               ; calc
        tst.l   60(sp)
        bne.s   .av_desn
        move.l  4(a1),d0                ; calc[0][1]
        move.l  8(a1),d1                ; calc[0][2]
        cmp.l   d0,d1
        beq.s   .av_out
        moveq   #2,d0                   ; the two cells ahead differ
        bra.s   .av_out
.av_desn:
        move.l  20(a1),d0               ; calc[1][1]
        move.l  4(a1),d1                ; calc[0][1]
.av_out:
        move.l  d0,(a0)+
        move.l  d1,(a0)
        movem.l (sp)+,d2-d7/a2-a4
        rts
; D2 = D2 * 24 (long, signed); D0 trashed
.av_mul24:
        lsl.l   #3,d2
        move.l  d2,d0
        add.l   d2,d2
        add.l   d0,d2
        rts

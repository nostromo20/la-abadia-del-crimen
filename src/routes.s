; ============================================================
; routes.s - asm twins of the route finder's hot spots (QL_ASM_ROUTES)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; Must give exactly the results of the C transcriptions in cpp/port/ql_kernels.c
; (c_bfs24, c_puertas_ruta), which follow BuscadorRutas.cpp line by line;
; tools/kerntest.py runs both on random grids, and hdiff compares the game with
; the PC oracle (which runs the original C++).
; C calling convention: args on the stack, D0-D1/A0-A1 scratch.
; ============================================================

        xdef    a_bfs24,a_puertas_ruta,a_reconstruye,a_bfs16

; ------------------------------------------------------------
; int a_bfs24(u8 *grid, s32 *stack, int *io)       see ql_kernels.h
; A0 grid, A1 stack base, A2 push pointer (posPila), A3 read pointer
; (posProcesadoPila), A4 current cell, A5 io, A6 neighbour cell;
; D4/D5 x/y of the current cell, D2 its height (alturaBase).
; io[4] (nivelRecursion) is counted in place.
; ------------------------------------------------------------
; BFS24_INLINE (2026-10-06): the four neighbour tests written out in the loop (BFNB below)
; instead of a call to .bf_dest each, which also needed the neighbour's x/y in D0/D1 before the
; test: x/y are made only for a push. Same tests, same order, same pushes (kerntest: a_bfs24 vs
; c_bfs24). 0 = the call version (kept below).
BFS24_INLINE    equ     1

; BFNB offset, result, dx, dy: esPosicionDestino for the neighbour at A4+offset (A6), D2
; alturaBase; on the goal: D0 = result, to .bf_out; a new reachable cell is pushed (y, x)
BFNB    macro
        lea     \1(a4),a6
        moveq   #0,d3
        move.b  (a6),d3
        bmi.s   .n\@                    ; already explored
        and.b   #$3F,d3                 ; altura
        move.w  d2,d6
        sub.w   d3,d6
        addq.w  #1,d6                   ; alturaBase - altura + 1
        cmp.w   #2,d6
        bhi.s   .n\@                    ; < 0 or >= 3
        moveq   #$3F,d6
        and.b   -1(a6),d6               ; (x-1, y)
        cmp.b   d3,d6
        beq.s   .e\@
        sub.w   d3,d6
        addq.w  #1,d6                   ; difAltura
        cmp.w   #2,d6
        bhi.s   .n\@
        moveq   #$3F,d7
        and.b   -24(a6),d7              ; (x, y-1) must have the same height
        cmp.b   d3,d7
        bne.s   .n\@
        bra.s   .d\@
.e\@:
        moveq   #$3F,d6
        and.b   -24(a6),d6              ; (x, y-1)
        sub.w   d3,d6
        addq.w  #1,d6                   ; difAltura
        cmp.w   #2,d6
        bhi.s   .n\@
.d\@:
        moveq   #$3F,d7
        and.b   -25(a6),d7              ; (x-1, y-1)
        sub.w   d3,d7
        addq.w  #1,d7                   ; difAltura2
        cmp.w   d6,d7
        bne.s   .n\@
        bset    #7,(a6)                 ; explored
        btst    #6,(a6)
        beq.s   .p\@
        bclr    #7,(a6)                 ; the goal: unmark it
        moveq   #\2,d0
        bra     .bf_out
.p\@:
        move.w  d5,d1                   ; push(x+dx, y+dy): y high word, x low word
        add.w   #\4,d1
        move.w  d1,(a2)+
        move.w  d4,d1
        add.w   #\3,d1
        move.w  d1,(a2)+
.n\@:
        endm

a_bfs24:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes saved -> args at 48
        move.l  48(sp),a0               ; grid
        move.l  52(sp),a1               ; stack
        move.l  56(sp),a5               ; io
        ; mark the border as explored
        moveq   #-$80,d1
        moveq   #23,d0
        move.l  a0,a2
.bf_col:
        or.b    d1,(a2)                 ; column 0
        or.b    d1,23(a2)               ; column 23
        lea     24(a2),a2
        dbra    d0,.bf_col
        moveq   #23,d0
        move.l  a0,a2                   ; row 0
        lea     23*24(a0),a3            ; row 23
.bf_row:
        or.b    d1,(a2)+
        or.b    d1,(a3)+
        dbra    d0,.bf_row
        moveq   #1,d0
        move.l  d0,16(a5)               ; nivelRecursion = 1
        move.l  a1,a2
        move.l  a1,a3
        move.w  6(a5),(a2)+             ; push(posXIni, posYIni): y high word ...
        move.w  2(a5),(a2)+             ; ... x low word
        move.w  6(a5),d5
        move.w  2(a5),d4
        bsr     .bf_cellp
        bset    #7,(a4)                 ; start cell explored
        moveq   #-1,d0
        move.l  d0,(a2)+                ; level mark
.bf_loop:
        move.l  (a3)+,d0                ; elem(posProcesadoPila++)
        cmp.l   #-1,d0
        bne.s   .bf_cell
        cmp.l   a3,a2                   ; whole stack processed?
        beq     .bf_nf
        moveq   #-1,d0
        move.l  d0,(a2)+                ; next level
        addq.l  #1,16(a5)
        bra.s   .bf_loop
.bf_cell:
        move.w  d0,d4                   ; x
        swap    d0
        move.w  d0,d5                   ; y
        bsr     .bf_cellp
        moveq   #$0F,d2
        and.b   (a4),d2                 ; alturaBase
        if      BFS24_INLINE
        BFNB    1,1,1,0                 ; (x+1, y)
        BFNB    -24,2,0,-1              ; (x, y-1)
        BFNB    -1,3,-1,0               ; (x-1, y)
        BFNB    24,4,0,1                ; (x, y+1)
        bra     .bf_loop
        else
        lea     1(a4),a6                ; (x+1, y)
        move.w  d4,d0
        addq.w  #1,d0
        move.w  d5,d1
        bsr.s   .bf_dest
        bne.s   .bf_f1
        lea     -24(a4),a6              ; (x, y-1)
        move.w  d4,d0
        move.w  d5,d1
        subq.w  #1,d1
        bsr.s   .bf_dest
        bne.s   .bf_f2
        lea     -1(a4),a6               ; (x-1, y)
        move.w  d4,d0
        subq.w  #1,d0
        move.w  d5,d1
        bsr.s   .bf_dest
        bne.s   .bf_f3
        lea     24(a4),a6               ; (x, y+1)
        move.w  d4,d0
        move.w  d5,d1
        addq.w  #1,d1
        bsr.s   .bf_dest
        beq.s   .bf_loop
        moveq   #4,d0
        bra.s   .bf_out
.bf_f1:
        moveq   #1,d0
        bra.s   .bf_out
.bf_f2:
        moveq   #2,d0
        bra.s   .bf_out
.bf_f3:
        moveq   #3,d0
        bra.s   .bf_out
        endif
.bf_nf:
        moveq   #-1,d4                  ; as the C: x = y = -1 (the level mark)
        moveq   #-1,d5
        moveq   #0,d0
.bf_out:
        ext.l   d4
        ext.l   d5
        move.l  d4,8(a5)
        move.l  d5,12(a5)
        move.l  a2,d1
        sub.l   a1,d1
        asr.l   #2,d1
        move.l  d1,20(a5)               ; posPila
        move.l  a3,d1
        sub.l   a1,d1
        asr.l   #2,d1
        move.l  d1,24(a5)               ; posProcesadoPila
        movem.l (sp)+,d2-d7/a2-a6
        rts

; A4 = grid + D5*24 + D4 (D0, D1 trashed)
.bf_cellp:
        move.w  d5,d1
        lsl.w   #3,d1                   ; y*8
        move.w  d1,d0
        add.w   d1,d1                   ; y*16
        add.w   d0,d1                   ; y*24
        add.w   d4,d1
        lea     0(a0,d1.w),a4
        rts

; esPosicionDestino for the neighbour at A6 (D0 x, D1 y), D2 alturaBase.
; Returns D3 = 1 (Z clear) if it is the goal, else D3 = 0 (Z set);
; pushes the neighbour when it is a new reachable cell. Uses D3, D6, D7.
.bf_dest:
        moveq   #0,d3
        move.b  (a6),d3
        bmi.s   .bd_no                  ; already explored
        and.b   #$3F,d3                 ; altura
        move.w  d2,d6
        sub.w   d3,d6
        addq.w  #1,d6                   ; alturaBase - altura + 1
        cmp.w   #2,d6
        bhi.s   .bd_no                  ; < 0 or >= 3
        moveq   #$3F,d6
        and.b   -1(a6),d6               ; (x-1, y)
        cmp.b   d3,d6
        beq.s   .bd_eq
        sub.w   d3,d6
        addq.w  #1,d6                   ; difAltura
        cmp.w   #2,d6
        bhi.s   .bd_no
        moveq   #$3F,d7
        and.b   -24(a6),d7              ; (x, y-1) must have the same height
        cmp.b   d3,d7
        bne.s   .bd_no
        bra.s   .bd_diag
.bd_eq:
        moveq   #$3F,d6
        and.b   -24(a6),d6              ; (x, y-1)
        sub.w   d3,d6
        addq.w  #1,d6                   ; difAltura
        cmp.w   #2,d6
        bhi.s   .bd_no
.bd_diag:
        moveq   #$3F,d7
        and.b   -25(a6),d7              ; (x-1, y-1)
        sub.w   d3,d7
        addq.w  #1,d7                   ; difAltura2
        cmp.w   d6,d7
        bne.s   .bd_no
        bset    #7,(a6)                 ; explored
        btst    #6,(a6)
        beq.s   .bd_push
        bclr    #7,(a6)                 ; the goal: unmark it
        moveq   #1,d3
        rts
.bd_push:
        move.w  d1,(a2)+                ; push(x, y): y high word, x low word
        move.w  d0,(a2)+
.bd_no:
        moveq   #0,d3
        rts

; ------------------------------------------------------------
; void a_puertas_ruta(u8 *hab0, const u8 *hp, int mascara)
; ------------------------------------------------------------
a_puertas_ruta:
        movem.l d2-d3,-(sp)             ; 8 bytes saved -> args at 12
        move.l  12(sp),a0               ; habitaciones[0]
        move.l  16(sp),a1               ; habitacionesPuerta[6][4]
        move.l  20(sp),d2               ; mascara
        moveq   #5,d1                   ; 6 doors
        moveq   #0,d0
.pr_door:
        move.b  (a1)+,d0                ; room
        move.b  (a1)+,d3                ; its connection bits
        btst    #0,d2
        beq.s   .pr_or1
        not.b   d3
        and.b   d3,0(a0,d0.w)           ; can go through: connection open
        bra.s   .pr_2
.pr_or1:
        or.b    d3,0(a0,d0.w)           ; cannot: connection closed
.pr_2:
        move.b  (a1)+,d0                ; the room on the other side
        move.b  (a1)+,d3
        btst    #0,d2
        beq.s   .pr_or2
        not.b   d3
        and.b   d3,0(a0,d0.w)
        bra.s   .pr_3
.pr_or2:
        or.b    d3,0(a0,d0.w)
.pr_3:
        asr.l   #1,d2                   ; next door
        dbra    d1,.pr_door
        movem.l (sp)+,d2-d3
        rts

; ------------------------------------------------------------
; void a_reconstruye(s32 *buffer, int lgtudBuffer, int *io)   see ql_kernels.h
; A1 = &buffer[posPila] (pop: -(A1)), A2 = &buffer[posPila2 + 1] (pushInv: -(A2)),
; D6/D7 posXDest/posYDest and D2/D3 posX/posY as sign-extended longs.
; ------------------------------------------------------------
a_reconstruye:
        movem.l d2-d7/a2-a4,-(sp)       ; 36 bytes saved -> args at 40
        move.l  40(sp),a0               ; buffer
        move.l  48(sp),a4               ; io
        move.l  (a4),d0
        lsl.l   #2,d0
        lea     0(a0,d0.l),a1           ; &buffer[posProcesadoPila]
        move.l  44(sp),d0
        lsl.l   #2,d0
        lea     0(a0,d0.l),a2           ; &buffer[lgtudBuffer]
        move.l  -(a1),d0                ; pop(posXDest, posYDest)
        move.w  d0,d6
        ext.l   d6
        swap    d0
        move.w  d0,d7
        ext.l   d7
        move.l  #$0000FFFF,-(a2)        ; pushInv(-1)
        moveq   #0,d0
        move.w  8+2(a4),d0
        move.l  d0,-(a2)                ; pushInv(posXFinal)
        move.w  12+2(a4),d0
        move.l  d0,-(a2)                ; pushInv(posYFinal)
        move.w  16+2(a4),d0
        eor.w   #2,d0
        move.l  d0,-(a2)                ; pushInv(oriFinal ^ 2)
        moveq   #1,d0
        cmp.l   4(a4),d0
        beq     .rc_out                 ; nivelRecursion == 1
.rc_level:
        moveq   #-1,d0
.rc_mark:
        cmp.l   -(a1),d0                ; pop until the level mark (-1, -1)
        bne.s   .rc_mark
        moveq   #0,d0
        move.w  d6,d0
        move.l  d0,-(a2)                ; pushInv(posXDest)
        move.w  d7,d0
        move.l  d0,-(a2)                ; pushInv(posYDest)
.rc_pop:
        move.l  -(a1),d0                ; pop(posX, posY)
        move.w  d0,d2
        ext.l   d2
        swap    d0
        move.w  d0,d3
        ext.l   d3
        move.l  d3,d4
        sub.l   d7,d4
        addq.l  #1,d4                   ; difAlturaY
        moveq   #2,d0
        cmp.l   d0,d4
        bhi.s   .rc_pop                 ; < 0 or >= 3
        move.l  d2,d5
        sub.l   d6,d5
        addq.l  #1,d5                   ; difAlturaX
        cmp.l   d0,d5
        bhi.s   .rc_pop
        lsl.w   #2,d5
        add.w   d4,d5                   ; 4*difAlturaX + difAlturaY
        moveq   #0,d1                   ; DERECHA
        cmp.w   #1,d5
        beq.s   .rc_found
        moveq   #1,d1                   ; ABAJO
        cmp.w   #6,d5
        beq.s   .rc_found
        moveq   #2,d1                   ; IZQUIERDA
        cmp.w   #9,d5
        beq.s   .rc_found
        moveq   #3,d1                   ; ARRIBA
        cmp.w   #4,d5
        bne.s   .rc_pop
.rc_found:
        move.l  d2,d6                   ; posXDest = posX
        move.l  d3,d7
        move.l  d1,-(a2)                ; pushInv(ori)
        cmp.l   20(a4),d2
        bne.s   .rc_level
        cmp.l   24(a4),d3
        bne.s   .rc_level               ; not yet back at the start
.rc_out:
        move.l  a1,d0
        sub.l   a0,d0
        asr.l   #2,d0
        move.l  d0,28(a4)               ; posPila
        move.l  a2,d0
        sub.l   a0,d0
        asr.l   #2,d0
        subq.l  #1,d0
        move.l  d0,32(a4)               ; posPila2
        movem.l (sp)+,d2-d7/a2-a4
        rts

; ------------------------------------------------------------
; int a_bfs16(u8 *hab, s32 *stack, int *io)          see ql_kernels.h
; A0 rooms, A1 stack base, A2 push pointer, A3 read pointer, A5 io;
; D4/D5 x/y of the room being expanded, D7 mascara (only its low byte
; can meet a room byte).
; ------------------------------------------------------------
a_bfs16:
        movem.l d2-d7/a2-a5,-(sp)       ; 40 bytes saved -> args at 44
        move.l  44(sp),a0               ; hab
        move.l  48(sp),a1               ; stack
        move.l  52(sp),a5               ; io
        move.l  8(a5),d7                ; mascara
        move.l  a1,a2
        move.l  a1,a3
        move.w  6(a5),(a2)+             ; push(posXIni, posYIni)
        move.w  2(a5),(a2)+
        move.w  6(a5),d0
        lsl.w   #4,d0
        or.w    2(a5),d0
        bset    #7,0(a0,d0.w)           ; start room explored
        moveq   #-1,d0
        move.l  d0,(a2)+                ; level mark
.b6_loop:
        move.l  (a3)+,d0                ; elem(posProcesadoPila++)
        cmp.l   #-1,d0
        bne.s   .b6_cell
        cmp.l   a3,a2
        beq.s   .b6_nf
        moveq   #-1,d0
        move.l  d0,(a2)+
        bra.s   .b6_loop
.b6_cell:
        move.w  d0,d4                   ; x
        swap    d0
        move.w  d0,d5                   ; y
        move.w  d4,d0                   ; (x+1, y), door bit 2
        addq.w  #1,d0
        move.w  d5,d1
        moveq   #2,d2
        bsr.s   .b6_dest
        bne.s   .b6_f1
        move.w  d4,d0                   ; (x, y-1), bit 3
        move.w  d5,d1
        subq.w  #1,d1
        moveq   #3,d2
        bsr.s   .b6_dest
        bne.s   .b6_f2
        move.w  d4,d0                   ; (x-1, y), bit 0
        subq.w  #1,d0
        move.w  d5,d1
        moveq   #0,d2
        bsr.s   .b6_dest
        bne.s   .b6_f3
        move.w  d4,d0                   ; (x, y+1), bit 1
        move.w  d5,d1
        addq.w  #1,d1
        moveq   #1,d2
        bsr.s   .b6_dest
        beq.s   .b6_loop
        moveq   #4,d0
        bra.s   .b6_out
.b6_f1:
        moveq   #1,d0
        bra.s   .b6_out
.b6_f2:
        moveq   #2,d0
        bra.s   .b6_out
.b6_f3:
        moveq   #3,d0
        bra.s   .b6_out
.b6_nf:
        moveq   #-1,d4
        moveq   #-1,d5
        moveq   #0,d0
.b6_out:
        ext.l   d4
        ext.l   d5
        move.l  d4,12(a5)
        move.l  d5,16(a5)
        move.l  a2,d1
        sub.l   a1,d1
        asr.l   #2,d1
        move.l  d1,20(a5)               ; posPila
        move.l  a3,d1
        sub.l   a1,d1
        asr.l   #2,d1
        move.l  d1,24(a5)               ; posProcesadoPila
        movem.l (sp)+,d2-d7/a2-a5
        rts

; esPantallaDestino for room (D0, D1), D2 = number of the door bit (mascaraDestino).
; D6 = 1 (Z clear) if it is the goal, else 0 (Z set). Uses D3, D6.
.b6_dest:
        cmp.w   #$10,d0
        bhi.s   .b6_no                  ; < 0 or > 0x10
        cmp.w   #$10,d1
        bhi.s   .b6_no
        move.w  d1,d3
        lsl.w   #4,d3
        or.w    d0,d3                   ; (y << 4) | x
        move.b  0(a0,d3.w),d6
        btst    d2,d6
        bne.s   .b6_no                  ; no way in from this side
        and.b   d7,d6
        bne.s   .b6_yes                 ; the goal
        btst    #7,0(a0,d3.w)
        bne.s   .b6_no                  ; explored
        move.w  d1,(a2)+                ; push(x, y)
        move.w  d0,(a2)+
        bset    #7,0(a0,d3.w)
.b6_no:
        moveq   #0,d6
        rts
.b6_yes:
        moveq   #1,d6
        rts

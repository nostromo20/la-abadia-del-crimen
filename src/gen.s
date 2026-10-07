; ============================================================
; gen.s - asm twins of the room generator (QL_ASM_GEN, 2026-10-06)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; a_interpreta = GeneradorPantallas::interpretaComandos, with the frequent commands of the
; screens' block bytecode inside (the tile drawing: Comandos.cpp dibujaTileYMueve with
; leeDatoORegistro(0), grabaTile and actualizaTile for nivelesProfTiles = 2; the tile position
; moves, pushes and pops; the while loops); the other commands go to their C++ handlers.
; a_tile_mueve = dibujaTileYMueve alone, for C callers. Must give exactly the C's results:
; tools/gentest.py builds every screen both ways (dev header +30 bit 5 = the C) and compares
; the tile buffers and screens; cpcref --tiles / roomcmp / tilecompose / spiraltest in regress.
; ============================================================

        xdef    a_tile_mueve,a_interpreta
        xref    ql_gen_ejecuta

; GeneradorPantallas fields (cpp/vigasoco/GeneradorPantallas.h; static_assert in
; GeneradorPantallas.cpp qlCompruebaCampos and Comandos.cpp)
GP_ROMS equ     0               ; u8 *roms
GP_BT   equ     8               ; TileInfo bufferTiles[20][16] (6 bytes: profX[2] profY[2] tile[2])
GP_CB   equ     1996            ; int comandosBloque
GP_DB   equ     2000            ; int datosBloque[17]
GP_PX   equ     2068            ; int tilePosX
GP_PY   equ     2072            ; int tilePosY
GP_EST  equ     2078            ; int estadoOpsX[4]
GP_PILA equ     2094            ; int pila[64]
GP_POSP equ     2350            ; int posPila

; The interpreter's registers (also the tile body's):
;   A5 gen, A0 roms, A1 datosBloque, A2 bufferTiles,
;   D2 comandosBloque, D3 estadoOpsX[3], D4 tilePosX, D5 tilePosY  (D2/D4/D5 written back to
;   gen before any C++ handler runs, and all read again after it)
;   tile body: A6 deltax, A4 deltay; D1 tile number; D0, D6, D7, A3 scratch

; ------------------------------------------------------------
; void a_tile_mueve(GeneradorPantallas *gen, int deltax, int deltay)
; ------------------------------------------------------------
a_tile_mueve:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes saved -> args at 48
        move.l  48(sp),a5
        move.l  52(sp),a6
        move.l  56(sp),a4
        bsr     ai_load
        bsr     tm_body
        bsr     ai_store
        movem.l (sp)+,d2-d7/a2-a6
        rts

ai_load:
        move.l  GP_ROMS(a5),a0
        lea     GP_DB(a5),a1
        lea     GP_BT(a5),a2
        move.l  GP_CB(a5),d2
        move.l  GP_EST+12(a5),d3
        move.l  GP_PX(a5),d4
        move.l  GP_PY(a5),d5
        rts
ai_store:
        move.l  d2,GP_CB(a5)
        move.l  d4,GP_PX(a5)
        move.l  d5,GP_PY(a5)
        rts

; dibujaTileYMueve (A6 deltax, A4 deltay)
tm_body:
.tm_loop:
        bsr     tm_lee
        move.l  d0,d1                   ; num
        moveq   #0,d0
        move.b  0(a0,d2.l),d0           ; the next byte
        cmp.w   #$c8,d0
        blo.s   .tm_nc
        bsr     tm_graba                ; a new command: draw, move, done
        add.l   a6,d4
        add.l   a4,d5
        rts
.tm_nc:
        addq.l  #1,d2
        cmp.w   #$80,d0
        bne.s   .tm_n80
        bsr     tm_graba                ; 0x80: draw, move, go on
        add.l   a6,d4
        add.l   a4,d5
        bra.s   .tm_loop
.tm_n80:
        cmp.w   #$81,d0
        bne.s   .tm_rep
        bsr     tm_graba                ; 0x81: draw, go on
        bra.s   .tm_loop
.tm_rep:
        bsr     tm_lee                  ; the repeat count
        move.l  d0,-(sp)
.tm_rl:
        tst.l   (sp)
        ble.s   .tm_re
        bsr     tm_graba
        add.l   a6,d4
        add.l   a4,d5
        subq.l  #1,(sp)
        bra.s   .tm_rl
.tm_re:
        addq.l  #4,sp
        moveq   #0,d0
        move.b  0(a0,d2.l),d0
        cmp.w   #$c8,d0
        bhs.s   .tm_done                ; a new command: done
        addq.l  #1,d2                   ; else skip it and go on
        bra.s   .tm_loop
.tm_done:
        rts

; leeDatoORegistro(0) -> D0 (D2 advanced)
tm_lee:
        moveq   #0,d0
        move.b  0(a0,d2.l),d0
        addq.l  #1,d2
        cmp.w   #$60,d0
        blo.s   .tl_out                 ; an immediate value
        cmp.w   #$82,d0
        bne.s   .tl_reg
        moveq   #0,d0                   ; 0x82: the next byte
        move.b  0(a0,d2.l),d0
        addq.l  #1,d2
.tl_out:
        rts
.tl_reg:
        cmp.w   #$70,d0
        blo.s   .tl_r
        eor.l   d3,d0                   ; x sense swapped: registers 0x70 / 0x71
.tl_r:
        sub.l   #$61,d0
        add.l   d0,d0
        add.l   d0,d0
        move.l  0(a1,d0.l),d0           ; datosBloque[dato - 0x61]
        rts

; grabaTile(D1): the cell (tilePosX - 8, tilePosY - 8) if it is in the 16x20 buffer, then
; actualizaTile: layer 1 moves to layer 0 (its depth taken down to the new one's when the new
; one is nearer in both), the new tile and depth (datosBloque[15], [16]) become layer 1
tm_graba:
        move.l  d4,d6
        subq.l  #8,d6
        cmp.l   #16,d6
        bhs.s   .tg_out
        move.l  d5,d7
        subq.l  #8,d7
        cmp.l   #20,d7
        bhs.s   .tg_out
        lsl.w   #5,d7                   ; row * 32
        move.w  d7,d0
        add.w   d7,d7
        add.w   d0,d7                   ; row * 96 (16 cells of 6 bytes)
        add.w   d6,d6                   ; column * 2
        add.w   d6,d7
        add.w   d6,d6
        add.w   d6,d7                   ; + column * 6
        lea     0(a2,d7.w),a3
        moveq   #0,d6
        move.b  1(a3),d6                ; oldProfX = profX[1]
        moveq   #0,d7
        move.b  3(a3),d7                ; oldProfY = profY[1]
        move.l  60(a1),d0               ; newProfX
        cmp.l   d6,d0
        bge.s   .tg_keep
        move.l  64(a1),d0               ; newProfY
        cmp.l   d7,d0
        bge.s   .tg_keep
        move.l  60(a1),d6
        move.l  64(a1),d7
.tg_keep:
        move.b  d6,(a3)                 ; profX[0]
        move.b  d7,2(a3)                ; profY[0]
        move.b  5(a3),4(a3)             ; tile[0] = tile[1]
        move.b  63(a1),1(a3)            ; profX[1] = newProfX (its low byte)
        move.b  67(a1),3(a3)            ; profY[1] = newProfY
        move.b  d1,5(a3)                ; tile[1]
.tg_out:
        rts

; ------------------------------------------------------------
; void a_interpreta(GeneradorPantallas *gen)
; ------------------------------------------------------------
a_interpreta:
        movem.l d2-d7/a2-a6,-(sp)       ; 44 bytes saved -> arg at 48
        move.l  48(sp),a5
        bsr     ai_load
.ai_loop:
        moveq   #0,d0
        move.b  0(a0,d2.l),d0
        not.b   d0                      ; numRutina = byte ^ 0xff
        addq.l  #1,d2
        cmp.w   #$1c,d0
        bhs.s   .ai_c
        add.w   d0,d0
        move.w  .ai_tab(pc,d0.w),d0
        jmp     .ai_tab(pc,d0.w)
.ai_tab:
        dc.w    .ai_c-.ai_tab           ; 00 EndBlock
        dc.w    .ai_w1-.ai_tab          ; 01 WhileParam1
        dc.w    .ai_w2-.ai_tab          ; 02 WhileParam2
        dc.w    .ai_push-.ai_tab        ; 03 PushTilePos
        dc.w    .ai_pop-.ai_tab         ; 04 PopTilePos
        dc.w    .ai_ew-.ai_tab          ; 05 EndWhile
        dc.w    .ai_dy-.ai_tab          ; 06 DrawTileDecY
        dc.w    .ai_ix-.ai_tab          ; 07 DrawTileIncX
        dc.w    .ai_c-.ai_tab           ; 08 UpdateReg
        dc.w    .ai_iy-.ai_tab          ; 09 IncTilePosY
        dc.w    .ai_ipx-.ai_tab         ; 0a IncTilePosX
        dc.w    .ai_dpy-.ai_tab         ; 0b DecTilePosY
        dc.w    .ai_dpx-.ai_tab         ; 0c DecTilePosX
        dc.w    .ai_c-.ai_tab           ; 0d UpdateTilePosY
        dc.w    .ai_c-.ai_tab           ; 0e UpdateTilePosX
        dc.w    .ai_c-.ai_tab           ; 0f IncParam1
        dc.w    .ai_c-.ai_tab           ; 10 IncParam2
        dc.w    .ai_c-.ai_tab           ; 11 DecParam1
        dc.w    .ai_c-.ai_tab           ; 12 DecParam2
        dc.w    .ai_c-.ai_tab           ; 13 Call
        dc.w    .ai_dx-.ai_tab          ; 14 DrawTileDecX
        dc.w    .ai_c-.ai_tab           ; 15 ChangePC
        dc.w    .ai_c-.ai_tab           ; 16 FlipX
        dc.w    .ai_c-.ai_tab           ; 17 FlipX
        dc.w    .ai_c-.ai_tab           ; 18 FlipX
        dc.w    .ai_c-.ai_tab           ; 19 FlipX
        dc.w    .ai_c-.ai_tab           ; 1a FlipX
        dc.w    .ai_c-.ai_tab           ; 1b CallPreserve
.ai_c:                                  ; a C++ handler
        bsr     ai_store
        moveq   #0,d0
        move.b  -1(a0,d2.l),d0
        not.b   d0
        move.l  d0,-(sp)
        move.l  a5,-(sp)
        jsr     ql_gen_ejecuta
        addq.l  #8,sp
        move.l  d0,d1
        bsr     ai_load                 ; the handler may have changed any of them
        tst.l   d1
        beq.s   .ai_loop
        movem.l (sp)+,d2-d7/a2-a6       ; EndBlock: done
        rts
.ai_w1:
        move.l  12*4(a1),d0             ; obtenerRegistro(0x6d) = datosBloque[12]
        bra.s   .ai_w
.ai_w2:
        move.l  13*4(a1),d0             ; obtenerRegistro(0x6e) = datosBloque[13]
.ai_w:
        ble.s   .ai_skip
        move.l  d0,d6                   ; aux
        move.l  d2,d1
        bsr     ai_pu                   ; push(comandosBloque)
        move.l  d6,d1
        bsr     ai_pu                   ; push(aux)
        bra     .ai_loop
.ai_skip:                               ; avanzaHastaFinDeWhile
        moveq   #1,d6                   ; profWhile
.ai_sk:
        move.b  0(a0,d2.l),d0
        cmp.b   #$82,d0
        bne.s   .ai_sk1
        addq.l  #2,d2
        bra.s   .ai_skn
.ai_sk1:
        cmp.b   #$fe,d0
        beq.s   .ai_skin
        cmp.b   #$fd,d0
        bne.s   .ai_sk2
.ai_skin:
        addq.l  #1,d6
        bra.s   .ai_sk3
.ai_sk2:
        cmp.b   #$fa,d0
        bne.s   .ai_sk3
        subq.l  #1,d6
.ai_sk3:
        addq.l  #1,d2
.ai_skn:
        tst.l   d6
        bgt.s   .ai_sk
        bra     .ai_loop
.ai_push:
        move.l  d4,d1
        bsr     ai_pu
        move.l  d5,d1
        bsr     ai_pu
        bra     .ai_loop
.ai_pop:
        bsr     ai_po
        move.l  d1,d5
        bsr     ai_po
        move.l  d1,d4
        bra     .ai_loop
.ai_ew:                                 ; EndWhile
        bsr     ai_po                   ; contador
        subq.l  #1,d1
        ble.s   .ai_ew0
        move.l  d1,d6
        bsr     ai_po                   ; comandosBloque = pop()
        move.l  d1,d2
        bsr     ai_pu                   ; push(comandosBloque)
        move.l  d6,d1
        bsr     ai_pu                   ; push(contador)
        bra     .ai_loop
.ai_ew0:
        bsr     ai_po
        bra     .ai_loop
.ai_iy:
        addq.l  #1,d5
        bra     .ai_loop
.ai_dpy:
        subq.l  #1,d5
        bra     .ai_loop
.ai_ipx:
        add.l   GP_EST(a5),d4           ; + estadoOpsX[0]
        bra     .ai_loop
.ai_dpx:
        sub.l   GP_EST+4(a5),d4         ; - estadoOpsX[1]
        bra     .ai_loop
.ai_dy:
        suba.l  a6,a6
        move.w  #-1,a4                  ; (sign-extended)
        bra.s   .ai_draw
.ai_ix:
        move.l  GP_EST+8(a5),a6         ; estadoOpsX[2]
        suba.l  a4,a4
        bra.s   .ai_draw
.ai_dx:
        move.w  #-1,a6
        suba.l  a4,a4
.ai_draw:
        bsr     tm_body
        bra     .ai_loop

; push(D1) / D1 = pop() on gen->pila (D0, A3 trashed)
ai_pu:
        lea     GP_PILA(a5),a3
        move.l  GP_POSP(a5),d0
        add.l   d0,d0
        add.l   d0,d0
        move.l  d1,0(a3,d0.l)
        addq.l  #1,GP_POSP(a5)
        rts
ai_po:
        lea     GP_PILA(a5),a3
        subq.l  #1,GP_POSP(a5)
        move.l  GP_POSP(a5),d1
        add.l   d1,d1
        add.l   d1,d1
        move.l  0(a3,d1.l),d1
        rts

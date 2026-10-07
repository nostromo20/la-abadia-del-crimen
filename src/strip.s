; ============================================================
; strip.s - the text strip under the panel, and the file calls of the save device
; La Abadia del Crimen - QL Port (hybrid build; cpp/port/ql_strip.cpp drives it)
; ============================================================
; The strip is QL lines STRIP_Y..255 (28 lines, layout A: below the panel at
; PANEL_QL_Y..PANEL_QL_Y+39). It is outside the CPC screen (QL lines PLAY_Y..
; PLAY_Y+199), so neither the game, the recolour nor hdiff ever touch it: the
; C++ draws it only when its text or the palette changes.
; ============================================================

STRIP_Y         equ PANEL_QL_Y+40       ; 228
        if      STRIP_Y<>228
        fail    "strip.s: the strip is meant to start at QL line 228"
        endif

        xdef    ql_strip_line,ql_strip_clear,ql_fsave,ql_fload,ql_fprobe

; ------------------------------------------------------------
; void ql_strip_line(int qlline, const u8 *bits, int colour)
; one QL line (STRIP_Y..255) from 32 bytes of 1-bit pixels (bit 7 = left),
; set pixels in the colour, the others black. colour 0-7: that QL colour;
; $100 + p: the PANEL colour of pen 2 (the panel's text) of CPC palette p,
; with its dither for the line's parity (palette_data.s pal_table).
; ------------------------------------------------------------
ql_strip_line:
        movem.l d2-d4/a2,-(sp)          ; 16 bytes -> args at 20
        movem.l 20(sp),d0/a1            ; line, bits
        move.l  28(sp),d2               ; colour
        cmp.l   #STRIP_Y,d0
        blt.s   .sl_out
        cmp.l   #255,d0
        bgt.s   .sl_out
        btst    #8,d2
        bne.s   .sl_pal
        and.w   #7,d2
        add.w   d2,d2
        lea     sl_cols(pc),a0
        move.w  0(a0,d2.w),d2
        bra.s   .sl_go
.sl_pal:
        and.w   #3,d2
        lsl.w   #6,d2                   ; 64 bytes a palette
        lea     pal_table,a0
        adda.w  d2,a0
        moveq   #32+2*2,d2              ; panel, even lines, pen 2
        btst    #0,d0
        beq.s   .sl_par
        moveq   #40+2*2,d2              ; odd lines
.sl_par:
        move.w  0(a0,d2.w),d2
.sl_go:
        lea     SCREEN_BASE,a0
        lsl.w   #7,d0                   ; * SCREEN_STRIDE
        adda.w  d0,a0                   ; (line < 256: fits a word offset, $7F80 max)
        lea     sl_mask(pc),a2
        moveq   #31,d3
.sl_byte:
        moveq   #0,d0
        move.b  (a1)+,d0
        move.w  d0,d1
        lsr.w   #4,d1                   ; left 4 pixels
        add.w   d1,d1
        move.w  0(a2,d1.w),d4
        and.w   d2,d4
        move.w  d4,(a0)+
        and.w   #15,d0                  ; right 4 pixels
        add.w   d0,d0
        move.w  0(a2,d0.w),d4
        and.w   d2,d4
        move.w  d4,(a0)+
        dbra    d3,.sl_byte
.sl_out:
        movem.l (sp)+,d2-d4/a2
        rts

; ------------------------------------------------------------
; void ql_strip_clear(void) - the strip black (QL lines STRIP_Y..255)
; ------------------------------------------------------------
ql_strip_clear:
        lea     SCREEN_BASE+STRIP_Y*SCREEN_STRIDE,a0
        move.w  #((256-STRIP_Y)*SCREEN_STRIDE/4)-1,d0
        moveq   #0,d1
.sc_l:
        move.l  d1,(a0)+
        dbra    d0,.sc_l
        rts

; a nibble of 4 pixels (bit 3 = left) -> the Mode 8 word mask of those pixels
; (pixel k: bits 7-2k and 6-2k of both bytes)
sl_mask:
        dc.w    $0000,$0303,$0C0C,$0F0F,$3030,$3333,$3C3C,$3F3F
        dc.w    $C0C0,$C3C3,$CCCC,$CFCF,$F0F0,$F3F3,$FCFC,$FFFF
sl_cols:
        dc.w    COL_BLACK,COL_BLUE,COL_RED,COL_MAGENTA,COL_GREEN,COL_CYAN,COL_YELLOW,COL_WHITE

; ------------------------------------------------------------
; Files on the chosen save device (ql_strip.cpp). name = a QDOS string
; (word length + characters) at an EVEN address. All return a QDOS error
; code (< 0) on failure, never stop: the channel is always closed.
; ------------------------------------------------------------

; int ql_fsave(const void *name, const char *buf, int len) -> bytes written or error
; (any old file of the name is deleted first: F1 overwrites, no backup)
ql_fsave:
        movem.l d2-d5/a2-a5,-(sp)       ; 32 bytes -> args at 36
        move.l  36(sp),d5               ; name (QDOS keeps only D4-D7/A4-A6 over a trap)
        move.l  40(sp),a4               ; buffer
        move.l  44(sp),d4               ; length
        moveq   #IO_DELET,d0            ; error ignored (none yet, or no device)
        moveq   #-1,d1
        move.l  d5,a0
        bsr     do_trap2
        moveq   #IO_OPEN,d0
        moveq   #-1,d1
        moveq   #2,d3                   ; new file
        move.l  d5,a0
        bsr     do_trap2
        tst.l   d0
        bne.s   .fv_out                 ; D0 = the error
        move.l  a0,a5
        moveq   #IO_SSTRG,d0
        move.l  d4,d2
        moveq   #-1,d3
        move.l  a4,a1
        bsr     do_trap3
        move.l  d1,d4                   ; bytes written ...
        tst.l   d0
        beq.s   .fv_ok
        move.l  d0,d4                   ; ... or the error (full, write-protected ...)
.fv_ok:
        move.l  a5,a0
        moveq   #IO_CLOSE,d0
        bsr     do_trap2
        move.l  d4,d0
.fv_out:
        movem.l (sp)+,d2-d5/a2-a5
        rts

; int ql_fload(const void *name, char *buf, int cap) -> bytes read or error
ql_fload:
        movem.l d2-d4/a2-a5,-(sp)       ; 28 bytes -> args at 32
        move.l  32(sp),a0               ; name
        move.l  36(sp),a4
        move.l  40(sp),d4
        moveq   #IO_OPEN,d0
        moveq   #-1,d1
        moveq   #1,d3                   ; old file, shared
        bsr     do_trap2
        tst.l   d0
        bne.s   .fd_out
        move.l  a0,a5
        moveq   #IO_FSTRG,d0
        move.l  d4,d2
        moveq   #-1,d3
        move.l  a4,a1
        bsr     do_trap3                ; end of file may come with D1 > 0
        move.l  d1,d4
        move.l  a5,a0
        moveq   #IO_CLOSE,d0
        bsr     do_trap2
        move.l  d4,d0
.fd_out:
        movem.l (sp)+,d2-d4/a2-a5
        rts

; int ql_fprobe(const void *name, int key) -> 0 if it opens (then closed), else the error
; key 1: an existing file (shared); key 4: a device's directory (is a medium there?)
ql_fprobe:
        movem.l d2-d4/a2-a5,-(sp)
        move.l  32(sp),a0
        move.l  36(sp),d3
        moveq   #IO_OPEN,d0
        moveq   #-1,d1
        bsr     do_trap2
        tst.l   d0
        bne.s   .fp_out
        moveq   #IO_CLOSE,d0
        bsr     do_trap2
        moveq   #0,d0
.fp_out:
        movem.l (sp)+,d2-d4/a2-a5
        rts

; ============================================================
; text.s - Character and string rendering for QL Mode 8
; La Abadia del Crimen - QL Port
; ============================================================
; Routines: draw_char, draw_string
; Uses font data from font.s (blank_glyph, font_base).
;
; Each font glyph is 8x8 pixels stored as 8 bytes (1 bit/pixel).
; The nibble_to_mask LUT converts 4-bit pixel patterns to QL
; Mode 8 word masks. Each font byte is split into high nibble
; (left 4 pixels) and low nibble (right 4 pixels), each mapped
; through the LUT then ANDed with the colour word.
;
; Characters are drawn directly to SCREEN_BASE (not the buffer)
; for UI overlay text. X must be a multiple of 4 for word alignment.

; ============================================================
; nibble_to_mask - Maps 4-bit pixel pattern to QL white mask
; Index: nibble value (0-15), each entry is a word.
; Usage: nibble_to_mask[nibble] AND colour = coloured pixels
; ============================================================
nibble_to_mask:
        dc.w    $0000,$0303,$0C0C,$0F0F
        dc.w    $3030,$3333,$3C3C,$3F3F
        dc.w    $C0C0,$C3C3,$CCCC,$CFCF
        dc.w    $F0F0,$F3F3,$FCFC,$FFFF

; ============================================================
; draw_char - Draw a single 8x8 font character
; Entry: D0.W = X (must be multiple of 4)
;        D1.W = Y
;        D2.W = colour word
;        D3.B = ASCII code
; Trashes: D0-D5/A0-A2
; ============================================================
draw_char:
        ; Strip high bit (game uses bit 7 as flag)
        and.w   #$7F,d3

        ; Select glyph pointer -> A1
        cmp.b   #$20,d3
        bne.s   .not_space
        lea     blank_glyph(pc),a1
        bra.s   .have_glyph
.not_space:
        cmp.b   #$2D,d3
        blo.s   .dc_done            ; below range, skip
        cmp.b   #$5A,d3
        bhi.s   .dc_done            ; above range, skip
        sub.b   #$2D,d3
        ext.w   d3
        lsl.w   #3,d3               ; glyph index * 8
        lea     font_base(pc),a1
        adda.w  d3,a1
.have_glyph:
        ; Calculate screen address: SCREEN_BASE + Y*128 + (X/4)*2
        lea     SCREEN_BASE,a0
        move.w  d1,d3
        lsl.w   #7,d3               ; Y * 128
        adda.w  d3,a0
        move.w  d0,d3
        lsr.w   #2,d3               ; X / 4
        add.w   d3,d3               ; word offset
        adda.w  d3,a0               ; A0 = screen address

        lea     nibble_to_mask(pc),a2

        ; 8-row loop
        moveq   #7,d3               ; row counter
.row_loop:
        moveq   #0,d4
        move.b  (a1)+,d4            ; font byte

        ; High nibble -> left 4 pixels (first word)
        move.w  d4,d5
        lsr.w   #4,d5               ; high nibble
        add.w   d5,d5               ; word offset into LUT
        move.w  0(a2,d5.w),d5       ; white mask for left 4px
        and.w   d2,d5               ; apply colour
        move.w  d5,(a0)             ; write left word

        ; Low nibble -> right 4 pixels (second word)
        move.w  d4,d5
        and.w   #$0F,d5             ; low nibble
        add.w   d5,d5               ; word offset into LUT
        move.w  0(a2,d5.w),d5       ; white mask for right 4px
        and.w   d2,d5               ; apply colour
        move.w  d5,2(a0)            ; write right word (next word)

        ; Next scanline
        adda.w  #SCREEN_STRIDE,a0
        dbra    d3,.row_loop

.dc_done:
        rts

; ============================================================
; draw_string - Draw a null-terminated string
; Entry: D0.W = X (must be multiple of 4)
;        D1.W = Y
;        D2.W = colour word
;        A0 = pointer to null-terminated string
; Trashes: D0-D7/A0-A4
; ============================================================
draw_string:
        move.w  d0,d6               ; D6 = current X
        move.w  d1,d7               ; D7 = Y (constant)
        movea.l a0,a4               ; A4 = string pointer
        move.w  d2,a3               ; A3 = colour (safe across draw_char)
.ds_loop:
        moveq   #0,d3
        move.b  (a4)+,d3            ; next character
        beq.s   .ds_done            ; null terminator
        cmp.w   #256,d6
        bge.s   .ds_done            ; off right edge

        move.w  d6,d0               ; X
        move.w  d7,d1               ; Y
        move.w  a3,d2               ; colour
        bsr     draw_char

        addq.w  #8,d6               ; advance X by 8 pixels
        bra.s   .ds_loop
.ds_done:
        rts

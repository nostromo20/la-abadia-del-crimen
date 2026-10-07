; ============================================================
; rel_title.s - the RELEASE loading screen: a tiny QDOS job that unpacks the title picture
; La Abadia del Crimen - QL Port (build_release.sh; docs/release.md)
; ============================================================
; BOOT sets MODE 8, then EXEC_Ws this job, then the game. This job unpacks the ZX0-packed
; loading screen (loadscreen/A4S_scr, 32 KB) straight into the screen memory at $20000 and
; removes itself: the picture stays up while QDOS loads the (much bigger) game file, and until
; the game's intro parchment dissolves it away.
;
; Assembled by build_release.sh with vasm -Fbin, -I build/rel (title.zx0).
; ============================================================

MT_FRJOB        equ 5
SCREEN_BASE     equ $20000

        org     0
base:
        bra.w   start                   ; +0
        dc.w    0                       ; +4
        dc.w    $4AFB                   ; +6 job header tag
        dc.w    12                      ; +8 job name
        dc.b    "ABADIA_TITLE"
start:
        lea     packed(pc),a0
        lea     SCREEN_BASE,a1
        bsr     zx0_decompress
        moveq   #MT_FRJOB,d0            ; remove this job (frees its area)
        moveq   #-1,d1
        moveq   #0,d3
        trap    #1
.hang:  bra.s   .hang                   ; (not reached)

        include "unzx0_68000.s"         ; Emmanuel Marty, zlib licence (unchanged)

packed:
        incbin  "title.zx0"
        even

; ============================================================
; libgcc68k.s - 32-bit multiply/divide helpers for GCC on a plain 68000
; ============================================================
; Ubuntu's m68k-linux-gnu libgcc is built for the 68020 (32-bit mul/div
; instructions), so the routines GCC calls for -m68000 are supplied here.
; Algorithms as in libgcc's lb1sf68.S (GPL with the GCC runtime exception).
; Arguments on the stack (4(sp), 8(sp)), result in D0, D2 preserved.
; ============================================================

        xdef    __mulsi3,__udivsi3,__divsi3,__umodsi3,__modsi3

__mulsi3:
        move.w  4(sp),d0                ; a.hi
        mulu.w  10(sp),d0               ; a.hi * b.lo
        move.w  8(sp),d1                ; b.hi
        mulu.w  6(sp),d1                ; b.hi * a.lo
        add.w   d1,d0
        swap    d0
        clr.w   d0
        move.w  6(sp),d1                ; a.lo
        mulu.w  10(sp),d1               ; a.lo * b.lo
        add.l   d1,d0
        rts

__udivsi3:
        move.l  d2,-(sp)
        move.l  12(sp),d1               ; divisor
        move.l  8(sp),d0                ; dividend
        cmp.l   #$10000,d1
        bcc.s   .ud_big
        move.l  d0,d2
        clr.w   d2
        swap    d2
        divu    d1,d2                   ; high quotient
        move.w  d2,d0
        swap    d0
        move.w  10(sp),d2               ; low dividend + high remainder
        divu    d1,d2                   ; low quotient
        move.w  d2,d0
        bra.s   .ud_done
.ud_big:
        move.l  d1,d2
.ud_shift:
        lsr.l   #1,d1
        lsr.l   #1,d0
        cmp.l   #$10000,d1
        bcc.s   .ud_shift
        divu    d1,d0
        and.l   #$ffff,d0
        move.l  d2,d1
        mulu    d0,d1
        swap    d2
        mulu    d0,d2
        swap    d2
        tst.w   d2
        bne.s   .ud_adjust
        add.l   d2,d1
        bcs.s   .ud_adjust
        cmp.l   8(sp),d1
        bls.s   .ud_done
.ud_adjust:
        subq.l  #1,d0
.ud_done:
        move.l  (sp)+,d2
        rts

__divsi3:
        move.l  d2,-(sp)
        moveq   #1,d2
        move.l  12(sp),d1
        bpl.s   .ds_1
        neg.l   d1
        neg.b   d2
.ds_1:
        move.l  8(sp),d0
        bpl.s   .ds_2
        neg.l   d0
        neg.b   d2
.ds_2:
        move.l  d1,-(sp)
        move.l  d0,-(sp)
        bsr     __udivsi3
        addq.l  #8,sp
        tst.b   d2
        bpl.s   .ds_3
        neg.l   d0
.ds_3:
        move.l  (sp)+,d2
        rts

__umodsi3:
        move.l  8(sp),d1
        move.l  4(sp),d0
        move.l  d1,-(sp)
        move.l  d0,-(sp)
        bsr     __udivsi3
        addq.l  #8,sp
        move.l  8(sp),d1
        move.l  d1,-(sp)
        move.l  d0,-(sp)
        bsr     __mulsi3
        addq.l  #8,sp
        move.l  4(sp),d1
        sub.l   d0,d1
        move.l  d1,d0
        rts

__modsi3:
        move.l  8(sp),d1
        move.l  4(sp),d0
        move.l  d1,-(sp)
        move.l  d0,-(sp)
        bsr     __divsi3
        addq.l  #8,sp
        move.l  8(sp),d1
        move.l  d1,-(sp)
        move.l  d0,-(sp)
        bsr     __mulsi3
        addq.l  #8,sp
        move.l  4(sp),d1
        sub.l   d0,d1
        move.l  d1,d0
        rts

; ============================================================
; memcpy / memmove / memset for the C++ code (2026-10-05, speed option 6). The C versions
; (cpp/port/ql_runtime.cpp: c_memcpy, c_memmove, c_memset in the dev build, the real ones with
; QL_C_MEMOPS + vasm -DC_MEMOPS) copied a long in ~8 instructions; here 16 bytes a dbra pass.
; tools/memtest.py: byte-identical to the C ones (overlaps, parities, lengths 0..600).
; Arguments on the stack; the result (d) in D0 and A0 (pointers come back in both).
; memcpy = memmove: forward when d <= s, backward when d > s (overlap safe either way).
; ============================================================
        ifnd    C_MEMOPS
        xdef    memcpy,memmove,memset

memcpy:
memmove:
        move.l  d2,-(sp)
        move.l  8(sp),d0                ; d
        movea.l d0,a1
        movea.l 12(sp),a0               ; s
        move.l  16(sp),d1               ; n
        cmpa.l  a0,a1
        bhi     mm_back
        move.w  a1,d2
        sub.w   a0,d2
        btst    #0,d2
        bne.s   mf_bytes                ; different parity: bytes only
        move.w  a1,d2
        btst    #0,d2
        beq.s   mf_even
        tst.l   d1
        beq.s   mm_done
        move.b  (a0)+,(a1)+             ; both odd: one byte, then both even
        subq.l  #1,d1
mf_even:
        move.l  d1,d2
        lsr.l   #4,d2                   ; 16-byte blocks
        beq.s   mf_tail
        subq.l  #1,d2
mf_blk:
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        dbra    d2,mf_blk
        sub.l   #$10000,d2              ; the high word of the count
        bcc.s   mf_blk
mf_tail:
        btst    #3,d1
        beq.s   mf_t4
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
mf_t4:
        btst    #2,d1
        beq.s   mf_t2
        move.l  (a0)+,(a1)+
mf_t2:
        btst    #1,d1
        beq.s   mf_t1
        move.w  (a0)+,(a1)+
mf_t1:
        btst    #0,d1
        beq.s   mm_done
        move.b  (a0)+,(a1)+
mm_done:
        movea.l d0,a0
        move.l  (sp)+,d2
        rts
mf_bytes:
        move.l  d1,d2
        beq.s   mm_done
        subq.l  #1,d2
mf_bl:
        move.b  (a0)+,(a1)+
        dbra    d2,mf_bl
        sub.l   #$10000,d2
        bcc.s   mf_bl
        bra.s   mm_done

mm_back:                                ; d > s: from the end down
        adda.l  d1,a0
        adda.l  d1,a1
        move.w  a1,d2
        sub.w   a0,d2
        btst    #0,d2
        bne.s   mb_bytes
        move.w  a1,d2
        btst    #0,d2
        beq.s   mb_even
        tst.l   d1
        beq     mm_done
        move.b  -(a0),-(a1)
        subq.l  #1,d1
mb_even:                                ; (rarer: one long a pass, smaller)
        move.l  d1,d2
        lsr.l   #2,d2                   ; longs
        beq.s   mb_t2
        subq.l  #1,d2
mb_blk:
        move.l  -(a0),-(a1)
        dbra    d2,mb_blk
        sub.l   #$10000,d2
        bcc.s   mb_blk
mb_t2:
        btst    #1,d1
        beq.s   mb_t1
        move.w  -(a0),-(a1)
mb_t1:
        btst    #0,d1
        beq     mm_done
        move.b  -(a0),-(a1)
        bra     mm_done
mb_bytes:
        move.l  d1,d2
        beq     mm_done
        subq.l  #1,d2
mb_bl:
        move.b  -(a0),-(a1)
        dbra    d2,mb_bl
        sub.l   #$10000,d2
        bcc.s   mb_bl
        bra     mm_done

; void *memset(void *d, int c, size_t n)
memset:
        move.l  d2,-(sp)
        move.l  8(sp),d0                ; d
        movea.l d0,a1
        move.l  16(sp),d1               ; n
        move.b  15(sp),d2               ; c
        lsl.w   #8,d2
        move.b  15(sp),d2
        move.w  d2,a0
        swap    d2
        move.w  a0,d2                   ; c in all four bytes
        btst    #0,d0                   ; d odd?
        beq.s   ms_even
        tst.l   d1
        beq.s   ms_done
        move.b  d2,(a1)+
        subq.l  #1,d1
ms_even:                                ; (one long a pass: memset is not hot, smaller)
        move.l  d1,a0                   ; n (the long count goes in d1 below)
        lsr.l   #2,d1
        beq.s   ms_tail
        subq.l  #1,d1
ms_blk:
        move.l  d2,(a1)+
        dbra    d1,ms_blk
        sub.l   #$10000,d1
        bcc.s   ms_blk
ms_tail:
        move.l  a0,d1                   ; n again: its low 2 bits
ms_t2:
        btst    #1,d1
        beq.s   ms_t1
        move.w  d2,(a1)+
ms_t1:
        btst    #0,d1
        beq.s   ms_done
        move.b  d2,(a1)+
ms_done:
        movea.l d0,a0
        move.l  (sp)+,d2
        rts

        ifnd    RELEASE
        ; the C references (c_memcpy...) kept through ld --gc-sections for tools/memtest.py
        cnop    0,4
mem_c_refs:
        dc.l    c_memcpy,c_memmove,c_memset
        endc
        endif

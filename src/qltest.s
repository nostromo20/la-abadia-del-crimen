; ============================================================
; qltest.s - in-emulator test hooks (autopilot + self-log)
; La Abadia del Crimen - QL Port (hybrid build)
; ============================================================
; Header byte +30 (POKEd by a test boot program, 0 in normal use):
;   bit 0  autopilot: keys come from the script area, not the keyboard
;   bit 1  self-log:  every LOG_EVERY steps a 32-byte record is added to a
;          RAM log and the whole log is rewritten to the file named in the
;          script area (so a freeze still leaves the log up to that point)
; Script area: image offset 288 (hdr_script), 1024 bytes, written by the
; boot program with LBYTES (tools/qltest.py makes it from tests/*.txt):
;   +0  word  log every N steps (0 = never)
;   +2  word  end step: from this step the autopilot holds ESC (0 = never)
;   +4  word  file name length, +6 30 bytes name (QDOS string)
;   +36 entries: word first step, word last step, word key mask (bit = QK_*)
;       terminated by first = $FFFF
; Log record (32 bytes, big-endian), decoded by tools/qltest.py:
;   +0 step  +4 frames EXCLUDING the log's own file I/O (+24 polls = real frames)  +8 phase  +9 estado  +10 key mask (word)
;   +12 fault word  +16 pantalla  +17..20 Guillermo x y height orientation
;   +21 abbot x  +22 abbot y  +23 flags (1 poll dead, 2 QSound)
;   +24 poll count (long)  +28 longest main-loop silence in frames (word)
;   +30 BEEPs issued so far (word, low 16 bits of beep_count, qlhooks.s)
; ============================================================

TF_AUTOPILOT    equ 0
TF_LOG          equ 1
SCRIPT_OFF      equ 288
LOG_RECORDS     equ 512                 ; 16 KB of BSS

LOG_FLUSH       equ 8                   ; rewrite the log file every 8 records

        xdef    autopilot_keys,test_log,test_poll,test_flush

        ifd     RELEASE
; release build (build_release.sh): no test hooks. The keyboard always drives, nothing is logged.
autopilot_keys:
        moveq   #0,d0
test_log:
test_poll:
test_flush:
        rts
        else

; ------------------------------------------------------------
; autopilot_keys: called by scan_keyrows (registers saved there).
; Returns D0 = 1 if it filled key_state (skip the keyboard), else 0.
; ------------------------------------------------------------
autopilot_keys:
        moveq   #0,d0
        btst    #TF_AUTOPILOT,ql_hdr+30
        beq.s   .ap_out
        move.l  ql_hdr+16,d1            ; the step about to run
        lea     ql_hdr+SCRIPT_OFF+36,a0
        moveq   #0,d2                   ; key mask
.ap_entry:
        move.w  (a0)+,d3                ; first
        cmp.w   #$FFFF,d3
        beq.s   .ap_done
        move.w  (a0)+,d4                ; last
        move.w  (a0)+,d5                ; mask
        cmp.w   d3,d1
        blo.s   .ap_entry
        cmp.w   d4,d1
        bhi.s   .ap_entry
        or.w    d5,d2
        bra.s   .ap_entry
.ap_done:
        move.w  ql_hdr+SCRIPT_OFF+2,d3  ; end step
        beq.s   .ap_set
        cmp.w   d3,d1
        blo.s   .ap_set
        bset    #QK_ESC,d2
.ap_set:
        lea     key_state,a0
        moveq   #0,d3                   ; key index
.ap_key:
        btst    d3,d2
        sne     (a0)
        and.b   #1,(a0)+
        addq.w  #1,d3
        cmp.w   #QK_COUNT,d3
        blo.s   .ap_key
        moveq   #1,d0
.ap_out:
        rts

; ------------------------------------------------------------
; test_poll: called by the poll routine every frame (A0/D0/D1 only)
; ------------------------------------------------------------
test_poll:
        addq.l  #1,poll_count
        move.l  ql_hdr+20,d0            ; frames
        sub.l   last_step_frames,d0     ; frames since the main loop's last step
        cmp.l   #$FFFF,d0
        bls.s   .tp_w
        move.w  #$FFFF,d0
.tp_w:
        move.w  d0,silence_now
        cmp.w   silence_max,d0
        bls.s   .tp_out
        move.w  d0,silence_max
.tp_out:
        rts

; ------------------------------------------------------------
; test_log: called by the main loop after every step
; ------------------------------------------------------------
test_log:
        move.l  ql_hdr+20,last_step_frames
        btst    #TF_LOG,ql_hdr+30
        beq     .tl_out
        moveq   #0,d0
        move.w  ql_hdr+SCRIPT_OFF,d0    ; log every N steps
        beq     .tl_out
        move.l  ql_hdr+16,d1            ; steps done
        divu    d0,d1
        swap    d1
        tst.w   d1
        bne     .tl_out
        move.w  log_count,d0
        cmp.w   #LOG_RECORDS,d0
        bhs     .tl_out                 ; log full
        movem.l d2-d7/a2-a5,-(sp)
        ; the state block (filled here when the harness bit did not do it)
        btst    #0,ql_hdr+31
        bne.s   .tl_have
        pea     ql_hdr+32
        jsr     abadia_state
        addq.l  #4,sp
.tl_have:
        lea     ql_hdr,a2
        lea     log_buf,a0
        move.w  log_count,d0
        lsl.l   #5,d0
        adda.l  d0,a0                   ; this record
        move.l  16(a2),(a0)+            ; step
        move.l  20(a2),d0
        sub.l   log_io_frames,d0
        move.l  d0,(a0)+                ; frames, less the time spent writing the log
        move.b  diag_phase,(a0)+
        move.b  32+240(a2),(a0)+        ; estado
        moveq   #0,d1                   ; key mask from key_state
        lea     key_state,a1
        moveq   #0,d2
.tl_k:
        tst.b   0(a1,d2.w)
        beq.s   .tl_kn
        bset    d2,d1
.tl_kn:
        addq.w  #1,d2
        cmp.w   #QK_COUNT,d2
        blo.s   .tl_k
        move.w  d1,(a0)+
        move.l  12(a2),(a0)+            ; fault word
        move.b  32+16(a2),(a0)+         ; pantalla
        move.b  32+20(a2),(a0)+         ; Guillermo x
        move.b  32+21(a2),(a0)+         ; y
        move.b  32+22(a2),(a0)+         ; height
        move.b  32+23(a2),(a0)+         ; orientation
        move.b  32+44(a2),(a0)+         ; abbot x
        move.b  32+45(a2),(a0)+         ; abbot y
        moveq   #0,d1
        tst.b   poll_dead
        beq.s   .tl_f1
        bset    #0,d1
.tl_f1:
        tst.b   qs_present
        beq.s   .tl_f2
        bset    #1,d1
.tl_f2:
        move.b  d1,(a0)+
        move.l  poll_count,(a0)+
        move.w  silence_max,(a0)+
        move.w  beep_count+2,(a0)+      ; BEEPs issued so far
        addq.w  #1,log_count
        moveq   #LOG_FLUSH-1,d0
        and.w   log_count,d0
        bne.s   .tl_noflush
        bsr.s   log_write
.tl_noflush:
        movem.l (sp)+,d2-d7/a2-a5
.tl_out:
        rts

; ------------------------------------------------------------
; test_flush: main_exit calls it, so the last records reach the file
; ------------------------------------------------------------
test_flush:
        btst    #TF_LOG,ql_hdr+30
        beq.s   .tf_out
        tst.w   log_count
        beq.s   .tf_out
        movem.l d2-d7/a2-a5,-(sp)
        bsr.s   log_write
        movem.l (sp)+,d2-d7/a2-a5
.tf_out:
        rts

; log_write: rewrite the whole log file; the frames it takes are added to
; log_io_frames so that the records' frame counts leave them out
log_write:
        move.l  ql_hdr+20,-(sp)
        moveq   #0,d0
        move.w  log_count,d0
        lsl.l   #5,d0
        move.l  d0,-(sp)
        pea     log_buf
        pea     ql_hdr+SCRIPT_OFF+4     ; QDOS name
        bsr     file_rewrite
        lea     12(sp),sp
        move.l  ql_hdr+20,d0
        sub.l   (sp)+,d0
        add.l   d0,log_io_frames
        rts

; ------------------------------------------------------------
; int file_rewrite(qdos_name *name, const u8 *buf, int len)
; delete + open new + write + close; returns bytes written or -1.
; The channel is kept in A5 (QDOS keeps only D4-D7/A4-A6).
; ------------------------------------------------------------
file_rewrite:
        movem.l d2-d4/a2-a5,-(sp)       ; 28 bytes -> args at 32
        move.l  32(sp),a3               ; name (A3 is reloaded from the stack after traps)
        move.l  36(sp),a4               ; buffer
        move.l  40(sp),d4               ; length
        moveq   #IO_DELET,d0
        moveq   #-1,d1
        move.l  32(sp),a0
        bsr     do_trap2
        moveq   #IO_OPEN,d0
        moveq   #-1,d1
        moveq   #2,d3                   ; new file
        move.l  32(sp),a0
        bsr     do_trap2
        tst.l   d0
        bne.s   .fr_err
        move.l  a0,a5
        moveq   #IO_SSTRG,d0
        move.l  d4,d2
        moveq   #-1,d3
        move.l  a4,a1
        bsr     do_trap3
        move.l  d1,d4
        move.l  a5,a0
        moveq   #IO_CLOSE,d0
        bsr     do_trap2
        move.l  d4,d0
        bra.s   .fr_out
.fr_err:
        moveq   #-1,d0
.fr_out:
        movem.l (sp)+,d2-d4/a2-a5
        rts

        section .bss,bss
        cnop    0,4
poll_count:
        ds.l    1
log_io_frames:
        ds.l    1
last_step_frames:
        ds.l    1
silence_max:
        ds.w    1
silence_now:
        ds.w    1
log_count:
        ds.w    1
        ds.w    1
log_buf:
        ds.b    LOG_RECORDS*32
        section .text.start,code
        endif                           ; RELEASE

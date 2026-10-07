; ============================================================
; rel_main.s - the RELEASE executable: a QDOS job that unpacks the game and runs it
; La Abadia del Crimen - QL Port (build_release.sh; docs/release.md)
; ============================================================
; File = this stub + the aPLib-packed release image (abadia_r_bin: the game linked at 0 plus its
; relocation table, tools/mkimage.py). EXEC/EXEC_W loads the whole file at the job's base and
; gives it DATASPACE bytes more (the QDOS file header, set by build_release.sh), so the job's
; area is: [stub][packed image][dataspace ...][QDOS stack, A7 at entry].
;
;   1. the packed image moves up, to the end of where the game's BSS will be (backwards copy:
;      the regions may overlap), so the game can unpack where the packed data was;
;   2. aPLib unpacks it to DEST (just after this stub): nothing is written past the packed data
;      (DEST + image <= its new place, checked below), the BSS clear later wipes the packed copy;
;   3. the settings block (+16, patched in the FILE by tools/relpatch.py) goes into the image
;      header: +28 sound mode, +31 flags, +1312 the save file name;
;   4. JSR to the image (+0 bra.w _start_real): it relocates itself, clears its BSS, runs on its
;      own stack and returns when ESC quits (poll unlinked, channel closed, auto-repeat back);
;   5. MT.FRJOB of this job: QDOS frees the whole area (code, image, BSS) and any channel.
; The image never knows it is a job: it is entered exactly as SuperBASIC's CALL enters it.
;
; Assembled by build_release.sh with vasm -Fbin -DIMAGE_LEN=.. -DNEED=.. (mkimage.py's RESPR
; figure: max(image + relocation table, image + BSS)), -I build/rel (abadia_r.apl).
; ============================================================

MT_FRJOB        equ 5
ERR_OM          equ -3                  ; out of memory
ERR_BP          equ -15                 ; bad parameter (the image is not the game)
STACK_KEEP      equ 1024                ; below A7: QDOS's job stack + the game's register save

        org     0
base:
        bra.w   start                   ; +0
        dc.w    0                       ; +4
        dc.w    $4AFB                   ; +6 job header tag
        dc.w    6                       ; +8 job name
        dc.b    "ABADIA"
; +16: settings, at fixed offsets in the FILE (tools/relpatch.py; docs/release.md)
cfg:
        dc.b    "ABCF"                  ; +16 tag
cfg_sound:
        dc.b    0                       ; +20 -> image +28: 0 detect QSound, 1 off, 2 force it
cfg_flags:
        dc.b    0                       ; +21 -> image +31: bit 1 skip the intro (others 0)
cfg_name:
        dc.w    0                       ; +22 -> image +1312: the start-up save device (up to its first _);
        ds.b    40                      ; empty: MDV1_ (unless the settings file abadia_cfg says otherwise)
cfg_end:                                ; +64

start:
        lea     dest(pc),a4             ; A4 = where the game goes
        ; enough room? (QDOS gave the job DATASPACE; a patched header could give less)
        move.l  a4,d0
        add.l   #NEED+STACK_KEEP,d0
        cmp.l   sp,d0
        bhi.s   .no_room
        ; 1. the packed image to the top of the BSS area, copied backwards, longs (both even)
        move.l  #packed_end-dest+3,d0
        lsr.l   #2,d0                   ; longs to copy (a few bytes past the end are harmless)
        move.l  d0,d1
        lsl.l   #2,d1
        lea     0(a4,d1.l),a0           ; source end
        move.l  a4,a1
        add.l   #NEED,a1                ; destination end = DEST + NEED (even: NEED is even)
        move.l  a1,a2
        sub.l   d1,a2                   ; A2 = the packed image's new place
.mv:    move.l  -(a0),-(a1)
        subq.l  #1,d0
        bne.s   .mv
        ; 2. unpack it to DEST
        move.l  a2,a0
        move.l  a4,a1
        bsr     apl_decompress
        cmp.l   #$4142514C,4(a4)        ; "ABQL" (qlstart.s)
        bne.s   .not_game
        ; 3. the settings into the image header
        move.b  cfg_sound(pc),28(a4)
        move.b  cfg_flags(pc),31(a4)
        lea     cfg_name(pc),a0
        lea     1312(a4),a1
        moveq   #42/2-1,d0
.nm:    move.w  (a0)+,(a1)+
        dbra    d0,.nm
        ; 4. the game (returns when ESC quits)
        jsr     (a4)
        moveq   #0,d3
        bra.s   .quit
.no_room:
        moveq   #ERR_OM,d3
        bra.s   .quit
.not_game:
        moveq   #ERR_BP,d3
.quit:
        ; 5. remove this job: everything it owns is freed
        moveq   #MT_FRJOB,d0
        moveq   #-1,d1
        trap    #1
.hang:  bra.s   .hang                   ; (not reached)

        include "unaplib_68000.s"       ; Emmanuel Marty, zlib licence (unchanged)

        cnop    0,4
dest:                                   ; the game is unpacked here (over the packed data)
packed:
        incbin  "abadia_r.apl"
packed_end:
        even

; the packed data must be moved up past the unpacked image: DEST + image <= DEST + NEED - packed
        if      (packed_end-packed+4)>(NEED-IMAGE_LEN)
        fail    "the packed image does not fit between the unpacked image and the end of the BSS"
        endif

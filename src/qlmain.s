; ============================================================
; qlmain.s - top level of the HYBRID build (asm platform + compiled C++)
; La Abadia del Crimen - QL Port
; ============================================================
; Build: bash build_hybrid.sh  (vasm -Felf + m68k-linux-gnu-g++ + ld,
; then tools/mkimage.py appends the relocation table).
;
; The old all-asm room viewer (main.s, build.sh) is unchanged. Modules that
; the C++ logic replaces are NOT included here (character.s, height.s,
; height_data.s, screen_change.s, sprite.s, rooms.s ...) - the files stay in
; the repository.
; ============================================================

        include "equates.s"

        ifnd    BUILD_ID
BUILD_ID        equ 0
        endif

        include "qlstart.s"
        include "qlhooks.s"
        include "libgcc68k.s"
        include "kernels.s"
        include "routes.s"
        include "gen.s"
        include "grid.s"
        include "tiles.s"
        include "colour.s"
        include "strip.s"
        include "qltest.s"
        include "screen.s"
; tile_data.s is no longer assembled: build_tiles (qlhooks.s) makes the same
; data at run time for whichever palette is active (checked identical for day)

; ------------------------------------------------------------
; VIGASOCO "romsPtr" image (0x24000 bytes, built by tools/mkroms.py from the
; CPC disk image). Writable: the game generates flipped graphics into it.
; ------------------------------------------------------------
        section .data,data
        xdef    rom_image
        cnop    0,4
rom_image:
        ifd     RELEASE                 ; release build (build_release.sh): the conservative trim
        ifd     ENGLISH_ONLY            ; (IDIOMA=1: also the CPC's Spanish parchment texts zeroed,
        incbin  "../build/roms_trim_en.bin"     ; romtrim.py --english)
        else
        incbin  "../build/roms_trim.bin"        ; (tools/romtrim.py, docs/compression.md): same layout
        endif
        else
        incbin  "../build/roms.bin"
        endif
        even

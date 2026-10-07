; ============================================================
; buffer.s - Offscreen buffer management
; La Abadia del Crimen - QL Port
; ============================================================
; Routines: clear_iso_buffer, copy_buffer_to_screen
;
; Double-buffering: room tiles are rendered into ISO_BUFFER
; ($45000, 256x160 pixels = 20480 bytes), then blitted to the
; visible screen in one pass. This avoids flicker during the
; tile-by-tile rendering loop in render_room.
;
; ISO_STRIDE = SCREEN_STRIDE = 128 bytes, so the blit is a
; straight sequential copy (no stride conversion needed).
; Destination = SCREEN_BASE + VP_Y * SCREEN_STRIDE (offset by
; VP_Y=24 pixels to leave room for the title bar).

; ============================================================
; clear_iso_buffer - Fill buffer with a solid colour
; Entry: D0.W = colour word (e.g. COL_BLACK)
; Trashes: D0-D1/A0
; ============================================================
clear_iso_buffer:
        move.w  d0,d1
        swap    d1
        move.w  d0,d1               ; D1.L = colour | colour
        lea     ISO_BUFFER,a0
        move.w  #(ISO_SIZE/4)-1,d0  ; longword count
.cib_loop:
        move.l  d1,(a0)+
        dbra    d0,.cib_loop
        rts

; ============================================================
; copy_buffer_to_screen - Blit buffer to screen
; ISO_STRIDE = SCREEN_STRIDE = 128, so straight block copy.
; Dest = SCREEN_BASE + VP_Y * SCREEN_STRIDE
; Trashes: D0/A0-A1
; ============================================================
copy_buffer_to_screen:
        lea     ISO_BUFFER,a0
        lea     SCREEN_BASE+(VP_Y*SCREEN_STRIDE),a1
        move.w  #(ISO_SIZE/4)-1,d0
.cbs_loop:
        move.l  (a0)+,(a1)+
        dbra    d0,.cbs_loop
        rts

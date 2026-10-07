; ============================================================
; main.s - Entry point for La Abadia del Crimen (QL Port)
; Milestone 11f: Main Loop Assembly
; ============================================================
; Raw 68000 binary loaded via LBYTES+CALL (no QDOS header).
; org 0, all data/code refs PC-relative. RTS returns to BASIC.
;
; Build: vasmm68k_mot -Fbin -m68000 -no-opt -o abadia.bin main.s
; Load:  LBYTES flp1_abadia_bin,131072 : CALL 131072
;
; Main loop structure (from DEVPLAN M11f):
;   game_init -> title_screen -> game_round_setup -> main_loop
;   main_loop: input -> time -> AI -> script -> screen ->
;              doors/objects -> render -> sync -> death -> loop
; ============================================================

        include "equates.s"

        org     0

; ============================================================
; start - Entry point
; ============================================================
start:
        bsr     game_init
        bsr     title_screen
        bsr     game_round_setup
        bra     main_loop

; ============================================================
; game_init - One-time initialisation
; Set display mode, init all subsystems.
; ============================================================
game_init:
        ; Set MODE 8
        moveq   #MT_DMODE,d0
        moveq   #8,d1               ; MODE 8
        moveq   #-1,d2              ; clear screen
        trap    #1

        ; Clear screen to black
        move.w  #COL_BLACK,d0
        bsr     clear_screen

        ; Initialise room data pointer (room_data_base may be >32KB away)
        bsr     init_room_data

        ; Initialise height data pointer (height_data_base also >32KB away)
        bsr     init_height_data

        ; Initialise isometric engine
        bsr     init_iso_engine

        ; Initialise input system (persistent con_ channel)
        bsr     init_input
        rts

; ============================================================
; title_screen - Show title and wait for SPACE
; ============================================================
title_screen:
        move.w  #COL_BLACK,d0
        bsr     clear_screen

        lea     str_game_title(pc),a0
        move.w  #16,d0
        move.w  #80,d1
        move.w  #COL_YELLOW,d2
        bsr     draw_string

        lea     str_game_sub(pc),a0
        move.w  #48,d0
        move.w  #100,d1
        move.w  #COL_WHITE,d2
        bsr     draw_string

        lea     str_start(pc),a0
        move.w  #40,d0
        move.w  #140,d1
        move.w  #COL_GREEN,d2
        bsr     draw_string

        ; Wait for SPACE key
.ts_wait:
        bsr     scan_keys
        moveq   #KEY_SPACE,d0
        bsr     check_key_edge
        bne.s   .ts_done

        ; Also accept ENTER
        moveq   #KEY_ENTER,d0
        bsr     check_key_edge
        bne.s   .ts_done

        ; Frame pace
        moveq   #MT_SUSJB,d0
        moveq   #-1,d1
        moveq   #1,d3
        trap    #1
        bra.s   .ts_wait

.ts_done:
        rts

; ============================================================
; game_round_setup - Prepare for a new game round
; Reset character, load starting room, initial render.
; ============================================================
game_round_setup:
        ; Reset character to starting position
        bsr     init_guillermo

        ; Clear quit flag
        lea     quit_flag(pc),a0
        clr.b   (a0)

        ; Clear redraw flags
        lea     needs_full_redraw(pc),a0
        move.b  #1,(a0)                 ; force initial full redraw

        ; Load starting room (room 36 - abbey church)
        moveq   #36,d0
        bsr     load_room
        bcs.s   .grs_no_room
        bsr     update_room_position
        bsr     load_height_data
        rts

.grs_no_room:
        ; Fallback: try room 2
        moveq   #2,d0
        bsr     load_room
        bsr     update_room_position
        bsr     load_height_data
        rts

; ============================================================
; main_loop - Core game loop (runs until ESC)
;
; Structure matches DEVPLAN M11f:
;   1. Input processing
;   2. Time update (stub)
;   3. AI update (stub)
;   4. Script engine (stub)
;   5. Screen change check
;   6. Door/object update (stub)
;   7. Rendering
;   8. Frame sync
;   9. Death check (stub)
; ============================================================
main_loop:

        ; ---- 1. Input processing ----
        bsr     scan_keys
        bsr     process_guillermo_input
        bsr     check_game_keys

        ; Check if quit requested
        move.b  quit_flag(pc),d0
        bne     clean_exit

        ; ---- 2. Time update (stub - M11b) ----
        ; bsr   update_time_system
        ; bsr   check_day_advance

        ; ---- 3. AI update (stub - M9) ----
        ; bsr   move_adso
        ; bsr   move_malaquias
        ; bsr   move_abbot
        ; bsr   move_berengario
        ; bsr   move_severino

        ; ---- 4. Script engine (stub - M12) ----
        ; bsr   script_engine_tick

        ; ---- 5. Screen change check ----
        move.b  screen_changed(pc),d0
        beq.s   .no_screen_change
        lea     screen_changed(pc),a0
        clr.b   (a0)
        lea     char_moved(pc),a0
        clr.b   (a0)
        lea     needs_full_redraw(pc),a0
        move.b  #1,(a0)
.no_screen_change:

        ; ---- 6. Door/object update (stub - M11a) ----
        ; bsr   update_doors
        ; bsr   update_objects

        ; ---- 7. Rendering ----
        ; Full redraw: room changed or first frame
        move.b  needs_full_redraw(pc),d0
        bne.s   .do_full_redraw

        ; Partial redraw: character moved within room
        move.b  char_moved(pc),d0
        bne.s   .do_partial_redraw

        bra.s   .render_done

.do_full_redraw:
        lea     needs_full_redraw(pc),a0
        clr.b   (a0)
        lea     char_moved(pc),a0
        clr.b   (a0)
        bsr     render_frame
        bra.s   .render_done

.do_partial_redraw:
        lea     char_moved(pc),a0
        clr.b   (a0)
        bsr     render_frame

.render_done:

        ; ---- 8. Frame sync ----
        ; CPC game: 7 poll ticks (140ms). Using 1 tick (20ms) for
        ; responsiveness during development. Adjust to 7 for CPC speed.
        moveq   #MT_SUSJB,d0
        moveq   #-1,d1              ; this job
        moveq   #FRAME_TICKS,d3     ; ticks per frame
        trap    #1

        ; ---- 9. Death check (stub - M11c) ----
        ; bsr   check_guillermo_death
        ; bne   game_over

        bra     main_loop

; ============================================================
; clean_exit - Shut down and return to BASIC
; ============================================================
clean_exit:
        bsr     close_input
        rts

; ============================================================
; check_game_keys - Handle ESC, debug controls (+/-/T)
; Sets quit_flag on ESC. Handles room viewer keys.
; Trashes: D0-D3/A0
; ============================================================
check_game_keys:
        ; ESC = quit
        moveq   #KEY_ESC,d0
        bsr     check_key_edge
        bne.s   .cgk_quit

        ; SPACE = force redraw (debug)
        moveq   #KEY_SPACE,d0
        bsr     check_key_edge
        bne.s   .cgk_force_redraw

        ; Debug room viewer controls (+/-/T)
        move.b  last_raw_key(pc),d1
        beq.s   .cgk_done

        cmp.b   #'+',d1
        beq.s   .cgk_next_room
        cmp.b   #'=',d1
        beq.s   .cgk_next_room
        cmp.b   #'-',d1
        beq.s   .cgk_prev_room
        cmp.b   #'t',d1
        beq.s   .cgk_test_room
        cmp.b   #'T',d1
        beq.s   .cgk_test_room
        bra.s   .cgk_done

.cgk_quit:
        lea     quit_flag(pc),a0
        move.b  #1,(a0)
        rts

.cgk_force_redraw:
        lea     needs_full_redraw(pc),a0
        move.b  #1,(a0)
        rts

.cgk_test_room:
        bsr     load_test_room
        bsr     load_height_data
        lea     needs_full_redraw(pc),a0
        move.b  #1,(a0)
        rts

.cgk_next_room:
        move.w  current_room_id(pc),d0
        addq.w  #1,d0
        cmp.w   #ROOM_COUNT,d0
        blt.s   .cgk_try
        moveq   #0,d0
        bra.s   .cgk_try

.cgk_prev_room:
        move.w  current_room_id(pc),d0
        subq.w  #1,d0
        bge.s   .cgk_try
        move.w  #ROOM_COUNT-1,d0

.cgk_try:
        bsr     load_room
        bcs.s   .cgk_done               ; invalid room, skip
        bsr     update_room_position
        bsr     load_height_data
        lea     needs_full_redraw(pc),a0
        move.b  #1,(a0)

.cgk_done:
        rts

; ============================================================
; render_frame - Full frame render
; Clears screen, draws room, sprites, and HUD.
; Trashes: D0-D7/A0-A5
; ============================================================
render_frame:
        ; Clear screen
        move.w  #COL_BLACK,d0
        bsr     clear_screen

        ; Title bar
        lea     str_milestone(pc),a0
        moveq   #8,d0
        moveq   #4,d1
        move.w  #COL_YELLOW,d2
        bsr     draw_string

        ; Render isometric room view (to buffer, then blit)
        ; Sprite is drawn into buffer by render_iso_view (M7c depth sort)
        bsr     render_iso_view

        ; HUD
        bsr     draw_dir_hud
        bsr     show_room_id

        ; Controls prompt
        lea     str_controls(pc),a0
        moveq   #8,d0
        move.w  #192,d1
        move.w  #COL_WHITE,d2
        bsr     draw_string
        rts

; ============================================================
; show_room_id - Display current room number and diagnostics
; Trashes: D0-D3/A0
; ============================================================
show_room_id:
        ; Draw "ROOM:" label
        lea     str_room(pc),a0
        moveq   #8,d0
        move.w  #16,d1
        move.w  #COL_GREEN,d2
        bsr     draw_string

        ; Convert room ID to 2-digit decimal string
        move.w  current_room_id(pc),d0
        bmi.s   .sri_test

        lea     str_room_num(pc),a0
        moveq   #0,d1
.sri_tens:
        cmp.w   #10,d0
        blt.s   .sri_units
        sub.w   #10,d0
        addq.w  #1,d1
        bra.s   .sri_tens
.sri_units:
        add.b   #'0',d1
        move.b  d1,(a0)+
        add.b   #'0',d0
        move.b  d0,(a0)+
        clr.b   (a0)
        bra.s   .sri_draw_num

.sri_test:
        lea     str_room_num(pc),a0
        move.b  #'T',(a0)+
        move.b  #'T',(a0)+
        clr.b   (a0)

.sri_draw_num:
        lea     str_room_num(pc),a0
        move.w  #56,d0
        move.w  #16,d1
        move.w  #COL_WHITE,d2
        bsr     draw_string

        ; Tile count "T:nnn"
        lea     str_tcnt(pc),a0
        move.w  #96,d0
        move.w  #16,d1
        move.w  #COL_GREEN,d2
        bsr     draw_string

        move.w  last_tile_count(pc),d0
        lea     str_tcnt_num(pc),a0
        moveq   #0,d1
.sri_h:
        cmp.w   #100,d0
        blt.s   .sri_t2
        sub.w   #100,d0
        addq.w  #1,d1
        bra.s   .sri_h
.sri_t2:
        add.b   #'0',d1
        move.b  d1,(a0)+
        moveq   #0,d1
.sri_t3:
        cmp.w   #10,d0
        blt.s   .sri_u2
        sub.w   #10,d0
        addq.w  #1,d1
        bra.s   .sri_t3
.sri_u2:
        add.b   #'0',d1
        move.b  d1,(a0)+
        add.b   #'0',d0
        move.b  d0,(a0)+
        clr.b   (a0)

        lea     str_tcnt_num(pc),a0
        move.w  #112,d0
        move.w  #16,d1
        move.w  #COL_WHITE,d2
        bsr     draw_string

        ; Height "H:NN"
        lea     str_height(pc),a0
        move.w  #200,d0
        move.w  #16,d1
        move.w  #COL_GREEN,d2
        bsr     draw_string

        lea     guillermo(pc),a0
        moveq   #0,d0
        move.b  CHR_HEIGHT(a0),d0

        lea     str_height_num(pc),a0
        moveq   #0,d1
.sri_ht:
        cmp.w   #10,d0
        blt.s   .sri_hu
        sub.w   #10,d0
        addq.w  #1,d1
        bra.s   .sri_ht
.sri_hu:
        add.b   #'0',d1
        move.b  d1,(a0)+
        add.b   #'0',d0
        move.b  d0,(a0)+
        clr.b   (a0)

        lea     str_height_num(pc),a0
        move.w  #216,d0
        move.w  #16,d1
        move.w  #COL_WHITE,d2
        bsr     draw_string
        rts

; ============================================================
; Game state variables
; ============================================================
quit_flag:
        dc.b    0
needs_full_redraw:
        dc.b    0
        even

; ============================================================
; String data
; ============================================================
str_game_title:
        dc.b    "LA ABADIA DEL CRIMEN",0
str_game_sub:
        dc.b    "QL PORT - 2025",0
str_start:
        dc.b    "PRESS SPACE TO START",0
str_milestone:
        dc.b    "M7D OCCLUSION",0
str_controls:
        dc.b    "+/- ROOM  T TEST  ARROWS MOVE  ESC QUIT",0
str_no_room:
        dc.b    "NO ROOM DATA",0
str_room:
        dc.b    "ROOM:",0
str_room_num:
        dc.b    "00",0
str_tcnt:
        dc.b    "T:",0
str_tcnt_num:
        dc.b    "000",0
str_height:
        dc.b    "H:",0
str_height_num:
        dc.b    "00",0
        even

; ============================================================
; Include modules
; Order matters for 68000 PC-relative addressing (16-bit signed
; displacement, max +-32KB). Code modules grouped together;
; large data (tile_data, room_data) placed at end.
;
; PC-relative constraints:
;   rooms.s  <-> room_ptrs.s  (load_room refs room_ptr_table)
;   iso.s    <-> tile_data.s  (render_tile_at refs tile_data)
;   rooms.s  --> room_data.s  via stored pointer (>32KB away)
;   sprite.s <-> sprite_data.s (draw_guillermo_sprite refs gfx/mask)
; ============================================================
        include "screen.s"
        include "text.s"
        include "font.s"
        include "buffer.s"
        include "input.s"
        include "character.s"
        include "sprite_data.s"
        include "sprite.s"
        include "height.s"
        include "rooms.s"
        include "room_ptrs.s"
        include "screen_change.s"
        include "iso_data.s"
        include "iso.s"
        include "tile_data.s"
        include "room_data.s"
        include "height_data.s"

; ============================================================
; iso_data.s - Test room data + rendering workspace
; La Abadia del Crimen - QL Port
; ============================================================
; Contains:
;   test_room_objects - M5 hardcoded 3D test scene (iso_project)
;   test_room_grid    - Tile atlas diagnostic (320-byte grid)
;   sort_buffer       - Workspace for depth sorting (2048 bytes)

; ============================================================
; test_room_objects - Hardcoded M5 isometric test scene
; Format: dc.w x3d, y3d, z3d, tile_index
; Terminated by dc.w $FFFF
;
; Used by render_test_room (iso.s) with iso_project for true
; 3D isometric rendering. This is separate from the CPC room
; pipeline — it tests the tile blitter with known positions.
;
; 4x4 floor grid + wall segments, 8 units per grid step.
; Floor at Y=0, walls at Y=8 (height offset).
;
; Tile indices (from ABADIA3.BIN / tile_data.s):
;   1 = diamond border pattern (floor)
;   2 = diagonal texture left
;   3 = diagonal texture right
;   4 = arch/column detail
;   5 = cross/window pattern
; ============================================================

test_room_objects:
        ; --- Floor tiles (Y=0) ---
        ; Row z=0
        dc.w    0,0,0,1
        dc.w    8,0,0,2
        dc.w    16,0,0,2
        dc.w    24,0,0,3
        ; Row z=8
        dc.w    0,0,8,2
        dc.w    8,0,8,1
        dc.w    16,0,8,1
        dc.w    24,0,8,2
        ; Row z=16
        dc.w    0,0,16,2
        dc.w    8,0,16,1
        dc.w    16,0,16,1
        dc.w    24,0,16,2
        ; Row z=24
        dc.w    0,0,24,3
        dc.w    8,0,24,2
        dc.w    16,0,24,2
        dc.w    24,0,24,1

        ; --- North wall (z=0, raised by Y=8) ---
        dc.w    0,8,0,4
        dc.w    8,8,0,5
        dc.w    16,8,0,5
        dc.w    24,8,0,4

        ; --- West wall (x=0, raised by Y=8) ---
        dc.w    0,8,8,4
        dc.w    0,8,16,5
        dc.w    0,8,24,4

        ; Terminator
        dc.w    $FFFF

        even

; ============================================================
; test_room_grid - Tile atlas diagnostic (320 bytes)
; Shows ALL 256 tiles in index order: rows 0-15 = tile atlas,
; rows 16-19 = common room tiles for comparison.
; Press 'T' in main loop to display.
;
; Layout:
;   Row 0:  tiles $00..$0F  (tile 0 = empty/black)
;   Row 1:  tiles $10..$1F
;   ...
;   Row 15: tiles $F0..$FF
;   Row 16: tiles $02,$04,$06,$08,$0A,$0C,$0E,$10 (room types)
;            + $12,$14,$16,$18,$1A,$1C,$1E,$20
;   Row 17: tiles $22,$24,$26,$28,$2A,$2C,$2E,$30
;            + $32,$34,$36,$38,$3A,$3C,$3E,$40
;   Row 18: 16x tile $09 (a common room floor tile)
;   Row 19: 16x tile $0F (a common room wall tile)
;
; Expected T: 255 (atlas, tile 0 empty) + 32 + 16 + 16 = 319
; (only tile $00 at row0/col0 is empty)
; ============================================================
test_room_grid:
        ;          col: 0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F
        dc.b    $00,$01,$02,$03,$04,$05,$06,$07,$08,$09,$0A,$0B,$0C,$0D,$0E,$0F  ; row 0: tiles $00-$0F
        dc.b    $10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$1A,$1B,$1C,$1D,$1E,$1F  ; row 1: tiles $10-$1F
        dc.b    $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$2A,$2B,$2C,$2D,$2E,$2F  ; row 2: tiles $20-$2F
        dc.b    $30,$31,$32,$33,$34,$35,$36,$37,$38,$39,$3A,$3B,$3C,$3D,$3E,$3F  ; row 3: tiles $30-$3F
        dc.b    $40,$41,$42,$43,$44,$45,$46,$47,$48,$49,$4A,$4B,$4C,$4D,$4E,$4F  ; row 4: tiles $40-$4F
        dc.b    $50,$51,$52,$53,$54,$55,$56,$57,$58,$59,$5A,$5B,$5C,$5D,$5E,$5F  ; row 5: tiles $50-$5F
        dc.b    $60,$61,$62,$63,$64,$65,$66,$67,$68,$69,$6A,$6B,$6C,$6D,$6E,$6F  ; row 6: tiles $60-$6F
        dc.b    $70,$71,$72,$73,$74,$75,$76,$77,$78,$79,$7A,$7B,$7C,$7D,$7E,$7F  ; row 7: tiles $70-$7F
        dc.b    $80,$81,$82,$83,$84,$85,$86,$87,$88,$89,$8A,$8B,$8C,$8D,$8E,$8F  ; row 8: tiles $80-$8F
        dc.b    $90,$91,$92,$93,$94,$95,$96,$97,$98,$99,$9A,$9B,$9C,$9D,$9E,$9F  ; row 9: tiles $90-$9F
        dc.b    $A0,$A1,$A2,$A3,$A4,$A5,$A6,$A7,$A8,$A9,$AA,$AB,$AC,$AD,$AE,$AF  ; row 10: tiles $A0-$AF
        dc.b    $B0,$B1,$B2,$B3,$B4,$B5,$B6,$B7,$B8,$B9,$BA,$BB,$BC,$BD,$BE,$BF  ; row 11: tiles $B0-$BF
        dc.b    $C0,$C1,$C2,$C3,$C4,$C5,$C6,$C7,$C8,$C9,$CA,$CB,$CC,$CD,$CE,$CF  ; row 12: tiles $C0-$CF
        dc.b    $D0,$D1,$D2,$D3,$D4,$D5,$D6,$D7,$D8,$D9,$DA,$DB,$DC,$DD,$DE,$DF  ; row 13: tiles $D0-$DF
        dc.b    $E0,$E1,$E2,$E3,$E4,$E5,$E6,$E7,$E8,$E9,$EA,$EB,$EC,$ED,$EE,$EF  ; row 14: tiles $E0-$EF
        dc.b    $F0,$F1,$F2,$F3,$F4,$F5,$F6,$F7,$F8,$F9,$FA,$FB,$FC,$FD,$FE,$FF  ; row 15: tiles $F0-$FF
        dc.b    $02,$04,$06,$08,$0A,$0C,$0E,$10,$12,$14,$16,$18,$1A,$1C,$1E,$20  ; row 16: even types
        dc.b    $22,$24,$26,$28,$2A,$2C,$2E,$30,$32,$34,$36,$38,$3A,$3C,$3E,$40  ; row 17: even types cont
        dc.b    $09,$09,$09,$09,$09,$09,$09,$09,$09,$09,$09,$09,$09,$09,$09,$09  ; row 18: tile $09 x16
        dc.b    $0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F,$0F  ; row 19: tile $0F x16
        dc.w    0               ; overlay count (none for test grid)

; ============================================================
; sort_buffer - Workspace for depth sorting (M5 test scene)
; Max 256 objects x 8 bytes (x3d, y3d, z3d, tile) = 2048 bytes.
; Used by sort_objects + render_test_room in iso.s.
; Not used by the CPC room renderer (rooms.s) which places
; tiles at non-overlapping rectangular grid positions.
; ============================================================
sort_buffer:
        ds.b    2048

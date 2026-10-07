; ============================================================
; equates.s - Hardware constants for Sinclair QL (Mode 8)
; La Abadia del Crimen - QL Port
; ============================================================
; EQU-only file - no binary output. Include before org.
;
; QL Mode 8 pixel format: interleaved G/F bits per byte.
; Each word encodes 4 pixels, each pixel = 2 bits green + 2 bits flash.
; Byte layout: G3 F3 G2 F2 G1 F1 G0 F0 (high byte = green, low = flash).
; The green/flash bit pairs select one of 8 colours per pixel.

; --- Screen layout (Mode 8: 256x256, 8 colours) ---
SCREEN_BASE     equ $20000          ; start of QL display RAM
SCREEN_SIZE     equ 32768           ; 256 lines * 128 bytes = 32KB
SCREEN_STRIDE   equ 128             ; bytes per scanline (256px / 4px * 2 bytes)
SCREEN_WIDTH    equ 256             ; pixels per line
SCREEN_HEIGHT   equ 256             ; total scanlines

; --- Mode 8 colour constants (word values) ---
; Each word fills 4 identical pixels. AND with a pixel mask
; to isolate specific pixel positions within the word.
COL_BLACK       equ $0000
COL_BLUE        equ $0055
COL_RED         equ $00AA
COL_MAGENTA     equ $00FF
COL_GREEN       equ $AA00
COL_CYAN        equ $AA55
COL_YELLOW      equ $AAAA
COL_WHITE       equ $AAFF

; --- Per-pixel white masks (4 pixels per word) ---
; Used by screen.s pixel_masks LUT and text.s nibble_to_mask LUT.
; AND a colour word with a pixel mask to isolate that pixel position.
PMASK_PX0       equ $C0C0           ; pixel 0 (leftmost): bits 7,6
PMASK_PX1       equ $3030           ; pixel 1: bits 5,4
PMASK_PX2       equ $0C0C           ; pixel 2: bits 3,2
PMASK_PX3       equ $0303           ; pixel 3 (rightmost): bits 1,0

; --- Game viewport ---
; Offscreen buffer for double-buffered room rendering.
; Matches CPC game area: 16 tile columns * 16px = 256px wide,
; 20 tile rows * 8px = 160px tall. Buffer is blitted to screen
; by copy_buffer_to_screen in buffer.s.
ISO_BUFFER      equ $45000              ; offscreen buffer base (above screen RAM)
ISO_WIDTH       equ 256                 ; viewport width = 16 cols * 16px
ISO_HEIGHT      equ 160                 ; viewport height = 20 rows * 8px
ISO_STRIDE      equ 128                 ; bytes per row (same as screen stride)
ISO_SIZE        equ 20480              ; stride * height (128 * 160)
VP_X            equ 0                   ; viewport X on screen (left-aligned)
VP_Y            equ 24                  ; viewport Y on screen (below title bar)

; --- Room system ---
MAX_ROOM_OBJECTS equ 256            ; max tiles in sort buffer (M5 test scene)

; --- Tile data layout ---
; CPC has 256 tiles, 32 bytes each (4 bytes/row * 8 rows).
; QL tiles: 64 bytes each (8 bytes/row * 8 rows = 4 words/row).
; tile_data (graphics) followed by tile_masks at +TILE_DATA_SIZE.
TILE_DATA_SIZE  equ 256*64          ; 16384 bytes of tile graphics

; --- QDOS trap codes ---
MT_DMODE        equ $10             ; Set/read display mode (trap #1, D1=mode)
IO_OPEN         equ $01             ; Open channel (trap #2, A0=name)
IO_CLOSE        equ $02             ; Close channel (trap #2, A0=chanID)
IO_FBYTE        equ $01             ; Fetch byte (trap #3, A0=chanID, D3=timeout)
MT_SUSJB        equ $08             ; Suspend job (trap #1, D1=jobID, D3=timeout)

; --- Input system ---
KEY_UP          equ 0
KEY_DOWN        equ 1
KEY_LEFT        equ 2
KEY_RIGHT       equ 3
KEY_SPACE       equ 4
KEY_N           equ 5
KEY_ESC         equ 6
KEY_Q           equ 7
KEY_R           equ 8
KEY_ENTER       equ 9
KEY_COUNT       equ 10
HOLD_FRAMES     equ 5               ; frames key stays "held" after release (~100ms)

; --- QL key codes (from IO.FBYTE) ---
QL_KEY_UP       equ $D0
QL_KEY_DOWN     equ $D8
QL_KEY_LEFT     equ $C0
QL_KEY_RIGHT    equ $C8

; --- Character structure offsets ---
CHR_ANIM        equ 0               ; animation counter (bits 0-1: walk cycle)
CHR_ORIENT      equ 1               ; orientation (0=+X, 1=-Y, 2=-X, 3=+Y)
CHR_X           equ 2               ; position X (grid col 0-15)
CHR_Y           equ 3               ; position Y (grid row 0-19)
CHR_HEIGHT      equ 4               ; elevation (future M8a)
CHR_FLAGS       equ 5               ; movement flags
CHR_SIZE        equ 15              ; bytes per character record

; --- Orientation constants ---
ORIENT_PX       equ 0               ; +X (right)
ORIENT_MY       equ 1               ; -Y (up)
ORIENT_MX       equ 2               ; -X (left)
ORIENT_PY       equ 3               ; +Y (down)

; --- Sprite constants ---
GUIL_WIDTH      equ 5               ; words (20 pixels)
GUIL_HEIGHT     equ 34              ; rows per frame
GUIL_FRAME_SIZE equ 340             ; bytes per frame (5*34*2)

; --- Height visual offset ---
HEIGHT_BASE     equ 2               ; baseline floor height (most rooms)
HEIGHT_PX_STEP  equ 2               ; pixels per height unit above baseline
HEIGHT_UNSET    equ $FF             ; CHR_HEIGHT not yet known (0 is a real floor height)

; --- Movement timing ---
MOVE_DELAY      equ 4               ; frames between advances
FRAME_TICKS     equ 1               ; QDOS ticks per game frame (1=20ms=50Hz)

; CHARCOL 1: separate colours for characters and panel, 2x2 dithers (src/colour.s);
; 0 = the previous single mapping (qlhooks.s versions). MASK_OFF: the sprite mask's
; distance from the packed mixing buffer (inside the shared 8 KB buffer, whose
; first 2 KB the packed buffer uses).
CHARCOL         equ 1
MASK_OFF        equ 4096

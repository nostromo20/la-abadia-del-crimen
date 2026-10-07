/* ql_port.h -- the C interface between the compiled VIGASOCO logic and the platform.
 *
 * The same C++ is built twice:
 *   - for the QL (m68k-linux-gnu-g++, -m68000), where these hooks are implemented in asm
 *     (src/qlhooks.s) or in cpp/port/ql_platform.cpp;
 *   - natively on the PC (the oracle, cpp/host/), where they are implemented by
 *     cpp/host/host_platform.cpp.
 *
 * Coordinates are CPC screen coordinates (Mode 1, 320x200): the play area is x 32..287,
 * y 0..159; the score panel is y 160..199. Inks are CPC inks 0..3.
 */
#ifndef QL_PORT_H
#define QL_PORT_H

#ifdef __cplusplus
extern "C" {
#endif

/* ---- keys (restores VIGASOCO's losControles queries) ---- */
enum QlKeys {
	QK_UP = 0, QK_DOWN, QK_LEFT, QK_RIGHT, QK_SPACE, QK_Q, QK_R, QK_S, QK_N, QK_ESC,
	QK_F1, QK_F2, QK_F3, QK_F5, QK_Y,
	QK_COUNT
};
int ql_key_down(int key);          /* nonzero while the key is held */

/* ---- sound ---- */
void ql_sound(int id);             /* SOUNDFILES id */
void ql_music(int id);             /* MUSICFILES id, -1 = stop */
void ql_music_ready(void);         /* the parchment is up: the beeper tune's clock starts */
void ql_bgmusic(void);             /* QL_BEEPER: CPC 41AB call 1007 (background tune, QSound only) */

/* ---- play area (direct to the display; never read back) ---- */
void ql_play_fill(int x, int y, int w, int h, int ink);       /* CPC coords, clipped to play area */
void ql_play_pixel(int x, int y, int ink);
void ql_play_tile(int x, int y, int tile);                    /* x multiple of 4, CPC coords */
/* the room build's 16x8 cell (GeneradorPantallas::dibujaTira): pen 0, then tiles t0 and t1 on
   it (0 = none); x multiple of 16 */
void ql_play_cell(int x, int y, int t0, int t1);
void ql_play_black(void);          /* the whole play area QL black (= terrain pen 3) */
/* the CPC's room build (2026-10-05): black play area, then the cells from the centre outwards
   (GeneradorPantallas::dibujaBufferTiles). The dev build keeps the old one (pen 0 fill, row by
   row) for tools/spiraltest.py: header +30 bit 4 (ql_espiral_vieja); QL_NO_SPIRAL: always old */
/* QL_ASM_GEN (2026-10-06): the room generator's tile-drawing commands in asm (src/gen.s
   a_tile_mueve); the dev build keeps the C for tools/gentest.py: header +30 bit 5 (ql_gen_viejo) */
#if !defined(QL_ASM_GEN)
#define ql_gen_asm() 0
#elif defined(QL_RELEASE)
#define ql_gen_asm() 1
#else
int ql_gen_viejo(void);
#define ql_gen_asm() (!ql_gen_viejo())
#endif
#if defined(QL_NO_SPIRAL)
#define ql_espiral() 0
#elif defined(QL_RELEASE)
#define ql_espiral() 1
#else
int ql_espiral_vieja(void);
#define ql_espiral() (!ql_espiral_vieja())
#endif
/* QL_TILE_COMPOSE: tile number id's graphic in the tile table (roms 0x8300) changed: rebuild the
   QL's Mode 8 copy that ql_play_tile draws (host: nothing to do) */
void ql_tile_rebuild(int id);
/* QL_INTRO_DISSOLVE (screen.s): a parchment page composed off-screen in the tile graphics
   area (32 KB, unused while a parchment is up: the parchment palette builds no tiles), then
   dissolved onto the screen. ql_off_begin clears it (and, as palette 0, leaves nothing to
   recolour); fill/pixel take CPC coordinates and pens like ql_play_fill/ql_play_pixel */
void ql_off_begin(void);
void ql_off_fill(int x, int y, int w, int h, int ink);
void ql_off_pixel(int x, int y, int ink);
void ql_off_dissolve(void);
extern int ql_compose_on;	/* GeneradorPantallas.cpp: 1 = composition on */
/* parchment page turn: lines j < lado: x..x+j pen c1, then 4 pixels pen c2 (y < 200) */
void ql_play_triangle(int x, int y, int lado, int c1, int c2);
/* copy a byte-per-pixel ink buffer (as built by MezcladorSprites) to the play area */
void ql_play_blit(int x, int y, int w, int h, const unsigned char *src, int srcStride);
/* QL_PACKED_MIX: src = packed CPC bytes (4 pixels each), srcStride in bytes */
void ql_play_blit_p(int x, int y, int w, int h, const unsigned char *src, int srcStride);
/* QL_INTERLEAVE: the same from the interleaved mixing buffer (src = the first element, stride
   in elements; ql_kernels.h) */
void ql_play_blit_pi(int x, int y, int w, int h, const unsigned char *src, int srcStride);
/* QL_HGRID_CACHE (RejillaPantalla.cpp): the height-data generation. EVERY write into the CPC
   height tables (roms 0x18a00-0x190ff: the mirror room's entry) must bump it, so no cached
   height grid outlives the data it was made from. Writers: Logica::iniciaHabitacionEspejo,
   compruebaAbreEspejo, despHabitacionEspejo, qlHarnessAbreEspejo, Serializar (load). */
extern unsigned int ql_hgen;
#ifdef QL_HGRID_CACHE
#define QL_HGEN_BUMP() (ql_hgen++)
#else
#define QL_HGEN_BUMP() ((void)0)
#endif
/* harness (header +31 bit 6 on the QL, FORCE_MIRROR on the host): the mirror / save-load
   sequence at tick 3 (ql_game.cpp); bit 7: every cache hit verified against a fresh fill */
int ql_harness_mirror(void);
int ql_harness_hgverify(void);
#ifdef QL_CHARCOL
/* src/colour.s: 1 while the palette has separate character colours (the mixer keeps the
   sprite mask only then) */
extern unsigned char char_sep;
/* src/colour.s: 1 = the next ql_play_blit_p area holds no sprite pixel (plain copy) */
extern unsigned char ql_blit_plain;
/* ql_game.cpp: after a palette change, redraw what the recolour cannot tell apart (sprites,
   panel) */
void ql_palette_repaint(int pal);
#endif
void ql_set_palette(int pal);      /* 0 black, 1 parchment, 2 day, 3 night */

/* ---- score panel (CPC y 160..199): the port keeps a 320x40 ink buffer, the platform
 *      presents dirty rectangles of it with whatever 256 px layout is chosen ---- */
void ql_panel_present(int x, int y, int w, int h, const unsigned char *panel);
/* the panel's on-screen pixels of x..x+w-1, panel lines y..y+h-1, moved dx pixels left (as
   CPC6128::scrollPanelLeft moves the pens; x, w, dx multiples of 4, all of it within x 32..287;
   panel: the pens after the move, for a platform that presents them instead) */
void ql_panel_scroll(int x, int y, int w, int h, int dx, const unsigned char *panel);

/* ---- files (save/load): whole-file write/read, return bytes or -1 ---- */
int ql_file_save(const char *buf, int len);
int ql_file_load(char *buf, int cap);
/* src/strip.s: files on the chosen save device (ql_strip.cpp); name = a QDOS string (word length
   + characters) at an even address. They return bytes, or a QDOS error code (< 0). ql_fprobe:
   0 if the name opens (key 1: an existing file; key 4: a device's directory), else the error */
int ql_fsave(const void *name, const char *buf, int len);
int ql_fload(const void *name, char *buf, int cap);
int ql_fprobe(const void *name, int key);

/* ---- the text strip under the panel (QL lines 228-255; src/strip.s, ql_strip.cpp) ---- */
/* one QL line from 32 bytes of 1-bit pixels; colour 0-7 = a QL colour, 0x100 + p = the panel's
   text colour (pen 2) in CPC palette p */
void ql_strip_line(int qlline, const unsigned char *bits, int colour);
void ql_strip_clear(void);
/* qlstart.s: the header's save-name field (+1312, QDOS string): its device part, when set,
   is the start-up save device unless a settings file says otherwise */
extern unsigned short hdr_savename[];

/* ---- misc ---- */
void ql_debug(int code, int value);  /* harness trace point, no-op on a real QL */
void ql_phase(int phase);            /* diagnostic breadcrumb (shown by the heartbeat) */

/* entry points the platform calls */
void abadia_init(int intro);       /* creates the game objects; intro = start with the parchment */
void abadia_tick(void);            /* one 130 ms logic step + drawing */
void abadia_sync(void);            /* the fork's runSync: phrase scroller (once per tick) */
void abadia_state(unsigned char *blk);  /* fills the harness state block (STATE_SIZE bytes) */

#define STATE_SIZE 256

#ifdef __cplusplus
}
#endif

/* deterministic rand(), identical on host and QL (glibc TYPE_3 algorithm) */
#ifdef __cplusplus
extern "C" {
#endif
int ql_rand(void);
void ql_srand(unsigned int seed);
#ifdef __cplusplus
}
#endif

#endif

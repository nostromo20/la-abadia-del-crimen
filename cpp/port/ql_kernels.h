/* ql_kernels.h -- the pixel inner loops of the sprite mixer, as plain C functions.
 *
 * Each kernel has a C reference (ql_kernels.c, prefix c_) used by the PC oracle, and on
 * the QL an asm twin (src/kernels.s, prefix a_) that must produce byte-identical output;
 * tools/kerntest.py checks that on random and recorded inputs. QL_ASM_KERNELS selects the
 * asm versions for the QL build.
 *
 * Buffers hold one CPC pen (0-3) per byte, as VIGASOCO's mixing buffer does.
 */
#ifndef QL_KERNELS_H
#define QL_KERNELS_H

#ifdef __cplusplus
extern "C" {
#endif

/* combinaTile: one 16x8 CPC tile (32 bytes) into the mixing buffer.
 * transp = pen that is transparent, or -1 for an opaque tile (tiles < 0x0b) */
void c_combina_tile(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void a_combina_tile(unsigned char *dest, int destStride, const unsigned char *tile, int transp);

/* Sprite::dibuja inner loop: h rows of w CPC bytes (4 pixels each), pen 0 transparent */
void c_sprite_blit(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
void a_sprite_blit(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);

/* dest[i] &= mask for n bytes (BuscadorRutas::limpiaBitsBusquedaEnPantalla) */
void c_and_mask(unsigned char *dest, int mask, int n);
void a_and_mask(unsigned char *dest, int mask, int n);

/* memset for the mixing buffer */
void c_fill(unsigned char *dest, int value, int n);
void a_fill(unsigned char *dest, int value, int n);

/* ---- packed mixing buffer (QL_PACKED_MIX): one CPC Mode 1 byte = 4 pixels ----
 * The buffer holds the pixels exactly as the CPC does (pixel k: pen bit 0 in bit 7-k,
 * pen bit 1 in bit 3-k), so a sprite byte from the ROM is drawn without unpacking and the
 * blit to the QL screen turns one buffer byte into one Mode 8 word. Strides are in BYTES.
 * The byte-per-pixel kernels above stay as they are: the PC oracle still uses them, and
 * kerntest checks that pack(byte-per-pixel result) == packed result. */
void c_combina_tile_p(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void a_combina_tile_p(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void c_sprite_blit_p(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
void a_sprite_blit_p(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
/* ---- the sprite mask (QL_CHARCOL, src/colour.s): one byte per packed byte, QL_MASK_OFF bytes
 * after it (inside the shared 8 KB buffer); bit 3-k = pixel k was drawn by a sprite. The _pm
 * kernels keep it: the sprite draw sets the bits of its drawn pixels, the tile combine clears
 * the bits under the pixels it draws. */
#define QL_MASK_OFF 4096
void c_combina_tile_pm(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void a_combina_tile_pm(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void c_sprite_blit_pm(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
void a_sprite_blit_pm(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
/* the screen copy with the mask (colour.s blit_packed, char_sep path): words = Mode 8 words out,
 * w bytes a line, h lines, src packed (stride bytes), tables = cmb[16][256] for even / odd lines,
 * odd = 1 when the first line is an odd QL line; out lines are outStride words apart */
void c_blit_pm(unsigned short *out, int outStride, const unsigned char *src, int stride, int w, int h,
               const unsigned short *cmbEven, const unsigned short *cmbOdd, int odd);

/* sets pixel p (counted from buf) to pen 3 (SpriteLuz); QL_CHARCOL: and it is no sprite pixel */
#if defined(QL_CHARCOL) && defined(QL_INTERLEAVE)
#define QL_PIX3(buf, p) ((buf)[2*((p) >> 2) + 1] |= (unsigned char)(0x88 >> ((p) & 3)), \
                         (buf)[2*((p) >> 2)] &= (unsigned char)~(0x08 >> ((p) & 3)))
#elif defined(QL_CHARCOL)
#define QL_PIX3(buf, p) ((buf)[(p) >> 2] |= (unsigned char)(0x88 >> ((p) & 3)), \
                         (buf)[((p) >> 2) + QL_MASK_OFF] &= (unsigned char)~(0x08 >> ((p) & 3)))
#else
#define QL_PIX3(buf, p) ((buf)[(p) >> 2] |= (unsigned char)(0x88 >> ((p) & 3)))
#endif

/* ---- route finder (QL_ASM_ROUTES): BuscadorRutas hot spots ----
 * c_ versions are line-by-line transcriptions of the C++ members (BuscadorRutas.cpp), kept
 * for kerntest's randomized differential test; the PC oracle runs the original C++.
 *
 * bfs24 = buscaEnPantallaComun with both esPosicionDestino and push/elem inlined:
 * grid = bufAlturas[24][24], stack = the search buffer (INT32: y<<16 | x, -1 = level mark).
 * io[0] posXIni, io[1] posYIni (in); out: io[2], io[3] = the cell being expanded when the
 * goal was found, io[4] nivelRecursion, io[5] posPila, io[6] posProcesadoPila.
 * Returns 0 = not found, 1..4 = goal at (x+1,y), (x,y-1), (x-1,y), (x,y+1). */
int c_bfs24(unsigned char *grid, int *stack, int *io);
int a_bfs24(unsigned char *grid, int *stack, int *io);
/* bfs16 = buscaPantalla(numPlanta, mascara) with esPantallaDestino and push/elem inlined:
 * hab = habitaciones[numPlanta] (16x16 rooms, index (y << 4) | x), stack = the search buffer.
 * io in: [0] posXIni, [1] posYIni, [2] mascara; out: [3], [4] = the room being expanded when
 * found, [5] posPila, [6] posProcesadoPila. Returns 0 or 1..4 as bfs24. */
int c_bfs16(unsigned char *hab, int *stack, int *io);
int a_bfs16(unsigned char *hab, int *stack, int *io);
/* reconstruye = the first part of reconstruyeCamino (walks the search stack back from the goal,
 * writing the moves at the top of the buffer). io in: [0] posProcesadoPila, [1] nivelRecursion,
 * [2] posXFinal, [3] posYFinal, [4] oriFinal, [5] posXIni, [6] posYIni; out: [7] posPila,
 * [8] posPila2 */
void c_reconstruye(int *buffer, int lgtudBuffer, int *io);
void a_reconstruye(int *buffer, int lgtudBuffer, int *io);
/* modificaPuertasRuta's loop: hab0 = habitaciones[0], hp = habitacionesPuerta[6][4] */
void c_puertas_ruta(unsigned char *hab0, const unsigned char *hp, int mascara);
void a_puertas_ruta(unsigned char *hab0, const unsigned char *hp, int mascara);

/* ---- height grid (QL_ASM_GRID): RejillaPantalla hot spots ----
 * rellena_alturas = rellenaAlturasPantalla after calculaMinimosValoresVisibles: clears the
 * 24x24 grid and draws the floor's height blocks (datos = the floor's table in the ROM)
 * clipped to the window at (minPosX, minPosY). */
void c_rellena_alturas(unsigned char *buf, const unsigned char *datos, int minPosX, int minPosY);
void a_rellena_alturas(unsigned char *buf, const unsigned char *datos, int minPosX, int minPosY);
/* avance = the part of obtenerAlturaPosicionesAvanceComun after estaEnRejillaCentral: fills
 * bufCalculoAvance[4][4] (calc) from the grid around (x, y) along tab = calculoAvancePosicion
 * [orientacion], and returns difAltura1/difAltura2 in dif[0]/dif[1] */
void c_avance(const unsigned char *grid, int *calc, int x, int y, const int *tab, int enDesnivel, int alturaLocal, int *dif);
void a_avance(const unsigned char *grid, int *calc, int x, int y, const int *tab, int enDesnivel, int alturaLocal, int *dif);

/* ---- tile depth pass (QL_ASM_TILES): MezcladorSprites::dibujaTilesEntreProfundidades on the
 * packed buffer. p: [0] bufferTiles (TileInfo[20][16], 6 bytes: profX[2], profY[2], tile[2]),
 * [1] bufTilesPosX, [2] bufTilesPosY, [3] numTilesX, [4] numTilesY, [5] profMinX, [6] profMinY,
 * [7] profMaxX, [8] profMaxY, [9] bufferMezclas, [10] desp (pixels), [11] anchoFinal,
 * [12] ultimaPasada, [13] the tile graphics (roms + 0x8300), [14] 1 = keep the sprite mask
 * (QL_CHARCOL: a_combina_tile_pm) */
void c_tiles_prof(const int *p);
void a_tiles_prof(const int *p);

/* QL_INTERLEAVE (2026-10-06): the mixing buffer interleaved, one word an element (4 pixels):
 * the sprite-mask byte first, the packed pens second (src/kernels.s a_*_pi / a_*_pmi, colour.s
 * ql_play_blit_pi: the screen copy reads mask * 256 + pens as one word). QL_PE(i) = the byte
 * offset of element i. Without it: the pens plane, the mask plane QL_MASK_OFF after it. */
#ifdef QL_INTERLEAVE
#define QL_PE(i) (2*(i))
#ifndef QL_ASM_KERNELS
#error "QL_INTERLEAVE has asm kernels only (tools/inttest.py checks them against the plane ones)"
#endif
void a_combina_tile_pi(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void a_combina_tile_pmi(unsigned char *dest, int destStride, const unsigned char *tile, int transp);
void a_sprite_blit_pi(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
void a_sprite_blit_pmi(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h);
#define k_combina_tile_p a_combina_tile_pi
#define k_sprite_blit_p a_sprite_blit_pi
#define k_combina_tile_pm a_combina_tile_pmi
#define k_sprite_blit_pm a_sprite_blit_pmi
#define QL_PLAY_BLIT_P ql_play_blit_pi
#else
#define QL_PE(i) (i)
#define QL_PLAY_BLIT_P ql_play_blit_p
#endif

#if defined(QL_INTERLEAVE)
#elif defined(QL_ASM_KERNELS)
#define k_combina_tile_p a_combina_tile_p
#define k_sprite_blit_p a_sprite_blit_p
#define k_combina_tile_pm a_combina_tile_pm
#define k_sprite_blit_pm a_sprite_blit_pm
#else
#define k_combina_tile_p c_combina_tile_p
#define k_sprite_blit_p c_sprite_blit_p
#define k_combina_tile_pm c_combina_tile_pm
#define k_sprite_blit_pm c_sprite_blit_pm
#endif

#ifdef QL_ASM_KERNELS
#define k_combina_tile a_combina_tile
#define k_sprite_blit a_sprite_blit
#define k_fill a_fill
#define k_and_mask a_and_mask
#else
#define k_combina_tile c_combina_tile
#define k_sprite_blit c_sprite_blit
#define k_fill c_fill
#define k_and_mask c_and_mask
#endif

#ifdef __cplusplus
}
#endif

#endif

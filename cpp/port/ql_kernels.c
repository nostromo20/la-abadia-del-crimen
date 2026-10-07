/* ql_kernels.c -- C reference versions of the mixer kernels (see ql_kernels.h).
 * Same pixel rules as VIGASOCO's MezcladorSprites::combinaTile and Sprite::dibuja. */
#include "ql_kernels.h"

/* pen of pixel k (0-3) of a CPC Mode 1 byte, as CPC6128::unpackPixelMode1 */
#define PEN(d, k) ((((d) >> (3 - (k))) & 1) << 1 | (((d) >> (7 - (k))) & 1))

void c_combina_tile(unsigned char *dest, int destStride, const unsigned char *tile, int transp)
{
	int j, i, k;
	for (j = 0; j < 8; j++){
		unsigned char *d = dest;
		for (i = 0; i < 4; i++){
			int data = *tile++;
			for (k = 0; k < 4; k++){
				int c = PEN(data, k);
				if (c != transp) *d = c;
				d++;
			}
		}
		dest += destStride;
	}
}

void c_sprite_blit(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h)
{
	int j, i, k;
	for (j = 0; j < h; j++){
		const unsigned char *s = src;
		unsigned char *d = dest;
		for (i = 0; i < w; i++){
			int data = *s++;
			for (k = 0; k < 4; k++){
				int c = PEN(data, k);
				if (c != 0) *d = c;
				d++;
			}
		}
		src += srcStride;
		dest += destStride;
	}
}

void c_and_mask(unsigned char *dest, int mask, int n)
{
	while (n-- > 0) *dest++ &= (unsigned char)mask;
}

void c_fill(unsigned char *dest, int value, int n)
{
	while (n-- > 0) *dest++ = (unsigned char)value;
}

/* ---- packed buffer (see ql_kernels.h) ---- */

/* mask of the bits of the pixels of CPC byte d whose pen is transp */
static unsigned char pen_mask(int d, int transp)
{
	int k, m = 0;
	for (k = 0; k < 4; k++)
		if (PEN(d, k) == transp) m |= 0x88 >> k;
	return (unsigned char)m;
}

void c_combina_tile_p(unsigned char *dest, int destStride, const unsigned char *tile, int transp)
{
	int j, i;
	for (j = 0; j < 8; j++){
		for (i = 0; i < 4; i++){
			int s = tile[i];
			if (transp < 0) dest[i] = (unsigned char)s;
			else {
				int m = pen_mask(s, transp);       /* transparent pixels keep dest */
				dest[i] = (unsigned char)((dest[i] & m) | (s & ~m));
			}
		}
		tile += 4;
		dest += destStride;
	}
}

void c_sprite_blit_p(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h)
{
	int j, i;
	for (j = 0; j < h; j++){
		for (i = 0; i < w; i++){
			int s = src[i];
			int m = pen_mask(s, 0);                /* pen 0 is transparent */
			dest[i] = (unsigned char)((dest[i] & m) | s);
		}
		src += srcStride;
		dest += destStride;
	}
}

/* ---- route finder (see ql_kernels.h) ---- */

/* BuscadorRutas::esPosicionDestino(posX, posY, alturaBase) + the 5-argument one with
 * buscandoSolucion = true, + push() */
static int bfs_destino(unsigned char *g, int *stack, int *posPila, int posX, int posY, int alturaBase)
{
	unsigned char *p = g + posY*24 + posX;
	int altura = *p;
	int difAltura, difAltura2;
	if ((altura & 0x80) != 0) return 0;
	altura &= 0x3f;
	difAltura = alturaBase - altura + 1;
	if ((difAltura < 0) || (difAltura >= 3)) return 0;
	if (altura != (p[-1] & 0x3f)){
		difAltura = (p[-1] & 0x3f) - altura + 1;
		if ((difAltura < 0) || (difAltura >= 3)) return 0;
		if (altura != (p[-24] & 0x3f)) return 0;
		difAltura2 = (p[-25] & 0x3f) - altura + 1;
		if (difAltura != difAltura2) return 0;
	} else {
		difAltura = (p[-24] & 0x3f) - altura + 1;
		if ((difAltura < 0) || (difAltura >= 3)) return 0;
		difAltura2 = (p[-25] & 0x3f) - altura + 1;
		if (difAltura != difAltura2) return 0;
	}
	*p |= 0x80;
	if ((*p & 0x40) != 0){
		*p &= 0x7f;
		return 1;
	}
	stack[(*posPila)++] = ((posY & 0xffff) << 16) | (posX & 0xffff);
	return 0;
}

int c_bfs24(unsigned char *g, int *stack, int *io)
{
	int i, posX, posY, altura;
	int posPila, posProcesadoPila;
	for (i = 0; i < 24; i++){
		g[i*24 + 0] |= 0x80;
		g[i*24 + 23] |= 0x80;
		g[0*24 + i] |= 0x80;
		g[23*24 + i] |= 0x80;
	}
	io[4] = 1;
	posPila = 0;
	stack[posPila++] = ((io[1] & 0xffff) << 16) | (io[0] & 0xffff);
	g[io[1]*24 + io[0]] |= 0x80;
	stack[posPila++] = -1;
	posProcesadoPila = 0;
	for (;;){
		int rdo = stack[posProcesadoPila];
		posX = (short)(rdo & 0xffff);
		posY = (short)((rdo >> 16) & 0xffff);
		posProcesadoPila++;
		if ((posX == -1) && (posY == -1)){
			if (posProcesadoPila == posPila){
				i = 0;
				break;
			}
			stack[posPila++] = -1;
			io[4]++;
		} else {
			altura = g[posY*24 + posX] & 0x0f;
			if (bfs_destino(g, stack, &posPila, posX + 1, posY, altura)){ i = 1; break; }
			if (bfs_destino(g, stack, &posPila, posX, posY - 1, altura)){ i = 2; break; }
			if (bfs_destino(g, stack, &posPila, posX - 1, posY, altura)){ i = 3; break; }
			if (bfs_destino(g, stack, &posPila, posX, posY + 1, altura)){ i = 4; break; }
		}
	}
	io[2] = posX;
	io[3] = posY;
	io[5] = posPila;
	io[6] = posProcesadoPila;
	return i;
}

void c_puertas_ruta(unsigned char *hab0, const unsigned char *hp, int mascara)
{
	int i, j;
	for (i = 0; i < 6; i++){
		for (j = 0; j < 2; j++){
			if (mascara & 0x01){
				hab0[hp[i*4 + 2*j]] = (~hp[i*4 + 2*j + 1]) & hab0[hp[i*4 + 2*j]];
			} else {
				hab0[hp[i*4 + 2*j]] = (hp[i*4 + 2*j + 1]) | hab0[hp[i*4 + 2*j]];
			}
		}
		mascara = mascara >> 1;
	}
}

/* ---- height grid (see ql_kernels.h): RejillaPantalla::rellenaAlturasPantalla ---- */

/* RejillaPantalla::fijaAlturaRecortando */
static void fija_altura_recortando(unsigned char *buf, int minPosX, int minPosY, int posX, int posY, int altura)
{
	posY = posY - minPosY;
	if ((posY < 0) || (posY >= 24)) return;
	posX = posX - minPosX;
	if ((posX < 0) || (posX >= 24)) return;
	buf[posY*24 + posX] = (unsigned char)altura;
}

void c_rellena_alturas(unsigned char *buf, const unsigned char *datosAltura, int minPosX, int minPosY)
{
	static const int incrementos[4][2] = { { 1, 0 }, { 0, -1 }, { -1, 0 }, { 0, 1 } };
	int i, j;
	for (j = 0; j < 24; j++)
		for (i = 0; i < 24; i++)
			buf[j*24 + i] = 0;
	while ((*datosAltura) != 0xff){
		int tipoBloque = datosAltura[0];
		int lgtudX, lgtudY, altura, posX, posY, distX, distY;
		if (((tipoBloque & 0x07) == 0) || ((tipoBloque & 0x07) >= 6)) break;
		lgtudX = datosAltura[3];
		lgtudY = datosAltura[4];
		if ((tipoBloque & 0x08) == 0){
			lgtudY = lgtudX & 0x0f;
			lgtudX = (lgtudX >> 4) & 0x0f;
		}
		altura = (tipoBloque >> 4) & 0x0f;
		posX = datosAltura[1];
		posY = datosAltura[2];
		if ((tipoBloque & 0x08) == 0) datosAltura += 4;
		else datosAltura += 5;
		lgtudX++;
		lgtudY++;
		distX = posX - minPosX;
		if (distX < 0){
			if (-distX >= lgtudX) continue;
		} else if (distX >= 24) continue;
		distY = posY - minPosY;
		if (distY < 0){
			if (-distY >= lgtudY) continue;
		} else if (distY >= 24) continue;
		if ((tipoBloque & 0x07) != 5){
			for (j = 0; j < lgtudY; j++){
				int oldAltura = altura;
				for (i = 0; i < lgtudX; i++){
					fija_altura_recortando(buf, minPosX, minPosY, posX + i, posY + j, altura);
					altura += incrementos[(tipoBloque & 0x07) - 1][0];
				}
				altura = oldAltura + incrementos[(tipoBloque & 0x07) - 1][1];
			}
		} else {
			distX = posX - minPosX;
			if (distX < 0){
				posX = 0;
				if ((distX + lgtudX) > 24) lgtudX = 24;
				else lgtudX = lgtudX + distX;
			} else {
				posX = distX;
				if ((distX + lgtudX) > 24) lgtudX = lgtudX - (distX + lgtudX - 24);
			}
			distY = posY - minPosY;
			if (distY < 0){
				posY = 0;
				if ((distY + lgtudY) > 24) lgtudY = 24;
				else lgtudY = lgtudY + distY;
			} else {
				posY = distY;
				if ((distY + lgtudY) > 24) lgtudY = lgtudY - (distY + lgtudY - 24);
			}
			for (j = 0; j < lgtudY; j++)
				for (i = 0; i < lgtudX; i++)
					buf[(posY + j)*24 + posX + i] = (unsigned char)altura;
		}
	}
}

/* RejillaPantalla::obtenerAlturaPosicionesAvanceComun from "calcula la primera posicion" on
 * (grid = bufAlturas, calc = bufCalculoAvance, tab = calculoAvancePosicion[orientacion]) */
void c_avance(const unsigned char *grid, int *calc, int posXLocal, int posYLocal, const int *tab, int enDesnivel, int alturaLocal, int *dif)
{
	int i, j;
	int despIni = enDesnivel ? 6 : 4;
	posXLocal += tab[despIni];
	posYLocal += tab[despIni + 1];
	for (j = 0; j < 4; j++){
		int oldPosXLocal = posXLocal;
		int oldPosYLocal = posYLocal;
		for (i = 0; i < 4; i++){
			int alturaPos = grid[posYLocal*24 + posXLocal];
			if (alturaPos < 0x10) alturaPos = alturaPos - alturaLocal;
			else alturaPos = alturaPos & 0x30;
			calc[j*4 + i] = alturaPos;
			posXLocal += tab[0];
			posYLocal += tab[1];
		}
		posXLocal = oldPosXLocal + tab[2];
		posYLocal = oldPosYLocal + tab[3];
	}
	if (!enDesnivel){
		dif[0] = calc[0*4 + 1];
		dif[1] = calc[0*4 + 2];
		if (dif[0] != dif[1]) dif[0] = 2;
	} else {
		dif[0] = calc[1*4 + 1];
		dif[1] = calc[0*4 + 1];
	}
}

/* BuscadorRutas::reconstruyeCamino up to "aqui llega cuando ya ha encontrado el camino completo",
 * with pop and pushInv inlined (DERECHA 0, ABAJO 1, IZQUIERDA 2, ARRIBA 3) */
void c_reconstruye(int *buffer, int lgtudBuffer, int *io)
{
	int posPila = io[0];
	int posXDest, posYDest, rdo;
	int posPila2 = lgtudBuffer - 1;
	posPila--;
	rdo = buffer[posPila];
	posXDest = (short)(rdo & 0xffff);
	posYDest = (short)((rdo >> 16) & 0xffff);
	buffer[posPila2--] = -1 & 0xffff;
	buffer[posPila2--] = io[2] & 0xffff;
	buffer[posPila2--] = io[3] & 0xffff;
	buffer[posPila2--] = (io[4] ^ 2) & 0xffff;
	if (io[1] != 1){
		int posX, posY, difAlturaX, difAlturaY, ori;
		while (1){
			do {
				posPila--;
				rdo = buffer[posPila];
				posX = (short)(rdo & 0xffff);
				posY = (short)((rdo >> 16) & 0xffff);
			} while (!((posX == -1) && (posY == -1)));
			buffer[posPila2--] = posXDest & 0xffff;
			buffer[posPila2--] = posYDest & 0xffff;
			while (1){
				posPila--;
				rdo = buffer[posPila];
				posX = (short)(rdo & 0xffff);
				posY = (short)((rdo >> 16) & 0xffff);
				difAlturaY = posY - posYDest + 1;
				if ((difAlturaY < 0) || (difAlturaY >= 3)) continue;
				difAlturaX = posX - posXDest + 1;
				if ((difAlturaX < 0) || (difAlturaX >= 3)) continue;
				switch (4*difAlturaX + difAlturaY){
					case 1: ori = 0; break;
					case 6: ori = 1; break;
					case 9: ori = 2; break;
					case 4: ori = 3; break;
					default: continue;
				}
				break;
			}
			posXDest = posX;
			posYDest = posY;
			buffer[posPila2--] = ori & 0xffff;
			if ((io[5] == posX) && (io[6] == posY)) break;
		}
	}
	io[7] = posPila;
	io[8] = posPila2;
}

/* BuscadorRutas::esPantallaDestino + push */
static int bfs16_destino(unsigned char *hab, int *stack, int *posPila, int posX, int posY, int mascara, int mascaraDestino)
{
	if ((posX < 0) || (posX > 0x10) || (posY < 0) || (posY > 0x10)) return 0;
	if ((hab[(posY << 4) | posX] & mascaraDestino) == 0){
		if ((hab[(posY << 4) | posX] & mascara) != 0) return 1;
		if (((hab[(posY << 4) | posX]) & 0x80) == 0){
			stack[(*posPila)++] = ((posY & 0xffff) << 16) | (posX & 0xffff);
			hab[(posY << 4) | posX] |= 0x80;
		}
	}
	return 0;
}

/* BuscadorRutas::buscaPantalla(numPlanta, mascara) */
int c_bfs16(unsigned char *hab, int *stack, int *io)
{
	int posPila = 0, posProcesadoPila = 0, posX, posY, r;
	int mascara = io[2];
	stack[posPila++] = ((io[1] & 0xffff) << 16) | (io[0] & 0xffff);
	hab[(io[1] << 4) | io[0]] |= 0x80;
	stack[posPila++] = -1;
	for (;;){
		int rdo = stack[posProcesadoPila];
		posX = (short)(rdo & 0xffff);
		posY = (short)((rdo >> 16) & 0xffff);
		posProcesadoPila++;
		if ((posX == -1) && (posY == -1)){
			if (posProcesadoPila == posPila){ r = 0; break; }
			stack[posPila++] = -1;
		} else {
			if (bfs16_destino(hab, stack, &posPila, posX + 1, posY, mascara, 0x04)){ r = 1; break; }
			if (bfs16_destino(hab, stack, &posPila, posX, posY - 1, mascara, 0x08)){ r = 2; break; }
			if (bfs16_destino(hab, stack, &posPila, posX - 1, posY, mascara, 0x01)){ r = 3; break; }
			if (bfs16_destino(hab, stack, &posPila, posX, posY + 1, mascara, 0x02)){ r = 4; break; }
		}
	}
	io[3] = posX;
	io[4] = posY;
	io[5] = posPila;
	io[6] = posProcesadoPila;
	return r;
}

/* ---- tile depth pass (see ql_kernels.h) ---- */

/* MezcladorSprites::combinaTile on the packed buffer */
static void tp_combina(const int *p, int tile, int despX)
{
	int transparente = (tile < 0x0b) ? -1 : ((tile & 0x80) ? 1 : 2);
	if (p[14])
		c_combina_tile_pm((unsigned char *)p[9] + (despX >> 2), p[11], (const unsigned char *)p[13] + tile*32, transparente);
	else
		c_combina_tile_p((unsigned char *)p[9] + (despX >> 2), p[11], (const unsigned char *)p[13] + tile*32, transparente);
}

/* MezcladorSprites::dibujaTilesEntreProfundidades (nivelesProfTiles = 2) */
void c_tiles_prof(const int *p)
{
	unsigned char *bt = (unsigned char *)p[0];
	int bufTilesPosX = p[1], bufTilesPosY = p[2];
	int numTilesX = p[3], numTilesY = p[4];
	int profMinX = p[5], profMinY = p[6], profMaxX = p[7], profMaxY = p[8];
	int desp = p[10], ultimaPasada = p[12];
	int i, j, k;
	for (j = 0; j < numTilesY; j++){
		int despX = desp;
		for (i = 0; i < numTilesX; i++){
			int bx = bufTilesPosX + i, by = bufTilesPosY + j;
			if (!((bx < 0) || (bx >= 16) || (by < 0) || (by >= 20))){
				unsigned char *ti = bt + (by*16 + bx)*6;    /* profX = ti[k], profY = ti[2+k], tile = ti[4+k] */
				int haPintado = 0;
				for (k = 0; k < 2; k++){
					if (ti[4 + k] != 0){
						int visible = 1;
						if (!(haPintado && ((ti[k] & 0x80) == 0x80))){
							if (ti[k] < profMinX){
								if (ti[2 + k] < profMinY) visible = 0;
							}
							if (visible){
								if (ti[2 + k] >= profMaxY) visible = 0;
								else if (ti[k] >= profMaxX) visible = 0;
							}
						} else {
							if (haPintado && ((ti[k] & 0x80) == 0x80)) tp_combina(p, ti[4 + k], despX);
						}
						if (visible && ((ti[k] & 0x80) == 0)){
							ti[k] |= 0x80;
							haPintado = 1;
							tp_combina(p, ti[4 + k], despX);
						}
					}
					if (ultimaPasada) ti[k] &= 0x7f;
				}
			}
			despX = despX + 16;
		}
		desp = desp + p[11]*4*8;
	}
}

/* ---- the sprite mask (see ql_kernels.h) ---- */

void c_combina_tile_pm(unsigned char *dest, int destStride, const unsigned char *tile, int transp)
{
	int j, i;
	for (j = 0; j < 8; j++){
		for (i = 0; i < 4; i++){
			int s = tile[i];
			if (transp < 0){
				dest[i] = (unsigned char)s;
				dest[i + QL_MASK_OFF] = 0;
			} else {
				int m = pen_mask(s, transp);
				dest[i] = (unsigned char)((dest[i] & m) | (s & ~m));
				dest[i + QL_MASK_OFF] &= (unsigned char)m;     /* the tile's drawn pixels: no sprite */
			}
		}
		tile += 4;
		dest += destStride;
	}
}

void c_sprite_blit_pm(unsigned char *dest, int destStride, const unsigned char *src, int srcStride, int w, int h)
{
	int j, i;
	for (j = 0; j < h; j++){
		for (i = 0; i < w; i++){
			int s = src[i];
			int m = pen_mask(s, 0);
			dest[i] = (unsigned char)((dest[i] & m) | s);
			dest[i + QL_MASK_OFF] |= (unsigned char)(~m & 0x0f);  /* drawn pixels: sprite */
		}
		src += srcStride;
		dest += destStride;
	}
}

void c_blit_pm(unsigned short *out, int outStride, const unsigned char *src, int stride, int w, int h,
               const unsigned short *cmbEven, const unsigned short *cmbOdd, int odd)
{
	int j, i;
	for (j = 0; j < h; j++){
		const unsigned short *t = ((j + odd) & 1) ? cmbOdd : cmbEven;
		for (i = 0; i < w; i++)
			out[i] = t[(src[i + QL_MASK_OFF] & 0x0f) * 256 + src[i]];
		out += outStride;
		src += stride;
	}
}

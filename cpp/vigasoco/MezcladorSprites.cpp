// MezcladorSprites.cpp
//
/////////////////////////////////////////////////////////////////////////////

#include <cassert>

#include "cpc6128.h"

#include "GeneradorPantallas.h"
#include "Juego.h"
#include "MezcladorSprites.h"
#include "ql_hostcls.h"
#include <string.h>
#include "Sprite.h"
#include "ql_kernels.h"

//memset
#include <string.h>

using namespace Abadia;

#ifdef QL_HOST_CLASSES
// MIXDUMP (host scene recorder only): every mixer batch's inputs (tile buffer in the CPC's layout,
// the sprites, their graphics) and outputs (each processed sprite's area), for tools/mixcheck.py
#include <stdio.h>
#include <stdlib.h>
#include "SpriteMonje.h"
#include "MotorGrafico.h"
static FILE *mixDump(void)
{
	static FILE *f = 0;
	static int tried = 0;
	if (!tried){
		tried = 1;
		if (getenv("MIXDUMP")) f = fopen(getenv("MIXDUMP"), "wb");
	}
	return f;
}
static void md_put(FILE *f, int v) { fputc(v & 0xff, f); fputc((v >> 8) & 0xff, f); fputc((v >> 16) & 0xff, f); fputc((v >> 24) & 0xff, f); }
namespace Abadia {
struct QlMixDump {
	static void batch(MezcladorSprites *m, Sprite **sprites, int num)
	{
		FILE *f = mixDump();
		if (!f) return;
		fputc('B', f);
		md_put(f, qlc_tick);
		md_put(f, elJuego->motor->numPantalla);
		for (int y = 0; y < 20; y++){
			for (int x = 0; x < 16; x++){
				GeneradorPantallas::TileInfo *ti = &m->genPant->bufferTiles[y][x];
				for (int k = 0; k < 2; k++){
					fputc(ti->profX[k], f); fputc(ti->profY[k], f); fputc(ti->tile[k], f);
				}
			}
		}
		md_put(f, num);
		for (int i = 0; i < num; i++){
			Sprite *s = sprites[i];
			int kind = (s == elJuego->sprites[Juego::spriteLuz]) ? 2 : ((i >= 2 && i < 8) ? 1 : 0);
			int v[19] = { s->esVisible, s->haCambiado, s->desaparece, s->profundidad, s->posXPant, s->posYPant,
				s->oldPosXPant, s->oldPosYPant, s->ancho, s->alto, s->oldAncho, s->oldAlto, s->despGfx,
				s->posXLocal, s->posYLocal, kind, kind == 1 ? ((SpriteMonje *)s)->animacionTraje : 0,
				kind == 1 ? ((SpriteMonje *)s)->qlDespTraje() : 0, 0 };
			for (int k = 0; k < 19; k++) md_put(f, v[k]);
			if (s->esVisible && kind != 2){
				// graphics as the mixer reads them (monks: the 10 head lines, then the habit)
				int n = s->ancho*s->alto;
				if (kind == 1){
					fwrite(&m->roms[s->despGfx], 1, s->ancho*10, f);
					fwrite(&m->roms[((SpriteMonje *)s)->qlDespTraje()], 1, n - s->ancho*10, f);
				} else {
					fwrite(&m->roms[s->despGfx], 1, n, f);
				}
			}
		}
		fflush(f);
	}
	static void area(MezcladorSprites *m, Sprite **sprites, int num, Sprite *s)
	{
		FILE *f = mixDump();
		if (!f) return;
		int idx = 0;
		while (idx < num && sprites[idx] != s) idx++;
		fputc('O', f);
		md_put(f, idx); md_put(f, s->despBuffer); md_put(f, s->posXTile); md_put(f, s->posYTile);
		md_put(f, s->anchoFinal); md_put(f, s->altoFinal);
		fwrite(&m->bufferMezclas[s->despBuffer], 1, s->anchoFinal*4*s->altoFinal, f);
		fflush(f);
	}
};
}
static int qlTileCause;
#define QL_MIXDUMP_BATCH(s, n) QlMixDump::batch(this, s, n)
#define QL_MIXDUMP_AREA(s, n, spr) QlMixDump::area(this, s, n, spr)
#else
#define QL_MIXDUMP_BATCH(s, n)
#define QL_MIXDUMP_AREA(s, n, spr)
#endif

/////////////////////////////////////////////////////////////////////////////
// inicializaci�n y limpieza
/////////////////////////////////////////////////////////////////////////////
MezcladorSprites::MezcladorSprites(GeneradorPantallas *generador, UINT8 *buffer, int lgtudBuffer)
{
	genPant = generador;

	roms = elJuego->roms;
	cpc6128 = elJuego->cpc6128;

	bufferMezclas = buffer;
	lgtudBufferMezclas = lgtudBuffer;
#ifdef QL_HOST_CLASSES
	qlc_register(buffer, lgtudBuffer);
#endif

}

MezcladorSprites::~MezcladorSprites()
{
}

/////////////////////////////////////////////////////////////////////////////
// dibujo de los sprites del juego, mezcl�ndolos con los tiles
/////////////////////////////////////////////////////////////////////////////

void MezcladorSprites::mezclaSprites(Sprite **sprites, int num)
{
	// inicia la primera posici�n vac�a del buffer de sprites
	sgtePosBuffer = 0;

	// inicialmente no hay nung�n sprite que procesar
	numSprites = numSpritesRedib = 0;

	// recorre los sprites y comprueba si hay que dibujar alguno
	for (int i = num - 1; i >= 0; i--){
		if (sprites[i]->esVisible){
			// si el sprite es visible, lo mete en la lista
			listaSprites[numSprites] = i;
			numSprites++;

			// incrementa el contador de sprites que deben ser redibujados, indica
			if (sprites[i]->haCambiado){
				numSpritesRedib++;
			}
		}
	}

	// si no hab�a ning�n sprite que redibujar, sale
	if (numSpritesRedib == 0) return;

	QL_MIXDUMP_BATCH(sprites, num);

	int i = 1;
	bool huboIntercambio;

	// ordena los sprites ascendentemente seg�n su profundidad usando el m�todo de la burbuja mejorado
	do {
		// inicialmente no hay intercambios
		huboIntercambio = false;

		// recorre los elementos no ordenados
		for (int j = numSprites - 1; j >= i; j--){
			if (sprites[listaSprites[j - 1]]->profundidad > sprites[listaSprites[j]]->profundidad){
				// realiza un intercambio
				int aux = listaSprites[j - 1];
				listaSprites[j - 1] = listaSprites[j];
				listaSprites[j] = aux;

				huboIntercambio = true;
			}
		}

		i++;
	} while (huboIntercambio || (i <  numSprites));

	// recorre los sprites de la lista, calculando el �rea que debe dibujarse y mezcl�ndolos en el buffer de sprites
	for (int i = 0; i < numSprites; i++){
		// obtiene un puntero al sprite que se est� procesando
		Sprite *spr = sprites[listaSprites[i]];

		// indica que el sprite no se ha procesado todav�a
		spr->seHaProcesado = false;

		// si el sprite no ha cambiado, pasa a procesar el siguiente sprite
		if (!spr->haCambiado) continue;

		// calcula el area a redibujar seg�n los tiles que contienen el sprite
		spr->ajustaATiles();

		// ajusta las dimensiones del area a redibujar para que abarque el sprite antiguo
		spr->ampliaDimViejo();

		// calcula el desplazamiento correspondiente a la posici�n inicial en el buffer de tiles. 
		// las coordenadas del sprite (32, 40) se corresponden al primer pixel del buffer de tiles
		bufTilesPosX = (4*spr->posXTile/16) - (32/16);
		bufTilesPosY = (spr->posYTile/8) - (40/8);

		// guarda la direcci�n del buffer de sprites obtenida
		spr->despBuffer = sgtePosBuffer;
		sgtePosBuffer = sgtePosBuffer + spr->anchoFinal*spr->altoFinal*4;

		// si no hay sitio para el sprite en el buffer de sprites, vuelca a pantalla los sprites procesados y repite el proceso con el resto
		if (sgtePosBuffer > lgtudBufferMezclas){
			// si el primer sprite es demasiado grande y no cabe en el buffer, error
			assert(sgtePosBuffer != 0);
			assert(spr->anchoFinal*spr->altoFinal*4 < lgtudBufferMezclas);

			postProcesaSprites(sprites, num);

			return;
		}

		// si hay espacio en el buffer de sprites, el sprite se procesa
		spr->seHaProcesado = true;

		// limpia la zona asignada del buffer de sprites
#ifdef QL_PACKED_MIX	// QL: packed buffer, 4 pixels a byte (offsets stay in pixels)
		k_fill(&bufferMezclas[QL_PE(spr->despBuffer >> 2)], 0, QL_PE(spr->anchoFinal*spr->altoFinal));
#ifdef QL_CHARCOL
		// QL: separate character colours: the area's sprite mask is cleared when its first sprite
		// is drawn (below); until then the tiles go through the plain combine and an area with no
		// sprite at all is copied by the plain path
		qlSprDrawn = false;
		spr->qlMask = false;
#endif
#else
		k_fill(&bufferMezclas[spr->despBuffer], 0, spr->anchoFinal*spr->altoFinal*4);
#ifdef QL_HOST_CLASSES
		memset(&qlc_mixCls[spr->despBuffer], QLC_TERRAIN, spr->anchoFinal*spr->altoFinal*4);
#endif
#endif

		// empieza a dibujar desde la m�nima profundidad
		int profMinX = 0, profMinY = 0;

		// recorre los sprites de la lista, mezclando la parte que se vea con el sprite que se est� procesando
		for (int j = 0; j < numSprites; j++){
			// obtiene un puntero al sprite que se va a mezclar
			Sprite *sprAMezclar = sprites[listaSprites[j]];

			// si el sprite a mezclar va a desaparecer, pasa al siguiente sprite
			if (sprAMezclar->desaparece) continue;

			int lgtudClipX, lgtudClipY, dist1X, dist2X, dist1Y, dist2Y;

			// comprueba si el sprite a mezclar puede verse en la zona del sprite que se est� dibujando
			if (!recortaSprite(spr->posXTile, spr->anchoFinal, sprAMezclar->posXPant, sprAMezclar->ancho, lgtudClipX, dist1X, dist2X)){
				continue;
			}

			// comprueba si el sprite a mezclar puede verse en la zona del sprite que se est� dibujando
			if (!recortaSprite(spr->posYTile, spr->altoFinal, sprAMezclar->posYPant, sprAMezclar->alto, lgtudClipY, dist1Y, dist2Y)){
				continue;
			}

			// si llega aqu� es porque alguna parte del sprite es visible

			// vuelca al buffer de sprites los tiles no dibujados que est�n detr�s del sprite actual
			dibujaTilesEntreProfundidades(spr, profMinX, profMinY, sprAMezclar->posXLocal + 1, sprAMezclar->posYLocal + 1, spr->despBuffer, false);

			// actualiza el l�mite inferior de profundidad para la siguiente iteraci�n
			profMinX = sprAMezclar->posXLocal + 1;
			profMinY = sprAMezclar->posYLocal + 1;

			// dibuja la parte visible del sprite que se est� mezclando en el �rea ocupada por el sprite actual
#ifdef QL_CHARCOL
			if (char_sep && !qlSprDrawn && sprAMezclar != elJuego->sprites[Juego::spriteLuz]){
#ifndef QL_INTERLEAVE	// (interleaved: the area's clear above zeroed the mask bytes too, and only
						// the mask kernels have touched them since)
				k_fill(&bufferMezclas[(spr->despBuffer >> 2) + QL_MASK_OFF], 0, spr->anchoFinal*spr->altoFinal);
#endif
				qlSprDrawn = true;
				spr->qlMask = true;
			}
#endif
#ifdef QL_HOST_CLASSES
			{
				// SpriteLuz writes from the start of the buffer: watch all of it
				static unsigned char save[65536];
				qlc_begin(bufferMezclas, lgtudBufferMezclas, save);
				sprAMezclar->dibuja(spr, bufferMezclas, lgtudClipX, lgtudClipY, dist1X, dist2X, dist1Y, dist2Y);
				qlc_end(bufferMezclas, lgtudBufferMezclas, save,
					(sprAMezclar == elJuego->sprites[Juego::spriteLuz]) ? QLC_LAMP : QLC_CHAR);
			}
#else
			sprAMezclar->dibuja(spr, bufferMezclas, lgtudClipX, lgtudClipY, dist1X, dist2X, dist1Y, dist2Y);
#endif
		}

		// si falta alg�n tile por superponer al sprite, lo dibuja y limpia las marcas del buffer de tiles
		dibujaTilesEntreProfundidades(spr, profMinX, profMinY, 0xfd, 0xfd, spr->despBuffer, true);
	}

	// vuelca a pantalla los procesados
	postProcesaSprites(sprites, num);
}

/////////////////////////////////////////////////////////////////////////////
// mezcla de tiles al buffer de sprites
/////////////////////////////////////////////////////////////////////////////

// vuelca al buffer de sprites los tiles no dibujados que est�n detr�s del sprite actual
void MezcladorSprites::dibujaTilesEntreProfundidades(Sprite *spr, int profMinX, int profMinY, int profMaxX, int profMaxY, int desp, bool ultimaPasada)
{
#if defined(QL_ASM_TILES) && defined(QL_PACKED_MIX)
	// QL: the whole pass below (with combinaTile on the packed buffer) in asm (src/tiles.s)
	{
		int p[15];
		// src/tiles.s assumes 6-byte entries of 2 layers (profX[2], profY[2], tile[2])
		typedef char tileInfoLayout[(sizeof(GeneradorPantallas::TileInfo) == 6 && GeneradorPantallas::nivelesProfTiles == 2) ? 1 : -1];
		p[0] = (int)&genPant->bufferTiles[0][0];
		p[1] = bufTilesPosX; p[2] = bufTilesPosY;
		p[3] = spr->anchoFinal/4; p[4] = spr->altoFinal/8;
		p[5] = profMinX; p[6] = profMinY; p[7] = profMaxX; p[8] = profMaxY;
		p[9] = (int)bufferMezclas; p[10] = desp; p[11] = spr->anchoFinal;
		p[12] = ultimaPasada ? 1 : 0;
		p[13] = (int)&roms[0x8300];
#ifdef QL_CHARCOL
		p[14] = char_sep && qlSprDrawn;		// tiles behind every sprite: the mask is not in use yet
#ifdef QL_INTERLEAVE
		p[14] |= 2;							// (bit 1: the interleaved buffer)
#endif
#else
		p[14] = 0;
#endif
		a_tiles_prof(p);
		return;
	}
#endif
	// calcula el n�mero de tiles a procesar
	int numTilesX = spr->anchoFinal/4;
	int numTilesY = spr->altoFinal/8;

	// recorre los tiles en y que ocupa el sprite que se est� procesando
	for (int j = 0; j < numTilesY; j++){
		int despX = desp;

		// recorre los tiles en x que ocupa el sprite que se est� procesando
		for (int i = 0; i < numTilesX; i++){
			// si est� dentro del buffer de tiles
			if (estaEnBufferTiles(bufTilesPosX + i, bufTilesPosY + j)){
				// obtiene la entrada actual del buffer de tiles
				GeneradorPantallas::TileInfo *ti = &genPant->bufferTiles[bufTilesPosY + j][bufTilesPosX + i];

				// inicialmente en esta llamada no se ha pintado en esta posici�n del buffer de tiles
				bool haPintado = false;

				// recorre las distintas capas de tiles del buffer de tiles
				for (int k = 0; k < GeneradorPantallas::nivelesProfTiles; k++){
					// si hay alg�n tile en la entrada actual
					// QL (CPC): tile 0 is never drawn
					if (ti->tile[k] != 0){
					// En VGA si usamos y pintamos el tile 0
						bool visible = true;

						// si en esta llamada no se ha pintado en esta posici�n del buffer de tiles, 
						// comprueba si hay que pintar el tile que hay en esta capa de profundidad. 
						// Si se ha pintado en esta llamada y el tile de esta capa se hab�a pintado
						// en otra iteraci�n anterior, lo combina sin comprobar la profundidad
						if (!(haPintado && ((ti->profX[k] & 0x80) == 0x80))){
							// comprueba si el tile supera el l�mite inferior de profundidad
							if (ti->profX[k] < profMinX){
								if (ti->profY[k] < profMinY){
									visible = false;
								}
							}

							// comprueba si el tile no rebasa el l�mite superior de profundidad
							if (visible){
								if (ti->profY[k] >= profMaxY){
									visible = false;
								} else if (ti->profX[k] >= profMaxX){
									visible = false;
								}
							}
						} else {
							if (haPintado && ((ti->profX[k] & 0x80) == 0x80)){
								// combina el tile actual con lo que hay en el buffer de sprites
#ifdef QL_HOST_CLASSES
								qlTileCause = 1;	// TILELOG: drawn again over the lower layer
#endif
								combinaTile(spr, ti->tile[k], despX);
#ifdef QL_HOST_CLASSES
								qlTileCause = 0;
#endif
							}
						}

						// si el tile est� entre los l�mites de profundidad y no se ha dibujado todav�a
						if (visible && ((ti->profX[k] & 0x80) == 0)){
							// marca el tile como dibujado
							ti->profX[k] |= 0x80;

							// indica que en esta llamada ha pintado alg�n tile para esta posici�n del buffer de tiles
							haPintado = true;

							// combina el tile actual con lo que hay en el buffer de sprites
							combinaTile(spr, ti->tile[k], despX);
						}

					}

					if (ultimaPasada){
						// limpia la marca de dibujado
						ti->profX[k] &= 0x7f;
					}
				}
			}

			// avanza al pixel del siguiente tile en x dentro del buffer de sprites
			despX = despX + 16;
		}

		// avanza al pixel del siguiente tile en y dentro del buffer de sprites
		desp = desp + spr->anchoFinal*4*8;
	}
}

// combina un tile con lo que hay en la posici�n actual del buffer de sprites
void MezcladorSprites::combinaTile(Sprite *spr, int tile, int despBufSprites)
{
	assert ((tile >= 0) && (tile < 0x100));

	// QL (CPC): restored from the CPC routine at 0x4e49. Tiles < 0x0b are copied as they are;
	// the others go through the AND/OR tables chosen by bit 7 of the tile number, which on the
	// CPC make pen 2 transparent for tiles 0x00-0x7f and pen 1 for tiles 0x80-0xff (pens as
	// unpackPixelMode1 numbers them; same result as the fork's generaMascaras()).
	UINT8 *tileData = &roms[0x8300 + tile*32];
	UINT8 *dest = &bufferMezclas[despBufSprites];
	int despSgteLinea = spr->anchoFinal*4 - 16;
	int transparente = (tile < 0x0b) ? -1 : ((tile & 0x80) ? 1 : 2);

#ifdef QL_PACKED_MIX
#ifdef QL_CHARCOL
	if (char_sep && qlSprDrawn) k_combina_tile_pm(&bufferMezclas[QL_PE(despBufSprites >> 2)], spr->anchoFinal, tileData, transparente);
	else
#endif
	k_combina_tile_p(&bufferMezclas[QL_PE(despBufSprites >> 2)], spr->anchoFinal, tileData, transparente);
#else
#ifdef QL_HOST_CLASSES
	{
		static unsigned char save[65536];
		int n = spr->anchoFinal*4*7 + 16;
		qlc_begin(dest, n, save);
		k_combina_tile(dest, spr->anchoFinal*4, tileData, transparente);
		// TILELOG=file (host only): every tile drawn over character pixels in the mixer
		static FILE *tl = 0;
		static int tlTried = 0;
		if (!tlTried){ tlTried = 1; if (getenv("TILELOG")) tl = fopen(getenv("TILELOG"), "w"); }
		if (tl){
			unsigned char *c = qlc_mixCls + (dest - qlc_mixBase);
			int over = 0;
			for (int i = 0; i < n; i++) if (dest[i] != QLC_SENTINEL && c[i] == QLC_CHAR) over++;
			if (over){
				int rel = despBufSprites - spr->despBuffer;
				fprintf(tl, "%d area %d,%d tile %02x at %d,%d cause %d over %d\n", qlc_tick, spr->posXTile, spr->posYTile,
					tile, spr->posXTile*4 + (rel % (spr->anchoFinal*4)), spr->posYTile + rel / (spr->anchoFinal*4), qlTileCause, over);
				fflush(tl);
			}
		}
		qlc_end(dest, n, save, QLC_TERRAIN);
	}
#else
	k_combina_tile(dest, spr->anchoFinal*4, tileData, transparente);
#endif
#endif
#if 0 // pre-kernel C++ loop
	for (int j = 0; j < 8; j++){
		for (int i = 0; i < 4; i++){
			int data = *tileData++;
			for (int k = 0; k < 4; k++){
				int color = cpc6128->unpackPixelMode1(data, k);
				if (color != transparente){
					*dest = color;
				}
				dest++;
			}
		}
		dest += despSgteLinea;
	}
#endif
#if 0 // VGA (fork)
	// halla el desplazamiento del tile (cada tile ocupa 32 bytes)
	UINT8 *tileData = &roms[0x8300 + tile*32];
	//pasamos los 0x20000 de la rom CPC y ahi esta el GraficosVGA
	UINT8 *tileDataVGA = &roms[0x24000-1 - 0x4000 + 0x1400 + tile*8*16]; // VGA

	// halla el desplazamiento de destino
	UINT8 *dest = &bufferMezclas[despBufSprites];

	// calcula el desplazamiento a la siguiente l�nea del buffer de sprites
	int despSgteLinea = spr->anchoFinal*4 - 16;

	// los tiles < 0x0b no tienen ninguna transparencia
//	if (tile >0 && tile < 0x0b){ // TODO: revisar
	if (tile < 0x0b){
		// dibuja cada linea del tile
		for (int j = 0; j < 8; j++){
			// repite para 16 bytes (16 pixels)
			for (int i = 0; i < 16; i++){
//CPC			for (int i = 0; i < 4; i++){
				// lee un byte del gr�fico (1 pixels)

				// para cada pixel del byte leido
//CPC				for (int k = 0; k < 4; k++){
					// obtiene el color del pixel
					*dest=*tileDataVGA;
					tileDataVGA++;
//					*dest = cpc6128->unpackPixelMode1(data, k);
					dest++;
//CPC fin for 4 pixeles empaquetados en un byte				}
				// avanza la posici�n del gr�fico
				tileData++;
			}
			// avanza a la siguiente l�nea del sprite en el buffer de sprites
			dest += despSgteLinea;
		}
	} else {


		// dibuja cada linea del tile
		for (int j = 0; j < 8; j++){
			// repite para 16 bytes (16 pixels)
			for (int i = 0; i < 4; i++){
				// lee un byte del gr�fico (1 pixels)


				// para cada pixel del byte leido
				for (int k = 0; k < 4; k++){
					// obtiene el color del pixel


					// obtiene el color del pixel en el buffer de sprites
					if (*tileDataVGA!=0)
					{
						*dest=*tileDataVGA;
					}
					tileDataVGA++;

					// combina el color del pixel del buffer de sprites con el nuevo
					//*dest = (oldColor & genPant->mascaras[numTabla + 1][color]) | genPant->mascaras[numTabla][color];
					//printf("*dest %d oldColor %d color %d numTabla %d\n",*dest,oldColor,color,numTabla);
					//*dest = 0; // se pinta en azul, el color del fondo
					//*dest = 1;  // se pinta en naranja
					//*dest = 2; // amarillo claro
					// *dest= 3; // negro
					dest++;
				}

				// avanza la posici�n del gr�fico
				tileData++;
			}
			// avanza a la siguiente l�nea del sprite en el buffer de sprites
			dest += despSgteLinea;
		}
	}
#endif
}

/////////////////////////////////////////////////////////////////////////////
// postprocesado de sprites
/////////////////////////////////////////////////////////////////////////////

void MezcladorSprites::postProcesaSprites(Sprite **sprites, int num)
{
	// recorre los sprites y comprueba si hay que dibujar alguno
	for (int i = 0; i < num; i++){
		// si el sprite no es visible, pasa al siguiente
		if (!sprites[i]->esVisible) continue;

		// si el sprite no se ha procesado, pasa al siguiente
		if (!sprites[i]->seHaProcesado) continue;

		QL_MIXDUMP_AREA(sprites, num, sprites[i]);

		// vuelca el buffer del sprite a pantalla, recortando lo que no sea visible
		vuelcaBufferAPantalla(sprites[i]);

		// indica que ya se ha dibujado el sprite
		sprites[i]->haCambiado = false;
		sprites[i]->seHaProcesado = false;

		// si el sprite es de un objeto que desaparece, marca el sprite como inactivo
		if (sprites[i]->desaparece){
			sprites[i]->desaparece = false;
			sprites[i]->esVisible = false;
		}
	}

	// si queda alg�n sprite por procesar lo dibuja
	mezclaSprites(sprites, num);
}

// vuelca el contenido del buffer de sprites a pantalla
void MezcladorSprites::vuelcaBufferAPantalla(Sprite *spr)
{
	int posX = spr->posXTile;
	int posY = spr->posYTile;
	int ancho = spr->anchoFinal;
	int alto = spr->altoFinal;
	int desp = spr->despBuffer;
	int distXSgteLinea = 0;

	// si la posici�n inicial en y est� fuera del �rea visible, sale
	if (posY >= 200) return;

	// comprueba la distancia en y desde el inicio del sprite al inicio de la pantalla
	int distY = posY - 40;

	// si el sprite empieza antes que el inicio de la pantalla, recorta en y
	if (distY < 0){
		distY = -distY;

		// si no se ve ning�na parte del sprite en pantalla, sale
		if (distY >= alto){
			return;
		}

		// recorta la posici�n inicial y el alto
		alto = alto - distY;
		posY = 0;

		// avanza las lineas no visibles del sprite
		desp += spr->anchoFinal*distY*4;
	} else {
		posY = posY - 40;
	}

	// si la posici�n inicial en x est� fuera del �rea visible, sale
	if (posX >= ((32 + 256)/4)) return;

	// comprueba la distancia en x desde el inicio del sprite al inicio de la pantalla
	int distX = posX - (32/4);

	if (distX < 0){
		distX = -distX;

		// si no se ve ning�na parte del sprite en pantalla, sale
		if (distX >= ancho){
			return;
		}

		// recorta la posici�n inicial y el ancho
		ancho = ancho - distX;
		posX = 0;

		// avanza los pixels no visibles del sprite
		desp += distX*4;

		distXSgteLinea += distX*4;
	} else {
		posX = posX - (32/4);
	}

	// si el sprite es m�s ancho que la zona visible de pantalla, lo recorta
	if ((posX + ancho) >= (256/4)){
		distX = posX + ancho - (256/4);
		ancho = ancho - distX;

		distXSgteLinea += distX*4;
	}

	// si el sprite es m�s alto que la zona visible de pantalla, lo recorta
	if ((posY + alto) >= 160){
		distY = posY + alto - 160;
		alto = alto - distY;
	}

	// convierte la posici�n x a pixels
	posX = posX*4 + 32;

	// obtiene un puntero al primer pixel visible
	UINT8 *src = &bufferMezclas[desp];

	// QL: the platform copies the visible part to the play area
#ifdef QL_PACKED_MIX
#ifdef QL_CHARCOL
	ql_blit_plain = spr->qlMask ? 0 : 1;	// no sprite drawn into this area: the plain copy
#endif
	QL_PLAY_BLIT_P(posX, posY, ancho*4, alto, &bufferMezclas[QL_PE(desp >> 2)], (ancho*4 + distXSgteLinea) >> 2);
#else
	ql_play_blit(posX, posY, ancho*4, alto, src, ancho*4 + distXSgteLinea);
#endif
}

/////////////////////////////////////////////////////////////////////////////
// m�todos auxiliares
/////////////////////////////////////////////////////////////////////////////

// comprueba si el sprite a mezclar puede verse en la zona del sprite que se est� dibujando
// si es as� lo recorta al �rea que se est� dibujando y devuelve true. En otro caso, devuelve false
bool MezcladorSprites::recortaSprite(int posVis, int lgtudVis, int pos, int lgtud, int &lgtudClip, int &dist1, int &dist2)
{
	// comprueba que sprite primero
	int dif = posVis - pos;

	// si los 2 sprites empiezan en la misma coordenada
	if (dif == 0){
		dist1 = dist2 = 0;

		lgtudClip = lgtudVis;

		// si la longitud del sprite original es mayor que la longitud del sprite a mezclar, recorta la longitud
		if (lgtudVis > lgtud){
			lgtudClip = lgtud;
		}
	} else if (dif > 0){
		// si el sprite a mezclar empieza antes que el original

		// si el sprite a mezclar termina antes de que empiece el sprite original, queda fuera del �rea visible
		if (dif >= lgtud){
			return false;
		}

		dist1 = 0;
		dist2 = dif;	// distancia del sprite a mezclar al sprite original

		// si el sprite a mezclar termina antes de que lo haga el sprite original, recorta la longitud
		if ((dif + lgtudVis) >= lgtud){
			lgtudClip = lgtud - dif;
		} else {
			// el sprite a mezclar ocupa toda la zona del sprite original, por lo que recorta la longitud
			lgtudClip = lgtudVis; 
		}
	} else {
		// si el sprite original empieza antes que el que hay que mezclar
		dif = -dif;

		// si el sprite a mezclar empieza despu�s de que termine el sprite original, queda fuera del �rea visible
		if (dif >= lgtudVis){
			return false;
		}

		dist1 = dif;	// distancia de la posici�n original al inicio del sprite a mezclar
		dist2 = 0;

		// si el sprite a mezclar no termina antes de que lo haga el sprite original, recorta la longitud
		if ((lgtudVis - dif) <= lgtud){
			lgtudClip = lgtudVis - dif;
		} else {
			// el sprite a mezclar est� contenido en el sprite original
			lgtudClip = lgtud; 
		}
	}

	return true;
}

// comprueba si una posici�n del buffer de tiles es v�lida
bool MezcladorSprites::estaEnBufferTiles(int bufPosX, int bufPosY)
{
	if (bufPosX < 0) return false;
	if (bufPosX >= 16) return false;

	if (bufPosY < 0) return false;
	if (bufPosY >= 20) return false;

	return true;
}

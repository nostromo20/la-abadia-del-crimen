// SpriteMonje.cpp
//
/////////////////////////////////////////////////////////////////////////////

#include "Juego.h"
#include "SpriteMonje.h"
#include "cpc6128.h"
#include "ql_kernels.h"

using namespace Abadia;

/////////////////////////////////////////////////////////////////////////////
// tabla de desplazamientos a los datos gr�ficos de los trajes de los monjes
/////////////////////////////////////////////////////////////////////////////

// CPC (restored for the QL)
int SpriteMonje::despAnimTraje[16] = {
	0x0ab59 + 0x0082,  
	0x0ab59 + 0x0000,
	0x0ab59 + 0x0082,
	0x0ab59 + 0x00fa,
	0x0ab59 + 0x0262,
	0x0ab59 + 0x0172,
	0x0ab59 + 0x0262,
	0x0ab59 + 0x01ef,
	0x16b59 + 0x0262,
	0x16b59 + 0x0172,
	0x16b59 + 0x0262,
	0x16b59 + 0x01ef,
	0x16b59 + 0x0082,
	0x16b59 + 0x0000,
	0x16b59 + 0x0082,
	0x16b59 + 0x00fa
};

#if 0 // VGA (fork)
// VGA
int SpriteMonje::despAnimTraje[16] = {
	61628, // 0x0ab59 + 0x0082,  
	61108, // 0x0ab59 + 0x0000,
	61628, // 0x0ab59 + 0x0082,
	62108, // 0x0ab59 + 0x00fa,
	63548, // 0x0ab59 + 0x0262,
	62588, // 0x0ab59 + 0x0172,
	63548, // 0x0ab59 + 0x0262,
	63088, // 0x0ab59 + 0x01ef,
	63548+120305, // 0x16b59 + 0x0262,
	62588+120305, // 0x16b59 + 0x0172,
	63548+120305, // 0x16b59 + 0x0262,
	63088+120305, // 0x16b59 + 0x01ef,
	61628+120305, // 0x16b59 + 0x0082,
	61108+120305, // 0x16b59 + 0x0000,
	61628+120305, // 0x16b59 + 0x0082,
	62108+120305, // 0x16b59 + 0x00fa
};

#endif
/////////////////////////////////////////////////////////////////////////////
// inicializaci�n y limpieza
/////////////////////////////////////////////////////////////////////////////

SpriteMonje::SpriteMonje()
{
	animacionTraje = 0;
}

SpriteMonje::~SpriteMonje()
{
}


/////////////////////////////////////////////////////////////////////////////
// dibujado de sprites
/////////////////////////////////////////////////////////////////////////////

// CPC (restored for the QL) del sprite actual en el �rea ocupada por el sprite que se le pasa como par�metro
void SpriteMonje::dibuja(Sprite *spr, UINT8 *bufferMezclas, int lgtudClipX, int lgtudClipY, int dist1X, int dist2X, int dist1Y, int dist2Y)
{
	// obtiene los objetos que se usan luego
	UINT8 *roms = elJuego->roms;
	CPC6128 *cpc6128 = elJuego->cpc6128;

	int despSrc;

	// si ya ha pasado la zona de la cabeza, obtiene los gr�ficos de la parte del traje
	if (dist2Y >= 10){
		despSrc = despAnimTraje[animacionTraje] + (dist2Y - 10)*ancho + dist2X;
	} else {
		despSrc = despGfx + dist2Y*ancho + dist2X;
	}

	// calcula la direcci�n de destino de los gr�ficos en el buffer de sprites
	int despDest = spr->despBuffer + (dist1Y*spr->anchoFinal + dist1X)*4;

	// QL: head rows (while dist2Y < 10) from despGfx, the rest from the habit graphics
	int filasCabeza = (dist2Y < 10) ? 10 - dist2Y : 0;
	if (filasCabeza > lgtudClipY) filasCabeza = lgtudClipY;
	if (filasCabeza > 0){
#ifdef QL_PACKED_MIX
#ifdef QL_CHARCOL
		if (char_sep) k_sprite_blit_pm(&bufferMezclas[QL_PE(despDest >> 2)], spr->anchoFinal, &roms[despSrc], ancho, lgtudClipX, filasCabeza);
		else
#endif
		k_sprite_blit_p(&bufferMezclas[QL_PE(despDest >> 2)], spr->anchoFinal, &roms[despSrc], ancho, lgtudClipX, filasCabeza);
#else
		k_sprite_blit(&bufferMezclas[despDest], spr->anchoFinal*4, &roms[despSrc], ancho, lgtudClipX, filasCabeza);
#endif
		despDest += filasCabeza*spr->anchoFinal*4;
		despSrc = despAnimTraje[animacionTraje] + dist2X;
	}
	if (lgtudClipY - filasCabeza > 0){
#ifdef QL_PACKED_MIX
#ifdef QL_CHARCOL
		if (char_sep) k_sprite_blit_pm(&bufferMezclas[QL_PE(despDest >> 2)], spr->anchoFinal, &roms[despSrc], ancho, lgtudClipX, lgtudClipY - filasCabeza);
		else
#endif
		k_sprite_blit_p(&bufferMezclas[QL_PE(despDest >> 2)], spr->anchoFinal, &roms[despSrc], ancho, lgtudClipX, lgtudClipY - filasCabeza);
#else
		k_sprite_blit(&bufferMezclas[despDest], spr->anchoFinal*4, &roms[despSrc], ancho, lgtudClipX, lgtudClipY - filasCabeza);
#endif
	}
#if 0 // pre-kernel C++ loop
	// recorre los pixels visibles en Y
	for (int lgtudY = 0; lgtudY < lgtudClipY; lgtudY++){
		UINT8 *src = &roms[despSrc];
		UINT8 *dest = &bufferMezclas[despDest];

		// recorre los pixels visibles en X
		for (int lgtudX = 0; lgtudX < lgtudClipX; lgtudX++){
			// lee un byte del gr�fico (4 pixels)
			int data = *src;

			// para cada pixel del byte leido
			for (int k = 0; k < 4; k++){
				// obtiene el color del pixel
				int color = cpc6128->unpackPixelMode1(data, k);

				// si no es un pixel transparente lo copia al destino
				if (color != 0){
					*dest = color;
				}
				dest++;
			}
			src++;
		}

		despSrc += ancho;
		despDest += spr->anchoFinal*4;

		dist2Y++;

		// si ya se ha dibujado la cabeza, obtiene los gr�ficos de la parte del traje
		if (dist2Y == 10){
			despSrc = despAnimTraje[animacionTraje] + dist2X;
		}
	}
#endif
}

#if 0 // VGA (fork)
// VGA
// dibuja la parte visible del sprite actual en el �rea ocupada por el sprite que se le pasa como par�metro
void SpriteMonje::dibuja(Sprite *spr, UINT8 *bufferMezclas, int lgtudClipX, int lgtudClipY, int dist1X, int dist2X, int dist1Y, int dist2Y)
{
	// obtiene los objetos que se usan luego
	UINT8 *roms = elJuego->roms + 0x20000-1;

	int despSrc;

	// si ya ha pasado la zona de la cabeza, obtiene los gr�ficos de la parte del traje
	if (dist2Y >= 10){
		despSrc = despAnimTraje[animacionTraje] + (dist2Y - 10)*ancho*4 + dist2X*4;
	} else {
		despSrc = despGfx + dist2Y*ancho*4 + dist2X*4;
	}

	// calcula la direcci�n de destino de los gr�ficos en el buffer de sprites
	int despDest = spr->despBuffer + (dist1Y*spr->anchoFinal + dist1X)*4;

	// recorre los pixels visibles en Y
	for (int lgtudY = 0; lgtudY < lgtudClipY; lgtudY++){
		UINT8 *src = &roms[despSrc];
		UINT8 *dest = &bufferMezclas[despDest];

		// recorre los pixels visibles en X
		for (int lgtudX = 0; lgtudX < lgtudClipX*4; lgtudX++){
			// lee un byte del gr�fico (1 pixel)
			int data = *src++;

			if(data!=255) *dest=data;
			dest++;
		}

		despSrc += ancho*4;
		despDest += spr->anchoFinal*4;

		dist2Y++;

		// si ya se ha dibujado la cabeza, obtiene los gr�ficos de la parte del traje
		if (dist2Y == 10){
			despSrc = despAnimTraje[animacionTraje] + dist2X*4;
		}
	}
}
#endif

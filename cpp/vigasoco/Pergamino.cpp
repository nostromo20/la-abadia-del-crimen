

// Pergamino.cpp
//
/////////////////////////////////////////////////////////////////////////////


#include <cassert>

#include "cpc6128.h"

#include "Juego.h"
#include "Paleta.h"
#include "Pergamino.h"
#include "system.h"
#include "alphabet.h"
#include "GestorFrases.h"
#include "ql_strip.h"

using namespace Abadia;

// QL (CPC): the parchment graphics are drawn with their own pens (the fork remapped them
// to its VGA palette here)
// QL: the CPC's own times (docs/speed_vs_cpc.md: tools/cpctime.py, the original code on a Z80 at
// the CPC's speed, its 300 Hz interrupt included), in hundredths of a millisecond. Before
// 2026-10-05 the port used 8 / 30 / 600 / 1965 / 20 ms (from the disassembly's comments, which
// counted a delay iteration as 10 us instead of 8 us).
enum {
	QLP_TRAZO = 744,		// a stroke (one pixel), stroke to stroke (0x6781-0x67c4 + the key scan)
	QLP_ESPACIO = 2694,		// a space / the end of a character (0x67cd: 3000 x 8 us)
	QLP_LINEA = 53532,		// a new line (0x67de: 60000 x 8 us)
	QLP_PAGINA = 176121,	// the page's wait (0x67f6: 3 x 65536 x 8 us)
	QLP_HOJA = 2657,		// one call of the page-turn animation (0x6697: 2524 ms / 95 calls)
	QLP_FIN = 12000			// the end of the text: waiting for SPACE (no CPC cost; a step's worth)
};
extern int qlFramesPaso;		// ql_game.cpp: the 50 Hz frames the last logic step took
extern "C" int ql_pagina_vieja(void);	// qlhooks.s: header +30 bit 3 (tools/pagetest.py)
extern "C" void ql_play_triangle_old(int x, int y, int lado, int c1, int c2);
// QL: the page turn's lines that already hold the previous animation frame's triangle (only their
// changing ends are written: src/colour.s ql_play_triangle_inc); set by pasaPagina per call
extern "C" void ql_play_triangle_inc(int x, int y, int lado, int c1, int c2, int incDesde, int incHasta);
static int qlIncDesde, qlIncHasta;
#ifdef QL_RELEASE
static const bool qlPaginaVieja = false;	// (the release: no harness, the old paths left out)
#else
static bool qlPaginaVieja;		// this page-turn call by the old per-pixel paths
#endif

int Pergamino::AdaptaColorAPaletaVGA(int a,int b)
{
	return cpc6128->unpackPixelMode1(a, b);
}

Pergamino::Pergamino()
{
	cpc6128 = elJuego->cpc6128;
	roms = elJuego->roms;
	qlOff = false;

	// puntero a la tabla de punteros a los gr???ficos de los caracteres
	// QL: little-endian table of offsets into roms, read byte by byte
	#define QL_CHAROFS(c) (roms[0x680c + 2*(c)] | (roms[0x680c + 2*(c) + 1] << 8))

	for (unsigned char c=0;c<255-0x20;c++) 
	{
		// si el caracter no est??? definido, muestra una 'z'
		TablapTrazosCaracter[c]=roms+QL_CHAROFS('z'-0x20);
	}
	// Recorre desde el caracter 0x21 hasta el 0x126 , apuntando
	// a los datos de la rom original donde se encuentran los
	// datos para dibujar los trazos
	// son los caracteres imprimibles del ASCII
	// a???n as??? algunos no est???n definidos porque el juego original no los usaba
	for (char c='!';c<'~';c++) 
	{
		// si el caracter no est??? definido, dejamos apuntando a la 'z'
		if (QL_CHAROFS(c - 0x20) != 0)
		{
			TablapTrazosCaracter[c-0x20]=roms+QL_CHAROFS(c-0x20);
		}
	}
	// Se a???aden los caracteres usados en las traducciones del remake PC
	// de los textos del pergamino

	//TablapTrazosCaracter['???'-0x20]=charD6; 
	TablapTrazosCaracter[0xD6-0x20]=charD6; 
	//TablapTrazosCaracter['???'-0x20]=charE0;
	TablapTrazosCaracter[0xE0-0x20]=charE0;
	//TablapTrazosCaracter['???'-0x20]=charE1;
	TablapTrazosCaracter[0xE1-0x20]=charE1;
	//TablapTrazosCaracter['???'-0x20]=charE3;
	TablapTrazosCaracter[0xE3-0x20]=charE3;
	//TablapTrazosCaracter['???'-0x20]=charE4;
	TablapTrazosCaracter[0xE4-0x20]=charE4;
	//TablapTrazosCaracter['???'-0x20]=charE7;
	TablapTrazosCaracter[0xE7-0x20]=charE7;
	//TablapTrazosCaracter['???'-0x20]=charE8;
	TablapTrazosCaracter[0xE8-0x20]=charE8;
	//TablapTrazosCaracter['???'-0x20]=charE9;
	TablapTrazosCaracter[0xE9-0x20]=charE9;
	//TablapTrazosCaracter['???'-0x20]=charEA;
	TablapTrazosCaracter[0xEA-0x20]=charEA;
	//TablapTrazosCaracter['???'-0x20]=charEC;
	TablapTrazosCaracter[0xEC-0x20]=charEC;
	//TablapTrazosCaracter['???'-0x20]=charED;
	TablapTrazosCaracter[0xED-0x20]=charED;
	//TablapTrazosCaracter['???'-0x20]=charEF;
	TablapTrazosCaracter[0xEF-0x20]=charEF;
	//TablapTrazosCaracter['???'-0x20]=charF1;
	TablapTrazosCaracter[0xF1-0x20]=charF1;
	//TablapTrazosCaracter['???'-0x20]=charF2;
	TablapTrazosCaracter[0xF2-0x20]=charF2;
	//TablapTrazosCaracter['???'-0x20]=charF3;
	TablapTrazosCaracter[0xF3-0x20]=charF3;
	//TablapTrazosCaracter['???'-0x20]=charF6;
	TablapTrazosCaracter[0xF6-0x20]=charF6;
	//TablapTrazosCaracter['???'-0x20]=charF9;
	TablapTrazosCaracter[0xF9-0x20]=charF9;
	//TablapTrazosCaracter['???'-0x20]=charFA;
	TablapTrazosCaracter[0xFA-0x20]=charFA;
	//TablapTrazosCaracter['???'-0x20]=charFC; 
	TablapTrazosCaracter[0xFC-0x20]=charFC; 

	// En el original, no se usaba la w,
	// as??? que la aprovechaban para la ???
	// aqu??? la ??? est???n en charF1
	// asi que dejamos la w en su sitio, 0x77
	//TablapTrazosCaracter['w'-0x20]=char77; 
	TablapTrazosCaracter[0x77-0x20]=char77; 

	// En la rom original hay muchos caracteres ASCII
	// no definidos
	//TablapTrazosCaracter['''-0x20]=char27; 
	TablapTrazosCaracter[0x27-0x20]=char27; 
	//TablapTrazosCaracter['B'-0x20]=char42; 
	TablapTrazosCaracter[0x42-0x20]=char42; 
	//TablapTrazosCaracter['F'-0x20]=char46; 
	TablapTrazosCaracter[0x46-0x20]=char46; 
	//TablapTrazosCaracter['I'-0x20]=char49; 
	TablapTrazosCaracter[0x49-0x20]=char49; 
	//TablapTrazosCaracter['K'-0x20]=char4B; 
	TablapTrazosCaracter[0x4B - 0x20]=char4B; 
	//TablapTrazosCaracter['N'-0x20]=char4E; 
	TablapTrazosCaracter[0x4E - 0x20]=char4E; 
	//TablapTrazosCaracter['Q'-0x20]=char51; 
	TablapTrazosCaracter[0x51-0x20]=char51; 
	//TablapTrazosCaracter['R'-0x20]=char52; 
	TablapTrazosCaracter[0x52-0x20]=char52; 
	//TablapTrazosCaracter['U'-0x20]=char55; 
	TablapTrazosCaracter[0x55-0x20]=char55; 
	//TablapTrazosCaracter['V'-0x20]=char56; 
	TablapTrazosCaracter[0x56-0x20]=char56; 
	//TablapTrazosCaracter['W'-0x20]=char57; 
	TablapTrazosCaracter[0x57-0x20]=char57; 
	//TablapTrazosCaracter['X'-0x20]=char58; 
	TablapTrazosCaracter[0x58-0x20]=char58; 
	//TablapTrazosCaracter['Z'-0x20]=char5A; 
	TablapTrazosCaracter[0x5A-0x20]=char5A; 
	
	pasaPaginaStep = 1;
	x = 240;
	y = 0;
	dim = 3;
	writing = false;
	num=0;
}

Pergamino::~Pergamino()
{
}

/////////////////////////////////////////////////////////////////////////////
// dibujo del pergamino
/////////////////////////////////////////////////////////////////////////////

// dibuja el pergamino
// the page's drawing: on screen, or (QL_INTRO_DISSOLVE) into the off-screen page
void Pergamino::qlFill(int x, int y, int w, int h, int color)
{
#ifdef QL_INTRO_DISSOLVE
	if (qlOff){ ql_off_fill(x, y, w, h, color); return; }
#endif
	cpc6128->fillMode1Rect(x, y, w, h, color);
}

void Pergamino::qlPixel(int x, int y, int color)
{
#ifdef QL_INTRO_DISSOLVE
	if (qlOff){
		if ((unsigned)x < 320u && (unsigned)y < 200u) ql_off_pixel(x, y, color);
		return;
	}
#endif
	cpc6128->setMode1Pixel(x, y, color);
}

void Pergamino::dibuja()
{
	// limpia la memoria de video	
	qlFill(0, 0, 320, 200, 0);	// QL (CPC 0x65af): pen 0

	// limpia los bordes del rect???ngulo que formar??? el pergamino
	// VGA
	qlFill(0, 0, 64, 200, 1);	// CPC: 0xf0 = pen 1
	qlFill(192 + 64, 0, 64, 200, 1);
	qlFill(0, 192, 320, 8, 1);

	// apunta a los datos del borde superior del pergamino
	UINT8* data = &roms[0x788a];

	// rellena la parte superior del pergamino
	dibujaTiraHorizontal(0, data);

	// rellena la parte derecha del pergamino
	data = &roms[0x7a0a];
	dibujaTiraVertical(248, data);

	// rellena la parte izquierda del pergamino
	data = &roms[0x7b8a];
	dibujaTiraVertical(64, data);

	// rellena la parte inferior del pergamino
	data = &roms[0x7d0a];
	dibujaTiraHorizontal(184, data);
}

// dibuja un borde horizontal del pergamino de 8 pixels de alto
void Pergamino::dibujaTiraHorizontal(int y, UINT8 *data)
{
	// recorre todo el ancho del pergamino
	for (int i = 0; i < 192/4; i++)
	{
		// la parte superior ocupa 8 pixels de alto
		for (int j = 0; j < 8; j++)
		{
			for (int k = 0; k < 4; k++)
			{				
				qlPixel(64 + 4*i + k, j + y, AdaptaColorAPaletaVGA(*data, k));
			}
			data++;
		}
	}
}

// dibuja el pergamino
void Pergamino::dibujaTiraVertical(int x, UINT8 *data)
{
	// recorre el alto del pergamino
	for (int j = 0; j < 192; j++)
	{
		// lee 8 pixels y los escribe en pantalla
		for (int i = 0; i < 2; i++)
		{
			for (int k = 0; k < 4; k++)
			{
				qlPixel(x + 4*i + k, j, AdaptaColorAPaletaVGA(*data, k));
			}
			data++;
		}
	}
}

/////////////////////////////////////////////////////////////////////////////
// escritura de texto en el pergamino
/////////////////////////////////////////////////////////////////////////////
void Pergamino::muestraTexto(const unsigned char *mensaje)
{
	if (writing) {		
		// Tweak to speed up the writing process on the manuscript		
		// QL: as many steps as the CPC does in 130 ms (the fork did a fixed 8 strokes, about
		// half the CPC's speed, and did not wait at line and page ends). CPC timings, Manuel
		// Abadia's disassembly 0x6725-0x6809: stroke ~8 ms, space/character end ~30 ms,
		// new line ~600 ms, page end ~1965 ms before the page turns.
#ifdef QL_PERGAMINO_PASOS	// the pacing before 2026-10-05: 130 ms a step, the costs in ms
		presupuesto += 130;
#else
		// QL: the frames this step took (the real clock; nominal in the harness and the oracle),
		// in CPC hundredths of a millisecond, so the parchment keeps the CPC's own time even when
		// a step overruns
		presupuesto += 2000*qlFramesPaso;
#endif
		while (presupuesto > 0 && !finished){
			coste = QLP_TRAZO;
			dibujaTexto();
			presupuesto -= coste;
		}
	}
	else {
#ifdef QL_INTRO_DISSOLVE
		// QL: the page is composed off-screen while the screen keeps what it shows (the loading
		// screen, or the game at the end), then dissolved in (2x2, ~16 frames). The CPC draws it
		// under a black palette instead.
		ql_off_begin();
		elJuego->paleta->setGamePalette(1);
		qlOff = true;
		dibuja();
		qlOff = false;
		ql_off_dissolve();
		// QL: on the intro only, once the page is up: the text strip under the panel
		if (elJuego->estado == Juego::ESTADO_INTRO) qlsIntro(true);
#else
		// pone la paleta negra
		elJuego->paleta->setGamePalette(0);

		// QL: no hardware palette to hide the drawing under: the parchment's colours are set
		// before it is drawn (it was drawn in the previous palette's colours, then recoloured)
		elJuego->paleta->setGamePalette(1);

		// dibuja el pergamino
		dibuja();
#endif
		// QL: the page is up: the beeper tune starts now (ql_sound.c ql_music_ready)
		ql_music_ready();
		
		// posici???n inicial del texto en el pergamino
		posX = 76;
		posY = 16;
		
		// puntero a la tabla de punteros a los gr???ficos de los caracteres
		charTable = 0;	// QL: not used (see QL_CHAROFS)

		// pone la paleta del pergamino
		elJuego->paleta->setGamePalette(1); //CPC
		writing = true;
		finished = false;
		presupuesto = 0;
		
		texto = mensaje;
		pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
	}
}

void Pergamino::dibujaTexto()
{
	// si se puls??? el bot???n 1 o espacio, termina	
	if (ql_key_down(QK_SPACE)){	// QL: space ends the parchment		
		finished = true;
	} 
	else 
	{
		bool ret = false;		
		switch (*texto)
		{
			case 0x1a:			// f???n de pergamino					
				coste = QLP_FIN;	// QL: nothing more to write, wait for space
				break;
			case 0x0d:			// salto de l???nea					
				if (posY > 148)
				{
					// si hay que pasar p???gina del pergamino					
					// QL: CPC 0x67de (the new line's delay) then 0x67f0 (the page's wait), then the
					// turning page, a frame a call
					coste = ((pasaPaginaStep == 1) && (num == 0)) ? QLP_LINEA + QLP_PAGINA + QLP_HOJA : QLP_HOJA;
					ret = pasaPagina();
					if (ret == false)
					{
						posX = 76;
						posY = 16;
					}						
				}
				else
				{
					posX = 76;
					posY += 16;
					coste = QLP_LINEA;	// QL: CPC 0x67de					
				}
				
				// apunta al siguiente car???cter a imprimir			
				if ((*texto != 0x1a) && !ret){
					texto++;
					pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
				}
				break;
			case 0x20:			// espacio
				posX += 10;
				coste = QLP_ESPACIO;	// QL: CPC 0x67cd					
				if (*texto != 0x1a)
				{
					texto++;
					pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
				}
				break;
			case 0x0a:			// salto de p???gina
				posX = 76;
				posY = 16;								
				coste = ((pasaPaginaStep == 1) && (num == 0)) ? QLP_PAGINA + QLP_HOJA : QLP_HOJA;	// QL: CPC 0x675e -> 0x67f0
				if ((*texto != 0x1a) && (!pasaPagina()))
				{
					texto++;
					pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
				}				
				break;
			default:			// car???cter imprimible
				//UINT8 const * pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
				//pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
				// elige un color dependiendo de si es may???sculas o min???sculas

				// la paleta CPC del pergamino es 07,28,20,12
				// o sea
				// el color 0 es el 07 que es pink
				// el color 1 es el 28 que es red
				// el color 2 es el 20 que es black
				// el color 3 es el 12 que es bright red

				//CPC					int color = (((*texto) & 0x60) == 0x40) ? 3 : 2;
				//Para VGA pongo el color 1?? para las mayusculas y el color 0?? para las minusculas
				int color = (((*texto) & 0x60) == 0x40) ? 3 : 2;	// QL (CPC): capitals pen 3, others pen 2

				// obtiene el desplazamiento a los datos de formaci???n del car???cter
				// transformando del dato nativo en litte_endian
				// al tipo del sistema (si es little_endian no hace nada,
				// y si es big_endian intercambia el orden)
				
				//int charOffset = 0;SDL_SwapLE16(charTable[(*texto) - 0x20]);

				// para alertar si nos hemos dejado algo sin definir
				//if (*texto!='z' && charOffset==SDL_SwapLE16(charTable['z'-0x20])) 	
				//	printf("????????? NOS HEMOS DEJADO ALGUN CARACTER SIN DEFINIR !!! %c\n",*texto);

				// si el caracter no est??? definido, muestra una 'z'
				//if (charTable[(*texto) - 0x20] == 0){
				//	charOffset = SDL_SwapLE16(charTable['z' - 0x20]);
				//}

				
				if ((*pTrazosCaracter & 0xf0) != 0xf0)
				{
					int newPosX = posX+(*pTrazosCaracter & 0x0f);
					int newPosy = posY+((*pTrazosCaracter>>4)&0x0f);

					// dibuja el trazo del car???cter
					cpc6128->setMode1Pixel(newPosX, newPosy, color);
					pTrazosCaracter++;					
				}
				else 
				{				
					// avanza la posici???n hasta el siguiente car???cter
					// posX += roms[charOffset] & 0x0f;
					posX += *pTrazosCaracter & 0x0f;
					coste = QLP_ESPACIO;	// QL: CPC 0x67cd
					if (*texto != 0x1a)
					{
						texto++;
						pTrazosCaracter = TablapTrazosCaracter[(*texto)-0x20];
					}
				}

		}
	}	
}

/////////////////////////////////////////////////////////////////////////////
// paso de p???gina del pergamino
/////////////////////////////////////////////////////////////////////////////
// dibuja un tri???ngulo rect???ngulo de color1 con catetos paralelos a los ejes x e y, y limpia los 4 
//  pixels a la derecha de la hipotenusa del tri???ngulo con el color2
void Pergamino::dibujaTriangulo(int x, int y, int lado, int color1, int color2)
{
	lado = lado*4;

	// QL: the same pixels as the per-pixel loops below, as two row fills per line (pixel by
	// pixel, each page turn took about a minute on a 68008)
	if (qlPaginaVieja) ql_play_triangle_old(x, y, lado, color1, color2);	// (the harness's check)
	else ql_play_triangle_inc(x, y, lado, color1, color2, qlIncDesde, qlIncHasta);	// QL: one platform call
	qlIncDesde = qlIncHasta = 0;
#if 0 // pre-QL per-pixel loops
	for (int j = 0; j < lado; j++)
	{
		// dibuja el tri???ngulo
		for (int i = 0; i <= j; i++)
		{
			cpc6128->setMode1Pixel(x + i, y + j, color1);
		}

		// elimina restos de una ejecuci???n anterior
		for (int i = 0; i < 4; i++)
		{			
			cpc6128->setMode1Pixel(x + j + i + 1, y + j, color2);	// QL: pen 0 (the fork used VGA 255)
		}
	}
#endif
}

// restaura un trozo de 8x8 pixels de la parte superior y otro de la parte derecha del pergamino
void Pergamino::restauraParteSuperiorYDerecha(int x, int y, int lado)
{
	x = x + 4;

	// apunta a los datos borrados del borde superior del pergamino
	UINT8* data = &roms[0x788a + (48 - lado)*4*2];
	if (!qlPaginaVieja){
		// QL: the same CPC bytes as whole 4-pixel groups (column by column: 8 lines of one byte)
		ql_play_blit_p(x, y, 4, 8, data, 1);
		ql_play_blit_p(x + 4, y, 4, 8, data + 8, 1);
		x = 248;
		y = (lado - 3)*4;
		ql_play_blit_p(x, y, 8, 8, &roms[0x7a0a + y*2], 2);	// 8 lines of 2 bytes
		return;
	}

	// 8 pixels de ancho
	for (int i = 0; i < 2; i++)
	{
		// 8 pixels de alto
		for (int j = 0; j < 8; j++)
		{
			for (int k = 0; k < 4; k++)
			{				
				cpc6128->setMode1Pixel(x + 4*i + k, y + j, AdaptaColorAPaletaVGA(*data, k));
			}
			data++;
		}
	}
	x = 248;
	y = (lado - 3)*4;

	// apunta a los datos borrados de la parte derecha del pergamino
	data = &roms[0x7a0a + y*2];

	// 8 pixels de alto
	for (int j = 0; j < 8; j++)
	{
		// 8 pixels de ancho
		for (int i = 0; i < 2; i++)
		{
			for (int k = 0; k < 4; k++)
			{				
				cpc6128->setMode1Pixel(x + 4*i + k, y + j, AdaptaColorAPaletaVGA(*data, k));
			}
			data++;
		}
	}
}

// restaura un trozo de 4x8 pixels de la parte inferior del pergamino
void Pergamino::restauraParteInferior(int x, int y, int lado)
{
	x = 64 + lado*4;
	y = 184;

	// apunta a los datos borrados del borde inferior del pergamino
	UINT8* data = &roms[0x7d0a + lado*4*2];
	if (!qlPaginaVieja){
		ql_play_blit_p(x, y, 4, 8, data, 1);	// QL: 8 lines of one CPC byte
		return;
	}

	// dibuja un trozo de 4x8 pixels de la parte inferior del pergamino
	for (int j = 0; j < 8; j++)
	{
		for (int k = 0; k < 4; k++)
		{			
			cpc6128->setMode1Pixel(x + k, y + j, AdaptaColorAPaletaVGA(*data, k));
		}
		data++;
	}
}

// realiza el efecto de pasar una p???gina del pergamino
bool Pergamino::pasaPagina()
{	
	bool ret = true;
#ifndef QL_RELEASE
	qlPaginaVieja = ql_pagina_vieja() != 0;
#endif
	switch(pasaPaginaStep)
	{
		case 1:
			// step 1
			// realiza el efecto del paso de p???gina desde la esquina superior derecha hasta la mitad de la p???gina
			if (num < 45)
			{
				if (num > 0){ qlIncDesde = 0; qlIncHasta = dim*4 - 4; }	// QL: the lines kept from the previous frame
				dibujaTriangulo(x, y, dim, 3, 0);	// QL: CPC pen 3 (fork VGA colour 1)
				restauraParteSuperiorYDerecha(x, y, dim);

				x = x - 4;
				dim++;
				num++;
				
			}
			else
			{
				pasaPaginaStep = 2;
			}
			break;
		case 2:
			// step 2
			restauraParteSuperiorYDerecha(x, y, dim);
			x = 64;
			y = 4;
			dim = 47;
			num = 0;
			pasaPaginaStep = 3;
			break;
		case 3:	
			// step 3
			// realiza el efecto del paso de p???gina desde la mitad de la p???gina hasta terminar en la esquina inferior izquierda
			if (num < 46)
			{
				if (num > 0){ qlIncDesde = 4; qlIncHasta = dim*4; }	// QL: the lines kept from the previous frame
				dibujaTriangulo(x, y, dim, 3, 0);	// QL: CPC pen 3 (fork VGA colour 1)
				y = y - 4;

				// apunta a los datos borrados del borde izquierdo del pergamino
				UINT8* data = &roms[0x7b8a + y*2];

				// dibuja un trozo de 8x4 de la parte izquierda del pergamino
				if (!qlPaginaVieja) ql_play_blit_p(x, y, 8, 4, data, 2);	// QL: 4 lines of 2 bytes
				else
				for (int j = 0; j < 4; j++)
				{
					for (int i = 0; i < 2; i++)
					{
						for (int k = 0; k < 4; k++)
						{							
							cpc6128->setMode1Pixel(x + 4*i + k, y + j, AdaptaColorAPaletaVGA(*data, k));
						}
						data++;
					}
				}

				// restaura un trozo de 4x8 pixels de la parte inferior del pergamino
				restauraParteInferior(x, y, dim);
				y = y + 8;
				dim--;
				num++;
				
			}
			else 
			{
				pasaPaginaStep = 4;
			}
			break;
		case 4:	
			// step 4
			restauraParteInferior(x, y, 1);
			restauraParteInferior(x, y, 0);
			pasaPaginaStep = 1;
			num = 0;
			x = 240;
			y = 0;
			dim = 3;		
			ret = false;			
			break;
	}
	return ret;
}
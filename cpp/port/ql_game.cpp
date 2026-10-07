// ql_game.cpp -- glue between the platform (QL asm or the PC oracle) and the VIGASOCO logic.
//
// Shared by both builds, so the QL binary and the oracle step identical code.

#include "cpc6128.h"
#include "system.h"

#include "Juego.h"
#include "Logica.h"
#include "GestorFrases.h"
#include "MotorGrafico.h"
#include "Personaje.h"
#include "PersonajeConIA.h"
#include "Puerta.h"
#include "Objeto.h"
#include "Sprite.h"
#include "Pergamino.h"
#include "RejillaPantalla.h"

#include <string.h>
#include "ql_sound.h"
#include "ql_strip.h"

using namespace Abadia;

static System sysObj;
System *const sys = &sysObj;

// the platform supplies the VIGASOCO romsPtr image (0x24000 bytes, writable)
extern "C" unsigned char *ql_rom_image(void);

static CPC6128 *cpc;
static Juego *juego;
static unsigned int ticks;

extern "C" void abadia_init(int intro)
{
	memset(&sysObj, 0, sizeof(sysObj));
	ticks = 0;
	cpc = new CPC6128();
	juego = new Juego(ql_rom_image(), cpc);
	snd_init(juego->roms);
	qlsInicio(juego->roms);			// QL: home drive, settings file, save device (files only)
	juego->preRun(intro != 0);
	if (intro) juego->empiezaIntroduccion();
#ifdef QL_INTRO_DISSOLVE
	if (intro) cpc->discardPanel();		// the loading screen stays until the parchment
	else
#endif
	cpc->flushPanel();
}

#ifndef QL_RELEASE	// (a release build, build_release.sh, has no harness)
extern "C" int ql_harness_night(void);	// qlhooks.s: header +31 bit 5

// harness (header +31 bit 6 on the QL, FORCE_MIRROR on the host), at tick 3: save, open the
// mirror, load the save (the mirror closes again), so the height-grid cache is exercised across
// every kind of height-table write. On the QL, fills of the mirror room's window go through the
// cache between the steps, on a separate RejillaPantalla (the game's own is untouched); with
// header bit 7 every hit is verified against a fresh fill. Game state changes identically on
// both sides (the mirror really opens, then the load restores the saved state).
#ifdef QL_HGRID_CACHE
// the outcome of the sequence, read by tools/hgridtest.py: [0..9] 1 = that fill hit the cache,
// [10] 1 = opening the mirror changed the grid, [11] 1 = after the first load the grid is the
// closed one, [12] 1 = after the second load (a save made with the mirror open) it is the open one
int ql_hg_test[16];
extern unsigned int ql_hg_hits;
static int hgSame(const UINT8 *a, const UINT8 *b)
{
	for (int k = 0; k < 24*24; k++) if (a[k] != b[k]) return 0;
	return 1;
}
static void hgFill(RejillaPantalla *t, int i)
{
	unsigned int h = ql_hg_hits;
	t->qlRellenaVentana(2, 0x1c, 0x5c);	// the mirror's entry {f5 20 62 0b}: floor 2, window x 0x1c, y 0x5c
	ql_hg_test[i] = (ql_hg_hits != h);
}
#endif

static void qlHarnessMirror()
{
#ifdef QL_HGRID_CACHE
	static RejillaPantalla *t = 0;
	static UINT8 closed[24*24], open[24*24];
	if (!t) t = new RejillaPantalla(elMotorGrafico);
	hgFill(t, 0);							// miss (first time)
	hgFill(t, 1);							// hit
	memcpy(closed, &t->bufAlturas[0][0], sizeof closed);
#endif
	juego->guarda();						// the save: mirror closed
	juego->logica->qlHarnessAbreEspejo();
#ifdef QL_HGRID_CACHE
	hgFill(t, 2);							// must miss: the table changed
	hgFill(t, 3);							// hit, of the new data
	memcpy(open, &t->bufAlturas[0][0], sizeof open);
	ql_hg_test[10] = !hgSame(closed, open);
#endif
	juego->carga();							// load: the mirror is closed again
#ifdef QL_HGRID_CACHE
	hgFill(t, 4);							// must miss
	hgFill(t, 5);							// hit
	ql_hg_test[11] = hgSame(closed, &t->bufAlturas[0][0]);
#endif
	// a save made with the mirror OPEN, loaded over a closed mirror: Serializar writes the table
	juego->logica->qlHarnessAbreEspejo();
	juego->guarda();
	juego->logica->qlHarnessCierraEspejo();	// closed again (as a new game would)
#ifdef QL_HGRID_CACHE
	hgFill(t, 6);							// must miss
	hgFill(t, 7);							// hit
#endif
	juego->carga();							// the open mirror comes back from the save
#ifdef QL_HGRID_CACHE
	hgFill(t, 8);							// must miss
	hgFill(t, 9);							// hit
	ql_hg_test[12] = hgSame(open, &t->bufAlturas[0][0]);
#endif
}
#endif	// QL_RELEASE

// QL: the 50 Hz frames since the previous logic step. On the QL the poll's frame counter (the
// real clock); in the harness (header +30 bit 2) and the PC oracle a nominal clock, the step
// schedule (6 frames: 120 ms a step; 6, 7, 6, 7 ... before 2026-10-05), so that both sides see
// the same numbers.
extern "C" int ql_frames_real(void);	// qlhooks.s: the frame counter, or -1 for the nominal clock
unsigned int ql_hg_step;			// abadia_tick's count (RejillaPantalla.cpp ql_hg_prewarm)
int qlFramesPaso;
extern "C" { unsigned char ql_sin_espera; }	// 1: the next step does not wait (src/qlstart.s)
static int ultimoFrame = -1, fasePaso, framesFrase;

static void qlCuentaFrames()
{
	int f = ql_frames_real();
	if (f < 0){
#ifdef QL_PASO_130
		fasePaso ^= 1;
		qlFramesPaso = fasePaso ? 6 : 7;
#else
		qlFramesPaso = 6;
#endif
		return;
	}
	qlFramesPaso = (ultimoFrame < 0) ? 6 : f - ultimoFrame;
	if (qlFramesPaso < 0) qlFramesPaso = 0;
	ultimoFrame = f;
}

extern "C" void abadia_tick(void)
{
	qlCuentaFrames();
	// harness only (header +31 bit 5, as the host's FORCE_NIGHT): night from tick 2, through
	// the real palette change, so the colour checks cover night and the day -> night switch
#ifndef QL_RELEASE
	if (ticks == 2 && ql_harness_night()){
		juego->logica->momentoDia = 0;
		juego->paleta->setGamePalette(3);
	}
	if (ticks == 3 && ql_harness_mirror()) qlHarnessMirror();
#endif
	juego->tick();
	ql_hg_step++;					// (RejillaPantalla.cpp ql_hg_prewarm: a new step, a new scan)
	// QL: the CPC's "no wait" (Logica::qlEspera): src/qlstart.s wait_tick reads it
	ql_sin_espera = (juego->estado == Juego::ESTADO_JUEGO && !juego->logica->qlEspera) ? 1 : 0;
	ticks++;
	cpc->flushPanel();
}

extern "C" void abadia_sync(void)
{
	if (juego->estado == Juego::ESTADO_JUEGO){
#ifdef QL_FRASE_PASOS		// the fork's pacing: one character every 2 logic steps (260 ms)
		elGestorFrases->procesaFraseActual();
#else
		// QL (CPC 0x3b54): one character every 45 interrupts of 300 Hz = 7.5 frames = 150 ms,
		// whatever the logic step takes (counted in half frames)
		framesFrase += 2*qlFramesPaso;
		while (framesFrase >= 15){
			framesFrase -= 15;
			elGestorFrases->avanzaFrase();
		}
#endif
	}
	cpc->flushPanel();
}

#ifdef QL_CHARCOL
// QL_CHARCOL (src/colour.s): after a palette change the screen's terrain is recoloured, but
// characters and panel have colours of their own that the recolour cannot tell apart from the
// terrain's: redraw them. Only during play (palettes 2 and 3, not under the full-screen
// parchment): the visible sprites are redrawn by the mixer in this step, the panel is presented
// again from its pens at the next flush. Pure drawing: no game state changes.
extern "C" void ql_palette_repaint(int pal)
{
	qlsPaleta();				// the strip under the panel: redrawn at the next gameplay step
	if (!juego || (pal != 2 && pal != 3) || cpc->pantallaCompleta) return;
	for (int i = 0; i < Juego::numSprites; i++){
		Sprite *s = juego->sprites[i];
		if (s && s->esVisible) s->haCambiado = true;
	}
	cpc->repaintPanel();
}
#endif

extern "C" int abadia_game_over(void)
{
	return juego->compruebaFinInvestigacion() ? 1 : 0;
}

extern "C" int abadia_ending(void)
{
	return juego->enFinal ? 1 : 0;
}

// ---------------------------------------------------------------------------
// harness: draw one screen on its own and export the tile buffer
// ---------------------------------------------------------------------------

#include "GeneradorPantallas.h"

extern "C" void abadia_show_screen(int n)
{
	juego->motor->dibujaPantallaNumero(n, true);
}

// 20 rows x 16 columns x nivelesProfTiles x (tile, profX, profY)
extern "C" void abadia_tilebuf(unsigned char *out)
{
	GeneradorPantallas *g = juego->motor->genPant;
	for (int y = 0; y < 20; y++){
		for (int x = 0; x < 16; x++){
			for (int k = 0; k < GeneradorPantallas::nivelesProfTiles; k++){
				*out++ = g->bufferTiles[y][x].tile[k];
				*out++ = g->bufferTiles[y][x].profX[k];
				*out++ = g->bufferTiles[y][x].profY[k];
			}
		}
	}
}

// ---------------------------------------------------------------------------
// harness state block (layout documented in tools/state_layout.txt)
// ---------------------------------------------------------------------------

static void put16(unsigned char *p, int v) { p[0] = (v >> 8) & 0xff; p[1] = v & 0xff; }
static void put32(unsigned char *p, unsigned int v) { put16(p, v >> 16); put16(p + 2, v & 0xffff); }

extern "C" void abadia_state(unsigned char *b)
{
	memset(b, 0, STATE_SIZE);
	b[0] = 'A'; b[1] = 'B'; b[2] = 'B'; b[3] = 'Y';
	put32(b + 4, ticks);

	Logica *l = juego->logica;
	b[8] = l->dia;
	b[9] = l->momentoDia;
	b[10] = l->obsequium;
	b[11] = (l->haFracasado ? 1 : 0) | (l->investigacionCompleta ? 2 : 0) | (l->espejoCerrado ? 4 : 0)
		| (l->usandoLampara ? 8 : 0) | (l->lamparaDesaparecida ? 16 : 0) | (elGestorFrases->mostrandoFrase ? 32 : 0);
	put16(b + 12, l->duracionMomentoDia);
	put16(b + 14, l->bonus);
	MotorGrafico *m = juego->motor;
	b[16] = m->numPantalla;
	b[17] = m->oriCamara;
	b[18] = l->numPersonajeCamara;
	b[19] = l->mascaraPuertas;
	b[240] = juego->estado;
	{
		// parchment progress: page-turn step, offset of the text pointer
		Pergamino *p = juego->pergamino;
		const unsigned char *t0 = (juego->estado == Juego::ESTADO_FINAL) ? Pergamino::pergaminoFinal[juego->idioma]
			: Pergamino::pergaminoInicio[juego->idioma];
		b[241] = p->pasaPaginaStep;
		put16(b + 242, p->writing ? (int)(p->texto - t0) : 0);
		b[244] = p->writing ? *p->texto : 0;
	}

	// characters: 8 x 8 bytes from +20
	for (int i = 0; i < Juego::numPersonajes; i++){
		Personaje *p = juego->personajes[i];
		unsigned char *q = b + 20 + i*8;
		q[0] = p->posX; q[1] = p->posY; q[2] = p->altura; q[3] = p->orientacion;
		q[4] = p->estado; q[5] = p->contadorAnimacion; q[6] = p->objetos;
		q[7] = (p->bajando ? 1 : 0) | (p->enDesnivel ? 2 : 0) | (p->giradoEnDesnivel ? 4 : 0) | (p->flipX ? 8 : 0);
	}

	// doors: 7 x 4 bytes from +84
	for (int i = 0; i < Juego::numPuertas; i++){
		Puerta *d = juego->puertas[i];
		unsigned char *q = b + 84 + i*4;
		q[0] = d->orientacion; q[1] = d->estaAbierta ? 1 : 0; q[2] = d->posX; q[3] = d->posY;
	}

	// objects: 8 x 4 bytes from +112
	for (int i = 0; i < Juego::numObjetos; i++){
		Objeto *o = juego->objetos[i];
		unsigned char *q = b + 112 + i*4;
		int quien = 0xff;
		for (int k = 0; k < Juego::numPersonajes; k++){
			if (o->personaje == juego->personajes[k]) quien = k;
		}
		q[0] = o->posX; q[1] = o->posY; q[2] = o->altura; q[3] = o->seHaCogido ? quien : 0xfe;
	}

	// sprites: 24 x 4 bytes from +144 (visible flag, x in 4-px units, y, depth)
	for (int i = 0; i < Juego::numSprites && i < 24; i++){
		Sprite *s = juego->sprites[i];
		unsigned char *q = b + 144 + i*4;
		q[0] = s->esVisible ? 1 : 0; q[1] = s->posXPant; q[2] = s->posYPant; q[3] = s->profundidad;
	}
}

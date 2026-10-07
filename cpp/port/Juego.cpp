// Juego.cpp -- QL replacement for the fork's Juego.cpp.
//
// Kept from the fork (CPC paths): entity creation, flipped-graphics generation, the
// ordering of Juego::run(), actualizaLuz(). Removed: menus, VGA graphics, SDL, config/save
// files, information mode. The end-of-investigation screen is reduced to a flag the
// platform polls (step 7 of the QL plan).

#include "cpc6128.h"

#include "Abad.h"
#include "Adso.h"
#include "Berengario.h"
#include "Bernardo.h"
#include "BuscadorRutas.h"
#include "GestorFrases.h"
#include "Guillermo.h"
#include "Jorge.h"
#include "Juego.h"
#include "Logica.h"
#include "Malaquias.h"
#include "Marcador.h"
#include "Monje.h"
#include "MotorGrafico.h"
#include "Objeto.h"
#include "Personaje.h"
#include "PersonajeConIA.h"
#include "Pergamino.h"
#include "Serializar.h"
#include "Puerta.h"
#include "RejillaPantalla.h"
#include "Severino.h"
#include "Sprite.h"
#include "SpriteLuz.h"
#include "SpriteMonje.h"
#include "system.h"
#include "ql_port.h"
#include "ql_strip.h"

#include <string.h>

using namespace Abadia;

Juego::Juego(UINT8 *romData, CPC6128 *cpc)
{
	idioma = QL_IDIOMA;
	GraficosCPC = true;
	modoInformacion = false;
	pausa = false;
	enFinal = false;
	qlMsg = 0;				// QL: no save/load message
	qlMsgSteps = 0;
	qlMsgShown = false;
	estado = ESTADO_JUEGO;
	teclaGuardar = teclaCargar = false;

	// the image starts with the 0x4000 bytes of the title screen, as in VIGASOCO
	roms = romData + 0x4000;
	cpc6128 = cpc;

	for (int i = 0; i < numSprites; i++) sprites[i] = 0;
	for (int i = 0; i < numPersonajes; i++) personajes[i] = 0;
	for (int i = 0; i < numPuertas; i++) puertas[i] = 0;
	for (int i = 0; i < numObjetos; i++) objetos[i] = 0;

	paleta = new Paleta();
	motor = new MotorGrafico(buffer, 8192);
	marcador = new Marcador();
	logica = new Logica(roms, buffer, 8192);
	pergamino = new Pergamino();
}

// ---------------------------------------------------------------------------
// QL state machine: intro parchment -> game -> end of investigation / ending parchment
// ---------------------------------------------------------------------------

void Juego::empiezaIntroduccion()
{
	estado = ESTADO_INTRO;
	pergamino->writing = false;
	pergamino->finished = false;
	cpc6128->pantallaCompleta = true;
	sys->playMusic(START);
}

// the fork's muestraPantallaFinInvestigacion() text, in the play area
void Juego::muestraFinInvestigacion()
{
	static const char *frase1[2] = { "HAS RESUELTO EL", "YOU HAVE SOLVED" };
	static const char *frase2[2] = { "XX POR CIENTO DE", "XX  PER  CENT" };
	static const char *frase3[2] = { "LA INVESTIGACION", "OF THE RESEARCH" };
	static const char *frase4[2] = { "PULSA ESPACIO", "PRESS SPACE" };
	int i = (idioma == 0) ? 0 : 1;
	char porcentaje[20];
	int k;
	for (k = 0; frase2[i][k] && k < 19; k++) porcentaje[k] = frase2[i][k];
	porcentaje[k] = 0;
	int porc = logica->calculaPorcentajeMision();
	porcentaje[0] = ((porc/10) % 10) + 0x30;
	porcentaje[1] = (porc % 10) + 0x30;

	limpiaAreaJuego(3);
	const char *lineas[4] = { frase1[i], porcentaje, frase3[i], frase4[i] };
	static const int ys[4] = { 32, 48, 64, 128 };
	for (k = 0; k < 4; k++){
		int n = 0;
		while (lineas[k][n]) n++;
		marcador->imprimeFrase(lineas[k], (320 - n*8)/2, ys[k], 2, 3);
	}
}

// save/load through the fork's Serializar (text format, QL memory streams)
static char bufferPartida[24*1024];
// QL: the game as it was before a load, put back if the save turns out corrupt (a save is ~7 KB)
static char bufferRespaldo[12*1024];

// QL: save/load messages (the panel's phrase area, the game's font: letters and spaces only)
enum { QLM_GUARDADA, QLM_ERROR_GUARDAR, QLM_NO_HAY, QLM_CARGADA, QLM_ERROR_CARGAR };
static const char *qlMensajes[2][5] = {
#ifdef QL_SOLO_INGLES		// (the English-only release)
	{ "", "", "", "", "" },
#else
	{ "PARTIDA GRABADA", "ERROR AL GRABAR", "NO HAY PARTIDA", "PARTIDA CARGADA", "ERROR AL CARGAR" },
#endif
	{ "GAME SAVED", "SAVE FAILED", "NO SAVED GAME", "GAME LOADED", "LOAD FAILED" }
};

// QL: the save/load messages are in the text strip under the panel (ql_strip.cpp); the
// versions in the panel's phrase area (fdc7872) are kept under QL_MSG_FRASES (not defined)
void Juego::guarda()
{
	QLOut out(bufferPartida, sizeof(bufferPartida));
	out << logica;
#ifdef QL_MSG_FRASES
	int ok = 0;
	if (!out.fail()) ok = (ql_file_save(bufferPartida, out.len) == (int)out.len);
	qlMensaje(ok ? QLM_GUARDADA : QLM_ERROR_GUARDAR);
#else
	// "SAVING TO <DEV>..." before the write, then the outcome, on the chosen save device
	qlsGuardar(bufferPartida, out.fail() ? -1 : (int)out.len, paleta->actual);
#endif
}

void Juego::carga()
{
#ifdef QL_MSG_FRASES
	int n = ql_file_load(bufferPartida, sizeof(bufferPartida));
	if (n <= 0){
		qlMensaje(QLM_NO_HAY);		// nothing loaded: the game goes on untouched
		return;
	}
#else
	int n = qlsCargar(bufferPartida, sizeof(bufferPartida), paleta->actual);
	if (n <= 0) return;				// nothing loaded (message shown): the game goes on untouched
#endif
	// QL: keep the game as it is, in case the save is corrupt or from another version
	QLOut respaldo(bufferRespaldo, sizeof(bufferRespaldo));
	respaldo << logica;
	QLIn in(bufferPartida, n);
	in >> logica;
	if (in.fail()){
		if (!respaldo.fail()){
			// QL: back to the game as it was before the load
			QLIn r(bufferRespaldo, respaldo.len);
			r >> logica;
		} else {
			// as the fork: the game may be half-loaded, start again
			logica->inicia();
		}
#ifdef QL_MSG_FRASES
		qlMensaje(QLM_ERROR_CARGAR);
#else
		qlsCargado(false);
#endif
	} else {
#ifdef QL_MSG_FRASES
		qlMensaje(QLM_CARGADA);
#else
		qlsCargado(true);
#endif
	}
	paleta->setGamePalette(2);
	reiniciaPantalla();
}

void Juego::tick()
{
	switch (estado){
		case ESTADO_INTRO:
			pergamino->muestraTexto(Pergamino::pergaminoInicio[idioma]);
			if (pergamino->finished){
				pergamino->writing = false;
				cpc6128->pantallaCompleta = false;
				sys->stopMusic();
				// CPC 0x24ef: the black palette first, so the parchment is not shown in the game's
				// colours (QL: palette 0 blanks the screen, and the next palette needs no recolour)
				paleta->setGamePalette(0);
				paleta->setGamePalette(2);
#if 0	// QL: reiniciaPantalla clears the play area, after the panel
				limpiaAreaJuego(0);
#endif
				marcador->limpiaAreaMarcador();	// clears the parchment from the panel lines too
				reiniciaPantalla();
				qlsIntro(false);			// QL: "PRESS SPACE TO CONTINUE" goes
				estado = ESTADO_JUEGO;
			}
			break;

		case ESTADO_JUEGO:
			// QL: F1 saves, F2 loads (the fork had menus for this)
			if (ql_key_down(QK_F1) && !teclaGuardar) guarda();
			if (ql_key_down(QK_F2) && !teclaCargar) carga();
			teclaGuardar = ql_key_down(QK_F1) != 0;
			teclaCargar = ql_key_down(QK_F2) != 0;
			run();
#ifdef QL_MSG_FRASES
			qlActualizaMensaje();
#endif
			qlsJuego(paleta->actual);		// QL: the strip (drawn only when it changes)
			if (compruebaFinInvestigacion()){
				qlsFueraDeJuego();
				muestraFinInvestigacion();
				estado = ESTADO_FIN_INVESTIGACION;
			} else if (enFinal){
				qlsFueraDeJuego();
				estado = ESTADO_FINAL;
				pergamino->writing = false;
				pergamino->finished = false;
				cpc6128->pantallaCompleta = true;
				sys->playMusic(END);
			}
			break;

		case ESTADO_FIN_INVESTIGACION:
			if (ql_key_down(QK_SPACE)){
				// a new game, as the fork's "new game" does
				logica->inicia();
				paleta->setGamePalette(2);
				reiniciaPantalla();
				estado = ESTADO_JUEGO;
			}
			break;

		case ESTADO_FINAL:
			// the ending parchment stays until ESC leaves the QL program
			pergamino->muestraTexto(Pergamino::pergaminoFinal[idioma]);
			if (pergamino->finished) pergamino->finished = false;
			break;
	}
}

// clears the play area to an ink and the CPC side borders to black (the QL has no borders)
// QL: a save/load message, shown when the phrase area is free (a game phrase has priority)
void Juego::qlMensaje(int cual)
{
	qlMsg = qlMensajes[(idioma == 0) ? 0 : 1][cual];
	qlMsgSteps = 15;				// ~2 s
	qlMsgShown = false;
}

// once a step, after the logic: display only (no game state changes)
void Juego::qlActualizaMensaje()
{
	if (!qlMsg) return;
	if (logica->gestorFrases->mostrandoFrase){
		// a game phrase is showing: ours waits; if ours was up, the phrase scrolls it out
		if (qlMsgShown) qlMsg = 0;
		return;
	}
	if (!qlMsgShown){
		int n = 0;
		while (qlMsg[n]) n++;
		marcador->limpiaAreaFrases();
		marcador->imprimeFrase(qlMsg, 96 + (128 - 8*n)/2, 164, 2, 3);
		qlMsgShown = true;
		return;
	}
	if (--qlMsgSteps <= 0){
		marcador->limpiaAreaFrases();
		qlMsg = 0;
	}
}

void Juego::limpiaAreaJuego(int color)
{
	cpc6128->fillMode1Rect(32, 0, 256, 160, color);
}

void Juego::muestraFinal()
{
	enFinal = true;
}

void Juego::reiniciaPantalla()
{
	// QL: the whole panel first (into its buffer, shown at the next flush), then the play
	// area, so the two appear together (the play area showed ~1.5 s before the panel)
	marcador->dibujaMarcador();

	// forces the screen to be redrawn
	motor->posXPantalla = motor->posYPantalla = -1;

	marcador->dibujaObjetos(personajes[0]->objetos, 0xff);
	marcador->muestraDiaYMomentoDia();
	marcador->decrementaObsequium(0);
	marcador->limpiaAreaFrases();
	// QL: black (pen 3) until the room is built from the centre at the next step (as
	// GeneradorPantallas::limpiaPantalla), not a pen 0 (cyan/blue) flash
	if (ql_espiral() && !cpc6128->pantallaCompleta) ql_play_black();
	else limpiaAreaJuego(0);
}

void Juego::preRun(bool intro)
{
	marcador->limpiaAreaMarcador();

	creaEntidadesJuego();
	generaGraficosFlipeados();
	motor->personaje = personajes[0];
	logica->despHabitacionEspejo();
	logica->inicia();

	marcador->limpiaAreaMarcador();
	logica->inicia();
	// QL: with the intro to follow, the game screen is drawn when the intro ends (as on the CPC,
	// which goes straight to the parchment); drawing it here showed the play area in the game's
	// colours for ~1.5 s between the loading screen and the parchment
	if (intro) return;
	paleta->setGamePalette(2);
	reiniciaPantalla();
}

// the fork's muestraPantallaFinInvestigacion() without the text screen: true while the
// game is over (the platform shows the result and restarts)
bool Juego::compruebaFinInvestigacion()
{
	if (!logica->haFracasado) return false;

	// the camera follows guillermo straight away
	laLogica->numPersonajeCamara = 0x80;

	// waits for the current phrase to finish
	if (elGestorFrases->mostrandoFrase) return false;

	return true;
}

// one logic step (Juego::run of the fork, information mode removed)
void Juego::run()
{
	elBuscadorDeRutas->contadorAnimGuillermo = laLogica->guillermo->contadorAnimacion;

	ql_phase(0x10);
	logica->compruebaAbreEspejo();
	logica->actualizaVariablesDeTiempo();

	if (compruebaFinInvestigacion()) return;

	ql_phase(0x11);
	logica->compruebaLecturaLibro();
	marcador->realizaScrollMomentoDia();
	ql_phase(0x12);
	logica->ejecutaAccionesMomentoDia();
	logica->compruebaBonusYCambiosDeCamara();
	ql_phase(0x13);
	motor->compruebaCambioPantalla();
	ql_phase(0x14);
	logica->compruebaCogerDejarObjetos();
	logica->compruebaAbrirCerrarPuertas();

	for (int i = 0; i < numPersonajes; i++){
		ql_phase(0x20 + i);		// character i
		personajes[i]->run();
	}

	ql_phase(0x16);
	logica->buscRutas->generadoCamino = false;

	actualizaLuz();

	// if guillermo or adso are in front of the mirror, shows their reflection
	laLogica->realizaReflejoEspejo();

	ql_phase(0x17);
	motor->dibujaPantalla();
	ql_phase(0x18);
	motor->dibujaSprites();

	if (laLogica->guillermo->contadorAnimacion == 1){
		ql_phase(0x19);
		sys->playSound(STEPS);
	}
	ql_phase(0x1a);
}

// flips in x every graphic that needs it (CPC version of the fork's generaGraficosFlipeados)
void Juego::generaGraficosFlipeados()
{
	UINT8 tablaFlipX[256];

	for (int i = 0; i < 256; i++){
		int pixel0 = cpc6128->unpackPixelMode1(i, 0);
		int pixel1 = cpc6128->unpackPixelMode1(i, 1);
		int pixel2 = cpc6128->unpackPixelMode1(i, 2);
		int pixel3 = cpc6128->unpackPixelMode1(i, 3);

		int data = 0;
		data = cpc6128->packPixelMode1(data, 0, pixel3);
		data = cpc6128->packPixelMode1(data, 1, pixel2);
		data = cpc6128->packPixelMode1(data, 2, pixel1);
		data = cpc6128->packPixelMode1(data, 3, pixel0);

		tablaFlipX[i] = data;
	}

	// guillermo
	flipeaGraficos(tablaFlipX, &roms[0x0a300], &roms[0x16300], 5, 0x366);
	flipeaGraficos(tablaFlipX, &roms[0x0a666], &roms[0x16666], 4, 0x084);

	// adso
	flipeaGraficos(tablaFlipX, &roms[0x0a6ea], &roms[0x166ea], 5, 0x1db);
	flipeaGraficos(tablaFlipX, &roms[0x0a8c5], &roms[0x168c5], 4, 0x168);

	// monks' habits
	flipeaGraficos(tablaFlipX, &roms[0x0ab59], &roms[0x16b59], 5, 0x2d5);

	// monks' faces
	flipeaGraficos(tablaFlipX, &roms[0x0b103], &roms[0x17103], 5, 0x2bc);

	// doors
	flipeaGraficos(tablaFlipX, &roms[0x0aa49], &roms[0x16a49], 6, 0x0f0);
}

void Juego::flipeaGraficos(UINT8 *tablaFlip, UINT8 *src, UINT8 *dest, int ancho, int bytes)
{
	memcpy(dest, src, bytes);

	int numLineas = bytes/ancho;
	int numIntercambios = (ancho + 1)/2;

	for (int j = 0; j < numLineas; j++){
		UINT8 *ptr1 = dest;
		UINT8 *ptr2 = ptr1 + ancho - 1;

		for (int i = 0; i < numIntercambios; i++){
			UINT8 aux = *ptr1;
			*ptr1 = tablaFlip[*ptr2];
			*ptr2 = tablaFlip[aux];

			ptr1++;
			ptr2--;
		}

		dest = dest + ancho;
	}
}

// the light sprite follows adso (unchanged from the fork)
void Juego::actualizaLuz()
{
	sprites[spriteLuz]->esVisible = false;

	if (motor->pantallaIluminada) return;

	if (!(personajes[1]->sprite->esVisible)){
		for (int i = 0; i < numSprites; i++){
			if (sprites[i]->esVisible){
				sprites[i]->haCambiado = false;
			}
		}
		return;
	}

	SpriteLuz *sprLuz = (SpriteLuz *) sprites[spriteLuz];
	sprLuz->ajustaAPersonaje(personajes[1]);
}

// creates the sprites, characters, doors and objects (CPC graphics offsets)
void Juego::creaEntidadesJuego()
{
	sprites[0] = new Sprite();
	sprites[1] = new Sprite();

	for (int i = 2; i < 8; i++){
		sprites[i] = new SpriteMonje();
	}

	for (int i = primerSpritePuertas; i < primerSpritePuertas + numPuertas; i++){
		sprites[i] = new Sprite();
		sprites[i]->ancho = sprites[i]->oldAncho = 0x06;
		sprites[i]->alto = sprites[i]->oldAlto = 0x28;
	}

	static const int despObjetos[8] = { 0x88f0, 0x9fb0, 0x9f80, 0xa010, 0x9fe0, 0x9fe0, 0x9fe0, 0x88c0 };

	for (int i = primerSpriteObjetos; i < primerSpriteObjetos + numObjetos; i++){
		sprites[i] = new Sprite();
		sprites[i]->ancho = sprites[i]->oldAncho = 0x04;
		sprites[i]->alto = sprites[i]->oldAlto = 0x0c;
		sprites[i]->despGfx = despObjetos[i - primerSpriteObjetos];
	}

	sprites[spritesReflejos] = new Sprite();
	sprites[spritesReflejos + 1] = new Sprite();

	sprites[spriteLuz] = new SpriteLuz();

	personajes[0] = new Guillermo(sprites[0]);
	personajes[1] = new Adso(sprites[1]);
	personajes[2] = new Malaquias((SpriteMonje *)sprites[2]);
	personajes[3] = new Abad((SpriteMonje *)sprites[3]);
	personajes[4] = new Berengario((SpriteMonje *)sprites[4]);
	personajes[5] = new Severino((SpriteMonje *)sprites[5]);
	personajes[6] = new Jorge((SpriteMonje *)sprites[6]);
	personajes[7] = new Bernardo((SpriteMonje *)sprites[7]);

	for (int i = 0; i < 8; i++){
		personajes[i]->despX = -2;
		personajes[i]->despY = -34;
	}
	personajes[1]->despY = -32;

	for (int i = 0; i < numPuertas; i++){
		puertas[i] = new Puerta(sprites[primerSpritePuertas + i]);
	}

	for (int i = 0; i < numObjetos; i++){
		objetos[i] = new Objeto(sprites[primerSpriteObjetos + i]);
	}
}

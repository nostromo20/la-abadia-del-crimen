// Juego.h -- QL replacement for the fork's Juego (menus, VGA, SDL, config and save files
// removed). Keeps the fields and methods the logic classes use, the entity creation and the
// per-tick ordering of Juego::run().
#ifndef __ABADIA_JUEGO_H__
#define __ABADIA_JUEGO_H__

#include "Singleton.h"
#include "Types.h"
#include "Paleta.h"

class CPC6128;

namespace Abadia {

class Logica;
class Marcador;
class MotorGrafico;
class Objeto;
class Personaje;
class Puerta;
class Sprite;
class Pergamino;

#define elJuego Juego::getSingletonPtr()

class Juego : public Singleton<Juego>
{
public:
	static const int numPersonajes = 8;
	static const int numPuertas = 7;
	static const int numObjetos = 8;

	static const int primerSpritePersonajes = 0;
	static const int primerSpritePuertas = primerSpritePersonajes + numPersonajes;
	static const int primerSpriteObjetos = primerSpritePuertas + numPuertas;
	static const int spritesReflejos = primerSpriteObjetos + numObjetos;
	static const int spriteLuz = spritesReflejos + 2;
	static const int numSprites = spriteLuz + 1;

	int idioma;						// 0 Spanish, 1 English (the QL build keeps only these two)
	bool GraficosCPC;				// always true on the QL
	bool modoInformacion;			// always false on the QL
	bool pausa;
	bool enFinal;					// the ending parchment has been requested

	enum { ESTADO_INTRO, ESTADO_JUEGO, ESTADO_FIN_INVESTIGACION, ESTADO_FINAL };
	int estado;						// QL: what abadia_tick does (the fork's state machine, reduced)
	Pergamino *pergamino;

	CPC6128 *cpc6128;
	Paleta *paleta;
	UINT8 buffer[8192];				// sprite mixing buffer / route-finder buffer
	UINT8 *roms;					// VIGASOCO "roms" image (romsPtr + 0x4000)
	Logica *logica;
	Marcador *marcador;
	MotorGrafico *motor;

	Sprite *sprites[numSprites];
	Puerta *puertas[numPuertas];
	Objeto *objetos[numObjetos];
	Personaje *personajes[numPersonajes];

	void limpiaAreaJuego(int color);
	void muestraFinal();
	void reiniciaPantalla();

	void preRun(bool intro = false);
	void run();
	void tick();					// one 130 ms step of whatever the current state is
	void empiezaIntroduccion();
	void muestraFinInvestigacion();
	void guarda();
	void carga();
	// QL: save/load feedback in the panel's phrase area (display only)
	const char *qlMsg;				// the message waiting or showing, 0 = none
	int qlMsgSteps;				// steps it stays up
	bool qlMsgShown;
	void qlMensaje(int cual);
	void qlActualizaMensaje();
	bool teclaGuardar, teclaCargar;		// previous state of F1/F2 (act on the press)
	bool compruebaFinInvestigacion();

	Juego(UINT8 *romData, CPC6128 *cpc);

protected:
	void creaEntidadesJuego();
	void actualizaLuz();
	void generaGraficosFlipeados();
	void flipeaGraficos(UINT8 *tablaFlip, UINT8 *src, UINT8 *dest, int ancho, int bytes);
};

}

#endif

// RejillaPantalla.cpp
//
/////////////////////////////////////////////////////////////////////////////
#include <cassert>
#include "cpc6128.h"
#include "MotorGrafico.h"
#include "Juego.h"
#include "Personaje.h"
#include "RejillaPantalla.h"
#include "ql_kernels.h"

using namespace Abadia;

/////////////////////////////////////////////////////////////////////////////
// inicializaciï¿½n y limpieza
/////////////////////////////////////////////////////////////////////////////

RejillaPantalla::RejillaPantalla(MotorGrafico *motorGrafico)
{
	roms = elJuego->roms;
	motor = motorGrafico;
}

RejillaPantalla::~RejillaPantalla()
{
}

/////////////////////////////////////////////////////////////////////////////
// tabla para el cï¿½lculo del avance segï¿½n las posiciones que ocupa el personaje
/////////////////////////////////////////////////////////////////////////////

int RejillaPantalla::calculoAvancePosicion[4][8] = {
	{  0, +1,   -1,  0,   +1, -2,   +2, -1 },
	{ +1,  0,    0, +1,   -2, -2,   -1, -2 },
	{  0, -1,   +1,  0,   -2, +1,   -2, +1 },
	{ -1,  0,    0, -1,   +1, +1,   +1, +2 }
};

/////////////////////////////////////////////////////////////////////////////
// 
/////////////////////////////////////////////////////////////////////////////


// dada la posiciï¿½n de un personaje, calcula los mï¿½nimos valores visibles del ï¿½rea de juego
void RejillaPantalla::calculaMinimosValoresVisibles(Personaje *pers)
{
	minPosX = (pers->posX & 0xf0) - 4;
	minPosY = (pers->posY & 0xf0) - 4;
	minAltura = motor->obtenerAlturaBasePlanta(pers->altura);
}

// dado un personaje, rellena la rejilla con la informaciï¿½n de altura de la planta recortada para la pantalla
void RejillaPantalla::rellenaAlturasPantalla(Personaje *pers)
{
#ifdef QL_HGRID_CACHE
	// QL: the fill (asm) through a cache of clean grids (qlRellenaVentana)
	calculaMinimosValoresVisibles(pers);
	qlRellenaVentana(motor->obtenerPlanta(minAltura), minPosX, minPosY);
	return;
#endif
#ifdef QL_ASM_GRID
	// QL: the clear and the block loop below in asm (src/grid.s)
	calculaMinimosValoresVisibles(pers);
	{
		static const int datosPlanta[] = { 0x18a00, 0x18f00, 0x19080 };
		a_rellena_alturas(&bufAlturas[0][0], &roms[datosPlanta[motor->obtenerPlanta(minAltura)]], minPosX, minPosY);
	}
	return;
#endif
	// limpia la matriz de alturas
	for (int j = 0; j < 24; j++){
		for (int i = 0; i < 24; i++){
			bufAlturas[j][i] = 0;
		}
	}

	// obtiene los mï¿½nimos valores visibles para la pantalla en la que se encuentra el personaje
	calculaMinimosValoresVisibles(pers);

	// halla el desplazamiento a los datos de la altura para la planta en la que se encuentra el personaje
	int datosAlturaPlanta[] = { 0x18a00, 0x18f00, 0x19080 };
	UINT8 *datosAltura = &roms[datosAlturaPlanta[motor->obtenerPlanta(minAltura)]];

	// mientras queden datos de altura de la planta
	while ((*datosAltura) != 0xff){
		int tipoBloque = datosAltura[0];

		// si el bloque no es de un tipo conocido, sale
		if (((tipoBloque & 0x07) == 0) || ((tipoBloque & 0x07) >= 6)){
			break;
		}

		int lgtudX = datosAltura[3];
		int lgtudY = datosAltura[4];

		// si la entrada no es de 5 bytes, la longitud se codifica en 4 bits en vez de en 8
		if ((tipoBloque & 0x08) == 0){
			lgtudY = lgtudX & 0x0f;
			lgtudX = (lgtudX >> 4) & 0x0f;
		}
	
		int altura = (tipoBloque >> 4) & 0x0f;
		int posX = datosAltura[1];
		int posY = datosAltura[2];

		// avanza a la siguiente entrada
		if ((tipoBloque & 0x08) == 0){
			datosAltura += 4;
		} else {
			datosAltura += 5;
		}

		lgtudX++;
		lgtudY++;

		// rechaza los bloques que estï¿½n completamente fuera de la zona de pantalla

		// halla la distancia en x entre las coordenadas
		int distX = posX - minPosX;

		// si el bloque empieza antes que el rectï¿½ngulo de recorte
		if (distX < 0){
			// si el bloque termina antes de que empiece la zona visible
			if (-distX >= lgtudX){
				continue;
			}
		} else if (distX >= 24){
			// si el bloque empieza despuï¿½s de que termine la zona visible
			continue;
		}

		// halla la distancia en y entre las coordenadas
		int distY = posY - minPosY;

		// si el bloque empieza antes que el rectï¿½ngulo de recorte
		if (distY < 0){
			// si el bloque termina antes de que empiece la zona visible
			if (-distY >= lgtudY){
				continue;
			}
		} else if (distY >= 24){
			// si el bloque empieza despuï¿½s de que termine la zona visible
			continue;
		}

		// si llega hasta aquï¿½, alguna parte del bloque es visible, por lo que modifica el buffer de alturas

		// segï¿½n el tipo de bloque, fija los datos de la altura
		if ((tipoBloque & 0x07) != 5){
			static int incrementos[4][2] = {
				{  1,  0 },
				{  0, -1 },
				{ -1,  0 },
				{  0,  1 }
			};

			// modifica la tabla de alturas con los datos del bloque
			for (int j = 0; j < lgtudY; j++){
				int oldAltura = altura;

				for (int i = 0; i < lgtudX; i++){
					fijaAlturaRecortando(posX + i, posY + j, altura);
					altura += incrementos[(tipoBloque & 0x07) - 1][0];
				}

				altura = oldAltura + incrementos[(tipoBloque & 0x07) - 1][1];
			}
		} else {
			// halla la distancia en x entre las coordenadas
			distX = posX - minPosX;

			// si el bloque empieza antes que el rectï¿½ngulo de recorte
			if (distX < 0){
				posX = 0;

				// si el bloque es mï¿½s grande que la zona visible, se recorta en longitud
				if ((distX + lgtudX) > 24){
					lgtudX = 24;
				} else {
					// en otro caso, recorta la longitud del bloque a la zona visible
					lgtudX = lgtudX + distX;
				}
			} else {
				// si el bloque empieza despuï¿½s del inicio de la zona visible
				posX = distX;

				// si el bloque es mï¿½s grande que la zona visible, recorta la longitud del bloque
				if ((distX + lgtudX) > 24){
					lgtudX = lgtudX - (distX + lgtudX - 24);
				}
			}

			// halla la distancia en y entre las coordenadas
			distY = posY - minPosY;

			// si el bloque empieza antes que el rectï¿½ngulo de recorte
			if (distY < 0){
				posY = 0;

				// si el bloque es mï¿½s grande que la zona visible, se recorta en longitud
				if ((distY + lgtudY) > 24){
					lgtudY = 24;
				} else {
					// en otro caso, recorta la longitud del bloque a la zona visible
					lgtudY = lgtudY + distY;
				}
			} else {
				// si el bloque empieza despuï¿½s del inicio de la zona visible
				posY = distY;

				// si el bloque es mï¿½s grande que la zona visible, recorta la longitud del bloque
				if ((distY + lgtudY) > 24){
					lgtudY = lgtudY - (distY + lgtudY - 24);
				}
			}

			// modifica la tabla de alturas con el bloque recortado
			for (int j = 0; j < lgtudY; j++){
				for (int i = 0; i < lgtudX; i++){
					bufAlturas[posY + j][posX + i] = altura;
				}
			}
		}
	}
}

// comprueba si la posiciï¿½n que se le pasa (en coordenadas de mundo) estï¿½ dentro de las 20x20 posiciones
// centrales de la rejilla y si es asï¿½, devuelve la posiciï¿½n en el sistema de coordenadas de la rejilla
bool RejillaPantalla::ajustaAPosRejilla(int posX, int posY, int &posXRejilla, int &posYRejilla)
{
	posXRejilla = posX - minPosX;

	// si estï¿½ fuera del rango en las x, devuelve false
	if (posXRejilla < 2) return false;
	if (posXRejilla >= 22) return false;

	posYRejilla = posY - minPosY;

	// si estï¿½ fuera del rango en las y, devuelve false
	if (posYRejilla < 2) return false;
	if (posYRejilla >= 22) return false;

	return true;
}

// comprueba si la posiciï¿½n que se le pasa estï¿½ en las 20x20 posiciones centrales de la rejilla de la
// pantalla actual, y de ser asï¿½, se devuelve su posiciï¿½n en el sistema de coordenadas de la rejilla
bool RejillaPantalla::estaEnRejillaCentral(PosicionJuego *pos, int &posXRejilla, int &posYRejilla)
{
#ifndef QL_C_REJILLA
	// QL (speed option 6; ~30 calls a logic step): MotorGrafico::obtenerAlturaBasePlanta and
	// ajustaAPosRejilla written out here, without the two calls (the same results and writes)
	int altura = pos->altura;
	int base = (altura < 0x0d) ? 0x00 : ((altura >= 0x18) ? 0x16 : 0x0b);
	if (base != minAltura) return false;
	int x = pos->posX - minPosX;
	posXRejilla = x;
	if ((unsigned)(x - 2) >= 20u) return false;
	int y = pos->posY - minPosY;
	posYRejilla = y;
	return (unsigned)(y - 2) < 20u;
#endif
	// si la posiciï¿½n no estï¿½ en la misma planta que la de la rejilla actual, sale
	if (motor->obtenerAlturaBasePlanta(pos->altura) != minAltura){
		return false;
	}

	// si la posiciï¿½n no estï¿½ en las 20x20 posiciones centrales de la rejilla, sale
	if (!ajustaAPosRejilla(pos->posX, pos->posY, posXRejilla, posYRejilla)){
		return false;
	}

	return true;
}

// devuelve la diferencia de altura y posiciï¿½n del personaje si sigue avanzando hacia donde mira
bool RejillaPantalla::obtenerAlturaPosicionesAvance(Personaje *pers, int &difAltura1, int &difAltura2, int &avanceX, int &avanceY)
{
	// si el personaje no estï¿½ en la misma planta que la de la rejilla, sale
	if (elMotorGrafico->obtenerAlturaBasePlanta(pers->altura) != minAltura) return false;

	// obtiene la altura relativa con respecto a esta planta
	int alturaLocal = pers->altura - elMotorGrafico->obtenerAlturaBasePlanta(pers->altura);

	return obtenerAlturaPosicionesAvanceComun(pers, alturaLocal, difAltura1, difAltura2, avanceX, avanceY);
}

// devuelve la diferencia de altura y posiciï¿½n del personaje si sigue avanzando hacia donde mira
bool RejillaPantalla::obtenerAlturaPosicionesAvance2(Personaje *pers, int &difAltura1, int &difAltura2, int &avanceX, int &avanceY)
{
	return obtenerAlturaPosicionesAvanceComun(pers, 0, difAltura1, difAltura2, avanceX, avanceY);
}

/////////////////////////////////////////////////////////////////////////////
// mï¿½todos de ayuda
/////////////////////////////////////////////////////////////////////////////

// devuelve la diferencia de altura y posiciï¿½n del personaje si sigue avanzando hacia donde mira
bool RejillaPantalla::obtenerAlturaPosicionesAvanceComun(Personaje *pers, int alturaLocal, int &difAltura1, int &difAltura2, int &avanceX, int &avanceY)
{
	int posXLocal, posYLocal;

	// si la posiciï¿½n no estï¿½ dentro de las 20x20 posiciones centrales de la pantalla que se muestra, sale
	if (!estaEnRejillaCentral(pers, posXLocal, posYLocal)) return false;
#ifdef QL_ASM_GRID
	// QL: the 4x4 read and the choice of the two heights below in asm (src/grid.s)
	{
		int dif[2];
		a_avance(&bufAlturas[0][0], &bufCalculoAvance[0][0], posXLocal, posYLocal,
			calculoAvancePosicion[pers->orientacion], pers->enDesnivel ? 1 : 0, alturaLocal, dif);
		difAltura1 = dif[0];
		difAltura2 = dif[1];
		avanceX = elMotorGrafico->tablaDespOri[pers->orientacion][0];
		avanceY = elMotorGrafico->tablaDespOri[pers->orientacion][1];
		return true;
	}
#endif

	// calcula la primera posiciï¿½n de la rejilla a probar
	int despIni = pers->enDesnivel ? 6 : 4;
	posXLocal += calculoAvancePosicion[pers->orientacion][despIni];
	posYLocal += calculoAvancePosicion[pers->orientacion][despIni + 1];

	// rellena el buffer para el cï¿½lculo del avance con las posiciones relevantes segï¿½n la orientaciï¿½n
	for (int j = 0; j < 4; j++){
		int oldPosXLocal = posXLocal;
		int oldPosYLocal = posYLocal;
		
		for (int i = 0; i < 4; i++){
			// obtiene la altura de la posiciï¿½n
			int alturaPos = bufAlturas[posYLocal][posXLocal];

			if (alturaPos < 0x10){
				// si no hay un personaje en esa posiciï¿½n, obtiene la diferencia de altura entre la posiciï¿½n y el personaje
				alturaPos = alturaPos - alturaLocal;
			} else {
				alturaPos = alturaPos & 0x30;
			}
			bufCalculoAvance[j][i] = alturaPos;

			// apunta a la siguiente posiciï¿½n
			posXLocal += calculoAvancePosicion[pers->orientacion][0];
			posYLocal += calculoAvancePosicion[pers->orientacion][1];
		}

		// apunta a la siguiente posiciï¿½n
		posXLocal = oldPosXLocal + calculoAvancePosicion[pers->orientacion][2];
		posYLocal = oldPosYLocal + calculoAvancePosicion[pers->orientacion][3];
	}

	// si el personaje ocupa 4 posiciones en la rejilla
	if (!pers->enDesnivel){
		difAltura1 = bufCalculoAvance[0][1];
		difAltura2 = bufCalculoAvance[0][2];

		// si en las 2 posiciones hacia las que quiere avanzar el personaje no hay la misma altura
		if (difAltura1 != difAltura2){
			// indica que hay una diferencia de altura > 1
			difAltura1 = 2;
		}
	} else {
		// si el personaje ocupa una posiciï¿½n en la rejilla, guarda la diferencia de altura de las 2 posiciones hacia las que quiere avanzar
		difAltura1 = bufCalculoAvance[1][1];
		difAltura2 = bufCalculoAvance[0][1];
	}

	// guarda el avance en cada coordenada segï¿½n la orientaciï¿½n en la que se quiere avanzar
	avanceX = elMotorGrafico->tablaDespOri[pers->orientacion][0];
	avanceY = elMotorGrafico->tablaDespOri[pers->orientacion][1];

	return true;
}

/////////////////////////////////////////////////////////////////////////////
// QL_HGRID_CACHE: the height-grid cache
/////////////////////////////////////////////////////////////////////////////
//
// The fill's result (the CLEAN 24x24 grid, before characters and doors are stamped into it)
// depends only on: the floor's height table (roms 0x18a00 / 0x18f00 / 0x19080, read up to its
// 0xff), and the window (minPosX, minPosY). A grid is cached under (floor, minPosX, minPosY,
// ql_hgen); every write into the height tables bumps ql_hgen (see ql_port.h), so an entry made
// before the write never matches again. HG_N entries, least recently used replaced: 32, from
// the key traces of walk1/enter/saveload (the monks re-plan over about 30 windows in a cycle:
// 16 entries hit 21% on walk1, 32 hit 75%).

unsigned int ql_hgen = 1;
unsigned int ql_hg_hits, ql_hg_misses, ql_hg_prewarms;

#ifdef QL_HGRID_CACHE
extern "C" void a_copy576(UINT8 *dst, const UINT8 *src);	// grid.s
extern "C" void ql_fault(int code);					// qlstart.s

#define HG_N 32
static struct HGEntry {
	UINT8 grid[24*24];
	int planta, posXMin, posYMin;
	unsigned int gen, lru;
} hgCache[HG_N];
static unsigned int hgClock;
#ifndef QL_RELEASE
static UINT8 hgCheck[24*24];
#endif

void RejillaPantalla::qlRellenaVentana(int planta, int posXMin, int posYMin)
{
	static const int datosPlanta[] = { 0x18a00, 0x18f00, 0x19080 };
	const UINT8 *datos = &roms[datosPlanta[planta]];
	HGEntry *victim = &hgCache[0];
	for (int i = 0; i < HG_N; i++){
		HGEntry *e = &hgCache[i];
		if (e->gen == ql_hgen && e->planta == planta && e->posXMin == posXMin && e->posYMin == posYMin){
			a_copy576(&bufAlturas[0][0], e->grid);
			e->lru = ++hgClock;
			ql_hg_hits++;
#ifndef QL_RELEASE
			if (ql_harness_hgverify()){
				// harness: the hit must equal a fresh fill
				a_rellena_alturas(hgCheck, datos, posXMin, posYMin);
				for (int k = 0; k < 24*24; k++){
					if (hgCheck[k] != (&bufAlturas[0][0])[k]) ql_fault(0x48474331);	// 'HGC1'
				}
			}
#endif
			return;
		}
		if (e->lru < victim->lru) victim = e;
	}
	ql_hg_misses++;
	a_rellena_alturas(&bufAlturas[0][0], datos, posXMin, posYMin);
	a_copy576(victim->grid, &bufAlturas[0][0]);
	victim->planta = planta;
	victim->posXMin = posXMin;
	victim->posYMin = posYMin;
	victim->gen = ql_hgen;
	victim->lru = ++hgClock;
}

// QL (2026-10-06): pre-warming in the step's spare time (src/qlstart.s wait_tick, only while 3 or
// more frames are left to wait: one fill is 4-16 ms on the 68008). The windows a character will
// most likely need next: for each of the 8, the window it is in and the one it faces (the monks'
// route searches fill the window they are in, so the misses come as they cross into the next
// one). One missing window is filled per call, straight into a cache entry: the game's own
// grids are not touched, so the cache stays transparent (an entry is the fill of its key, made
// from the current height tables: ql_hgen). Returns 1 if it filled one, 0 if all are cached.
// The entries it replaces are the least recently used, as for a miss.
static unsigned int hgPrewarmGen = 0;			// ql_hgen when the last scan found nothing
static unsigned int hgPrewarmStep = 0xffffffff;	// ... and the step

extern "C" int ql_hg_prewarm(void)
{
	extern unsigned int ql_hg_step;				// ql_game.cpp: abadia_tick's count
	if (!elJuego || hgPrewarmStep == ql_hg_step && hgPrewarmGen == ql_hgen) return 0;
	static const int datosPlanta[] = { 0x18a00, 0x18f00, 0x19080 };
	for (int i = 0; i < Juego::numPersonajes; i++){
		Personaje *p = elJuego->personajes[i];
		if (!p) continue;
		int base = elMotorGrafico->obtenerAlturaBasePlanta(p->altura);
		int planta = elMotorGrafico->obtenerPlanta(base);
		for (int k = 0; k < 2; k++){
			int x = p->posX, y = p->posY;
			if (k == 1){
				x += 16*MotorGrafico::tablaDespOri[p->orientacion & 3][0];
				y += 16*MotorGrafico::tablaDespOri[p->orientacion & 3][1];
			}
			int posXMin = (x & 0xf0) - 4, posYMin = (y & 0xf0) - 4;
			HGEntry *victim = &hgCache[0];
			bool hay = false;
			for (int j = 0; j < HG_N; j++){
				HGEntry *e = &hgCache[j];
				if (e->gen == ql_hgen && e->planta == planta && e->posXMin == posXMin && e->posYMin == posYMin){
					hay = true;
					break;
				}
				if (e->lru < victim->lru) victim = e;
			}
			if (hay) continue;
			a_rellena_alturas(victim->grid, &elJuego->roms[datosPlanta[planta]], posXMin, posYMin);
			victim->planta = planta;
			victim->posXMin = posXMin;
			victim->posYMin = posYMin;
			victim->gen = ql_hgen;
			victim->lru = ++hgClock;
			ql_hg_prewarms++;
			return 1;
		}
	}
	hgPrewarmStep = ql_hg_step;
	hgPrewarmGen = ql_hgen;
	return 0;
}
#else
void RejillaPantalla::qlRellenaVentana(int planta, int posXMin, int posYMin)
{
}
extern "C" int ql_hg_prewarm(void) { return 0; }
#endif

// si los datos de altura estï¿½n dentro de la zona de la rejilla, los graba
void RejillaPantalla::fijaAlturaRecortando(int posX, int posY, int altura)
{
	// recorta en y
	posY = posY - minPosY;

	// si la coordenada y estï¿½ fuera de la zona visible en y, sale
	if ((posY < 0) || (posY >= 24)){
		return;
	}

	// recorta en x
	posX = posX - minPosX;

	// si la coordenada x estï¿½ fuera de la zona visible en x, sale
	if ((posX < 0) || (posX >= 24)){
		return;
	}

	bufAlturas[posY][posX] = altura;
}

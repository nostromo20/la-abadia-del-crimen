// Comandos.cpp
//
/////////////////////////////////////////////////////////////////////////////

#include "Comandos.h"
#include "Juego.h"
#include "GeneradorPantallas.h"
#include "MotorGrafico.h"
#include "ql_port.h"

using namespace Abadia;

/////////////////////////////////////////////////////////////////////////////
// comandos para saltos
/////////////////////////////////////////////////////////////////////////////

// cambia el origen de los datos del generador de bloques
bool ChangePC::ejecutar(GeneradorPantallas *gen)
{
	gen->comandosBloque = gen->obtenerDir(gen->comandosBloque);

	return false;
}

void call(GeneradorPantallas *gen, bool modificaTiles)
{
	// guarda el estado necesario para reanudar la interpretaci�n del bloque
	gen->push(gen->tilePosX);
	gen->push(gen->tilePosY);

	gen->push(gen->estadoOpsX[0]);
	gen->push(gen->estadoOpsX[1]);
	gen->push(gen->estadoOpsX[2]);
	gen->push(gen->estadoOpsX[3]);

	gen->push(gen->datosBloque[12]);
	gen->push(gen->datosBloque[13]);
	gen->push(gen->datosBloque[14]);
	gen->push(gen->datosBloque[15]);
	gen->push(gen->datosBloque[16]);

	// obtiene un puntero a las caracter�sticas del bloque
	int despTipoBloque = gen->obtenerDir(gen->comandosBloque);

	gen->comandosBloque = gen->comandosBloque + 2;

	gen->push(gen->comandosBloque);

	// obtiene un puntero a los tiles que forman el bloque
	UINT8 *tilesBloque = &gen->roms[gen->obtenerDir(despTipoBloque)];

	// avanza el puntero hasta los comandos que forman el bloque
	gen->comandosBloque = despTipoBloque + 2;

	// interpreta otro bloque
	gen->iniciaInterpretacionBloque(tilesBloque, modificaTiles, gen->datosBloque[14]);

	// recupera los valores introducidos en la pila
	gen->comandosBloque = gen->pop();

	gen->datosBloque[16] = gen->pop();
	gen->datosBloque[15] = gen->pop();
	gen->datosBloque[14] = gen->pop();
	gen->datosBloque[13] = gen->pop();
	gen->datosBloque[12] = gen->pop();

	gen->estadoOpsX[3] = gen->pop();
	gen->estadoOpsX[2] = gen->pop();
	gen->estadoOpsX[1] = gen->pop();
	gen->estadoOpsX[0] = gen->pop();

	gen->tilePosY = gen->pop();
	gen->tilePosX = gen->pop();
}

// interpreta otro bloque, sin modificar los tiles que se usan
bool CallPreserve::ejecutar(GeneradorPantallas *gen)
{
	// indica que se ha cambiado el sentido de las x
	gen->cambioSistemaCoord = true;

	// interpreta otro bloque sin modificar los tiles que se usan
	call(gen, false);

	return false;
}

// interpreta otro bloque, sin modificar los tiles que se usan
bool Call::ejecutar(GeneradorPantallas *gen)
{
	// interpreta otro bloque modificando los tiles que se usan
	call(gen, true);

	return false;
}

/////////////////////////////////////////////////////////////////////////////
// m�todo de ayuda para los bucles
/////////////////////////////////////////////////////////////////////////////

void avanzaHastaFinDeWhile(GeneradorPantallas *gen)
{
	int profWhile = 1;

	// mientras no se hayan pasado las instrucciones del while
	while (profWhile > 0){
		int dato = gen->roms[gen->comandosBloque];

		// si encuentra un marcador, avanza 2 bytes
		if (dato == 0x82){
			gen->comandosBloque += 2;
		} else {
			// en otro caso, sigue pasando y contando los while a los que entra y a los que sale
			if ((dato == 0xfe) || (dato == 0xfd)){
				profWhile++;
			} else if (dato == 0xfa){
				profWhile--;
			}

			gen->comandosBloque++;
		}
	}
}

/////////////////////////////////////////////////////////////////////////////
// comandos para bucles
/////////////////////////////////////////////////////////////////////////////

// inicia la ejecuci�n de una serie de instrucciones mientras el par�metro 1 sea > 0
bool WhileParam1::ejecutar(GeneradorPantallas *gen)
{
	// obtiene el valor del par�metro 1
	int aux = gen->obtenerRegistro(0x6d, 0);

	// si el bucle se va a ejecutar alguna vez, inserta en la pila la direcci�n de retorno y el valor actual del par�metro 1
	if (aux > 0){
		gen->push(gen->comandosBloque);
		gen->push(aux);
	} else {
		// en otro caso, salta las instrucciones hasta el f�n del while
		avanzaHastaFinDeWhile(gen);
	}

	return false;
}

// inicia la ejecuci�n de una serie de instrucciones mientras el par�metro 2 sea > 0
bool WhileParam2::ejecutar(GeneradorPantallas *gen)
{
	// obtiene el valor del par�metro 2
	int aux = gen->obtenerRegistro(0x6e, 0);

	// si el bucle se va a ejecutar alguna vez, inserta en la pila la direcci�n de retorno y el valor actual del par�metro 2
	if (aux > 0){
		gen->push(gen->comandosBloque);
		gen->push(aux);
	} else {
		// en otro caso, salta las instrucciones hasta el f�n del while
		avanzaHastaFinDeWhile(gen);
	}

	return false;
}

// termina la ejecuci�n de un blucle mientras
bool EndWhile::ejecutar(GeneradorPantallas *gen)
{
	// recupera el contador del bucle
	int contador = gen->pop();
	contador--;

	// si no se ha terminado todav�a
	if (contador > 0){
		// recupera la direcci�n de inicio del while
		gen->comandosBloque = gen->pop();

		// inserta en la pila la direcci�n de retorno y el contador
		gen->push(gen->comandosBloque);
		gen->push(contador);
	} else {
		// en otro caso se limpia la pila
		gen->pop();
	}

	return false;
}

/////////////////////////////////////////////////////////////////////////////
// comandos sobre los par�metros
/////////////////////////////////////////////////////////////////////////////

// incrementa el primer par�metro en el buffer de los datos del bloque
bool IncParam1::ejecutar(GeneradorPantallas *gen)
{
	gen->actualizaRegistro(0x6d, 1);

	return false;
}

// decrementa el primer par�metro en el buffer de los datos del bloque
bool DecParam1::ejecutar(GeneradorPantallas *gen)
{
	gen->actualizaRegistro(0x6d, -1);

	return false;
}

// incrementa el segundo par�metro en el buffer de los datos del bloque
bool IncParam2::ejecutar(GeneradorPantallas *gen)
{
	gen->actualizaRegistro(0x6e, 1);

	return false;
}

// decrementa el segundo par�metro en el buffer de los datos del bloque
bool DecParam2::ejecutar(GeneradorPantallas *gen)
{
	gen->actualizaRegistro(0x6e, -1);

	return false;
}

/////////////////////////////////////////////////////////////////////////////
// comandos sobre la posici�n
/////////////////////////////////////////////////////////////////////////////

// incrementa la coordenada x del buffer de tiles
bool IncTilePosX::ejecutar(GeneradorPantallas *gen)
{
	gen->tilePosX = gen->tilePosX + gen->estadoOpsX[0];

	return false;
}

// decrementa la coordenada x del buffer de tiles
bool DecTilePosX::ejecutar(GeneradorPantallas *gen)
{
	gen->tilePosX = gen->tilePosX - gen->estadoOpsX[1];

	return false;
}

// incrementa la coordenada y del buffer de tiles
bool IncTilePosY::ejecutar(GeneradorPantallas *gen)
{
	gen->tilePosY++;

	return false;
}

// decrementa la coordenada y del buffer de tiles
bool DecTilePosY::ejecutar(GeneradorPantallas *gen)
{
	gen->tilePosY--;

	return false;
}

// cambia la coordenada x del buffer de tiles
bool UpdateTilePosX::ejecutar(GeneradorPantallas *gen)
{
	// obtiene el valor inicial de la expresi�n
	int rdo = gen->leeDatoORegistro(0);

	// evalua una expresi�n
	rdo = gen->evaluaExpresion(rdo);

	// modifica la posici�n en x en el buffer de tiles
	gen->tilePosX = gen->tilePosX + rdo;

	return false;
}


// cambia la coordenada y del buffer de tiles
bool UpdateTilePosY::ejecutar(GeneradorPantallas *gen)
{
	// obtiene el valor inicial de la expresi�n
	int rdo = gen->leeDatoORegistro(0);

	// evalua una expresi�n
	rdo = gen->evaluaExpresion(rdo);

	// modifica la posici�n en y en el buffer de tiles
	gen->tilePosY = gen->tilePosY + rdo;

	return false;
}

// guarda en la pila la posici�n actual en el buffer de tiles
bool PushTilePos::ejecutar(GeneradorPantallas *gen)
{
	gen->push(gen->tilePosX);
	gen->push(gen->tilePosY);

	return false;
}

// recupera de la pila una posici�n en el buffer de tiles
bool PopTilePos::ejecutar(GeneradorPantallas *gen)
{
	gen->tilePosY = gen->pop();
	gen->tilePosX = gen->pop();

	return false;
}

/////////////////////////////////////////////////////////////////////////////
// comandos de dibujo
/////////////////////////////////////////////////////////////////////////////

// dibuja un tile en el buffer de tiles (si es visible), cambiando la posici�n actual en el buffer
#ifdef QL_ASM_GEN
#include <stddef.h>
extern "C" void a_tile_mueve(GeneradorPantallas *gen, int deltax, int deltay);
// the field offsets src/gen.s uses (GP_*)
static_assert(offsetof(GeneradorPantallas, roms) == 0, "src/gen.s GP_ROMS");
static_assert(offsetof(GeneradorPantallas, bufferTiles) == 8, "src/gen.s GP_BT");
static_assert(offsetof(GeneradorPantallas, comandosBloque) == 1996, "src/gen.s GP_CB");
static_assert(offsetof(GeneradorPantallas, datosBloque) == 2000, "src/gen.s GP_DB");
static_assert(offsetof(GeneradorPantallas, tilePosX) == 2068, "src/gen.s GP_PX");
static_assert(offsetof(GeneradorPantallas, tilePosY) == 2072, "src/gen.s GP_PY");
static_assert(offsetof(GeneradorPantallas, estadoOpsX) == 2078, "src/gen.s GP_EST");
static_assert(sizeof(GeneradorPantallas::TileInfo) == 6 && GeneradorPantallas::nivelesProfTiles == 2, "src/gen.s");
#endif
void dibujaTileYMueve(GeneradorPantallas *gen, int deltax, int deltay)
{
#ifdef QL_ASM_GEN
	// QL: the whole command in asm (src/gen.s: leeDatoORegistro, grabaTile, actualizaTile inside)
	if (ql_gen_asm()){
		a_tile_mueve(gen, deltax, deltay);
		return;
	}
#endif
	while (true){
		// lee el siguiente operando del buffer de construcci�n del bloque
		int num = gen->leeDatoORegistro(0);

		// lee el pr�ximo byte a procesar
		int dato = gen->roms[gen->comandosBloque];

		// si se encuentra una nueva orden, pinta, actualiza la posici�n y sale
		if (dato >= 0xc8){
			gen->grabaTile(num);
			gen->tilePosX += deltax;
			gen->tilePosY += deltay;

			break;
		}

		gen->comandosBloque++;

		// si se encuentra un 0x80, pinta, actualiza la posici�n y contin�a
		if (dato == 0x80){
			gen->grabaTile(num);
			gen->tilePosX += deltax;
			gen->tilePosY += deltay;
		} else if (dato == 0x81){
			// si lee 0x81, pinta y contin�a
			gen->grabaTile(num);
		} else {
			// lee el n�mero de veces que ha de repteir la operaci�n
			int numVeces = gen->leeDatoORegistro(0);

			// repite la misma operaci�n las veces leidas
			for (int i = 0; i < numVeces; i++){
				gen->grabaTile(num);
				gen->tilePosX += deltax;
				gen->tilePosY += deltay;
			}

			// lee el pr�ximo byte a procesar
			dato = gen->roms[gen->comandosBloque];

			// si se encuentra una nueva orden, sale
			if (dato >= 0xc8){
				break;
			} else {
				// en otro caso se salta algo y contin�a
				gen->comandosBloque++;
			}
		}
	}
}

// dibuja una serie de tiles y decrementa la coordenada y del buffer de tiles
bool DrawTileDecY::ejecutar(GeneradorPantallas *gen)
{
	dibujaTileYMueve(gen, 0, -1);

	return false;
}

// dibuja una serie de tiles e incrementa la coordenada x del buffer de tiles
bool DrawTileIncX::ejecutar(GeneradorPantallas *gen)
{
	dibujaTileYMueve(gen, gen->estadoOpsX[2], 0);

	return false;
}

// dibuja una serie de tiles y decrementa la coordenada x del buffer de tiles
bool DrawTileDecX::ejecutar(GeneradorPantallas *gen)
{
	dibujaTileYMueve(gen, -1, 0);

	return false;
}

/////////////////////////////////////////////////////////////////////////////
// resto de comandos
/////////////////////////////////////////////////////////////////////////////

// actualiza un registro relacionado con los datos del bloque
bool UpdateReg::ejecutar(GeneradorPantallas *gen)
{
	// lee el registro al que se va a acceder
	int dato = gen->roms[gen->comandosBloque];

	int posReg = -1;

	// obtiene la posici�n del registro que se va a modificar
	gen->leeDatoORegistro(&posReg);

	// obtiene el valor inicial de la expresi�n
	int rdo = gen->leeDatoORegistro(0);

	// evalua una expresi�n
	rdo = gen->evaluaExpresion(rdo);

	// si se modifica un registro de coordenadas locales de la rejilla, ajusta el resultado entre 0 y 100
	if (dato >= 0x70){
		// si no se estaban calculando las coordenadsa locales de la rejilla para este bloque, sale
		if (gen->datosBloque[posReg] == 0){
			return false;
		}

		// si hay desbordamiento, modifica el resultado
		if (rdo > 100){
			rdo = 0;
		}
	}

	// actualiza el registro
	gen->datosBloque[posReg] = rdo;

	return false;
}

// termina la evaluaci�n de un bloque
bool EndBlock::ejecutar(GeneradorPantallas *gen)
{
	bool seCambioSistemaCoord = gen->cambioSistemaCoord;

	gen->cambioSistemaCoord= false;

	// si se empez� a trabajar con respecto al nuevo sistema de coordenadas
	if (!seCambioSistemaCoord){
		gen->estadoOpsX[0] = 1;
		gen->estadoOpsX[1] = 1;
		gen->estadoOpsX[2] = 1;
		gen->estadoOpsX[3] = 0;
	}

	return true;
}

// cambia el sentido de las x
bool FlipX::ejecutar(GeneradorPantallas *gen)
{
#ifndef QL_FLIPX_TOGGLE
	// CPC 0x218d: the command SETS the flipped state (x++ -> x--, x-- -> x++, registers 0x70 and
	// 0x71 swapped); it does not toggle it. A block reached through two flips (material 0x44:
	// FlipX, CallPreserve 0x1ee8 -> CallPreserve 0x1f20 -> 0x198c FlipX) stays flipped, so the
	// depth adjustment of 0x1975 goes to register 0x70 there. VIGASOCO toggled, which left the
	// column bases of those blocks with depths one off in x and y (tools/cpcref.py --tiles).
	gen->estadoOpsX[0] = -1;
	gen->estadoOpsX[1] = -1;
	gen->estadoOpsX[2] = -1;
	gen->estadoOpsX[3] = 1;
	return false;
#endif
	gen->estadoOpsX[0] = -gen->estadoOpsX[0];
	gen->estadoOpsX[1] = -gen->estadoOpsX[1];
	gen->estadoOpsX[2] = -gen->estadoOpsX[2];
	gen->estadoOpsX[3] ^= 0x01;

	return false;
}

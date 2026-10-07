// Serializar.h
//
//              Metodos sobrecargados de los
//              operadores << y >> 
//              para cargar/salvar la partida
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _SERIALIZAR_H
#define _SERIALIZAR_H

#include "ql_stream.h"	// QL: memory streams instead of <fstream>
#include <stddef.h>
#include "EntidadJuego.h"
#include "Objeto.h"
#include "Puerta.h"
#include "Sprite.h"
#include "Personaje.h"
#include "Guillermo.h"
#include "Adso.h"
#include "Malaquias.h"
#include "Abad.h"
#include "Berengario.h"
#include "Severino.h"
#include "Jorge.h"
#include "Bernardo.h"
#include "Logica.h"

namespace Abadia {

QLOut& operator<< (
	QLOut& out,
	const PosicionJuego* const pos );

QLIn& operator>> (
	QLIn& in,
	PosicionJuego* const pos );

QLOut& operator<< (
	QLOut& out,
	const Objeto* const obj );

QLIn& operator>> (
	QLIn& in,
	Objeto* const obj );

QLOut& operator<< (
	QLOut& out,
	const Puerta* const puerta );

QLIn& operator>> (
	QLIn& in,
	Puerta* const puerta );

QLOut& operator<< (
	QLOut& out,
	const Sprite* const sprite );

QLIn& operator>> (
	QLIn& in,
	Sprite* const sprite );

QLOut& operator<< (
	QLOut& out,
	const Personaje* const pers );

QLIn& operator>> (
	QLIn& in,
	Personaje* const pers );

QLOut& operator<< (
	QLOut& out,
	const Guillermo* const guillermo );

QLIn& operator>> (
	QLIn& in,
	Guillermo* const guillermo );

QLOut& operator<< (
	QLOut& out,
	const PersonajeConIA* const persIA );

QLIn& operator>> (
	QLIn& in,
	PersonajeConIA* const persIA );

QLIn& operator>> (
	QLIn& in,
	Adso* const adso );

QLOut& operator<< (
	QLOut& out,
	const Adso* const adso );

QLOut& operator<< (
	QLOut& out,
	const Malaquias* const malaquias );

QLIn& operator>> (
	QLIn& in,
	Malaquias* const malaquias );

QLOut& operator<< (
	QLOut& out,
	const Abad* const abad );

QLIn& operator>> (
	QLIn& in,
	Abad* const abad );

QLOut& operator<< (
	QLOut& out,
	const Berengario* const berengario );

QLIn& operator>> (
	QLIn& in,
	Berengario* const berengario );

QLOut& operator<< (
	QLOut& out,
	const Severino* const severino );

QLIn& operator>> (
	QLIn& in,
	Severino* const severino );

QLOut& operator<< (
	QLOut& out,
	const Jorge* const jorge );

QLIn& operator>> (
	QLIn& in,
	Jorge* const jorge );

QLOut& operator<< (
	QLOut& out,
	const Bernardo* const bernardo );

QLIn& operator>> (
	QLIn& in,
	Bernardo* const bernardo );

QLOut& operator<< (
	QLOut& out,
	const Logica* const logica);

QLIn& operator>> (
	QLIn& in,
	Logica* const logica);

}; // namespace Abadia

#endif // _SERIALIZAR_H

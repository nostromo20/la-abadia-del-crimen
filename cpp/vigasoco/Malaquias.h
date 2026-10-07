// Malaquias.h
//
//	Clase que representa a Malaqu�as
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _MALAQUIAS_H_
#define _MALAQUIAS_H_

#include "ql_stream.h"
#include "Monje.h"

namespace Abadia {


class Malaquias : public Monje
{
// campos
public:
	int estaMuerto;								// indica si el personaje est� muerto o muri�ndose
	int estado2;								// guarda informaci�n extra sobre el estado del personaje

protected:
	int contadorEnScriptorium;					// indica el tiempo que guillermo est� sin salir del scriptorium
	static PosicionJuego posicionesPredef[9];	// posiciones a las que puede ir el personaje seg�n el estado

// m�todos
public:
	void piensa() override;

	// inicializaci�n y limpieza
	explicit Malaquias(SpriteMonje *spr);
	~Malaquias() override = default;

	// cargar/salvar
	friend QLOut& operator<<(QLOut&,const Malaquias* const);
	friend QLIn& operator>>(QLIn&,Malaquias* const);

protected:
	void avanzaAnimacionOMueve() override;
};


}

#endif	// _MALAQUIAS_H_

// Paleta.h -- QL port: the palette is a platform concern (CPC inks -> QL colours).
//
// CPC hardware palettes used by the game (from the fork's Paleta.cpp):
//   0 black {20,20,20,20}, 1 parchment {07,28,20,12}, 2 day {06,14,03,20}, 3 night {04,29,00,20}
#ifndef _PALETA_H_
#define _PALETA_H_

#include "ql_port.h"

class Paleta {
public:
	int actual;
	Paleta() : actual(2) {}
	void setIntroPalette() { setGamePalette(1); }
	void setGamePalette(int pal) {
		actual = pal;
		ql_set_palette(pal);
#ifdef QL_CHARCOL
		ql_palette_repaint(pal);
#endif
	}
};

#endif	// _PALETA_H_

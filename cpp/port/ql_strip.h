// ql_strip.h -- QL: the text strip under the panel and the save device (ql_strip.cpp).
#ifndef QL_STRIP_H
#define QL_STRIP_H

#include "Types.h"
#include "ql_port.h"

// start-up (during the loading screen): the home drive, the settings files, the save device
void qlsInicio(const UINT8 *roms);
// once per gameplay step, after the logic: F3/F5, timers, the settings write, the strip.
// The common step (nothing pending, the same palette, F3/F5 up) costs a few byte tests here.
extern unsigned char qlsPendiente;	// a message or settings timer, a redraw, a key still down
extern int qlsPaletaDibujada;
void qlsJuegoPaso(int paleta);
#ifdef QL_ASM_KERNELS
extern "C" unsigned char key_state[];	// src/qlhooks.s (QL builds only): 1 while down this step
#endif
inline void qlsJuego(int paleta)
{
#ifdef QL_ASM_KERNELS
	if (qlsPendiente || paleta != qlsPaletaDibujada || key_state[QK_F3] || key_state[QK_F5])
#else
	if (qlsPendiente || paleta != qlsPaletaDibujada || ql_key_down(QK_F3) || ql_key_down(QK_F5))
#endif
		qlsJuegoPaso(paleta);
}
// leaving gameplay (end of the investigation, the ending parchment): the strip cleared once
void qlsFueraDeJuego();
// the intro parchment's page is up (after the dissolve) / the intro has ended
void qlsIntro(bool mostrar);
// a palette change: the strip is redrawn at the next gameplay step
void qlsPaleta();
// F1: "SAVING TO <DEV>..." at once, the write, then the result; true if saved
bool qlsGuardar(const char *buf, int len, int paleta);
// F2: "LOADING FROM <DEV>..." at once, the read; the bytes read (> 0), or 0 with the message
// shown (no save / insert the cartridge)
int qlsCargar(char *buf, int cap, int paleta);
// F2's outcome once the data is read: GAME LOADED or LOAD FAILED (corrupt)
void qlsCargado(bool ok);

#endif

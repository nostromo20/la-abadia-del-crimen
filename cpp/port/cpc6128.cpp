// cpc6128.cpp -- QL port of VIGASOCO's CPC6128 helper (see cpc6128.h)

#include "cpc6128.h"
#include <string.h>

#define CLEAN_PANEL() do { dirtyX0 = dirtyY0 = 10000; dirtyX1 = dirtyY1 = -1; } while (0)

CPC6128::CPC6128()
{
	memset(panel, 0, sizeof(panel));
	pantallaCompleta = false;
	qlPanelEnPantalla = false;
	CLEAN_PANEL();
}

void CPC6128::markPanel(int x, int y, int w, int h)
{
	if (x < dirtyX0) dirtyX0 = x;
	if (y < dirtyY0) dirtyY0 = y;
	if (x + w - 1 > dirtyX1) dirtyX1 = x + w - 1;
	if (y + h - 1 > dirtyY1) dirtyY1 = y + h - 1;
}

void CPC6128::discardPanel()
{
	CLEAN_PANEL();
	qlPanelEnPantalla = false;
}

// the part of the panel the QL shows (ql_panel_present: x 32..287)
#define QL_PANEL_X0 32
#define QL_PANEL_X1 287

void CPC6128::flushPanel()
{
	if (pantallaCompleta) qlPanelEnPantalla = false;	// the parchment draws over the panel lines
	if (dirtyX0 > dirtyX1) return;
	if (!pantallaCompleta && dirtyX0 <= QL_PANEL_X0 && dirtyX1 >= QL_PANEL_X1 && dirtyY0 == 0 && dirtyY1 == PANEL_H - 1){
		qlPanelEnPantalla = true;
	}
	ql_panel_present(dirtyX0, dirtyY0, dirtyX1 - dirtyX0 + 1, dirtyY1 - dirtyY0 + 1, panel);
	CLEAN_PANEL();
}

void CPC6128::scrollPanelLeft(int x, int y, int w, int h, int dx)
{
	y -= PANEL_Y;
	for (int j = 0; j < h; j++){
		UINT8 *row = &panel[(y + j)*PANEL_W];
		memmove(&row[x - dx], &row[x], w);
	}
#ifndef QL_NO_PANEL_SCROLL
	// QL (speed option 6): the screen already shows these pens (none of the area is waiting for a
	// flush): move its words too, instead of presenting the whole area again at the next flush
	// (GestorFrases' phrase scroll: 128x8 pixels every 150 ms). The pens left behind at the right
	// (x+w-dx..x+w-1) are unchanged, as on the screen.
	int x0 = x - dx;
	if (qlPanelEnPantalla && !pantallaCompleta && ((x | w | dx) & 3) == 0 && dx > 0 &&
			x0 >= QL_PANEL_X0 && x + w - 1 <= QL_PANEL_X1 &&
			(dirtyX0 > dirtyX1 || x0 > dirtyX1 || x + w - 1 < dirtyX0 || y > dirtyY1 || y + h - 1 < dirtyY0)){
		ql_panel_scroll(x, y, w, h, dx, panel);
		return;
	}
#endif
	markPanel(x - dx, y, w, h);
}

void CPC6128::fillMode1Rect(int x, int y, int width, int height, int color)
{
	// clip to the screen
	if (x < 0){ width += x; x = 0; }
	if (y < 0){ height += y; y = 0; }
	if (x + width > 320) width = 320 - x;
	if (y + height > 200) height = 200 - y;
	if ((width <= 0) || (height <= 0)) return;

	if (pantallaCompleta){
		ql_play_fill(x, y, width, height, color);
		return;
	}

	// play area part
	if (y < PANEL_Y){
		int h = (y + height > PANEL_Y) ? PANEL_Y - y : height;
		ql_play_fill(x, y, width, h, color);
		height -= h;
		y += h;
	}

	// panel part
	if (height > 0){
		for (int j = 0; j < height; j++){
			memset(&panel[(y - PANEL_Y + j)*PANEL_W + x], color, width);
		}
		markPanel(x, y - PANEL_Y, width, height);
	}
}

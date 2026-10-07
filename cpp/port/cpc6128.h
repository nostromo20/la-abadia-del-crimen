// cpc6128.h -- QL port of VIGASOCO's CPC6128 helper.
//
// There is no CPC frame buffer. Play-area writes (y < 160) go straight to the platform
// (ql_play_*); the play area is never read back. The score panel (y 160..199) is kept as a
// 320x40 byte-per-pixel pen buffer here, because Marcador/GestorFrases scroll it by reading
// pixels back; changed areas are handed to ql_panel_present() by flushPanel().
#ifndef _CPC_6128_H_
#define _CPC_6128_H_

#include "Types.h"
#include "ql_port.h"

class CPC6128
{
public:
	enum { PANEL_Y = 160, PANEL_W = 320, PANEL_H = 40 };

	UINT8 panel[PANEL_W*PANEL_H];		// score panel, one pen per byte
	bool pantallaCompleta;				// parchment: the whole CPC screen goes to the platform

	// dirty rectangle of the panel since the last flush (x0 > x1 = clean)
	int dirtyX0, dirtyY0, dirtyX1, dirtyY1;
	// QL: the screen shows the panel's pens everywhere outside the dirty rectangle (a flush
	// presented all of the visible panel since the last discard / full-screen parchment)
	bool qlPanelEnPantalla;

	CPC6128();
	void discardPanel();			// QL: forget the panel's changes (not shown)

	inline void setMode1Pixel(int x, int y, int color)
	{
		if ((unsigned)x >= 320u || (unsigned)y >= 200u) return;
		if (y < PANEL_Y || pantallaCompleta){
			ql_play_pixel(x, y, color);
			return;
		}
		y -= PANEL_Y;
		panel[y*PANEL_W + x] = color;
		if (x < dirtyX0) dirtyX0 = x;
		if (x > dirtyX1) dirtyX1 = x;
		if (y < dirtyY0) dirtyY0 = y;
		if (y > dirtyY1) dirtyY1 = y;
	}

	inline int getMode1Pixel(int x, int y)
	{
		if ((unsigned)x >= 320u || y < PANEL_Y || y >= 200) return 0;
		return panel[(y - PANEL_Y)*PANEL_W + x];
	}

	void fillMode1Rect(int x, int y, int width, int height, int color);

	// moves w panel pixels starting at (x, y) dx pixels to the left, for h lines (same
	// result as the left-to-right per-pixel copy loops of Marcador and GestorFrases)
	// (QL: when the screen shows those pens, the screen is scrolled too: ql_panel_scroll, no
	// present of the whole area; speed option 6. QL_NO_PANEL_SCROLL: always the present)
	void scrollPanelLeft(int x, int y, int w, int h, int dx);

	// hands the dirty part of the panel to the platform
	void flushPanel();
	// QL_CHARCOL: present the whole panel again at the next flush (after a palette change)
	void repaintPanel() { markPanel(0, 0, PANEL_W, PANEL_H); }
	// QL: an area of the panel buffer written directly (panel y), for the next flush
	void marcaPanel(int x, int y, int w, int h) { markPanel(x, y, w, h); }

	inline int unpackPixelMode1(int data, int pixel)
	{
		return (((data >> (3 - pixel)) & 0x01) << 1) | ((data >> (7 - pixel)) & 0x01);
	}

	inline int packPixelMode1(int oldByte, int pixel, int color)
	{
		int mask = 0x88 >> pixel;
		static const int byteColors[4] = { 0x00, 0xf0, 0x0f, 0xff };
		return ((oldByte & (~mask)) & 0xff) | (byteColors[color] & mask);
	}

protected:
	void markPanel(int x, int y, int w, int h);
};

#endif	// _CPC_6128_H_

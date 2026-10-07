// ql_strip.cpp -- QL: the text strip under the panel, and the save device.
//
// The strip is QL lines 228-255 (layout A: under the panel), three text lines of up to 32
// characters of the GAME'S OWN FONT (the panel/scroll font, roms 0xb400, mapped as
// Marcador::imprimirCaracter does, with its extra W) plus three glyphs it lacks ('-' '/' '_').
// It is outside the CPC screen, so the game, the recolour and hdiff never touch it; it is drawn
// only when its text or the palette changes (src/strip.s), in the panel's text colour (pen 2
// of the panel colours) on black.
//
//   gameplay      "F5-HELP" for the first ~5 s of play, then blank; the help (F5 toggles); a
//                 message for a few seconds (then blank, or the help if it is up)
//   intro         "PRESS SPACE TO CONTINUE" in red, once the parchment has dissolved in
//   otherwise     nothing (the end of the investigation, the ending parchment)
//
// The save device (F3 cycles MDV1_ MDV2_ FLP1_ FLP2_ WIN1_ WIN2_ RAM1_): the save file is
// abadia_sav on it. At start-up the "home" drive is the first of WIN1_ FLP1_ MDV1_ MDV2_ that
// holds the game's own program file; the settings file abadia_cfg (magic, a generation counter,
// the device) is read from home and from MDV2_, the highest counter wins. Without one, the
// header's save-name field (its device part, set by the dev loaders) and then MDV1_. The file
// is written ~2 s after the last F3: to MDV2_ when that is the device chosen, else to home.
// Every file call returns an error code instead of stopping (src/strip.s); display and files
// only: no game state is touched.

#include "ql_strip.h"
#include "ql_port.h"


namespace {

enum { ERR_RO = -20,				// QDOS "read only": a write-protected medium
	   AYUDA_PASOS = 42,		// "F5-HELP" when play starts: ~5 s (120 ms steps; 38 at 130 ms)
	   MSG_PASOS = 22,			// a save/load message: ~2.6 s (20 at 130 ms)
	   DISP_PASOS = 17,			// SAVE DEVICE: ...: ~2 s (15 at 130 ms)
	   CFG_PASOS = 17 };		// the settings file, ~2 s after the last F3 (15 at 130 ms)

struct QStr { UINT16 len; char s[46]; };	// a QDOS string (even address: UINT16 first)

// F3's order (2026-10-05: MDV1_ first, the default)
const char *const dispositivos[] = { "mdv1_", "mdv2_", "flp1_", "flp2_", "win1_", "win2_", "ram1_" };
const int numDispositivos = 7;
const char *const sondeo[] = { "win1_", "flp1_", "mdv1_", "mdv2_" };	// the home drive, in order
#ifdef QL_RELEASE
const char programa[] = "abadia";			// the release job (build_release.sh)
#else
const char programa[] = "abadia_h_bin";		// the dev image (build_hybrid.sh)
#endif

const UINT8 *fuente;				// roms + 0xb400: '-' (0x2d) .. 'Z'
char disp[8] = "mdv1_";				// the save device (lower case, ends in '_')
int dispIdx = 0;					// its place in dispositivos (-1: from the header, not listed)
char casa[8];						// the home drive ("" = not found)
unsigned int generacion;			// the settings file's counter (highest seen / written)

bool ayuda;							// F5: the help instead of a blank strip
int ayudaPasos;						// > 0: "F5-HELP" is up (the first ~5 s of play)
char msg[33];						// a message replacing both for msgPasos steps
int msgPasos;						// > 0 counting; -1 = until replaced (SAVING/LOADING)
int cfgPasos;						// > 0: steps until the settings file is written
bool visible, sucio = true, enIntro, teclaF3, teclaF5;

// the glyphs the CPC font lacks, in its style (2-pixel strokes); the W is the fork's
const UINT8 glifoW[8] = { 0x00,0x66,0xe6,0xc6,0xd6,0xd6,0xfe,0x66 };
const UINT8 glifoGuion[8] = { 0x00,0x00,0x00,0x00,0x3e,0x7c,0x00,0x00 };	// '-'
const UINT8 glifoBarra[8] = { 0x00,0x03,0x06,0x0c,0x18,0x30,0x60,0xc0 };	// '/'
const UINT8 glifoSubr[8] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xfe };	// '_'
const UINT8 glifoBlanco[8] = { 0 };

int largo(const char *s) { int n = 0; while (s[n]) n++; return n; }

void copia(char *d, const char *s, int max)
{
	int i = 0;
	for (; s[i] && i < max - 1; i++) d[i] = s[i];
	d[i] = 0;
}

void anade(char *d, const char *s, int max)
{
	int n = largo(d);
	copia(d + n, s, max - n);
}

void mayus(char *d, const char *s, int max)
{
	copia(d, s, max);
	for (int i = 0; d[i]; i++) if (d[i] >= 'a' && d[i] <= 'z') d[i] -= 32;
}

bool igual(const char *a, const char *b)
{
	while (*a && *a == *b){ a++; b++; }
	return *a == *b;
}

void nombre(QStr *q, const char *dev, const char *fich)
{
	char t[46];
	copia(t, dev, sizeof t);
	anade(t, fich, sizeof t);
	q->len = (UINT16)largo(t);
	for (int i = 0; i < q->len; i++) q->s[i] = t[i];
}

const UINT8 *glifo(int c)
{
	if (c >= 'a' && c <= 'z') c -= 32;
	switch (c){
		case ' ': return glifoBlanco;
		case '-': return glifoGuion;
		case '/': return glifoBarra;
		case '_': return glifoSubr;
		case 'W': return glifoW;
		case ',': c = 0x3c; break;			// as Marcador::imprimirCaracter
		case '.': c = 0x3d; break;
	}
	if (c < 0x30 || c > 'Z') return glifoBlanco;	// (0x2d-0x2f hold other glyphs)
	return fuente + 8*(c - 0x2d);
}

// one text line: its glyphs looked up once, then each of its 8 rows into 32 bytes of bits,
// centred (x is a multiple of 4: half-byte shifts only)
struct Linea { int n, x; const UINT8 *g[32]; };

void preparaLinea(Linea *l, const char *t)
{
	l->n = 0;
	if (!t) return;
	int n = largo(t);
	if (n > 32) n = 32;
	l->n = n;
	l->x = (256 - 8*n)/2;
	for (int i = 0; i < n; i++) l->g[i] = glifo((UINT8)t[i]);
}

void fila(const Linea *l, int r, UINT8 *bits)
{
	for (int i = 0; i < 32; i++) bits[i] = 0;
	int x = l->x;
	for (int i = 0; i < l->n; i++, x += 8){
		UINT8 g = l->g[i][r];
		int b = x >> 3;
		if (x & 4){
			bits[b] |= g >> 4;
			if (b + 1 < 32) bits[b + 1] |= (UINT8)(g << 4);
		} else {
			bits[b] |= g;
		}
	}
}

// the whole strip (28 lines), no clear first (no flicker): 1 line in the middle, or 3
void dibujaTextos(const char *l0, const char *l1, const char *l2, int color)
{
	static Linea ls[3];
	static const Linea vacia = { 0, 0, { 0 } };
	UINT8 bits[32];
	preparaLinea(&ls[0], l0);
	preparaLinea(&ls[1], l1);
	preparaLinea(&ls[2], l2);
	for (int y = 228; y < 256; y++){
		int k = (y - 230) >> 3, r = (y - 230) & 7;
		fila((y < 230 || y >= 254) ? &vacia : &ls[k], r, bits);
		ql_strip_line(y, bits, color);
	}
}

int colorTexto(int paleta)
{
	if (paleta != 3) paleta = 2;		// gameplay: day or night (0/1 only in transitions)
	return 0x100 + paleta;
}

void dibuja(int paleta)
{
	char a[33], b[33], c[33], D[8];
	mayus(D, disp, sizeof D);
	if (msgPasos){
		dibujaTextos(0, msg, 0, colorTexto(paleta));
	} else if (ayuda){
		copia(a, "F1-SAVE F2-LOAD F3-DEVICE:", sizeof a); anade(a, D, sizeof a);	// 31 characters
		copia(b, "ARROW L/R-TURN UP-WALK DOWN-ADSO", sizeof b);				// 32
		copia(c, "SPACE-DROP ITEM F5-HIDE", sizeof c);
		dibujaTextos(a, b, c, colorTexto(paleta));
	} else if (ayudaPasos > 0){
		dibujaTextos(0, "F5-HELP", 0, colorTexto(paleta));
	} else {
		dibujaTextos(0, 0, 0, colorTexto(paleta));	// blank
	}
	visible = true;
	sucio = false;
	qlsPaletaDibujada = paleta;
}

// msg = a + the device in capitals + b
void mensaje(const char *a, const char *dev, const char *b, int pasos)
{
	char D[8];
	copia(msg, a, sizeof msg);
	if (dev){ mayus(D, dev, sizeof D); anade(msg, D, sizeof msg); }
	if (b) anade(msg, b, sizeof msg);
	msgPasos = pasos;
	ayudaPasos = 0;			// after a message: blank (or the help, if it is up)
	sucio = true;
}

bool esMdv(const char *dev) { return dev[0] == 'm' && dev[1] == 'd' && dev[2] == 'v'; }

// a failed write: write-protected (any device), no cartridge (a microdrive: its directory does
// not open), or the message given
void fallo(const char *dev, int err, const char *a, const char *d)
{
	QStr q;
	nombre(&q, dev, "");
	if (err == ERR_RO) mensaje("", dev, " IS WRITE PROTECTED", MSG_PASOS);
	else if (esMdv(dev) && ql_fprobe(&q, 4) != 0) mensaje("INSERT ", dev, " SAVE CARTRIDGE", MSG_PASOS);
	else mensaje(a, d, 0, MSG_PASOS);
}

// a settings file: "ABDV", the counter (big-endian), the device's length and characters
void leeCfg(const char *dev, bool *hay)
{
	QStr q;
	char b[24];
	nombre(&q, dev, "abadia_cfg");
	int n = ql_fload(&q, b, sizeof b);
	if (n < 10 || b[0] != 'A' || b[1] != 'B' || b[2] != 'D' || b[3] != 'V') return;
	unsigned int g = ((unsigned)(UINT8)b[4] << 24) | ((unsigned)(UINT8)b[5] << 16) |
		((unsigned)(UINT8)b[6] << 8) | (UINT8)b[7];
	int l = (UINT8)b[8];
	if (l < 2 || l > 7 || 9 + l > n || b[8 + l] != '_') return;
	if (*hay && g <= generacion) return;
	for (int i = 0; i < l; i++){
		char c = b[9 + i];
		if (c >= 'A' && c <= 'Z') c += 32;
		disp[i] = c;
	}
	disp[l] = 0;
	generacion = g;
	*hay = true;
}

void escribeCfg()
{
	const char *dest = igual(disp, "mdv2_") ? "mdv2_" : (casa[0] ? casa : disp);
	char b[16];
	int l = largo(disp);
	generacion++;
	b[0] = 'A'; b[1] = 'B'; b[2] = 'D'; b[3] = 'V';
	b[4] = (char)(generacion >> 24); b[5] = (char)(generacion >> 16);
	b[6] = (char)(generacion >> 8); b[7] = (char)generacion;
	b[8] = (char)l;
	for (int i = 0; i < 7; i++) b[9 + i] = i < l ? disp[i] : 0;
	QStr q;
	nombre(&q, dest, "abadia_cfg");
	int r = ql_fsave(&q, b, sizeof b);
	if (r != (int)sizeof b) fallo(dest, r, "SETTING NOT SAVED", 0);
}

void buscaIdx()
{
	dispIdx = -1;
	for (int i = 0; i < numDispositivos; i++) if (igual(disp, dispositivos[i])) dispIdx = i;
}

}	// namespace

unsigned char qlsPendiente = 1;		// ql_strip.h: qlsJuego's fast check
int qlsPaletaDibujada = -1;

static void pendiente()
{
	qlsPendiente = !visible || sucio || msgPasos || cfgPasos || ayudaPasos || teclaF3 || teclaF5;
}

void qlsInicio(const UINT8 *roms)
{
	fuente = roms + 0xb400;
	// the home drive: where the game's own program file is
	casa[0] = 0;
	for (int i = 0; i < 4 && !casa[0]; i++){
		QStr q;
		nombre(&q, sondeo[i], programa);
		if (ql_fprobe(&q, 1) == 0) copia(casa, sondeo[i], sizeof casa);
	}
	// the settings files: home and MDV2_, the highest counter wins
	bool hay = false;
	generacion = 0;
	if (casa[0]) leeCfg(casa, &hay);
	if (!igual(casa, "mdv2_")) leeCfg("mdv2_", &hay);
	if (!hay){
		// the header's save-name field (its device part: up to the first '_'), else MDV1_
		copia(disp, "mdv1_", sizeof disp);
		int l = hdr_savename[0];
		const char *s = (const char *)&hdr_savename[1];
		int k = 0;
		while (k < l && k < 7 && s[k] != '_') k++;
		if (l > 0 && k >= 1 && k < 7 && k < l && s[k] == '_'){
			for (int i = 0; i <= k; i++){
				char c = s[i];
				if (c >= 'A' && c <= 'Z') c += 32;
				disp[i] = c;
			}
			disp[k + 1] = 0;
		}
	}
	buscaIdx();
	pendiente();
}

void qlsJuegoPaso(int paleta)
{
	if (msgPasos > 0 && --msgPasos == 0) sucio = true;
	if (cfgPasos > 0 && --cfgPasos == 0) escribeCfg();
	if (!visible) ayudaPasos = AYUDA_PASOS;		// play starts (intro end, a new game): F5-HELP ~5 s
	else if (ayudaPasos > 0 && --ayudaPasos == 0) sucio = true;
#ifdef QL_ASM_KERNELS		// (QL builds only) the asm's key table straight: no calls per step
	bool f3 = key_state[QK_F3] != 0, f5 = key_state[QK_F5] != 0;
#else
	bool f3 = ql_key_down(QK_F3) != 0, f5 = ql_key_down(QK_F5) != 0;
#endif
	if (f3 && !teclaF3){
		dispIdx = (dispIdx + 1) % numDispositivos;	// (-1, a device from the header: MDV1_ next)
		copia(disp, dispositivos[dispIdx], sizeof disp);
		mensaje("SAVE DEVICE: ", disp, 0, DISP_PASOS);
		cfgPasos = CFG_PASOS;
	}
	if (f5 && !teclaF5){
		ayuda = !ayuda;
		if (msgPasos > 0) msgPasos = 0;
		ayudaPasos = 0;			// hidden again: blank
		sucio = true;
	}
	teclaF3 = f3;
	teclaF5 = f5;
	if (!visible || sucio || paleta != qlsPaletaDibujada) dibuja(paleta);
	pendiente();
}

void qlsFueraDeJuego()
{
	if (visible) ql_strip_clear();
	visible = false;
	pendiente();
}

void qlsIntro(bool mostrar)
{
	if (mostrar){
		dibujaTextos(0, "PRESS SPACE TO CONTINUE", 0, 2);	// QL red
		enIntro = true;
	} else if (enIntro){
		ql_strip_clear();
		enIntro = false;
	}
}

void qlsPaleta()
{
	sucio = true;
	pendiente();
}

bool qlsGuardar(const char *buf, int len, int paleta)
{
	QStr q;
	nombre(&q, disp, "abadia_sav");
	mensaje("SAVING TO ", disp, "...", -1);
	dibuja(paleta);							// up before the drive starts
	int r = ql_fsave(&q, buf, len);
	bool ok = r == len;
	if (ok) mensaje("GAME SAVED", 0, 0, MSG_PASOS);
	else fallo(disp, r, "SAVE FAILED: ", disp);
	pendiente();
	return ok;
}

int qlsCargar(char *buf, int cap, int paleta)
{
	QStr q;
	nombre(&q, disp, "abadia_sav");
	mensaje("LOADING FROM ", disp, "...", -1);
	dibuja(paleta);
	int n = ql_fload(&q, buf, cap);
	if (n > 0){ pendiente(); return n; }
	// nothing read: is there a medium at all? (a microdrive: the cartridge)
	QStr d;
	nombre(&d, disp, "");
	if (esMdv(disp) && ql_fprobe(&d, 4) != 0) mensaje("INSERT ", disp, " SAVE CARTRIDGE", MSG_PASOS);
	else mensaje("NO SAVED GAME ON ", disp, 0, MSG_PASOS);
	pendiente();
	return 0;
}

void qlsCargado(bool ok)
{
	mensaje(ok ? "GAME LOADED" : "LOAD FAILED", 0, 0, MSG_PASOS);
	pendiente();
}

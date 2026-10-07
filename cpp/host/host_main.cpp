// host_main.cpp -- the PC "oracle": the same C++ logic as the QL image, with a host
// implementation of the platform hooks (cpp/port/ql_port.h).
//
//   oracle <roms.bin> <script> <ticks> <state_out> [dumpdir] [dump ticks...]
//
// script: lines "first last KEY KEY ..." (ticks inclusive); keys UP DOWN LEFT RIGHT SPACE Q R S N.
// state_out receives STATE_SIZE bytes per tick (after abadia_tick + abadia_sync), the same
// block the QL image writes at header +32. Screens are dumped as raw 320x200 ink bytes
// (play area y 0..159, panel 160..199) to dumpdir/screen_NNNNN.bin.

#include "ql_port.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>
#include <string>

extern "C" int abadia_game_over(void);

static unsigned char romImage[0x24000];
static unsigned char screen[320*200];
#ifdef QL_HOST_CLASSES
// oracle_scenes: which source drew each screen pixel (ql_hostcls.h), for tools/colour_mapper.html
#include "ql_hostcls.h"
static unsigned char screenCls[320*200];
static int curCls = QLC_TERRAIN;
unsigned char *qlc_mixBase, *qlc_mixCls;
int qlc_tick;
int qlc_mixLen;
extern "C" void qlc_register(unsigned char *buf, int len)
{
	qlc_mixBase = buf;
	qlc_mixLen = len;
	qlc_mixCls = (unsigned char *)calloc(len, 1);
}
extern "C" void qlc_begin(unsigned char *p, int n, unsigned char *save)
{
	memcpy(save, p, n);
	memset(p, QLC_SENTINEL, n);
}
extern "C" void qlc_end(unsigned char *p, int n, const unsigned char *save, int cls)
{
	unsigned char *c = qlc_mixCls + (p - qlc_mixBase);
	for (int i = 0; i < n; i++){
		if (p[i] == QLC_SENTINEL) p[i] = save[i];
		else c[i] = (unsigned char)cls;
	}
}
#define SETCLS(i, v) (screenCls[i] = (unsigned char)(v))
#include "Juego.h"
#include "Logica.h"
#include "Paleta.h"
#else
#define SETCLS(i, v) ((void)0)
#endif
static int keys[QK_COUNT];
static int curPalette = 2;

struct ScriptLine { int first, last; int k[QK_COUNT]; };
static std::vector<ScriptLine> script;

extern "C" unsigned char *ql_rom_image(void) { return romImage; }
extern "C" int ql_key_down(int key) { return (key >= 0 && key < QK_COUNT) ? keys[key] : 0; }
#include "ql_sound.h"
static FILE *ayLog;
static int ayFrame;
// AY register writes, logged per 50 Hz frame for tools/ayrender.py (frame reg val)
extern "C" void ql_ay_write(int reg, int val) { if (ayLog) fprintf(ayLog, "%d %d %d\n", ayFrame, reg, val); }
extern "C" void ql_debug(int, int) {}
extern "C" void ql_phase(int) {}
// the QL image's harness night switch (header +31 bit 5); the host does FORCE_NIGHT itself
extern "C" int ql_harness_night(void) { return 0; }
// the QL's mirror / save-load harness (header +31 bit 6): FORCE_MIRROR here; no cache to verify
extern "C" int ql_harness_mirror(void) { return getenv("FORCE_MIRROR") ? 1 : 0; }
extern "C" int ql_harness_hgverify(void) { return 0; }
extern "C" int ql_frames_real(void) { return -1; }	// the nominal clock (ql_game.cpp)

static const char *saveFile() { return getenv("SAVEFILE") ? getenv("SAVEFILE") : "abadia_sav"; }
extern "C" int ql_file_save(const char *buf, int len)
{
	FILE *f = fopen(saveFile(), "wb");
	if (!f) return -1;
	int n = (int)fwrite(buf, 1, len, f);
	fclose(f);
	return n;
}
extern "C" int ql_file_load(char *buf, int cap)
{
	FILE *f = fopen(saveFile(), "rb");
	if (!f) return -1;
	int n = (int)fread(buf, 1, cap, f);
	fclose(f);
	return n;
}
// the save device's files (src/strip.s on the QL): the oracle has one save file (SAVEFILE),
// whatever the device; no program file, no settings file, every device has a medium
extern "C" int ql_fsave(const void *, const char *buf, int len) { return ql_file_save(buf, len); }
extern "C" int ql_fload(const void *name, char *buf, int cap)
{
	const unsigned char *q = (const unsigned char *)name;
	int n = *(const unsigned short *)q;			// (the QStr length, native order)
	if (n >= 10 && !memcmp(q + 2 + n - 10, "abadia_cfg", 10)) return -7;
	return ql_file_load(buf, cap);
}
extern "C" int ql_fprobe(const void *, int key) { return key == 4 ? 0 : -7; }
// the text strip under the panel is outside the CPC screen: nothing to model
extern "C" void ql_strip_line(int, const unsigned char *, int) {}
extern "C" void ql_strip_clear(void) {}
extern "C" { unsigned short hdr_savename[22] = { 0 }; }
extern "C" void ql_set_palette(int pal) { curPalette = pal; }

static void put(int x, int y, int ink)
{
	if (x < 32 || x >= 288 || y < 0 || y >= 200) return;	// y >= 160 only in parchment mode
	screen[y*320 + x] = ink & 3;
	SETCLS(y*320 + x, curCls);
}

extern "C" void ql_play_fill(int x, int y, int w, int h, int ink)
{
	for (int j = 0; j < h; j++) for (int i = 0; i < w; i++) put(x + i, y + j, ink);
}

extern "C" void ql_play_pixel(int x, int y, int ink) { put(x, y, ink); }
extern "C" void ql_play_triangle(int x, int y, int lado, int c1, int c2)
{
	for (int j = 0; j < lado; j++){
		if (y + j < 0 || y + j >= 200) continue;
		for (int i = 0; i <= j; i++) put(x + i, y + j, c1);
		for (int i = 0; i < 4; i++) put(x + j + i + 1, y + j, c2);
	}
}

extern "C" void ql_play_triangle_old(int x, int y, int lado, int c1, int c2) { ql_play_triangle(x, y, lado, c1, c2); }
extern "C" int ql_pagina_vieja(void) { return 0; }
extern "C" void ql_play_triangle_inc(int x, int y, int lado, int c1, int c2, int, int) { ql_play_triangle(x, y, lado, c1, c2); }
// packed CPC Mode 1 bytes (4 pixels each), as the parchment's page-turn restores use it
extern "C" void ql_play_blit_p(int x, int y, int w, int h, const unsigned char *src, int stride)
{
	for (int j = 0; j < h; j++){
		for (int i = 0; i < w/4; i++){
			int d = src[j*stride + i];
			for (int k = 0; k < 4; k++) put(x + i*4 + k, y + j, (((d >> (3 - k)) & 1) << 1) | ((d >> (7 - k)) & 1));
		}
	}
}

// CPC tile drawing: AND/OR tables by bit 7 of the tile (pen 2 transparent for tiles
// 0x00-0x7f, pen 1 for 0x80-0xff), as the CPC routine at 0x4f3d.
// QL_TILE_COMPOSE: the host draws straight from the tile table
extern "C" void ql_tile_rebuild(int id) { }
extern "C" int ql_espiral_vieja(void) { return 0; }
extern "C" void ql_play_fill(int x, int y, int w, int h, int ink);
extern "C" void ql_play_black(void) { ql_play_fill(32, 0, 256, 160, 3); }	// pen 3 = QL black
extern "C" void ql_play_tile(int x, int y, int tile);
extern "C" void ql_play_cell(int x, int y, int t0, int t1)
{
	ql_play_fill(x, y, 16, 8, 0);
	if (t0) ql_play_tile(x, y, t0);
	if (t1) ql_play_tile(x, y, t1);
}

extern "C" void ql_play_tile(int x, int y, int tile)
{
	const unsigned char *t = &romImage[0x4000 + 0x8300 + (tile & 0xff)*32];
	int transp = (tile & 0x80) ? 1 : 2;
	for (int j = 0; j < 8; j++){
		for (int i = 0; i < 4; i++){
			int d = *t++;
			for (int k = 0; k < 4; k++){
				int ink = (((d >> (3 - k)) & 1) << 1) | ((d >> (7 - k)) & 1);
				if (ink != transp) put(x + i*4 + k, y + j, ink);
			}
		}
	}
}

extern "C" void ql_play_blit(int x, int y, int w, int h, const unsigned char *src, int stride)
{
#ifdef QL_HOST_CLASSES
	const unsigned char *cs = qlc_mixCls + (src - qlc_mixBase);
	for (int j = 0; j < h; j++) for (int i = 0; i < w; i++){
		curCls = cs[j*stride + i];
		put(x + i, y + j, src[j*stride + i]);
	}
	curCls = QLC_TERRAIN;
#else
	for (int j = 0; j < h; j++) for (int i = 0; i < w; i++) put(x + i, y + j, src[j*stride + i]);
#endif
}

extern "C" void ql_panel_present(int x, int y, int w, int h, const unsigned char *panel)
{
	for (int j = 0; j < h; j++) for (int i = 0; i < w; i++)
	{
		screen[(160 + y + j)*320 + x + i] = panel[(y + j)*320 + x + i] & 3;
		SETCLS((160 + y + j)*320 + x + i, 3);
	}
}

// the QL scrolls the screen's words (src/qlhooks.s); the host presents the moved pens instead,
// so hdiff checks the QL's moved words against a present of the pens
extern "C" void ql_panel_scroll(int x, int y, int w, int h, int dx, const unsigned char *panel)
{
	ql_panel_present(x - dx, y, w, h, panel);
}

static int keyIndex(const char *s)
{
	static const char *names[QK_COUNT] = { "UP", "DOWN", "LEFT", "RIGHT", "SPACE", "Q", "R", "S", "N", "ESC", "F1", "F2", "F3", "F5", "Y" };
	for (int i = 0; i < QK_COUNT; i++) if (!strcmp(s, names[i])) return i;
	return -1;
}

static void loadScript(const char *path)
{
	FILE *f = fopen(path, "r");
	if (!f){ fprintf(stderr, "no script %s\n", path); exit(2); }
	char line[512];
	while (fgets(line, sizeof line, f)){
		char *p = strchr(line, '#'); if (p) *p = 0;
		ScriptLine sl; memset(&sl, 0, sizeof sl);
		char *tok = strtok(line, " \t\r\n");
		if (!tok) continue;
		sl.first = atoi(tok);
		tok = strtok(0, " \t\r\n");
		if (!tok) continue;
		sl.last = atoi(tok);
		while ((tok = strtok(0, " \t\r\n"))){
			int k = keyIndex(tok);
			if (k < 0){ fprintf(stderr, "bad key %s\n", tok); exit(2); }
			sl.k[k] = 1;
		}
		script.push_back(sl);
	}
	fclose(f);
}

static void setKeys(int tick)
{
	memset(keys, 0, sizeof keys);
	for (auto &sl : script){
		if (tick >= sl.first && tick <= sl.last){
			for (int i = 0; i < QK_COUNT; i++) if (sl.k[i]) keys[i] = 1;
		}
	}
}

extern "C" void abadia_show_screen(int n);
extern "C" void abadia_tilebuf(unsigned char *out);

// --tour roms.bin outdir first last: draws every screen on its own; writes
// outdir/tour_NNN.bin (320x200 pens) and outdir/tiles_NNN.bin (tile buffer)
static int tour(int argc, char **argv)
{
	FILE *f = fopen(argv[2], "rb");
	if (!f || fread(romImage, 1, sizeof romImage, f) != sizeof romImage){ fprintf(stderr, "bad roms\n"); return 2; }
	fclose(f);
	int first = atoi(argv[4]), last = atoi(argv[5]);
	if (getenv("NOCOMPOSE")) ql_compose_on = 0;
	abadia_init(0);
	for (int n = first; n <= last; n++){
		memset(screen, 0, sizeof screen);
		abadia_show_screen(n);
		char name[512];
		snprintf(name, sizeof name, "%s/tour_%03d.bin", argv[3], n);
		FILE *s = fopen(name, "wb"); fwrite(screen, 1, sizeof screen, s); fclose(s);
		unsigned char tb[20*16*2*3];
		abadia_tilebuf(tb);
		snprintf(name, sizeof name, "%s/tiles_%03d.bin", argv[3], n);
		s = fopen(name, "wb"); fwrite(tb, 1, sizeof tb, s); fclose(s);
	}
	return 0;
}

// --sndtest roms.bin out.txt: every sound entry (and the two parchment tunes) on a fresh
// engine, AY writes logged as "case frame reg val" (tools/sndtest.py compares with the QL)
static const int sndCases[] = { 0x0ffd, 0x1002, 0x1007, 0x100c, 0x1011, 0x1016, 0x101b, 0x1020,
	0x1025, 0x102a, 0x102f, -1, -2 };
extern "C" int snd_test_frames(int c) { return c < 0 ? 1500 : 150; }
static int sndtest(char **argv)
{
	FILE *f = fopen(argv[2], "rb");
	if (!f || fread(romImage, 1, sizeof romImage, f) != sizeof romImage){ fprintf(stderr, "bad roms\n"); return 2; }
	fclose(f);
	ayLog = fopen(argv[3], "w");
	for (unsigned k = 0; k < sizeof sndCases/sizeof sndCases[0]; k++){
		int c = sndCases[k];
		snd_init(romImage + 0x4000);
		if (c == -1) ql_music(0); else if (c == -2) ql_music(1); else snd_play(c);
		fprintf(ayLog, "case %d\n", c);
		for (ayFrame = 0; ayFrame < snd_test_frames(c); ayFrame++) snd_poll();
	}
	fclose(ayLog);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc >= 6 && !strcmp(argv[1], "--tour")) return tour(argc, argv);
	if (argc >= 4 && !strcmp(argv[1], "--sndtest")) return sndtest(argv);
	if (argc < 5){
		fprintf(stderr, "usage: oracle roms.bin script ticks state_out [dumpdir tick...]\n");
		return 2;
	}
	FILE *f = fopen(argv[1], "rb");
	if (!f || fread(romImage, 1, sizeof romImage, f) != sizeof romImage){ fprintf(stderr, "bad roms\n"); return 2; }
	fclose(f);
	loadScript(argv[2]);
	int ticks = atoi(argv[3]);
	FILE *out = fopen(argv[4], "wb");
	const char *dumpdir = argc > 5 ? argv[5] : 0;
	std::vector<int> dumps;
	for (int i = 6; i < argc; i++) dumps.push_back(atoi(argv[i]));

	if (getenv("AYLOG")) ayLog = fopen(getenv("AYLOG"), "w");
	if (getenv("NOCOMPOSE")) ql_compose_on = 0;	// QL_TILE_COMPOSE off: the CPC's tile buffers
	abadia_init(getenv("INTRO") ? 1 : 0);
	unsigned char blk[STATE_SIZE];
	for (int t = 0; t < ticks; t++){
		setKeys(t);
#ifdef QL_HOST_CLASSES
		int palBefore = curPalette;
		// FORCE_NIGHT: real game frames at night (time of day NOCHE, night palette) for the tool
		if (t == 2 && getenv("FORCE_NIGHT")){
			Abadia::elJuego->logica->momentoDia = 0;
			Abadia::elJuego->paleta->setGamePalette(3);
		}
#endif
#ifdef QL_HOST_CLASSES
		qlc_tick = t;
#endif
		abadia_tick();
#ifdef QL_HOST_CLASSES
		if (getenv("PALTRACE") && curPalette != palBefore) fprintf(stderr, "tick %d palette %d\n", t, curPalette);
#endif
		abadia_sync();
		// sound: 6.5 frames of 50 Hz polls per 130 ms step, as on the QL
		for (int k = 0; k < ((t & 1) ? 7 : 6); k++){ snd_poll(); ayFrame++; }
		abadia_state(blk);
		fwrite(blk, 1, STATE_SIZE, out);
		for (int d : dumps){
			if (d == t && dumpdir){
				char name[512];
				snprintf(name, sizeof name, "%s/screen_%05d.bin", dumpdir, t);
				FILE *s = fopen(name, "wb");
				fwrite(screen, 1, sizeof screen, s);
				fclose(s);
#ifdef QL_HOST_CLASSES
				snprintf(name, sizeof name, "%s/cls_%05d.bin", dumpdir, t);
				s = fopen(name, "wb");
				fwrite(screenCls, 1, sizeof screenCls, s);
				fclose(s);
				snprintf(name, sizeof name, "%s/pal_%05d.txt", dumpdir, t);
				s = fopen(name, "w");
				fprintf(s, "%d\n", curPalette);
				fclose(s);
#endif
			}
		}
	}
	fclose(out);
	return 0;
}

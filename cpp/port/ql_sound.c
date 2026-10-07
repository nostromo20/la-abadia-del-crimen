/* ql_sound.c -- the CPC game's sound/music engine (CPC 0x0ffd-0x1385, Manuel Abadia's
 * commented disassembly), translated routine by routine to C.
 *
 * The engine state lives in a byte array that mirrors CPC memory 0x0f96-0x0fe4 (three
 * channel entries of 0x18 bytes at 0x0f9d/0x0fb5/0x0fcd, addressed as ix-3..ix+0x14 with
 * ix = 0x0fa0/0x0fb8/0x0fd0), initialised from the game image. Sound data are read from the
 * game image at their CPC addresses (roms[addr], as VIGASOCO indexes it).
 *
 * The CPC calls the update (0x1060) from its 300 Hz interrupt; the QL calls snd_tick300()
 * six times per 50 Hz poll. PSG writes go to a shadow register file; snd_flush() hands the
 * registers that changed to the platform (ql_ay_write), with tone/noise/envelope periods
 * scaled from the CPC's 1 MHz AY clock to the target's (QL_AY_NUM/QL_AY_DEN).
 */
#include "ql_port.h"
#include "ql_sound.h"

#ifndef QL_AY_NUM
#define QL_AY_NUM 3          /* QSound AY clock 1.5 MHz / CPC 1 MHz (the author's earlier QSound work) */
#define QL_AY_DEN 2
#endif

static const unsigned char *rom;          /* CPC address space (VIGASOCO roms) */
static unsigned char ram[0x50];           /* CPC 0x0f96 - 0x0fe5 */
static unsigned char psg[16], psgOut[16], psgDirty[16];
#ifdef QL_FAST_SOUND
/* QL: set by every psgWrite. With no write since the last flush, psg[] is unchanged, so the
   flush would compute the same out[] (== psgOut[0..13]) with no psgDirty set: nothing to send. */
static unsigned char psgAny;
#endif
static int tempoReload = 6;               /* operand of the instruction at 0x1085 */
static int windowSrc;
static volatile int ready;                /* set last by snd_init; snd_poll does nothing before */
static volatile unsigned char reqHead, reqTail;   /* request ring, see snd_poll */
/* CPC 0x8000-0x9517 is where the game copies the parchment music; for the ending it comes
   from abadia8 (roms 0x1eb28), for the intro it is abadia3 as loaded (roms 0x8000) */

#define ROMB(a) rom[(a)]
#ifdef QL_FAST_SOUND
static inline int MEM(int a)
#else
static int MEM(int a)
#endif
{
	a &= 0xffff;
	if (a >= 0x8000 && a < 0x9518) return rom[windowSrc + (a - 0x8000)];
	return rom[a];
}

#define R(a) ram[(a) - 0x0f96]
#ifdef QL_FAST_SOUND
/* QL: each routine taking ix makes a pointer to its channel entry once (CHP) */
#define CHP unsigned char *const chp = &ram[ix - 0x0f96]
#define IX(off) chp[(off)]
#else
#define CHP
#define IX(off) ram[ix - 0x0f96 + (off)]
#endif

static void psgWrite(int reg, int val)
{
	psg[reg & 15] = (unsigned char)val;
	psgDirty[reg & 15] = 1;
#ifdef QL_FAST_SOUND
	psgAny = 1;
#endif
}

void snd_init(const unsigned char *romImage)
{
	int i;
	ready = 0;                            /* the poll interrupt ignores the engine until set */
	for (i = 0; i < 0x50; i++) ram[i] = romImage[0x0f96 + i];
	for (i = 0; i < 16; i++){ psg[i] = 0; psgOut[i] = 0xff; psgDirty[i] = 1; }
	psg[7] = 0x3f;
#ifdef QL_FAST_SOUND
	psgAny = 1;                           /* the first flush sends every register */
#endif
	tempoReload = 6;
	windowSrc = 0x8000;
	reqTail = reqHead;                    /* drop requests made before (re)initialisation */
	rom = romImage;
	ready = 1;
}

/* 0x1376: stops all sound */
void snd_stop(void)
{
	R(0x0fae) = R(0x0fc6) = R(0x0fde) = 0x84;
	psgWrite(7, 0x3f);
}

/* 0x104f: starts channel entry ix with the data at addr */
static void startChannel(int ix, int addr)
{
	CHP;
	IX(0x0e) = 0x05;
	IX(0x00) = addr & 0xff;
	IX(0x01) = addr >> 8;
	IX(0x02) = 0x01;
}

/* entry points 0x0ffd-0x102f and 0x103f (music) */
void snd_play(int entry)
{
	switch (entry){
		case 0x0ffd: startChannel(0x0fa0, 0x1480); break;
		case 0x1002: startChannel(0x0fd0, 0x1496); break;
		case 0x1007: if (R(0x0fde) == 0) startChannel(0x0fd0, 0x13fe); break;   /* 0x1034: only if channel 3 is idle */
		case 0x100c: startChannel(0x0fa0, 0x14f3); break;
		case 0x1011: startChannel(0x0fa0, 0x14ba); break;
		case 0x1016: startChannel(0x0fb8, 0x1560); break;
		case 0x101b: startChannel(0x0fb8, 0x14e7); break;
		case 0x1020: startChannel(0x0fd0, 0x14b1); break;
		case 0x1025: startChannel(0x0fb8, 0x149f); break;
		case 0x102a: startChannel(0x0fb8, 0x1550); break;
		case 0x102f: startChannel(0x0fb8, 0x14a8); break;
	}
}

/* 0x24d8/0x38d3: parchment music at CPC 0x8000 on channel 1, tempo reload 0x0b */
void snd_music(int addr, int tempo, int src)
{
	tempoReload = tempo;
	windowSrc = src;
	startChannel(0x0fa0, addr);
}

/* 0x1231: base tone table */
static void toneTable(int ix)
{
	CHP;
	for (;;){
		int a = IX(0x09);
		int hl = (IX(0x05) | (IX(0x06) << 8)) + a;
		int v = MEM(hl & 0xffff);
		if (v == 0x7f){
			IX(0x11) = IX(0x0f) = IX(0x08) = 0xff;
			IX(0x13) = 0;
			return;
		}
		if (v == 0x80){
			IX(0x09) = 0;
			continue;
		}
		IX(0x08) = v;
		IX(0x13) = MEM((hl + 1) & 0xffff);
		IX(0x0f) = IX(0x11) = MEM((hl + 2) & 0xffff);
		IX(0x09) = (IX(0x09) + 3) & 0xff;
		return;
	}
}

/* 0x129b: envelope / volume table */
static void envTable(int ix)
{
	CHP;
	for (;;){
		int hl = (IX(0x0a) | (IX(0x0b) << 8)) + IX(0x0c);
		int v = MEM(hl & 0xffff);
		if (v == 0x7f){
			IX(0x12) = IX(0x10) = IX(0x0d) = 0xff;
			IX(0x14) = 0;
			return;
		}
		if (v == 0x80){
			IX(0x0c) = 0;
			continue;
		}
		if (v & 0x80){
			R(0x0f9b) = v & 0x0f;
			R(0x0f99) = MEM((hl + 1) & 0xffff);
			R(0x0f9a) = MEM((hl + 2) & 0xffff);
			IX(0x12) = MEM((hl + 3) & 0xffff);
			IX(0x0d) = 0x01;
			IX(0x0e) |= 0x10;
			IX(0x0c) = (IX(0x0c) + 4) & 0xff;
			return;
		}
		IX(0x0d) = v;
		IX(0x14) = MEM((hl + 1) & 0xffff);
		IX(0x10) = IX(0x12) = MEM((hl + 2) & 0xffff);
		IX(0x0c) = (IX(0x0c) + 3) & 0xff;
		return;
	}
}

/* 0x1275 */
static void envUpdate(int ix)
{
	CHP;
	IX(0x12) = (IX(0x12) - 1) & 0xff;
	if (IX(0x12) != 0) return;
	IX(0x0d) = (IX(0x0d) - 1) & 0xff;
	if (IX(0x0d) == 0) envTable(ix);
	IX(0x0e) |= 0x20;
	IX(0x12) = IX(0x10);
	if (IX(0x0e) & 0x10) return;
	IX(0x07) = (IX(0x07) + IX(0x14)) & 0x0f;
}

/* 0x114c: processes one channel */
static void processChannel(int ix)
{
	CHP;
	if (!(IX(0x0e) & 0x01)) return;
	IX(0x0e) &= 0x87;
	if (R(0x0f98) == 0){
		IX(0x02) = (IX(0x02) - 1) & 0xff;
		if (IX(0x02) == 0){
			int de;
			IX(0x0e) = 0x01;
			de = IX(0x00) | (IX(0x01) << 8);
			/* 0x116e: command table at 0x1306 (6 entries: pattern, jump) */
			for (;;){
				int a = MEM(de), cmd = -1, k;
				for (k = 0; k < 6; k++){
					if (MEM(0x1306 + k*3) == a){ cmd = MEM(0x1306 + k*3 + 1) | (MEM(0x1306 + k*3 + 2) << 8); break; }
				}
				if (cmd < 0){
					int c, hl;
					if (a == 0xff){ IX(0x0e) = 0; return; }
					hl = de;
					IX(0x11) = IX(0x08) = IX(0x12) = IX(0x0d) = 1;
					IX(0x0c) = IX(0x09) = 0;
					c = MEM(hl); hl++;
					IX(0x02) = MEM(hl); hl++;
					if (c & 0x80){
						R(0x0f9c) = MEM(hl);
						IX(0x0e) |= 0x02 | 0x08;
						hl++;
					}
					IX(0x07) = 0;
					IX(0x00) = hl & 0xff;
					IX(0x01) = (hl >> 8) & 0xff;
					IX(0x0e) |= 0x80;
					if ((c & 0x0f) == 0x0f) return;
					IX(0x0e) &= 0x7f;
					{
						int t = (c & 0x0f) * 2;
						int tone = MEM(0x0fe5 + t) | (MEM(0x0fe5 + t + 1) << 8);
						int oct = (c >> 4) & 0x07;
						tone >>= oct;
						IX(0x03) = tone & 0xff;
						IX(0x04) = (tone >> 8) & 0xff;
					}
					break;
				} else {
					int bc = MEM(de + 1) | (MEM(de + 2) << 8);
					de += 3;
					switch (cmd){
						case 0x131b: R(0x0fb8) = bc & 0xff; R(0x0fb9) = bc >> 8; R(0x0fc6) = 5; R(0x0fba) = 1; break;
						case 0x132a: R(0x0fd0) = bc & 0xff; R(0x0fd1) = bc >> 8; R(0x0fde) = 5; R(0x0fd2) = 1; break;
						case 0x1339: IX(0x05) = bc & 0xff; IX(0x06) = bc >> 8; break;
						case 0x1340: IX(0x0a) = bc & 0xff; IX(0x0b) = bc >> 8; break;
						case 0x1318: de = bc; break;
						default: break;
					}
				}
			}
		}
	}
	/* 0x11f7 */
	if (IX(0x0e) & 0x80) return;
	if (IX(0x0e) & 0x04) return;
	envUpdate(ix);
	IX(0x11) = (IX(0x11) - 1) & 0xff;
	if (IX(0x11) != 0) return;
	IX(0x08) = (IX(0x08) - 1) & 0xff;
	if (IX(0x08) == 0) toneTable(ix);
	IX(0x11) = IX(0x0f);
	{
		int d = (signed char)IX(0x13);
		int f = (IX(0x03) | (IX(0x04) << 8)) + d;
		IX(0x03) = f & 0xff;
		IX(0x04) = (f >> 8) & 0xff;
	}
	IX(0x0e) |= 0x40;
}

/* 0x10d0: writes channel ix to the PSG */
static void writeChannel(int ix)
{
	CHP;
	int l = IX(0x0e), a;
	if (!(l & 0x01)) return;
	if (l & 0x04) return;
	if (l & 0x80) return;
	if (l & 0x40){
		psgWrite(IX(-3), IX(0x03));
		psgWrite(IX(-3) + 1, IX(0x04));
	}
	if (l & 0x20){
		if (!(l & 0x10)){
			psgWrite(IX(-2), IX(0x07));
		} else {
			psgWrite(11, R(0x0f99));
			psgWrite(12, R(0x0f9a));
			psgWrite(13, R(0x0f9b));
			psgWrite(IX(-2), 0x10);
		}
	}
	a = 0x07;
	if (l & 0x02){
		a = 0x3f;
		if (l & 0x08){
			psgWrite(6, R(0x0f9c));
			a = 0x3f;
		}
	}
	a &= IX(-1);
	R(0x0f96) ^= a;
}

/* 0x1060: the 300 Hz update */
void snd_tick300(void)
{
	int a;
	if (!rom) return;
	if (!((R(0x0fae) | R(0x0fc6) | R(0x0fde)) & 0x01)) return;
	a = (R(0x0f98) - 1) & 0xff;
	if (a == 0xff) a = tempoReload;
	R(0x0f98) = a;
	R(0x0f96) = 0x3f;
#ifdef QL_FAST_SOUND
	/* QL: both routines return at once when bit 0 of the entry's +0x0e is clear;
	   test it here, at the same moment, and save the call */
	if (R(0x0fae) & 0x01) processChannel(0x0fa0);
	if (R(0x0fc6) & 0x01) processChannel(0x0fb8);
	if (R(0x0fde) & 0x01) processChannel(0x0fd0);
	if (R(0x0fae) & 0x01) writeChannel(0x0fa0);
	if (R(0x0fc6) & 0x01) writeChannel(0x0fb8);
	if (R(0x0fde) & 0x01) writeChannel(0x0fd0);
#else
	processChannel(0x0fa0);
	processChannel(0x0fb8);
	processChannel(0x0fd0);
	writeChannel(0x0fa0);
	writeChannel(0x0fb8);
	writeChannel(0x0fd0);
#endif
	if (R(0x0f96) != R(0x0f97)){
		R(0x0f97) = R(0x0f96);
		psgWrite(7, R(0x0f96));
	}
}

/* sends the registers that changed, periods scaled to the target AY clock */
void snd_flush(void)
{
	unsigned char out[16];
	int i;
#ifdef QL_FAST_SOUND
	/* QL: same result with no work when nothing was written, and the clock scaling
	   (v*3 + 1)/2 for v >= 0 done with an add and a shift (no long multiply) */
	if (!psgAny) return;
	psgAny = 0;
	for (i = 0; i < 16; i++) out[i] = psg[i];
	for (i = 0; i < 3; i++){
		unsigned int v = psg[i*2] | ((psg[i*2 + 1] & 0x0f) << 8);
		unsigned int p = (v + (v << 1) + 1) >> 1;
		if (p > 0x0fff) p = 0x0fff;
		out[i*2] = p & 0xff;
		out[i*2 + 1] = (p >> 8) & 0x0f;
	}
	{
		unsigned int v = psg[6] & 0x1f;
		unsigned int n = (v + (v << 1) + 1) >> 1;
		if (n > 0x1f) n = 0x1f;
		out[6] = (unsigned char)n;
		v = psg[11] | (psg[12] << 8);
		n = (v + (v << 1) + 1) >> 1;
		if (n > 0xffff) n = 0xffff;
		out[11] = n & 0xff;
		out[12] = (n >> 8) & 0xff;
	}
	for (i = 0; i < 14; i++){
		if (out[i] != psgOut[i] || (i == 13 && psgDirty[13])){
			ql_ay_write(i, out[i]);
			psgOut[i] = out[i];
		}
		psgDirty[i] = 0;
	}
	return;
#endif
	for (i = 0; i < 16; i++) out[i] = psg[i];
	for (i = 0; i < 3; i++){
		long p = ((psg[i*2] | ((psg[i*2 + 1] & 0x0f) << 8)) * (long)QL_AY_NUM + QL_AY_DEN/2) / QL_AY_DEN;
		if (p > 0x0fff) p = 0x0fff;
		out[i*2] = p & 0xff;
		out[i*2 + 1] = (p >> 8) & 0x0f;
	}
	{
		long n = ((psg[6] & 0x1f) * (long)QL_AY_NUM + QL_AY_DEN/2) / QL_AY_DEN;
		if (n > 0x1f) n = 0x1f;
		out[6] = (unsigned char)n;
		n = ((psg[11] | (psg[12] << 8)) * (long)QL_AY_NUM + QL_AY_DEN/2) / QL_AY_DEN;
		if (n > 0xffff) n = 0xffff;
		out[11] = n & 0xff;
		out[12] = (n >> 8) & 0xff;
	}
	for (i = 0; i < 14; i++){
		/* register 13 (envelope shape) restarts the envelope: send it whenever it was written */
		if (out[i] != psgOut[i] || (i == 13 && psgDirty[13])){
			ql_ay_write(i, out[i]);
			psgOut[i] = out[i];
		}
		psgDirty[i] = 0;
	}
}

const unsigned char *snd_psg(void) { return psg; }

/* ---------------------------------------------------------------------------
 * requests from the game (main program) to the engine (50 Hz poll interrupt):
 * a small ring buffer, so the main program never touches the engine state that
 * the interrupt is updating (the CPC used di/ei around 0x104f instead)
 * ------------------------------------------------------------------------- */
#define REQ_STOP  0x10000
#define REQ_MUSIC 0x20000
#define REQ_CUT3  0x40000	/* QL_BEEPER: an effect that the CPC played on channel 3 */
static volatile int reqs[16];

static void request(int r)
{
	unsigned char n = (unsigned char)((reqHead + 1) & 15);
	if (n == reqTail) return;            /* full: drop */
	reqs[reqHead] = r;
	reqHead = n;
}

/* SOUNDFILES ids of the fork -> CPC entry points, matched by call site:
 * OPEN 0x101b (0x0da6), HIT 0x102a (0x635a), BELLS 0x100c (prima/sexta), CLOSE 0x1016,
 * GET 0x1025 / LET 0x102f (0x508c), MIRROR 0x0ffd (0x3361), STEPS 0x1002 (0x2620),
 * JINGLE 0x1011 (tercia/completas). The fork's names for 0x100c/0x1011 are kept. */
#ifdef QL_BEEPER
/* QL sound design (the author's): EVERY effect goes to the beeper (ql_beeper.c), on every machine;
 * the AY engine plays music only. id 9 = SPEECH (once per phrase, as the DOS version; the CPC
 * blipped per character). STEPS and SPEECH were channel-3 sounds on the CPC, where they cut the
 * background tune (0x1007, also channel 3) and left the channel free for it again: REQ_CUT3. */
void beep_effect(int id);
void beep_music(int on);
void beep_music_ready(void);
int ql_qsound(void);
#endif

void ql_sound(int id)
{
	static const int entries[9] = { 0x101b, 0x102a, 0x100c, 0x1016, 0x1025, 0x102f, 0x0ffd, 0x1002, 0x1011 };
#ifdef QL_BEEPER
	beep_effect(id);
	if (id == 7 || id == 9) request(REQ_CUT3);
	return;
#endif
	if (id >= 0 && id < 9) request(entries[id]);
}

/* The parchment has been drawn and dissolved in (Pergamino::muestraTexto). The beeper tune is
 * stepped from the main loop, and that first parchment step runs ~2.7 s on the 68008 (the page
 * composed off-screen, then the dissolve), so a tune started at ql_music() lost notes 2-4 and
 * came in late; it now starts here. QSound's tune runs in the poll and is not held. */
void ql_music_ready(void)
{
#ifdef QL_BEEPER
	beep_music_ready();
#endif
}

/* MUSICFILES: START = intro parchment music (CPC 0x24d8), END = ending (0x38c7), -1 stop */
void ql_music(int id)
{
#ifdef QL_BEEPER
	/* no QSound: the DOS parchment tune on the beeper for both parchments; QSound: the CPC tunes */
	if (!ql_qsound()){
		beep_music(id >= 0);
		return;
	}
#endif
	if (id < 0) request(REQ_STOP);
	else if (id == 0) request(REQ_MUSIC | 0);
	else if (id == 1) request(REQ_MUSIC | 1);
}

#ifdef QL_BEEPER
/* CPC 4186-41AB (VIGASOCO Logica::compruebaBonusYCambiosDeCamara): every main-loop pass once the
 * player has not touched the cursor keys for 0x32 passes, the CPC calls 0x1007, which starts the
 * background tune on channel 3 if that channel is idle. QSound only; no beeper music in play. */
void ql_bgmusic(void)
{
	if (ql_qsound()) request(0x1007);
}
#endif

void snd_poll(void)
{
	int i;
	if (!ready) return;
	while (reqTail != reqHead){
		int r = reqs[reqTail];
		reqTail = (unsigned char)((reqTail + 1) & 15);
		if (r == REQ_STOP){ snd_stop(); tempoReload = 6; }	/* CPC 0x2520: game tempo after the intro */
		else if (r == REQ_CUT3){
			/* the CPC effect would have replaced channel 3 and, once over, left it idle (0) */
			if (R(0x0fde) & 0x01) psgWrite(R(0x0fce), 0);	/* silence its volume register */
			R(0x0fde) = 0;
		}
		else if (r & REQ_MUSIC){
			snd_stop();
			if ((r & 0xffff) == 0) snd_music(0x8000, 0x0b, 0x8000);
			else snd_music(0x8000, 0x08, 0x1eb28);
		}
		else snd_play(r);
	}
#ifdef QL_FAST_SOUND
	/* QL: snd_tick300 returns at once while no channel is active, and only a request (handled
	   above) can make one active, so the six steps are skipped as a block */
	if (rom && ((R(0x0fae) | R(0x0fc6) | R(0x0fde)) & 0x01))
#endif
	for (i = 0; i < 6; i++) snd_tick300();
	snd_flush();
}

/* ql_beeper.c -- the QL beeper player (QL_BEEPER): sound effects on every machine, and the
 * parchment tune when there is no QSound. See docs/dos_sound.md sections 10-11.
 *
 * The game asks for sounds with beep_effect()/beep_music(); the main loop's frame wait
 * (qlstart.s wait_tick) calls beep_tick() once for every new 50 Hz frame, in USER mode, and
 * beep_tick() issues at most ONE IPC BEEP per call (never from the poll interrupt). A BEEP
 * replaces the one sounding, so no stop command is needed between them.
 *
 * - An effect plays its BEEP list from the frame of its trigger; a new effect replaces the
 *   current one at once (as the hardware does).
 * - The parchment tune loops while it is on. Its timeline keeps running under an effect, but
 *   its notes are not issued until the effect has finished; it resumes at the next note.
 * - Late frames (a long game step): only the LATEST due BEEP of a list is issued, never a burst.
 * - The tune's clock starts at beep_music_ready() (the parchment is up), not at beep_music(1):
 *   the parchment's first step (drawn off-screen, dissolved in) runs ~2.7 s with no main loop.
 */
#include "ql_beeps_data.h"

void ql_beep_ipc(const unsigned char *p8);     /* qlhooks.s: one MT.IPCOM BEEP */

static const QlBeepSound *eff;                  /* the effect owning the beeper, 0 = none */
static unsigned int effStart, effIdx;
static int effReq = -1;                         /* effect asked for since the last tick */
static int musicOn, musicReq = -1;              /* music on/off asked for since the last tick */
static unsigned int musStart, musIdx;
static int musWait, musReady;                   /* on, waiting for beep_music_ready() */

/* a 1-tick BEEP: replaces the note sounding, so the tune stops at once */
static const unsigned char beepStop[8] = { 0xFF, 0, 0, 0, 1, 0, 0, 0 };

void beep_effect(int id)
{
	if (id >= 0 && id < (int)(sizeof(qb_effects)/sizeof(qb_effects[0]))) effReq = id;
}

void beep_music(int on)
{
	musicReq = on ? 1 : 0;
	if (on) musReady = 0;                        /* (ready comes after the request) */
}

void beep_music_ready(void)
{
	musReady = 1;
}

/* now = the 50 Hz frame counter */
void beep_tick(unsigned int now)
{
	const unsigned char *send = 0;
	if (effReq >= 0){
		eff = &qb_effects[effReq];
		effStart = now;
		effIdx = 0;
		effReq = -1;
	}
	if (musicReq >= 0){
		if (musicReq){
			musicOn = 1;
			musWait = 1;
			musIdx = 0;
		} else {
			if (musicOn && !eff) send = beepStop;
			musicOn = 0;
		}
		musicReq = -1;
	}
	if (eff){
		unsigned int t = now - effStart;
		int last = -1;
		while (effIdx < eff->n && eff->list[effIdx].frame <= t) last = effIdx++;
		if (last >= 0) send = eff->list[last].b;
		if (t >= eff->end && effIdx >= eff->n) eff = 0;      /* finished sounding */
	}
	if (musicOn && musWait && musReady){
		musWait = 0;
		musStart = now;
	}
	if (musicOn && !musWait){
		unsigned int t = now - musStart;
		int last = -1;
		while (t >= QB_MUSIC_LOOP){                          /* next pass of the tune */
			musStart += QB_MUSIC_LOOP;
			t -= QB_MUSIC_LOOP;
			musIdx = 0;
		}
		while (musIdx < qb_music.n && qb_music.list[musIdx].frame <= t) last = musIdx++;
		if (last >= 0 && !eff && !send) send = qb_music.list[last].b;
	}
	if (send) ql_beep_ipc(send);
}

/* ql_sound.h -- the CPC sound engine port (ql_sound.c) */
#ifndef QL_SOUND_H
#define QL_SOUND_H
#ifdef __cplusplus
extern "C" {
#endif
void snd_init(const unsigned char *romImage);   /* VIGASOCO roms (romsPtr + 0x4000) */
void snd_poll(void);          /* 50 Hz: six 300 Hz engine steps + register flush */
void snd_tick300(void);
void snd_flush(void);
void snd_stop(void);
void snd_play(int entry);     /* CPC entry address 0x0ffd..0x102f */
void snd_music(int addr, int tempo, int src);
const unsigned char *snd_psg(void);
void ql_ay_write(int reg, int val);   /* platform: one AY register (already clock-scaled) */
#ifdef __cplusplus
}
#endif
#endif

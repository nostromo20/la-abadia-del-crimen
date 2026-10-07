/* ql_hostcls.h -- HOST ONLY (QL_HOST_CLASSES, the oracle_scenes build for tools/colour_mapper.html):
 * which source wrote each pixel of the mixing buffer, kept in a parallel buffer.
 *
 * Classes: 0 terrain (tiles, fills, the parchment), 1 characters (sprites drawn by the mixer:
 * monks, Guillermo, Adso, objects, doors), 2 lamp light (SpriteLuz), 3 panel/HUD.
 *
 * The mixer marks a region with a sentinel before a tile or sprite is drawn into it; every
 * byte that changed was written by that source, so the class is exact even when a pixel is
 * rewritten with the same pen. Never compiled into the QL image or the regular oracle. */
#ifndef QL_HOSTCLS_H
#define QL_HOSTCLS_H
#ifdef QL_HOST_CLASSES

#define QLC_TERRAIN 0
#define QLC_CHAR    1
#define QLC_LAMP    2
#define QLC_PANEL   3
#define QLC_SENTINEL 0xEE

#ifdef __cplusplus
extern "C" {
#endif
extern unsigned char *qlc_mixBase;      /* bufferMezclas */
extern unsigned char *qlc_mixCls;       /* its classes */
extern int qlc_mixLen;
void qlc_register(unsigned char *buf, int len);
/* before/after a draw into [p, p+n): sentinel the pens, then classify what changed */
void qlc_begin(unsigned char *p, int n, unsigned char *save);
void qlc_end(unsigned char *p, int n, const unsigned char *save, int cls);
/* MIXDUMP=file: the sprite mixer's inputs and outputs of every batch (tools/mixcheck.py runs the
 * CPC's own mixer, Z80 code 0x4914, on the inputs and compares); qlc_tick = the current step */
extern int qlc_tick;
#ifdef __cplusplus
}
#endif

#endif
#endif

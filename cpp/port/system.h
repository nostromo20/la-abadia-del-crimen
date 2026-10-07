// system.h -- QL replacement for the SDL "System" of the Samuel85/Abbey fork.
//
// The logic only needs: the pad (fork-style input), playSound/playMusic/stopMusic and a few
// no-ops. The fork's pad mapping changed several original VIGASOCO semantics (edge-triggered
// turns, inverted Malaquias/QR tests); the QL copy restores the original "losControles"
// queries, implemented by ql_key_down() below. See cpp/README.txt.
#ifndef QL_SYSTEM_H
#define QL_SYSTEM_H

#include "ql_port.h"

#define GAME_FRAME_TIME 130

enum MUSICFILES { START, END, BACKGROUND, TOTAL_MUSIC_FILES };
enum SOUNDFILES { OPEN, HIT, BELLS, CLOSE, GET, LET, MIRROR, STEPS, JINGLE, TOTAL_SOUND_FILES };

struct PlayerInput {
	bool up, down, left, right, button1, button2, button3, button4;
	bool start;
};

#define BUTTON_YES sys->pad.button3
#define BUTTON_NO sys->pad.button2

struct System {
	PlayerInput pad;
	void playSound(int i) { ql_sound(i); }
	void playMusic(int i) { ql_music(i); }
	void stopMusic() { ql_music(-1); }
	void hapticFeedback() {}
	void setNormalSpeed() {}
	void setFastSpeed() {}
};
extern System *const sys;

#endif

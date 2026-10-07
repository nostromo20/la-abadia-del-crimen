#!/usr/bin/env python3
"""Beeper check (QL_BEEPER): every MT.IPCOM BEEP the game issues, logged by qlrun (frame + the 8
parameter bytes, block header/reply/A6/D3 checked), compared with audio/dos/<name>_ql.json.

Drives the real sequencer (ql_beeper.c beep_tick, one call per 50 Hz frame, as qlstart.s
wait_tick does) after ql_sound(id) / ql_music(id), with QSound present and absent:
  - every effect (SOUNDFILES ids + SPEECH 9): the JSON list exactly, on both machines;
  - the parchment tune: no QSound -> the JSON list, then its second pass from the loop frame;
    QSound -> no BEEP at all (the AY plays the CPC tune);
  - an effect during the tune: the tune's notes up to it, the effect, then the tune again from
    the first note after the effect has finished (never a note under the effect);
  - catch-up: ticks 100 frames apart issue only the latest due BEEP, never a burst;
  - stopping the tune issues the 1-tick stop BEEP.

  beeptest.py        exit 1 on any difference
"""
import json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun

EFFECTS = ["open_door", "hit", "bells", "close", "get", "let", "mirror", "steps", "jingle", "speech"]
STOP = bytes([0xFF, 0, 0, 0, 1, 0, 0, 0])
TICK = 22917.0 / 50


def jlist(name):
    d = json.load(open(os.path.join(QL, "audio", "dos", name + "_ql.json")))
    return [(int(b["frame"]), bytes(b["ipc_bytes"])) for b in d["beeps"]]


def end_of(lst):
    return max(f + -(-(b[4] | (b[5] & 0x7F) << 8) // 1 // TICK) for f, b in lst)


LOOP = int(round(json.load(open(os.path.join(QL, "audio", "dos", "music_parchment.json")))["pass_ms"] / 20.0))
MUSIC = jlist("music_parchment")


class Rig:
    def __init__(self, sv164):
        image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
        self.syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
        self.r = qlrun.Runner(image, self.syms, qlrun.BASE, [], sv164=sv164)
        self.r.run(1)
        self.qs = self.r.mu.mem_read(qlrun.BASE + self.syms["qs_present"], 1)[0]
        # the game asks for sounds of its own at start-up (the day's JINGLE): let them play out
        self.now = self.r.r32(qlrun.BASE + 20) + 10
        self.f0 = self.now
        self.tick(100)
        self.startup = list(self.r.beeps)
        del self.r.beeps[:]
        self.f0 = self.now

    def tick(self, n=1, every=1):
        for _ in range(n):
            self.r.w32(qlrun.BASE + 20, self.now)
            if (self.now - self.f0) % every == 0:
                self.r.call("beep_tick", self.now)
            self.now += 1

    def log(self, since=0):
        return [(f - self.f0, b) for f, b in self.r.beeps[since:]]


def main():
    fails = []

    def check(name, got, exp):
        if got != exp:
            fails.append(name)
            print("FAIL %-34s got %d BEEPs, expected %d" % (name, len(got), len(exp)))
            for i, (g, e) in enumerate(zip(got + [None] * len(exp), exp + [None] * len(got))):
                if g != e:
                    print("    first difference at #%d: got %s expected %s" % (i, g, e))
                    break
        else:
            print("ok   %-34s %3d BEEPs" % (name, len(got)))

    for sv in (0, 0xC1000):
        tag = "QSound" if sv else "no QSound"
        rig = Rig(sv)
        print("== %s (qs_present %d)" % (tag, rig.qs))
        if bool(rig.qs) != bool(sv):
            fails.append("qs_present")
        # every effect, alone
        for i, name in enumerate(EFFECTS):
            rig = Rig(sv)
            rig.r.call("ql_sound", i)
            exp = jlist(name)
            rig.tick(exp[-1][0] + 40)
            check("%s / %s" % (tag, name), rig.log(), exp)
        # the parchment tune: two passes' worth of the start
        rig = Rig(sv)
        rig.r.call("ql_music", 0)
        rig.r.call("ql_music_ready")       # the parchment is up (Pergamino.cpp)
        span = LOOP + 600
        rig.tick(span)
        exp = [] if sv else [(f, b) for f, b in MUSIC] + [(f + LOOP, b) for f, b in MUSIC if f + LOOP < span]
        check("%s / parchment tune (intro)" % tag, rig.log(), exp)
        # ending parchment: the same tune
        rig = Rig(sv)
        rig.r.call("ql_music", 1)
        rig.r.call("ql_music_ready")       # the parchment is up (Pergamino.cpp)
        rig.tick(800)
        exp = [] if sv else [(f, b) for f, b in MUSIC if f < 800]
        check("%s / parchment tune (ending)" % tag, rig.log(), exp)
        # the tune waits for the parchment: nothing before ql_music_ready, then the tune from there
        rig = Rig(sv)
        rig.r.call("ql_music", 0)
        rig.tick(150)
        rig.r.call("ql_music_ready")
        rig.tick(400)
        exp = [] if sv else [(f + 150, b) for f, b in MUSIC if f + 150 < 550]
        check("%s / parchment tune held until the page is up" % tag, rig.log(), exp)
        # stop
        rig = Rig(sv)
        rig.r.call("ql_music", 0)
        rig.r.call("ql_music_ready")       # the parchment is up (Pergamino.cpp)
        rig.tick(300)
        n = len(rig.r.beeps)
        rig.r.call("ql_music", -1)
        rig.tick(200)
        exp = [] if sv else [(300, STOP)]
        check("%s / parchment tune stop" % tag, rig.log(n), exp)
        # an effect (steps, then bells) during the tune
        if not sv:
            for eff, at in (("steps", 500), ("bells", 700)):
                rig = Rig(sv)
                rig.r.call("ql_music", 0)
                rig.r.call("ql_music_ready")       # the parchment is up (Pergamino.cpp)
                rig.tick(at)
                rig.r.call("ql_sound", EFFECTS.index(eff))
                el = jlist(eff)
                stop = at + int(end_of(el)) + 300
                rig.tick(stop - at)
                end = at + int(end_of(el))
                exp = [x for x in MUSIC if x[0] < at] + [(f + at, b) for f, b in el]
                exp += [x for x in MUSIC if x[0] >= end and x[0] < stop]
                exp.sort(key=lambda x: x[0])
                check("%s / %s during the tune" % (tag, eff), rig.log(), exp)
        # catch-up: bells ticked only every 100 frames -> the latest due BEEP at each tick
        rig = Rig(sv)
        rig.r.call("ql_sound", EFFECTS.index("bells"))
        rig.tick(500, every=100)
        bl = jlist("bells")
        exp = []
        for t in range(0, 500, 100):
            due = [x for x in bl if x[0] <= t and (not exp or x[0] > exp[-1][2])]
            if due:
                exp.append((t, due[-1][1], due[-1][0]))
        check("%s / catch-up (bells, every 100)" % tag, rig.log(), [(t, b) for t, b, _ in exp])
        if rig.r.beep_errors:
            fails.append("block")
            print("FAIL BEEP block/register checks:", rig.r.beep_errors[:3])
    # end to end: the game itself, walking (real-QDOS model), BEEPs issued by wait_tick
    steps = jlist("steps")[0][1]
    for sv in (0, 0xC1000):
        image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
        syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
        r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(os.path.join(QL, "tests", "walk1.txt")),
                         realq=True, sv164=sv)
        r.run(300)
        frames = [f for f, b in r.beeps]
        nsteps = sum(1 for f, b in r.beeps if b == steps)
        dup = len(frames) - len(set(frames))
        # Q-emuLator: a KEYROW soon after a BEEP reads garbage -> a whole frame must separate them
        close = 0
        lastb = None
        for kind, fr in r.ipc_order:
            if kind == "B":
                lastb = fr
            elif lastb is not None and fr - lastb < 2:
                close += 1
        print("     KEYROW reads %d, of which within 2 frames after a BEEP: %d" % (len(r.keyrows), close))
        ok = nsteps >= 10 and dup == 0 and not r.beep_errors and close == 0
        print("%s  game run (%s): %d BEEPs, %d steps, %d frames with 2+ BEEPs, errors %s"
              % ("ok  " if ok else "FAIL", "QSound" if sv else "no QSound", len(frames), nsteps, dup, r.beep_errors[:2] or "none"))
        if not ok:
            fails.append("game run")
    print("BEEPER: %d checks failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

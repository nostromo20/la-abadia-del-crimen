#!/usr/bin/env python3
"""Tempo check of the beeper parchment tune (no QSound) against the DOS original.

1. The data: every BEEP of qb_music_parchment (cpp/port/ql_beeps_data.h) against the DOS note list
   (audio/dos/music_parchment.json, from ABADIA1.OVL's own engine at 299.945 Hz): onset frame x 20 ms
   vs the DOS onset (never early, at most one frame late), the BEEP's duration (22917 Hz ticks) vs
   the DOS note, and the loop length vs one DOS pass.
2. The game: the intro run in the harness without QSound (sv164 = 0, real-QDOS model, 50 Hz frame
   counter): the frames the MT.IPCOM BEEPs were really issued at, against the table.

  beepspeed.py [--ticks 1500]
"""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
BEEP_HZ = 22917.0


def table():
    src = open(os.path.join(QL, "cpp", "port", "ql_beeps_data.h")).read()
    body = src[src.index("qb_music_parchment["):]
    body = body[:body.index("};")]
    out = []
    for m in re.finditer(r"\{ (\d+), \{([^}]*)\} \}", body):
        b = [int(x, 16) for x in m.group(2).split(",")]
        out.append((int(m.group(1)), bytes(b)))
    loop = int(re.search(r"#define QB_MUSIC_LOOP (\d+)", src).group(1))
    return out, loop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=1500)
    a = ap.parse_args()
    dos = json.load(open(os.path.join(QL, "audio", "dos", "music_parchment.json")))
    notes = dos["notes"]
    beeps, loop = table()
    fails = 0

    # 1. the data. Long notes are re-issued (the BEEP duration limit, 1.43 s): match each BEEP to
    # the DOS note sounding at its onset
    worst_late, worst_dur, early = 0.0, 0.0, 0
    for fr, b in beeps:
        t = fr * 20.0
        n = max((x for x in notes if x["t_ms"] <= t + 0.001), key=lambda x: x["t_ms"])
        late = t - n["t_ms"]
        dur_ms = (b[4] | b[5] << 8) / BEEP_HZ * 1000.0
        reissue = late > 20.0                      # a re-issue inside a long note
        if not reissue:
            worst_late = max(worst_late, late)
            if late < -0.001:
                early += 1
            # BEEP = note + one frame (the next BEEP cuts it), capped at 32767 ticks
            want = min(n["dur_ms"] + 20.0, 32767 / BEEP_HZ * 1000.0)
            worst_dur = max(worst_dur, abs(dur_ms - want))
    pass_ms = dos["pass_ms"]
    print("DOS tune: %d notes, one pass %.1f ms (%.1f s), engine tick %.4f Hz"
          % (len(notes), pass_ms, pass_ms / 1000, dos["tick_hz"]))
    print("QL table: %d BEEPs, loop %d frames = %.1f ms" % (len(beeps), loop, loop * 20.0))
    ok1 = early == 0 and worst_late <= 20.0 and abs(loop * 20.0 - pass_ms) <= 20.0 and worst_dur <= 25.0
    print("%-4s onsets: none early, latest %.1f ms (one frame = 20 ms); durations within %.1f ms of note + 1 frame;"
          " loop off by %+.1f ms (%.3f%%)"
          % ("ok" if ok1 else "FAIL", worst_late, worst_dur, loop * 20.0 - pass_ms, 100 * (loop * 20.0 - pass_ms) / pass_ms))
    fails += not ok1

    # 2. the game, in the harness
    import qlrun
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    path = os.path.join(QL, "build", "tmp", "beepspeed_script.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n")
    for k in ("QEMU_KEYS", "FORCE_NIGHT", "FORCE_MIRROR"):
        os.environ.pop(k, None)
    os.environ["INTRO"] = "1"
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(path), realq=True, sv164=0)
    os.environ.pop("INTRO", None)
    r.run(a.ticks)
    sent = [(f, bytes(p)) for f, p in r.beeps]
    tune = set(b for _, b in beeps)
    first = next(i for i, (f, p) in enumerate(sent) if p == beeps[0][1])
    f0 = sent[first][0]
    got = [(f - f0, p) for f, p in sent[first:] if p in tune]      # the tune's BEEPs (not effects)
    others = len(sent) - first - len(got)
    span = got[-1][0]
    want = [(k * loop + fr, b) for k in range(span // loop + 1) for fr, b in beeps if k * loop + fr <= span]
    same_bytes = [p for _, p in got] == [b for _, b in want]
    offs = [g[0] - w[0] for g, w in zip(got, want)]
    late1 = sum(1 for o in offs if o == 1)
    # at most one frame late: the beeper is stepped from the main loop, and never on a frame
    # followed by the keyboard read (Q-emuLator: KEYROW just after a BEEP reads garbage)
    ok2 = same_bytes and len(got) == len(want) and offs and min(offs) == 0 and max(offs) <= 1
    secs = span * 0.02
    print("%-4s game (harness, no QSound): %d tune BEEPs over %.1f s (%.2f passes), every one at its table frame"
          " (offsets %s..%s frames); %d other BEEPs (effects) not counted%s"
          % ("ok" if ok2 else "FAIL", len(got), secs, span / float(loop), min(offs) if offs else "-",
             max(offs) if offs else "-", others, "" if same_bytes else "; BEEP order/contents differ"))
    fails += not ok2
    print("BEEPSPEED: %d failures" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

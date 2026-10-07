#!/usr/bin/env python3
"""CPC-derived QL IPC BEEP versions of the five sounds the DOS release leaves silent:
CLOSE (0x1016), BELLS (0x100C), JINGLE (0x1011), HIT (0x102A), MIRROR (0x0FFD).

Source = the QL port's own CPC sound engine (cpp/port/ql_sound.c, compiled in abadia_h_bin),
run headless (qlrun/Unicorn m68k) with snd_play(entry) + snd_poll() once per 50 Hz frame, logging
every ql_ay_write -- the same harness as tools/sndtest.py, which proves that stream identical to
the CPC oracle. The stream is captured until the sound ends (sndtest's stock renders stop at
150 frames, too short for BELLS). The first 150 frames are re-checked against
build/snd/host_ay.txt when it exists.
NOTE ql_sound.c writes periods scaled to the QSound AY clock (x1.5), so the real CPC frequency
is 1.5 MHz / (16 * period) here.

Fit (same beeper model as dos_sound_ql.py: f(p) = 22917/(2(p+9.6)), p 1..255, 43.3-1081 Hz):
  * no volume on the beeper, so each strike keeps its "core" = the frames whose volume is
    >= 1/3 of that strike's peak; fades below that are dropped (the BEEP just ends);
  * a tone outside the beeper range is moved by the fewest octaves that bring it in;
  * AY noise mixed into the tone -> BEEP fuzz (jitter on every half-cycle);
  * multi-strike sounds = one BEEP per strike at the CPC frame it starts (one 50 Hz frame
    = one QL frame, so no strike is closer than 1 BEEP per frame);
  * two simultaneous tones (JINGLE) -> a continuous bounce between them at the CPC tremolo rate.
Outputs: audio/dos/<name>_ql.json, build/snd/dos/<name>_ql_beep.wav, <name>_cpc.wav (full
length render, sndtest's AY model), and a "cpc_derived" list in audio/dos/index.json.

  cpc_sound_ql.py
"""
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from dos_sound_extract import dump_json
from dos_sound_ql import TICK, P_CEIL_HZ, P_FLOOR_HZ, FRAME_MS, ql_hz, pitch_for, cents, ipc_bytes, render_beeps

AUD = os.path.join(QL, "audio", "dos")
OUT = os.path.join(QL, "build", "snd", "dos")
AY_CLOCK = 1500000          # ql_sound.c scales periods for the 1.5 MHz QSound AY
MAX_FRAMES = 1500

# name, CPC entry, VIGASOCO id, where the game calls it (CPC address, from ql_sound.c's table and
# Spannish_abadia_source), recipe, fuzz for noise
SOUNDS = [
    ("close", 0x1016, "CLOSE", "door closes (CPC 0DAA call z,1016)", "strikes", 13),
    ("bells", 0x100C, "BELLS", "canonical hours prima/sexta/visperas (CPC 5F48, 5F93, 5FB9)", "strikes", 0),
    ("jingle", 0x1011, "JINGLE", "tercia/completas (CPC 5F8F, 5FB5, 5FC7; the CPC comment calls it 'campanas')", "dyad", 0),
    ("hit", 0x102A, "HIT", "Severino knocking at his cell door (CPC 635A)", "strikes", 13),
    ("mirror", 0x0FFD, "MIRROR", "the mirror opens (CPC 3361)", "sweep", 12),
]


# ------------------------------------------------------------------ capture
def capture(entry):
    import qlrun
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as M
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    base = qlrun.BASE
    r = qlrun.Runner(image, syms, base, [])
    r.run(1)
    log, frame = [], [0]

    def on_ay(mu, addr, size, data):
        sp = mu.reg_read(M.UC_M68K_REG_A7)
        log.append((frame[0], r.r32(sp + 4), r.r32(sp + 8)))
    r.mu.hook_add(UC_HOOK_CODE, on_ay, begin=base + syms["ql_ay_write"], end=base + syms["ql_ay_write"])
    r.call("snd_init", base + syms["rom_image"] + 0x4000)
    r.call("snd_play", entry)
    quiet = 0
    states = []
    regs = [0] * 16
    regs[7] = 0x3F
    for f in range(MAX_FRAMES):
        frame[0] = f
        n0 = len(log)
        r.call("snd_poll")
        for _, reg, val in log[n0:]:
            regs[reg] = val
        st = frame_state(regs)
        states.append(st)
        quiet = quiet + 1 if not st else 0
        if quiet >= 25 and f > 30:
            break
    while states and not states[-1]:
        states.pop()
    return log, states


def frame_state(regs):
    out = []
    for ch in range(3):
        tone = not (regs[7] >> ch & 1)
        noise = not (regs[7] >> (ch + 3) & 1)
        vol = regs[8 + ch]
        v = 15 if vol & 0x10 else vol & 15
        tp = regs[ch * 2] | (regs[ch * 2 + 1] & 15) << 8
        if (tone or noise) and v:
            out.append({"ch": ch, "hz": AY_CLOCK / (16 * tp) if tone and tp else 0.0, "vol": v,
                        "tone": tone, "noise": noise})
    return out


def check_oracle(entry, log):
    path = os.path.join(QL, "build", "snd", "host_ay.txt")
    if not os.path.exists(path):
        return "host_ay.txt not present (run tools/sndtest.py)"
    cases, cur = {}, None
    for line in open(path):
        p = line.split()
        if p[0] == "case":
            cur = int(p[1])
            cases[cur] = []
        else:
            cases[cur].append(tuple(int(x) for x in p))
    ref = cases.get(entry)
    mine = [w for w in log if w[0] < 150]
    if ref is None:
        return "case not in host_ay.txt"
    if ref != mine:
        raise SystemExit("0x%04X: QL engine stream differs from the CPC oracle in the first 150 frames" % entry)
    return "first 150 frames identical to the CPC oracle (build/snd/host_ay.txt)"


# ------------------------------------------------------------------ analysis helpers
def lead(st):
    """The channel that carries the pitch: loudest tone channel, highest pitch on ties."""
    tones = [c for c in st if c["tone"] and c["hz"]]
    if not tones:
        return None
    return max(tones, key=lambda c: (c["vol"], c["hz"]))


def fold(f):
    k = 0
    while f * 2 ** k > P_CEIL_HZ:
        k -= 1
    while f * 2 ** k < P_FLOOR_HZ:
        k += 1
    return f * 2 ** k, k


def strikes(states):
    """Split into strikes: a strike starts after silence, on a lead-pitch change > 3 %,
    or when the lead volume jumps up by >= 4 (a re-trigger)."""
    out = []
    prev = None
    for f, st in enumerate(states):
        ld = lead(st)
        if ld is None:
            prev = None
            continue
        new = prev is None or abs(ld["hz"] / prev["hz"] - 1) > 0.03 or ld["vol"] >= prev["vol"] + 4
        if new:
            out.append({"start": f, "frames": []})
        out[-1]["frames"].append((f, ld))
        prev = ld
    for s in out:
        peak = max(ld["vol"] for _, ld in s["frames"])
        core = [(f, ld) for f, ld in s["frames"] if ld["vol"] * 3 >= peak]
        s["core_start"], s["core_end"] = core[0][0], core[-1][0] + 1
        s["hz"] = statistics.median(ld["hz"] for _, ld in core)
        s["noise"] = any(ld["noise"] for _, ld in core)
        s["peak"] = peak
    return out


def beep(frame, v, **extra):
    d = {"t_ms": round(frame * FRAME_MS, 3), "frame": frame, "params": v, "ipc_bytes": ipc_bytes(v),
         "dur_ms": round(v[3] / TICK * 1000, 1)}
    d.update(extra)
    return d


def fit_strikes(states, fuzz):
    bs = []
    sts = strikes(states)
    # one octave shift for the whole sound (as for the DOS tunes): the highest octave where every
    # strike is in range and within 35 cents, so the strikes keep their intervals
    _, k = fold(max(s["hz"] for s in sts))
    while k > -4:
        fs = [s["hz"] * 2 ** k for s in sts]
        if all(P_FLOOR_HZ <= f <= P_CEIL_HZ for f in fs) and \
                max(abs(cents(ql_hz(pitch_for(f)), f)) for f in fs) <= 35:
            break
        k -= 1
    for s in sts:
        f = s["hz"] * 2 ** k
        p = pitch_for(f)
        dur = round((s["core_end"] - s["core_start"]) * FRAME_MS * TICK / 1000)
        bs.append(beep(s["core_start"], [p, 0, 0, dur, 0, 0, 0, fuzz if s["noise"] else 0],
                       cpc_hz=round(s["hz"], 1), octave_shift=k, target_hz=round(f, 1), ql_hz=round(ql_hz(p), 1),
                       cents_err=round(cents(ql_hz(p), f), 1),
                       cpc_strike_frames=[s["start"], s["frames"][-1][0] + 1]))
    desc = "%d strike%s, one BEEP each%s%s" % (len(bs), "s" if len(bs) > 1 else "",
                                               ", shifted %+d octave" % k if k else "",
                                               ", fuzz %d for the AY noise" % fuzz if fuzz and any(s["noise"] for s in sts) else "")
    return bs, desc


def fit_sweep(states, fuzz):
    """MIRROR: the tone channel sweeps (pure tone); another channel adds a noisy low grind."""
    peak = max(max(c["vol"] for c in st) for st in states if st)
    core = [f for f, st in enumerate(states) if st and max(c["vol"] for c in st) * 3 >= peak]
    f0, f1 = core[0], core[-1] + 1
    sweep = [c for c in states[f0] if c["tone"] and not c["noise"]][0]["ch"]
    hz = [next(c["hz"] for c in states[f] if c["ch"] == sweep) for f in range(f0, f1)]
    a, ka = fold(hz[0])
    b, kb = fold(hz[-1])
    assert ka == kb
    p0, p1 = pitch_for(a), pitch_for(b)
    x0, x1 = TICK / (2 * a) - 9.6, TICK / (2 * b) - 9.6
    interval = max(1, round((f1 - f0 - 1) * FRAME_MS * TICK / 1000 / abs(x1 - x0)))
    noisy = any(c["noise"] for f in range(f0, f1) for c in states[f])
    dur = round((f1 - f0) * FRAME_MS * TICK / 1000)
    v = [p0, p1, interval, dur, 1 if p1 > p0 else -1, 0, 0, fuzz if noisy else 0]
    b_ = beep(f0, v, cpc_hz=[round(hz[0], 1), round(hz[-1], 1)], octave_shift=ka,
              ql_hz=[round(ql_hz(p0), 1), round(ql_hz(p1), 1)])
    desc = ("sweep p%d -> p%d (%.1f -> %.1f Hz, step every %d ticks), fuzz %d for the noise channel"
            % (p0, p1, hz[0], hz[-1], interval, v[7]))
    return [b_], desc


def fit_dyad(states, fuzz):
    """JINGLE: two tones at once, re-struck (volume) every ~5 frames -> bounce between them."""
    peak = max(max(c["vol"] for c in st) for st in states if st)
    core = [f for f, st in enumerate(states) if st and max(c["vol"] for c in st) * 3 >= peak]
    f0, f1 = core[0], core[-1] + 1
    tones = sorted({round(c["hz"], 1) for c in states[f0] if c["tone"]})
    lo, hi = tones[0], tones[-1]
    (a, ka), (b, kb) = fold(lo), fold(hi)
    pa, pb = pitch_for(a), pitch_for(b)
    # tremolo period = mean distance between volume re-triggers of the loudest channel
    vols = [max(c["vol"] for c in st) for st in states[f0:f1]]
    retr = [i for i in range(1, len(vols)) if vols[i] > vols[i - 1]]
    period = (retr[-1] - retr[0]) / (len(retr) - 1) if len(retr) > 1 else 5
    leg_ms = period * FRAME_MS / 2                      # one full up-down bounce per re-strike
    steps = abs(pa - pb)
    interval = max(1, round(leg_ms * TICK / 1000 / steps))
    dur = round((f1 - f0) * FRAME_MS * TICK / 1000)
    p_start, p_end = min(pa, pb), max(pa, pb)           # start on the higher frequency
    v = [p_start, p_end, interval, dur, 1, 15, 0, 0]
    b_ = beep(f0, v, cpc_hz=[lo, hi], octave_shift=[ka, kb], target_hz=[round(a, 1), round(b, 1)],
              ql_hz=[round(ql_hz(pa), 1), round(ql_hz(pb), 1)], tremolo_frames=round(period, 2))
    desc = ("dyad %.0f + %.0f Hz folded to p%d/p%d (%.0f/%.0f Hz), continuous bounce, one up-down "
            "cycle per CPC re-strike (%.1f frames)" % (lo, hi, pa, pb, ql_hz(pa), ql_hz(pb), period))
    return [b_], desc


def main():
    os.makedirs(OUT, exist_ok=True)
    import sndtest
    idx_path = os.path.join(AUD, "index.json")
    idx = json.load(open(idx_path))
    derived = []
    for name, entry, vid, where, recipe, fuzz in SOUNDS:
        log, states = capture(entry)
        ok = check_oracle(entry, log)
        nframes = len(states)
        fit = {"strikes": fit_strikes, "sweep": fit_sweep, "dyad": fit_dyad}[recipe]
        beeps, desc = fit(states, fuzz)
        end_ms = max(b["t_ms"] + b["dur_ms"] for b in beeps)
        gaps = [b["frame"] - a["frame"] for a, b in zip(beeps, beeps[1:])]
        res = {"name": name, "source": "CPC engine 0x%04X (VIGASOCO %s) via cpp/port/ql_sound.c" % (entry, vid),
               "event": where, "tick_hz": TICK, "beeper_range_hz": [round(P_FLOOR_HZ, 1), round(P_CEIL_HZ, 1)],
               "cpc_length_ms": nframes * FRAME_MS, "ql_length_ms": round(end_ms, 1),
               "fit": desc, "min_frames_between_beeps": min(gaps) if gaps else None,
               "verification": ok, "beeps": beeps}
        dump_json(res, os.path.join(AUD, name + "_ql.json"))
        render_beeps(os.path.join(OUT, name + "_ql_beep.wav"), beeps, max(end_ms, nframes * FRAME_MS))
        sndtest.render(os.path.join(OUT, name + "_cpc.wav"), log, nframes + 10)
        derived.append({"name": name, "cpc_entry": "0x%04X" % entry, "vigasoco": vid, "event": where,
                        "beeps": len(beeps), "cpc_length_ms": res["cpc_length_ms"], "ql_length_ms": res["ql_length_ms"],
                        "fit": desc})
        print("%-7s %4.0f ms CPC -> %4.0f ms QL, %2d BEEP(s): %s" % (name, res["cpc_length_ms"], end_ms, len(beeps), desc))
    idx["cpc_derived"] = derived
    dump_json(idx, idx_path)


if __name__ == "__main__":
    main()

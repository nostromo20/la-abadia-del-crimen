#!/usr/bin/env python3
"""Convert the DOS PC-speaker sounds (audio/dos/<name>.json from dos_sound_extract.py) to QL IPC BEEP.

Beeper model (from the author's earlier QL sound work; sQLux QL_sound.c semantics):
  * 8049 tick = 22917 Hz; half-cycle = ((p+255)%256) + 10.6 ticks, so for p = 1..255
    f(p) = 22917 / (2*(p + 9.6)): p=1 is the CEILING (~1081 Hz), p=255 the FLOOR (~43.3 Hz);
    p=0 wraps to the lowest pitch and is never emitted;
  * interval/duration are 15-bit, sent LITTLE-endian; step is a signed nibble (+ = pitch number up
    = LOWER frequency); wrap 0 = one sweep, then the pitch holds at the end value.
Conversion rules:
  * tunes: one BEEP per note, onsets on the 50 Hz frame grid (the PoP q68 player paces notes off the
    frame counter with a cumulative-ms Bresenham, so onset error <= 20 ms, no drift); each BEEP lasts the
    note + one frame so the next BEEP cuts it (the DOS tunes are legato, no gaps); notes > 32767 ticks
    (1.43 s) are re-issued. The whole tune is transposed by octaves (never per-note folds, which would
    break the contour): the RECOMMENDED shift is the highest octave with no note above the ceiling,
    the ALT render is one octave lower (finer pitch steps, duller).
  * effects: one BEEP each; DOS divisor sweeps are linear in PERIOD, and the QL pitch number is
    linear in period too, so a sweep maps to p1 -> p2 with step +-1 every `interval` ticks exactly.
    Effects outside 43-1081 Hz are shifted by the fewest octaves that bring them in range.
Outputs:
  audio/dos/<name>_ql.json             the BEEP list (logical params + the 8 IPC bytes)
  build/snd/dos/<name>_ql_beep.wav     8049-model render (and _ql_beep_alt.wav for tunes)
  build/snd/dos/<name>_cpc.wav         the CPC reference render (copied from build/snd, or rendered
                                       longer for the background tune via the QL build's engine)
  dos_sound_ql.py [--no-cpc-long]
"""
import json
import math
import os
import random
import shutil
import struct
import sys
import wave

from dos_sound_extract import dump_json, load_segments

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
AUD = os.path.join(QL, "audio", "dos")
OUT = os.path.join(QL, "build", "snd", "dos")
TICK = 22917
SR = 44100
FRAME_MS = 20.0
P_CEIL_HZ = TICK / (2 * (1 + 9.6))
P_FLOOR_HZ = TICK / (2 * (255 + 9.6))
MAX_DUR = 32767

CPC_REF = {"music_parchment": "music_ending.wav", "music_background": "s1007.wav", "open_door": "open_door.wav",
           "steps": "steps.wav", "get": "get.wav", "let": "let.wav", "speech": "speech_1020.wav"}


def ql_hz(p):
    return TICK / (2 * (((p + 255) % 256) + 10.6))


def pitch_for(f):
    return max(1, min(255, round(TICK / (2 * f) - 9.6)))


def cents(a, b):
    return 1200 * math.log2(a / b)


def ipc_bytes(v):
    p1, p2, iv, du, st, wr, rn, fz = v
    iv &= 0x7FFF
    du &= 0x7FFF
    return [p1, p2, iv & 255, iv >> 8, du & 255, du >> 8, ((st & 15) << 4) | (wr & 15), ((rn & 15) << 4) | (fz & 15)]


# ------------------------------------------------------------------ 8049 synth (port of synthQL)
def synth(v, sr=SR, rng=None):
    rng = rng or random.Random(1)
    p1, p2, intv, dur, step, wrap, rnd, fuzz = v
    intv &= 0x7FFF
    dur &= 0x7FFF
    dur_t = max(dur, 1)
    n = max(1, round(dur_t / TICK * sr))
    buf = [0.0] * n
    lo, hi = min(p1, p2), max(p1, p2)
    pitch, s, level, t = p1, step, 1.0, 0.0
    bounces = float("inf") if wrap >= 8 else wrap
    stepping = intv > 0 and (s != 0 or rnd >= 8)
    next_step = intv if stepping else float("inf")
    while t < dur_t:
        ht = ((pitch % 256) + 255) % 256 + 10.6
        if fuzz >= 8:
            ht += rng.randrange(1 << (fuzz - 7))
        t1 = min(t + ht, dur_t)
        i0, i1 = min(n, round(t / TICK * sr)), min(n, round(t1 / TICK * sr))
        for i in range(i0, i1):
            buf[i] = level
        while t1 >= next_step:
            np_ = pitch + s
            if rnd >= 8:
                np_ += rng.randrange(1 << (rnd - 7))
            if s != 0 and (np_ > hi or np_ < lo):
                if bounces > 0:
                    bounces -= 1
                    s = -s
                else:
                    s = 0
                np_ = max(lo, min(hi, np_))
            pitch = np_ % 256
            next_step += intv
        level = -level
        t += ht
    return buf


def render_beeps(path, beeps, total_ms, amp=0.45, pad_ms=150):
    """Each BEEP starts at its onset and is cut by the next one (the IPC replaces the current sound)."""
    pad = int(SR * pad_ms / 1000)
    n = int(round(total_ms / 1000 * SR)) + 2 * pad
    out = [0.0] * n
    for i, b in enumerate(beeps):
        s0 = pad + int(round(b["t_ms"] / 1000 * SR))
        s1 = pad + int(round(beeps[i + 1]["t_ms"] / 1000 * SR)) if i + 1 < len(beeps) else n
        buf = synth(b["params"])
        for k, x in enumerate(buf):
            if s0 + k >= min(s1, n):
                break
            out[s0 + k] = x
    pcm = [int(x * amp * 32767) for x in out]
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack("<%dh" % len(pcm), *pcm))


# ------------------------------------------------------------------ tunes
def tune_stats(notes, k):
    """(out-of-range note indices, rms cents, max cents, pitch collisions) for an octave shift k.
    A collision = two different DOS pitches landing on the same QL pitch number."""
    errs, over = [], []
    owner = {}
    for nt in notes:
        f = nt["hz"] * 2 ** k
        if P_FLOOR_HZ <= f <= P_CEIL_HZ:
            owner.setdefault(pitch_for(f), set()).add(nt["divisor"])
    coll = sum(1 for v in owner.values() if len(v) > 1)
    for i, nt in enumerate(notes):
        f = nt["hz"] * 2 ** k
        if f > P_CEIL_HZ or f < P_FLOOR_HZ:
            over.append(i)
            continue
        errs.append(cents(ql_hz(pitch_for(f)), f))
    rms = math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else 0
    return over, rms, max((abs(e) for e in errs), default=0), coll


def convert_tune(rec, k):
    notes = rec["notes"]
    # onset frame = first 20 ms frame at/after the DOS onset (cumulative, so no drift)
    frames = [math.ceil(nt["t_ms"] / FRAME_MS - 1e-9) for nt in notes]
    reissue_ms = math.floor(MAX_DUR / TICK * 1000 / FRAME_MS) * FRAME_MS
    beeps = []
    for i, nt in enumerate(notes):
        f = nt["hz"] * 2 ** k
        p = pitch_for(f)
        t = frames[i] * FRAME_MS
        if i + 1 < len(notes):
            end = frames[i + 1] * FRAME_MS + FRAME_MS          # overlap one frame: the next BEEP cuts it
        else:
            end = t + nt["dur_ms"]
        while True:
            rem = round((end - t) * TICK / 1000)
            d = min(rem, MAX_DUR)
            beeps.append({"t_ms": round(t, 3), "frame": int(round(t / FRAME_MS)), "note": i,
                          "onset_err_ms": round(t - nt["t_ms"], 2) if t < nt["t_ms"] + FRAME_MS else None,
                          "dos_hz": nt["hz"], "target_hz": round(f, 2), "ql_hz": round(ql_hz(p), 2),
                          "cents_err": round(cents(ql_hz(p), f), 1), "params": [p, 0, 0, d, 0, 0, 0, 0]})
            if rem <= MAX_DUR:
                break
            t += reissue_ms                                    # long note: re-issue before it runs out
    return beeps


# ------------------------------------------------------------------ effects
def convert_effect(rec):
    segs = [s for s in load_segments(rec) if s["on"]]
    total_ms = sum(s["dur_ms"] for s in segs)
    fmin, fmax = min(s["hz"] for s in segs), max(s["hz"] for s in segs)
    k = 0
    while fmax * 2 ** k > P_CEIL_HZ:
        k -= 1
    while fmin * 2 ** k < P_FLOOR_HZ and fmax * 2 ** (k + 1) <= P_CEIL_HZ:
        k += 1
    dur = round(total_ms * TICK / 1000)
    f0, f1 = segs[0]["hz"] * 2 ** k, segs[-1]["hz"] * 2 ** k
    p0, p1 = pitch_for(f0), pitch_for(f1)
    note = rec["notes"][0]
    env = note["envelope"]["divisor_deltas"]
    monotonic = all(isinstance(x, int) for x in env[:-1]) and len(env) == 2 and env[-1] == "loop"
    if p0 != p1 and monotonic:
        # linear divisor ramp -> linear pitch-number ramp: |p1-p0| steps spread over the sweep
        # rate: the DOS ramp's real-valued pitch-number slope (one QL step per unit of pitch number)
        x0, x1 = TICK / (2 * f0) - 9.6, TICK / (2 * f1) - 9.6
        ramp_ms = segs[-1]["t_ms"] - segs[0]["t_ms"]
        steps = abs(p1 - p0)
        interval = max(1, round(ramp_ms * TICK / 1000 / abs(x1 - x0)))
        v = [p0, p1, interval, dur, 1 if p1 > p0 else -1, 0, 0, 0]
        kind = "sweep %d -> %d (%d steps every %d ticks = %.1f ms)" % (p0, p1, steps, interval, interval / TICK * 1000)
    else:
        p = pitch_for(note["hz"] * 2 ** k)
        v = [p, 0, 0, dur, 0, 0, 0, 0]
        kind = "single pitch" + (" (DOS vibrato +-%d divisor dropped: %.0f cents, below the beeper's step)"
                                  % (max(abs(x) for x in env if isinstance(x, int)),
                                     cents(note["hz"], 1193182 / (note["divisor"] + max(abs(x) for x in env if isinstance(x, int)))))
                                  if any(isinstance(x, int) for x in env) else "")
    b = {"t_ms": 0.0, "frame": 0, "params": v, "octave_shift": k,
         "dos_hz": [round(fmin, 2), round(fmax, 2)], "target_hz": [round(f0, 2), round(f1, 2)],
         "ql_hz": [round(ql_hz(v[0]), 2), round(ql_hz(v[1] if v[1] else v[0]), 2)], "fit": kind}
    return [b], k, total_ms


def cpc_background_long(dest, frames=1500):
    """Render the CPC 0x1007 tune for 30 s through the QL build's AY engine (the stock render is 3 s)."""
    sys.path.insert(0, HERE)
    import qlrun
    import sndtest
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
    r.call("snd_play", 0x1007)
    for f in range(frames):
        frame[0] = f
        r.call("snd_poll")
    sndtest.render(dest, log, frames)
    return log


def main():
    os.makedirs(OUT, exist_ok=True)
    idx = json.load(open(os.path.join(AUD, "index.json")))
    summary = []
    for s in idx["sounds"]:
        name = s["name"]
        rec = json.load(open(os.path.join(AUD, name + ".json")))
        res = {"name": name, "source": name + ".json", "tick_hz": TICK,
               "beeper_range_hz": [round(P_FLOOR_HZ, 1), round(P_CEIL_HZ, 1)]}
        if rec["loops"]:
            stats = {k: tune_stats(rec["notes"], k) for k in (0, -1, -2, -3)}
            # recommended: highest octave with every note in range, no collisions, max error <= 35 cents;
            # alt: the octave above it if that is at least in range (brighter, less in tune), else below
            k_rec = max(k for k in stats if not stats[k][0] and not stats[k][3] and stats[k][2] <= 35)
            k_alt = k_rec + 1 if k_rec + 1 in stats and not stats[k_rec + 1][0] else k_rec - 1
            over0 = stats[0][0]
            res["notes_above_ceiling_at_dos_pitch"] = [{"note": i, "hz": rec["notes"][i]["hz"],
                                                         "t_ms": rec["notes"][i]["t_ms"]} for i in over0]
            res["octave_options"] = {str(k): {"notes_out_of_range": len(v[0]), "rms_cents": round(v[1], 1),
                                              "max_cents": round(v[2], 1), "pitch_collisions": v[3]} for k, v in stats.items()}
            for tag, k in (("", k_rec), ("_alt", k_alt)):
                beeps = convert_tune(rec, k)
                for b in beeps:
                    b["ipc_bytes"] = ipc_bytes(b["params"])
                res["beeps" + tag] = beeps
                res["octave_shift" + tag] = k
                render_beeps(os.path.join(OUT, name + "_ql_beep%s.wav" % tag), beeps, rec["pass_ms"])
            iois = [b["t_ms"] for b in res["beeps"]]
            gaps = [b - a for a, b in zip(iois, iois[1:])]
            res["min_onset_gap_ms"] = min(gaps)
            res["beeps_faster_than_one_per_frame"] = sum(1 for g in gaps if g < FRAME_MS)
            res["onset_error_ms_max"] = max(b["onset_err_ms"] for b in res["beeps"] if b["onset_err_ms"] is not None)
            res["reissued_long_notes"] = len(res["beeps"]) - len(rec["notes"])
            line = ("%-17s tune  %3d notes -> %3d BEEPs, shift %+d oct (rms %.0f / max %.0f cents), alt %+d (rms %.0f), "
                    "%d notes above ceiling at DOS pitch, min onset gap %.0f ms"
                    % (name, len(rec["notes"]), len(res["beeps"]), k_rec, stats[k_rec][1], stats[k_rec][2], k_alt,
                       stats[k_alt][1], len(over0), res["min_onset_gap_ms"]))
        else:
            beeps, k, total = convert_effect(rec)
            for b in beeps:
                b["ipc_bytes"] = ipc_bytes(b["params"])
            res["beeps"] = beeps
            res["octave_shift"] = k
            render_beeps(os.path.join(OUT, name + "_ql_beep.wav"), beeps, total)
            line = "%-17s fx    %s  shift %+d oct  params %s" % (name, beeps[0]["fit"], k, beeps[0]["params"])
        dump_json(res, os.path.join(AUD, name + "_ql.json"))
        # CPC reference
        dst = os.path.join(OUT, name + "_cpc.wav")
        if name == "music_background" and "--no-cpc-long" not in sys.argv:
            try:
                cpc_background_long(dst)
            except Exception as e:                     # fall back to the stock 3 s render
                print("  (long CPC render failed: %s; copying the 3 s one)" % e)
                shutil.copyfile(os.path.join(QL, "build", "snd", CPC_REF[name]), dst)
        else:
            src = os.path.join(QL, "build", "snd", CPC_REF[name])
            if os.path.exists(src):
                shutil.copyfile(src, dst)
        if name == "music_parchment":
            src = os.path.join(QL, "build", "snd", "music_intro.wav")
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(OUT, "music_parchment_cpc_intro.wav"))
        print(line)
        summary.append(line)


if __name__ == "__main__":
    main()

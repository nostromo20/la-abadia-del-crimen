#!/usr/bin/env python3
"""Sound engine check (step 7): the CPC sound engine port (cpp/port/ql_sound.c) compiled for the
68000 must write the same AY register stream as the oracle build, for every sound entry and
both parchment tunes. With --wav, also renders each case to build/snd/*.wav (simple AY model
at the QSound clock, so the pitch is the CPC's) for listening.

  sndtest.py [--wav]
"""
import argparse, math, os, struct, subprocess, sys, wave
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as M

WSL_QL = qlpaths.WSL_QL
CASES = [0x0ffd, 0x1002, 0x1007, 0x100c, 0x1011, 0x1016, 0x101b, 0x1020, 0x1025, 0x102a, 0x102f, -1, -2]
NAMES = {0x0ffd: "mirror", 0x1002: "steps", 0x1007: "s1007", 0x100c: "bells_100c", 0x1011: "jingle_1011",
         0x1016: "close_door", 0x101b: "open_door", 0x1020: "speech_1020", 0x1025: "get", 0x102a: "hit",
         0x102f: "let", -1: "music_intro", -2: "music_ending"}


def parse_host(path):
    out, cur = {}, None
    for line in open(path):
        p = line.split()
        if p[0] == "case":
            cur = int(p[1])
            out[cur] = []
        else:
            out[cur].append(tuple(int(x) for x in p))
    return out


def run_ql():
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    base = qlrun.BASE
    # QSound present: with QL_BEEPER the AY engine plays the parchment tunes only when QSound is
    # there (without it they go to the beeper, checked by tools/beeptest.py)
    r = qlrun.Runner(image, syms, base, [], sv164=0xC1000)
    r.run(1)
    log = []
    frame = [0]

    def on_ay(mu, addr, size, data):
        sp = mu.reg_read(M.UC_M68K_REG_A7)
        reg = r.r32(sp + 4)
        val = r.r32(sp + 8)
        log.append((frame[0], reg, val))
    r.mu.hook_add(UC_HOOK_CODE, on_ay, begin=base + syms["ql_ay_write"], end=base + syms["ql_ay_write"])
    out = {}
    roms = base + syms["rom_image"] + 0x4000
    for c in CASES:
        del log[:]
        r.call("snd_init", roms)
        if c == -1:
            r.call("ql_music", 0)
        elif c == -2:
            r.call("ql_music", 1)
        else:
            r.call("snd_play", c)
        for f in range(1500 if c < 0 else 150):
            frame[0] = f
            r.call("snd_poll")
        out[c] = list(log)
    return out


def render(path, writes, frames, clock=1500000, rate=22050):
    regs = [0] * 16
    regs[7] = 0x3f
    by_frame = {}
    for f, reg, val in writes:
        by_frame.setdefault(f, []).append((reg, val))
    vol = [0] + [10 ** ((v - 15) * 1.5 / 10) for v in range(1, 16)]
    ph = [0.0, 0.0, 0.0]
    noise_ph = 0.0
    lfsr = 1
    noise_bit = 1
    env_ph = 0.0
    env_step = 0
    env_shape = 0
    samples = []
    per_frame = rate // 50
    for f in range(frames):
        for reg, val in by_frame.get(f, []):
            regs[reg] = val
            if reg == 13:
                env_step = 0
                env_ph = 0.0
                env_shape = val & 15
        for _ in range(per_frame):
            # envelope
            ep = max(1, regs[11] | (regs[12] << 8))
            env_ph += clock / (256.0 * ep) / rate * 16
            while env_ph >= 1.0:
                env_ph -= 1.0
                env_step += 1
            cont, att, alt, hold = env_shape >> 3 & 1, env_shape >> 2 & 1, env_shape >> 1 & 1, env_shape & 1
            if env_step < 16:
                e = env_step if att else 15 - env_step
            elif not cont:
                e = 0
            elif hold:
                e = (15 if att ^ alt else 0)
            else:
                cyc = (env_step // 16) & 1
                s = env_step & 15
                up = att ^ (alt and cyc)
                e = s if up else 15 - s
            # noise
            npd = max(1, regs[6] & 31)
            noise_ph += clock / (16.0 * npd) / rate
            while noise_ph >= 1.0:
                noise_ph -= 1.0
                bit = (lfsr ^ (lfsr >> 3)) & 1
                lfsr = (lfsr >> 1) | (bit << 16)
                noise_bit = lfsr & 1
            out = 0.0
            for ch in range(3):
                tp = max(1, regs[ch * 2] | ((regs[ch * 2 + 1] & 15) << 8))
                ph[ch] = (ph[ch] + clock / (16.0 * tp) / rate) % 1.0
                tone_on = not (regs[7] >> ch & 1)
                noise_on = not (regs[7] >> (ch + 3) & 1)
                t = (ph[ch] < 0.5) if tone_on else True
                n = noise_bit if noise_on else True
                if t and n:
                    a = regs[8 + ch]
                    v = vol[e] if a & 0x10 else vol[a & 15]
                    out += v
            samples.append(int(max(-1, min(1, out / 3.0 - 0.0)) * 30000))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.join(QL, "build", "snd"), exist_ok=True)
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    subprocess.run(["wsl", WSL_QL + "/build/host/oracle", "--sndtest", WSL_QL + "/build/roms.bin",
                    WSL_QL + "/build/snd/host_ay.txt"], check=True, env=env)
    host = parse_host(os.path.join(QL, "build", "snd", "host_ay.txt"))
    ql = run_ql()
    bad = 0
    for c in CASES:
        h, q = host.get(c, []), ql.get(c, [])
        same = h == q
        bad += not same
        print("%-14s %5d AY writes  %s" % (NAMES[c], len(h), "identical" if same else "DIFFER (ql %d)" % len(q)))
        if a.wav:
            render(os.path.join(QL, "build", "snd", NAMES[c] + ".wav"), h, 1500 if c < 0 else 150)
    print("SOUND: %d cases differ" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Extract the PC-speaker sounds of the DOS "La Abadia del Crimen" (Opera Soft 1988) as event lists.

The DOS game keeps ONE speaker engine in ABADIA1.OVL (see docs/dos_sound.md):
  * the overlay is loaded at segment 0x1000 (loader ABADIA.EXE, file 0x59e); its data segment is
    0x1800, so a data offset X lives at file offset 0x8000 + X;
  * the int 8 handler (file 0x471) reprograms PIT channel 0 to divisor 0xF8A (299.94 Hz) and calls
    the sound tick (0x57a) on EVERY interrupt;
  * a sound is a bytecode script started by 0x553 (unconditional) or 0x543 (only when idle),
    with BX = the script's data offset. Opcodes (jump table at DS:0F0C):
        00              END     speaker off, engine idle
        02 dd dd nn nn  NOTE    PIT ch2 divisor dddd, length nnnn ticks (both little-endian)
        04 nn nn        REST    speaker gate off for nnnn ticks (never used by any script)
        06 aa aa        CALL    script subroutine        08  RET (empty stack = END)
        0A aa aa        JUMP                              0C rr aa aa  ENVELOPE: every rr ticks add the
                                                         next signed byte of table aaaa to the divisor;
                                                         0x80 = restart table, 0x81 = hold
This script does two independent things and checks one against the other:
  1. a static decoder of the bytecode (score level: notes + envelope), which also simulates the
     engine tick by tick;
  2. Unicorn executing the REAL x86 engine code (0x553 start, 0x57a tick) on the overlay image,
     logging every OUT to ports 42h/43h/61h -> the speaker state at the end of every tick.
The two per-tick traces must be identical (asserted). Outputs:
  audio/dos/<name>.json         notes, per-tick segments, mapping/trigger notes
  build/snd/dos/<name>_dos.wav  square-wave render of the DOS original (44.1 kHz)

  dos_sound_extract.py [path/to/ABADIA1.OVL]
The DOS files are only READ.
"""
import json
import qlpaths  # local tool paths (tools/qlpaths.py)
import math
import os
import struct
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
DEFAULT_OVL = qlpaths.DOS_OVL

PIT_HZ = 1193182
TIMER_DIV = 0xF8A                       # int 8 rate set at file 0x463 / 0x4df
TICK_HZ = PIT_HZ / TIMER_DIV            # 299.94 Hz
TICK_MS = 1000.0 / TICK_HZ              # 3.3340 ms
DS_FILE = 0x8000                        # data segment 0x1800 = load segment 0x1000 + 0x800
LOAD_SEG = 0x1000

# script data offset -> (name, how the game starts it, game event, CPC/VIGASOCO equivalent, confidence)
SOUNDS = [
    (0xC1A8, "music_parchment", "0x6d7 (unconditional 0x553) from 0x1f0c (intro parchment, text DS:C966 "
     "'Ya al final de mi vida...') and 0x3436 (ending parchment, text DS:CF67 'Desfigurado por la angustia...')",
     "parchment music: SAME tune for intro and ending; loops (JUMP C1A8) until replaced",
     "CPC music START (intro) and END (ending) -- the CPC has two different tunes", "high"),
    (0xC45F, "music_background", "0x1f97 at game start (0x553), and 0x608a every main-loop pass when no "
     "phrase is on the scroll ([B85E]==0) via 0x6367 -> 0x543 (start only if the engine is idle)",
     "in-game background tune; loops forever (JUMP C45F); any effect cuts it and it restarts from the top",
     "CPC 0x1007 'inicia un sonido en el canal 1' (CPC 41AB, same routine)", "high (site); tune itself has no CPC twin checked"),
    (0xC176, "open_door", "0x1257: door bit 6 set (opening) -> 0x6370",
     "door opens (closing calls stub 0x636f = silent)", "CPC 0x101B OPEN (CPC 0DA6 call nz)", "high"),
    (0xC180, "steps", "0x2044: [BAF4] bit 0 set -> 0x6361", "Guillermo's footstep",
     "CPC 0x1002 STEPS (CPC 2620 call nz)", "high"),
    (0xC18A, "get", "0x53e5: object mask changed and new bit set -> 0x637c", "object picked up",
     "CPC 0x1025 GET (CPC 5090 call nz)", "high"),
    (0xC194, "let", "0x53de: object mask changed, bit cleared -> 0x6383", "object dropped",
     "CPC 0x102F LET (CPC 508C call z)", "high"),
    (0xC19E, "speech", "0x53a2 (phrase put on the scroll) and 0x2cc5 (20x with a delay when the demo's "
     "key buffer runs out)", "phrase blip / end-of-demo beeps",
     "CPC 0x1020 'canal 3' (CPC 3B73 per phrase character, 320B demo end x20)", "high"),
]
SILENT = [
    ("CLOSE (CPC 0x1016)", "0x125e -> stub 0x636f = ret"),
    ("BELLS (CPC 0x100C)", "0x4ad3/0x4b2e/0x4b60 -> stub 0x636d = ret"),
    ("JINGLE / campanas (CPC 0x1011)", "0x4b2a/0x4b5c/0x4b70 -> stub 0x636e = ret"),
    ("HIT, Severino knocking (CPC 0x102A)", "0x502f -> stub 0x6382 = ret"),
    ("MIRROR (CPC 0x0FFD)", "0x2e37 -> stub 0x6360 = ret"),
    ("C175 = bare END", "0x1f20/0x1faf via 0x63a3 -> 0x543: silences the speaker if idle"),
]


def u16(d, o):
    return d[o] | d[o + 1] << 8


def s8(b):
    return b - 256 if b >= 128 else b


# ----------------------------------------------------------------------------- static decoder
class Engine:
    """Python model of 0x553/0x57a, used for the score-level note list."""

    def __init__(self, img):
        self.img = img

    def rd(self, off):
        return self.img[DS_FILE + off]

    def rdw(self, off):
        return u16(self.img, DS_FILE + off)

    def run(self, script, max_ticks):
        flags = 1
        ptr = script
        stack = []
        env_tab, env_ptr, env_rate, env_cnt = 0x0F1A, 0x0F1A, 1, 1   # F1A holds 0x81 = hold
        div = 0
        dur = 0
        gate = 3
        notes = []
        trace = []
        loop_tick = None
        jumped_to_start = False
        for tick in range(max_ticks):
            if flags & 1:
                if flags & 2:
                    dur = (dur - 1) & 0xFFFF
                    if dur == 0:
                        flags &= 0x7D
                    elif not flags & 0x40:
                        env_cnt = (env_cnt - 1) & 0xFF
                        if env_cnt == 0:
                            env_cnt = env_rate
                            b = self.rd(env_ptr)
                            if b != 0x81:
                                if b == 0x80:
                                    env_ptr = env_tab
                                    b = self.rd(env_ptr)
                                env_ptr += 1
                                div = (div + s8(b)) & 0xFFFF
                if not flags & 2:
                    while True:
                        op = self.rd(ptr)
                        ptr += 1
                        if op == 0x00:
                            gate = 0
                            flags = 0
                            notes.append(("end", tick))
                            break
                        elif op == 0x02:
                            div = self.rdw(ptr)
                            dur = self.rdw(ptr + 2)
                            ptr += 4
                            env_ptr, env_cnt = env_tab, env_rate
                            flags = (flags & 0x3F) | 2
                            notes.append(("note", tick, div, dur, env_rate, env_tab))
                            break
                        elif op == 0x04:
                            dur = self.rdw(ptr)
                            ptr += 2
                            flags = (flags & 0x7F) | 0x42
                            gate = 0
                            notes.append(("rest", tick, dur))
                            break
                        elif op == 0x06:
                            stack.append(ptr + 2)
                            ptr = self.rdw(ptr)
                        elif op == 0x08:
                            if not stack:
                                gate, flags = 0, 0
                                notes.append(("end", tick))
                                break
                            ptr = stack.pop()
                        elif op == 0x0A:
                            tgt = self.rdw(ptr)
                            if tgt == script and loop_tick is None:
                                loop_tick = tick
                                jumped_to_start = True
                            ptr = tgt
                        elif op == 0x0C:
                            env_rate = env_cnt = self.rd(ptr)
                            env_tab = env_ptr = self.rdw(ptr + 1)
                            ptr += 3
                        else:
                            raise ValueError("opcode %02x at DS:%04x" % (op, ptr - 1))
            trace.append((gate & 3 == 3, div))
            if flags == 0 or jumped_to_start:
                break
        return notes, trace, loop_tick


# ----------------------------------------------------------------------------- Unicorn run
def emulate(img, script, ticks):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN
    from unicorn.x86_const import (UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS,
                                   UC_X86_REG_SP, UC_X86_REG_BX, UC_X86_INS_IN, UC_X86_INS_OUT)
    mu = Uc(UC_ARCH_X86, UC_MODE_16)
    mu.mem_map(0, 0x100000)
    base = LOAD_SEG * 16
    mu.mem_write(base, bytes(img))
    port61 = [0x30]
    pit_latch = {"lo": True, "val": 0, "div": 0}
    log = []
    cur = [0]

    def on_in(uc, port, size, user):
        return port61[0] if port == 0x61 else 0

    def on_out(uc, port, size, value, user):
        log.append((cur[0], port, value & 0xFF))
        if port == 0x61:
            port61[0] = value & 0xFF
        elif port == 0x43:
            pit_latch["lo"] = True
        elif port == 0x42:
            if pit_latch["lo"]:
                pit_latch["val"] = value & 0xFF
                pit_latch["lo"] = False
            else:
                pit_latch["div"] = pit_latch["val"] | (value & 0xFF) << 8
                pit_latch["lo"] = True

    mu.hook_add(UC_HOOK_INSN, on_in, None, 1, 0, UC_X86_INS_IN)
    mu.hook_add(UC_HOOK_INSN, on_out, None, 1, 0, UC_X86_INS_OUT)
    for r, v in ((UC_X86_REG_CS, LOAD_SEG), (UC_X86_REG_DS, 0x1800), (UC_X86_REG_ES, 0x1800),
                 (UC_X86_REG_SS, 0x9000), (UC_X86_REG_SP, 0xFFF0)):
        mu.reg_write(r, v)
    SENT = 0xFFFE                                     # return sentinel inside CS

    def call(ip, bx=None):
        if bx is not None:
            mu.reg_write(UC_X86_REG_BX, bx)
        sp = mu.reg_read(UC_X86_REG_SP) - 2
        mu.mem_write(0x90000 + sp, struct.pack("<H", SENT))
        mu.reg_write(UC_X86_REG_SP, sp)
        mu.reg_write(UC_X86_REG_CS, LOAD_SEG)
        mu.emu_start(base + ip, base + SENT, count=100000)
        mu.reg_write(UC_X86_REG_SP, 0xFFF0)
        mu.reg_write(UC_X86_REG_DS, 0x1800)
        mu.reg_write(UC_X86_REG_ES, 0x1800)

    cur[0] = -1
    call(0x553, script)                               # start: gate on, PIT ch2 mode 3
    trace = []
    for t in range(ticks):
        cur[0] = t
        call(0x57A)
        trace.append((port61[0] & 3 == 3, pit_latch["div"]))
    return trace, log


# ----------------------------------------------------------------------------- outputs
SEG_FIELDS = ["t_ms", "dur_ms", "tick", "ticks", "on", "divisor", "hz"]


def dump_json(obj, path):
    """indent=1, but every innermost list on one line (keeps the segment tables compact)."""
    import re
    txt = json.dumps(obj, indent=1)
    txt = re.sub(r"\[\s*([^\[\]{}]*?)\s*\]", lambda m: "[" + re.sub(r"\s*\n\s*", " ", m.group(1)) + "]", txt)
    with open(path, "w", newline="\n") as f:
        f.write(txt + "\n")


def load_segments(rec):
    return [dict(zip(rec["segment_fields"], row)) for row in rec["segments"]]


def hz(div):
    return PIT_HZ / (div or 0x10000)


def segments(trace):
    segs = []
    for t, (on, div) in enumerate(trace):
        key = (on, div)
        if segs and segs[-1]["key"] == key:
            segs[-1]["ticks"] += 1
        else:
            segs.append({"key": key, "tick": t, "ticks": 1})
    out = []
    for s in segs:
        on, div = s["key"]
        out.append({"t_ms": round(s["tick"] * TICK_MS, 3), "dur_ms": round(s["ticks"] * TICK_MS, 3),
                    "tick": s["tick"], "ticks": s["ticks"], "on": on,
                    "divisor": div, "hz": round(hz(div), 2) if on else 0})
    return out


def render_square(path, segs, rate=44100, amp=0.45, pad_ms=150):
    pad = [0] * int(rate * pad_ms / 1000)
    out = list(pad)
    phase = 0.0
    total = sum(s["ticks"] for s in segs)
    n_total = int(round(total * TICK_MS / 1000 * rate))
    t_acc = 0
    for s in segs:
        n0 = int(round(t_acc * TICK_MS / 1000 * rate))
        t_acc += s["ticks"]
        n1 = int(round(t_acc * TICK_MS / 1000 * rate))
        if not s["on"]:
            out.extend([0] * (n1 - n0))
            continue
        f = hz(s["divisor"])
        inc = f / rate
        for _ in range(n1 - n0):
            out.append(int(amp * 32767) if phase < 0.5 else -int(amp * 32767))
            phase = (phase + inc) % 1.0
    assert len(out) - len(pad) == n_total
    out += pad
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(out), *out))


def env_table(img, tab):
    vals = []
    o = tab
    while len(vals) < 32:
        b = img[DS_FILE + o]
        if b in (0x80, 0x81):
            vals.append("loop" if b == 0x80 else "hold")
            break
        vals.append(s8(b))
        o += 1
    return vals


def main():
    ovl = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OVL
    img = open(ovl, "rb").read()
    # sanity: this is the engine we decoded
    assert u16(img, 0x464) == TIMER_DIV and img[0x463] == 0xB9, "int 8 rate not where expected"
    assert [u16(img, DS_FILE + 0xF0C + 2 * i) for i in range(7)] == \
        [0x5FC, 0x67F, 0x6B7, 0x628, 0x608, 0x66C, 0x646], "opcode table mismatch"
    os.makedirs(os.path.join(QL, "audio", "dos"), exist_ok=True)
    os.makedirs(os.path.join(QL, "build", "snd", "dos"), exist_ok=True)
    eng = Engine(img)
    index = []
    for script, name, trigger, event, cpc, conf in SOUNDS:
        notes, trace, loop_tick = eng.run(script, 200000)
        # one pass: for looping tunes stop at the tick the JUMP back to the start happens
        n = loop_tick if loop_tick is not None else len(trace)
        if loop_tick is None:
            # trace includes the END tick (speaker off); keep it out of the audible list
            while n and not trace[n - 1][0]:
                n -= 1
        trace = trace[:n]
        emu, outlog = emulate(img, script, n)
        if emu != trace:
            bad = next(i for i in range(n) if emu[i] != trace[i])
            raise SystemExit("%s: emulator and decoder disagree at tick %d: %r vs %r" % (name, bad, emu[bad], trace[bad]))
        segs = segments(trace)
        note_list = []
        for ev in notes:
            if ev[0] == "note" and (loop_tick is None or ev[1] < loop_tick):
                _, t, div, dur, rate, tab = ev
                env = env_table(img, tab)
                note_list.append({"t_ms": round(t * TICK_MS, 3), "dur_ms": round(dur * TICK_MS, 3),
                                  "tick": t, "ticks": dur, "divisor": div, "hz": round(hz(div), 2),
                                  "envelope": {"every_ticks": rate, "table": "DS:%04X" % tab, "divisor_deltas": env}})
        ports = {}
        for _, p, _v in outlog:
            ports[p] = ports.get(p, 0) + 1
        rec = {
            "name": name, "script": "DS:%04X" % script, "file_offset": "0x%05X" % (DS_FILE + script),
            "trigger": trigger, "event": event, "cpc_equivalent": cpc, "mapping_confidence": conf,
            "tick_hz": round(TICK_HZ, 4), "tick_ms": round(TICK_MS, 5), "pit_hz": PIT_HZ,
            "loops": loop_tick is not None,
            "pass_ms": round(n * TICK_MS, 1), "pass_ticks": n,
            "notes": note_list,
            "segments": segs,
            "verification": "per-tick (gate, divisor) trace from Unicorn running the x86 engine == static decoder; "
                            "OUT counts %s" % {("%02Xh" % k): v for k, v in sorted(ports.items())},
        }
        rec["segment_fields"] = SEG_FIELDS
        rec["segments"] = [[sg[k] for k in SEG_FIELDS] for sg in segs]
        dump_json(rec, os.path.join(QL, "audio", "dos", name + ".json"))
        render_square(os.path.join(QL, "build", "snd", "dos", name + "_dos.wav"), segs)
        fr = [s["hz"] for s in segs if s["on"]]
        print("%-17s %s  %3d notes %4d segs  %7.0f ms%s  %.1f-%.1f Hz  emu==decoder"
              % (name, rec["script"], len(note_list), len(segs), rec["pass_ms"],
                 " (loop)" if rec["loops"] else "", min(fr), max(fr)))
        index.append({k: rec[k] for k in ("name", "script", "file_offset", "trigger", "event",
                                          "cpc_equivalent", "mapping_confidence", "loops", "pass_ms")})
    ipath = os.path.join(QL, "audio", "dos", "index.json")
    out = {"engine": "ABADIA1.OVL 0x553/0x57a, tick %.4f Hz" % TICK_HZ, "sounds": index,
           "silent_on_dos": [{"sound": a, "where": b} for a, b in SILENT]}
    if os.path.exists(ipath):                    # keep the list tools/cpc_sound_ql.py adds
        old = json.load(open(ipath))
        if "cpc_derived" in old:
            out["cpc_derived"] = old["cpc_derived"]
    dump_json(out, ipath)


if __name__ == "__main__":
    main()

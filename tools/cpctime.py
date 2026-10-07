#!/usr/bin/env python3
"""The ORIGINAL CPC game (La Abadia del Crimen, CPC 6128) run from its own entry point on a Z80
emulator, with the CPC's real timing, to measure how fast the CPC actually is
(docs/speed_vs_cpc.md). Built on tools/cpcref.py's memory/bank model (pip package z80).

Timing model (the CPC 6128):
  - the Z80 runs at 4 MHz, but the gate array stretches every instruction to a whole number of
    microseconds ("NOPs"): CPC time of an instruction = ceil(T-states / 4) us. (The known
    exceptions, e.g. OUT (n),A / IN A,(n) 11 T = 3 us, EX (SP),HL 19 T = 6 us, differ by at most
    1 us an instruction.) Validation: the parchment's delay loop (CPC 0x67C6: nop / dec bc /
    ld a,b / or c / jr nz) is 1 + 2 + 1 + 1 + 3 = 8 us an iteration here, which is the value the
    CPC literature gives and "32 ciclos" in Manuel Abadia's disassembly (32 T-units = 8 us; his
    "aprox 10 microsegundos" assumed 3.2 MHz on top of the rounding, counting the stretch twice).
  - interrupts: the gate array raises one every 52 HSYNCs = 3328 us (6 a 50 Hz frame, "300 Hz");
    held until accepted (IM 1: RST 38h, where the game puts JP 0x2D48: music, speech/phrase
    scroll, the main loop's counter).
  - the keyboard: PPI port A answers the row selected through PPI port C (key = row*8 + bit,
    as the game's 0x3482 numbers them: 0 cursor up, 8 cursor left, 1 cursor right, 0x2f space).

Fast-forward (exact, to keep Python runs short): the parchment's delay loop (0x67C6) and the
main loop's wait (0x2614) are skipped to the next interrupt in one go, adding their exact time.

  cpctime.py intro [--pages 1]          the intro parchment: times of strokes, lines, pages
  cpctime.py loop --keys SCRIPT --iters N   the main loop: time of every iteration
"""
import argparse, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cpcref

INT_US = 3328                   # 52 x 64 us
FRAME_T = 69888                 # the z80 package's frame length in T-states (frame_tick wraps)
KEYNUM = {"UP": 0, "RIGHT": 1, "DOWN": 2, "LEFT": 8, "SPACE": 0x2f, "ESC": 0x42,
          "S": 0x3c, "N": 0x2e, "Q": 0x43, "R": 0x32}


class Cpc:
    def __init__(self):
        r = cpcref.roms()
        mem = bytearray(0x10000)
        mem[0:0xc000] = r[0:0xc000]
        self.cpu = cpcref.Cpu(mem, r)
        m = self.m = self.cpu.m
        self.us = 0                     # CPC time, microseconds
        self.next_int = INT_US
        self.int_pending = False
        self.ints = 0
        self.row = 0
        self.keys = set()               # key numbers held
        self.ppi_c = 0
        m.set_input_callback(self._in)
        bank_out = self.cpu._out

        def out(port, value):
            hi = port >> 8
            if hi == 0xf6:
                self.ppi_c = value
                self.row = value & 0x0f
            bank_out(port, value)
        m.set_output_callback(out)
        self.hooks = {}                 # pc -> fn(self)

    def _in(self, port):
        hi = port >> 8
        if hi == 0xf4:
            v = 0xff
            for k in self.keys:
                if k >> 3 == self.row:
                    v &= ~(1 << (k & 7))
            return v & 0xff
        if hi == 0xf5:
            return 0x7e                 # PPI port B: VSYNC etc. (no VSYNC waits in the game)
        return 0xff

    def interrupt(self):
        m = self.m
        if m.halted:
            m.pc = (m.pc + 1) & 0xffff
            m.halted = False
        sp = (m.sp - 2) & 0xffff
        m.memory[sp] = m.pc & 0xff
        m.memory[(sp + 1) & 0xffff] = m.pc >> 8
        m.sp = sp
        m.pc = 0x0038
        m.iff1 = m.iff2 = 0
        self.us += 4                    # the acknowledge + RST: ~13 T
        self.ints += 1

    def step(self):
        m = self.m
        pc = m.pc
        h = self.hooks.get(pc)
        if h:
            h(self)
            pc = m.pc
        # exact fast-forward of the two busy waits
        if pc == 0x67C6 and m.bc != 1:
            left = m.bc if m.bc else 0x10000         # (bc = 0: 65536 iterations)
            it = min(left - 1, max(0, (self.next_int - self.us) // 8))
            if it > 0:
                m.bc = (left - it) & 0xffff
                self.us += 8 * it
        elif pc == 0x2614:
            # ld a,(0x2d4b) / cp n / jr c: spins until an interrupt raises the counter
            if m.memory[0x2D4B] < m.memory[0x2618] and self.us < self.next_int:
                self.us = self.next_int
        if self.us >= self.next_int:
            self.next_int += INT_US
            self.int_pending = True
        # never between a DD/FD prefix and its opcode, nor right after EI (int_disabled)
        if self.int_pending and m.iff1 and not m.int_disabled and str(m.index_rp_kind).lower().endswith("hl"):
            self.int_pending = False
            self.interrupt()
            return
        f0 = m.frame_tick
        m.ticks_to_stop = 1
        m.run()
        t = m.frame_tick - f0
        if t <= 0:
            t += FRAME_T
        self.us += (t + 3) // 4
        if m.halted:                    # HALT: the CPU idles until the next interrupt
            self.us = max(self.us, self.next_int)

    def run_until(self, pred, limit_us):
        while not pred(self):
            self.step()
            if self.us > limit_us:
                return False
        return True


def cmd_intro(a):
    c = Cpc()
    c.m.pc = 0x249A
    c.m.sp = 0xC000 - 2
    events = []
    # 0x6781: the start of a stroke (after the character's first delay is set up), 0x67CD: a
    # space or the end of a character, 0x67DE: a new line, 0x67F0: a page turn,
    # 0x672C: the writer's loop (one key check per stroke)
    marks = {0x6781: "stroke", 0x67CD: "space", 0x67DE: "newline", 0x6763: "char"}
    for pc, name in marks.items():
        c.hooks[pc] = (lambda n: (lambda cc: events.append((cc.us, n))))(name)
    limit = a.seconds * 1e6
    pages = 0
    end = []

    def at_char(cc):                    # 0x673D: cp 0x1a (the end of the parchment's text)
        if cc.m.a == 0x1A and not end:
            end.append(cc.us)
    c.hooks[0x673D] = at_char
    npage = [0]

    def at_page(cc):
        events.append((cc.us, "page"))
        npage[0] += 1
        print("page turn %d at %.2f s" % (npage[0], cc.us / 1e6))
    c.hooks[0x67F0] = at_page
    while c.us < limit and not end and npage[0] < a.pages:
        c.step()
    pages = npage[0]
    # summary
    chars = [e for e in events if e[1] == "char"]
    strokes = [e for e in events if e[1] == "stroke"]
    lines = [e for e in events if e[1] == "newline"]
    first = events[0][0] if events else 0
    print("CPC intro: first stroke at %.2f s (after the parchment is drawn)" % (first / 1e6))
    print("  characters %d, strokes %d, spaces/char ends %d, new lines %d, page turns %d"
          % (len(chars), len(strokes), sum(1 for e in events if e[1] == "space"), len(lines), pages))
    if len(chars) > 1:
        span = (chars[-1][0] - chars[0][0]) / 1e6
        print("  characters per second (whole span, incl. line/page waits): %.2f" % ((len(chars) - 1) / span))
    # per-line times
    prev = first
    for i, (t, _) in enumerate(lines[:12]):
        print("  line %d ends at %.2f s (%.2f s)" % (i + 1, t / 1e6, (t - prev) / 1e6))
        prev = t
    # stroke cost: time between consecutive strokes of one character
    ds = [strokes[i + 1][0] - strokes[i][0] for i in range(len(strokes) - 1)
          if 0 < strokes[i + 1][0] - strokes[i][0] < 20000]
    if ds:
        ds.sort()
        print("  stroke to stroke: median %.2f ms, mean %.2f ms" % (ds[len(ds) // 2] / 1000, sum(ds) / len(ds) / 1000))
    print("  interrupts %d (%.1f Hz)" % (c.ints, c.ints / (c.us / 1e6)))
    if end:
        print("  the text ends (the CPC waits for SPACE) at %.2f s" % (end[0] / 1e6))
    # a page turn: from the 0x67F0 call (after the page's last line) to the next page's first stroke
    for t, n in events:
        if n == "page":
            nxt = next((u for u, m in events if m == "stroke" and u > t), None)
            if nxt:
                print("  page turn at %.2f s: the next page's first stroke %.2f s later" % (t / 1e6, (nxt - t) / 1e6))
    return 0


def parse_keys(path):
    """tests/*.txt: first last KEY (per main-loop iteration here)"""
    out = []
    for line in open(path):
        line = line.split("#")[0].split()
        if len(line) >= 3:
            out.append((int(line[0]), int(line[1]), line[2]))
    return out


def cmd_loop(a):
    c = Cpc()
    c.m.pc = 0x249A
    c.m.sp = 0xC000 - 2
    script = parse_keys(a.keys) if a.keys else []
    it_start = []                       # (us, wait_us) per main-loop iteration
    state = {"wait0": None, "waited": 0, "need": []}

    def at_loop(cc):
        it_start.append((cc.us, state["waited"]))
        state["waited"] = 0
        n = len(it_start)
        cc.keys = {KEYNUM[k] for f, l, k in script if f <= n <= l and k in KEYNUM}

    def at_wait(cc):
        if state["wait0"] is None:          # (0x2614 is also the spin's own target)
            state["wait0"] = cc.us
            state["need"].append(cc.m.memory[0x2618])

    def after_wait(cc):
        if state["wait0"] is not None:
            state["waited"] += cc.us - state["wait0"]
            state["wait0"] = None
    c.hooks[0x25B7] = at_loop
    c.hooks[0x2614] = at_wait
    c.hooks[0x261B] = after_wait
    # the intro: SPACE ends the parchment; the game then waits for it to be released (0x2509)
    c.keys = {KEYNUM["SPACE"]}

    def released(cc):
        cc.keys = set()
    c.hooks[0x2509] = released
    if not c.run_until(lambda cc: len(it_start) >= 1, 120e6):
        print("main loop not reached")
        return 1
    print("main loop reached at %.2f s CPC time" % (c.us / 1e6))
    while len(it_start) < a.iters + 1:
        c.step()
    per = [(it_start[i + 1][0] - it_start[i][0], it_start[i + 1][1]) for i in range(len(it_start) - 1)]
    out = open(a.out, "w") if a.out else None
    for i, (dt, w) in enumerate(per):
        line = "%d %.2f %.2f" % (i + 1, dt / 1000, (dt - w) / 1000)
        if out:
            out.write(line + "\n")
    if out:
        out.close()
    ms = sorted(d / 1000 for d, w in per)
    work = sorted((d - w) / 1000 for d, w in per)
    print("wait threshold (0x2618) per iteration: %s" % state["need"][:a.iters])
    print("iterations %d: period mean %.1f ms, median %.1f, max %.1f; work (period - wait at 0x2614) mean %.1f, max %.1f; "
          "iterations waiting (work < period): %d"
          % (len(per), sum(ms) / len(ms), ms[len(ms) // 2], ms[-1], sum(work) / len(work), work[-1],
             sum(1 for d, w in per if w > 0)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("intro")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--seconds", type=float, default=200)
    p = sub.add_parser("loop")
    p.add_argument("--keys")
    p.add_argument("--iters", type=int, default=100)
    p.add_argument("--out")
    a = ap.parse_args()
    return cmd_intro(a) if a.cmd == "intro" else cmd_loop(a)


if __name__ == "__main__":
    sys.exit(main())

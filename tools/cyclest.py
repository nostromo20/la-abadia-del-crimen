#!/usr/bin/env python3
"""68008 cycle ESTIMATES for the hybrid image, from executed traces in unicorn.

Unicorn has no 68008 timing, so every basic block the image executes is costed with a
bus-bound model of the 68008 (8-bit data bus, 4 clocks per byte transferred):
    cycles = 4 * (instruction bytes + data bytes read/written) + internal cycles
internal: mulu/muls ~54, divu ~140, divs ~158, shifts/rotates 2*count (register count = 8
assumed), taken branches/dbra +2, address calculation for indexed modes +2, rts/jsr/bsr
stack traffic counted as data bytes. Accuracy: an estimate, roughly +-30%. NOT included:
display contention on the QL's lower 128 KB (the screen at $20000 and everything below
$40000 - QDOS gives up a share of bus cycles to the video), interrupts, QDOS itself.

  cyclest.py --script s.txt --ticks N [--skip K] [--top 25]
Prints per-tick cost (mean/max ms at 7.5 MHz) and the functions using most cycles.
"""
import argparse, bisect, os, re, struct, sys
import capstone
from unicorn import UC_HOOK_BLOCK

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun

MHZ = 7.5
EXCLUDE = {"wait_tick"}   # the frame-pacing busy-wait is idle time, not cost
md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)

SIZE = {"b": 1, "w": 2, "l": 4}


def mem_operands(ops):
    parts = []
    depth = 0
    cur = ""
    for ch in ops:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    out = []
    for p in parts:
        is_mem = ("(" in p) or (p.startswith("$") and not p.startswith("#"))
        idx = "," in p and "(" in p
        out.append((p, is_mem, idx))
    return out


def insn_cost(i):
    m = i.mnemonic
    base, _, suf = m.partition(".")
    sz = SIZE.get(suf, 2)
    ops = mem_operands(i.op_str)
    data = 0
    internal = 0
    branchy = base in ("bra", "bsr", "jmp", "jsr", "rts", "rte") or (base.startswith("b") and base not in ("btst", "bset", "bclr", "bchg")) or base.startswith("db")
    if base in ("lea", "pea"):
        internal += 2 + (2 if any(o[2] for o in ops) else 0)
        if base == "pea":
            data += 4
    elif base == "movem":
        regs = 0
        for p, mem, idx in ops:
            if not mem:
                for grp in p.split("/"):
                    if "-" in grp:
                        a, b = grp.split("-")
                        regs += abs(int(b[1:]) - int(a[1:])) + 1 + (8 if a[0] != b[0] else 0)
                    else:
                        regs += 1
        data += regs * sz
    elif branchy:
        if base in ("bsr", "jsr"):
            data += 4
        elif base == "rts":
            data += 4
        internal += 2
    else:
        nmem = [o for o in ops if o[1]]
        if base in ("move", "movea", "moveq", "clr", "scc", "st", "sf", "sne", "seq") or base.startswith("s") and len(base) == 3:
            # destination written only; source read
            for k, (p, mem, idx) in enumerate(ops):
                if mem:
                    data += sz
                    internal += 2 if idx else 0
        else:
            for k, (p, mem, idx) in enumerate(ops):
                if mem:
                    data += sz * (2 if k == len(ops) - 1 and base not in ("cmp", "cmpa", "cmpi", "tst", "btst", "cmpm") else 1)
                    internal += 2 if idx else 0
        if base in ("mulu", "muls"):
            internal += 54
        elif base == "divu":
            internal += 136
        elif base == "divs":
            internal += 156
        elif base in ("lsl", "lsr", "asl", "asr", "rol", "ror", "roxl", "roxr"):
            mm = re.match(r"#\$?([0-9a-f]+)", i.op_str)
            n = int(mm.group(1), 16) if mm else 8
            internal += 2 + 2 * n
        elif sz == 4 and not nmem:
            internal += 4
    return 4 * (i.size + data) + internal


class Estimator:
    def __init__(self, runner):
        self.r = runner
        self.cache = {}
        self.blocks = {}
        names = sorted((v, k) for k, v in runner.syms.items())
        self.addrs = [v for v, k in names]
        self.names = [k for v, k in names]
        self.total = 0
        self.per_tick = []
        self.func = {}
        runner.mu.hook_add(UC_HOOK_BLOCK, self.on_block)

    def block_cost(self, addr, size):
        key = (addr, size)
        c = self.cache.get(key)
        if c is None:
            code = bytes(self.r.mu.mem_read(addr, size))
            c = sum(insn_cost(i) for i in md.disasm(code, addr))
            self.cache[key] = c
        return c

    def on_block(self, mu, addr, size, data):
        c = self.block_cost(addr, size)
        off = addr - self.r.base
        k = bisect.bisect_right(self.addrs, off) - 1
        name = self.names[k] if k >= 0 else "?"
        if name in EXCLUDE:
            return
        self.total += c
        self.func[name] = self.func.get(name, 0) + c


def demangle_short(n):
    m = re.match(r"_ZN6Abadia(\d+)(\w+?)(\d+)(\w+)", n)
    if m:
        l1 = int(m.group(1)); rest = n[len("_ZN6Abadia") + len(m.group(1)):]
        cls = rest[:l1]; rest = rest[l1:]
        mm = re.match(r"(\d+)", rest)
        if mm:
            l2 = int(mm.group(1)); fn = rest[len(mm.group(1)):len(mm.group(1)) + l2]
            return cls + "::" + fn
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script")
    ap.add_argument("--ticks", type=int, default=100)
    ap.add_argument("--skip", type=int, default=0, help="ignore the first K ticks in the per-function table")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--spikes", type=float, default=0, help="break down every step costing more than this many ms")
    ap.add_argument("--per", action="store_true", help="print every step's estimate")
    ap.add_argument("--realq", action="store_true", help="real-QDOS model: 50 Hz polls (sound engine) included")
    ap.add_argument("--sv164", default="0", help="QSound vector (e.g. 0xC1000 = QSound present)")
    ap.add_argument("--poke", action="append", default=[], help="sym=value: a long written before the run "
                    "(e.g. ql_compose_on=0)")
    a = ap.parse_args()
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(a.script), realq=a.realq,
                     sv164=int(a.sv164, 0))
    for pk in a.poke:
        name, val = pk.split("=")
        r.mu.mem_write(qlrun.BASE + syms[name], int(val, 0).to_bytes(4, "big"))
    est = Estimator(r)
    marks = []

    snaps = []

    def cb(r):
        marks.append(est.total)
        if a.spikes:
            snaps.append(dict(est.func))
        if r.tick == a.skip:
            est.func.clear()
    r.tick_cb = cb
    r.run(a.ticks)
    per = [marks[i] - marks[i - 1] for i in range(1, len(marks))]
    init = marks[0] if marks else est.total
    per_s = per[a.skip:] if len(per) > a.skip else per
    ms = lambda c: c / (MHZ * 1000.0)
    print("ESTIMATE (68008 @ %.1f MHz, bus model, no display contention): %s" % (MHZ, r.stop_reason))
    print("  init + first tick: %.0f ms" % ms(init))
    if per_s:
        srt = sorted(per_s)
        print("  per logic step: mean %.1f ms, median %.1f ms, max %.1f ms (budget 130 ms) over %d steps"
              % (ms(sum(per_s) / len(per_s)), ms(srt[len(srt) // 2]), ms(srt[-1]), len(per_s)))
        if a.per:
            print("  per step ms: " + " ".join("%d:%.0f" % (a.skip + 1 + i, ms(c)) for i, c in enumerate(per_s)))
        over = sum(1 for c in per_s if ms(c) > 130)
        print("  steps over 130 ms: %d" % over)
    if a.spikes:
        for i in range(1, len(snaps)):
            c = marks[i] - marks[i - 1]
            if ms(c) <= a.spikes or i <= a.skip:
                continue
            prev, cur = snaps[i - 1] if i - 1 > a.skip else {}, snaps[i]
            if i - 1 == a.skip:
                prev = {}
            delta = sorted(((cur.get(k, 0) - prev.get(k, 0), k) for k in cur), reverse=True)[:10]
            print("  step %d: %.0f ms: %s" % (i, ms(c), ", ".join("%s %.0f" % (demangle_short(k), ms(v)) for v, k in delta if v > 0)))
    tot = sum(est.func.values()) or 1
    print("  top functions (after skip):")
    for name, c in sorted(est.func.items(), key=lambda x: -x[1])[:a.top]:
        print("    %5.1f%%  %8.1f ms  %s" % (100.0 * c / tot, ms(c), demangle_short(name)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""68000 decoders of the candidate codecs, run on the real compressed release files in unicorn
and timed with tools/cyclest.py's 68008 bus model (8-bit data bus, 4 clocks a byte, 7.5 MHz,
no display contention: the game loads into RESPR space above the screen). Every output is
checked byte-identical with the original. For docs/compression.md.

Decoders (build/codecs/dec): hand-written 68000 ones assembled with vasm (ZX0 v2 by Emmanuel
Marty, aPLib by Emmanuel Marty, LZ4 frame by Arnaud Carre (smallest and fastest variants),
Shrinkler by Aske Simon Christensen); C reference decoders compiled for the 68000 with
m68k-linux-gnu-gcc -O2 (LZMA: Igor Pavlov's LzmaDec.c from the LZMA SDK; upkr: c_unpacker;
Exomizer 3: rawdecrs/exodecr.c; LZSA2: expand_block_v2.c), built by build/codecs/cdec.sh.

  codecrun.py NAME [NAME...]       NAME = a file in build/codecs (compressed copies in out/)
"""
import os, struct, sys
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cyclest
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_BLOCK
from unicorn import m68k_const as M

D = os.path.join(QL, "build", "codecs")
DEC = os.path.join(D, "dec")
CODE, SRC, DST, STACK, RET = 0x1000, 0x100000, 0x200000, 0x3ff000, 0x800

# name, compressed extension, decoder binary, kind ("asm": a0 src, a1 dst; "c": dec(src, dst, n, m)),
# decoder bytes (None = the whole binary), extra RAM the decoder needs (bytes)
DECODERS = [
    ("ZX0 v2", "zx0", "unzx0_68000.bin", "asm", None, 0),
    ("aPLib", "apl", "unaplib_68000.bin", "asm", None, 0),
    ("LZ4 (smallest)", "lz4", "lz4_frame.bin", "asm", None, 0),
    ("LZ4 (fastest)", "lz4", "lz4_frame_fast.bin", "asm", None, 0),
    ("Shrinkler", "shr", "shrinkler_dec.bin", "shr", None, 3072),
    ("LZSA2 (C)", "lzsa2", "c/lzsa2.bin", "c", None, 0),
    ("upkr (C)", "upk", "c/upkr.bin", "c", None, 396),
    ("Exomizer 3 -b (C)", "exob", "c/exo.bin", "c", None, 158),
    ("LZMA1 (C, LzmaDec)", "lzmap", "c/lzma.bin", "c", None, 0),
]


class Timer:
    def __init__(self, mu):
        self.cost = {}
        self.cycles = 0
        mu.hook_add(UC_HOOK_BLOCK, self.on_block)

    def on_block(self, mu, addr, size, data):
        c = self.cost.get((addr, size))
        if c is None:
            code = bytes(mu.mem_read(addr, size))
            c = sum(cyclest.insn_cost(i) for i in cyclest.md.disasm(code, addr))
            self.cost[(addr, size)] = c
        self.cycles += c


def run(decbin, kind, comp, n_out):
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68040)
    mu.mem_map(0, 0x400000)
    code = open(os.path.join(DEC, decbin), "rb").read()
    mu.mem_write(CODE, code)
    mu.mem_write(RET, b"\x4e\x71\x4e\x71")
    mu.mem_write(SRC, comp + b"\0\0\0\0")
    entry = CODE
    if kind == "c":
        entry = CODE + 0x8c if False else None
        # the C binaries are linked with dec first? use the symbol address noted by cdec.sh
        entry = int(open(os.path.join(DEC, decbin.replace(".bin", ".entry"))).read(), 16)
        sp = STACK
        frame = struct.pack(">IIIII", RET, SRC, DST, len(comp), n_out)
        mu.mem_write(sp, frame)
    else:
        sp = STACK + 0x10
        mu.mem_write(sp, struct.pack(">I", RET))
        mu.reg_write(M.UC_M68K_REG_A0, SRC)
        mu.reg_write(M.UC_M68K_REG_A1, DST)
        if kind == "shr":
            for r in (M.UC_M68K_REG_A2, M.UC_M68K_REG_A3, M.UC_M68K_REG_D2):
                mu.reg_write(r, 0)
            mu.reg_write(M.UC_M68K_REG_D7, 1)          # parity context on (Shrinkler's default)
    mu.reg_write(M.UC_M68K_REG_A7, sp)
    t = Timer(mu)
    mu.emu_start(entry, RET)
    return bytes(mu.mem_read(DST, n_out)), t.cycles


def prepare(name):
    """the compressed inputs the decoders take, beside codecsize.py's outputs"""
    import lzma, subprocess
    out = os.path.join(D, "out")
    data = open(os.path.join(D, name), "rb").read()
    # LZMA for LzmaDec: 5-byte props header + the raw stream (lc lp pb from the "best" search)
    best = None
    for lc in range(4):
        for lp in range(3):
            for pb in range(3):
                if lc + lp > 4:
                    continue
                f = [{"id": lzma.FILTER_LZMA1, "preset": 9 | lzma.PRESET_EXTREME, "lc": lc, "lp": lp, "pb": pb,
                      "dict_size": 1 << 20}]
                c = lzma.compress(data, format=lzma.FORMAT_RAW, filters=f)
                if best is None or len(c) < len(best[0]):
                    best = (c, lc, lp, pb)
    c, lc, lp, pb = best
    props = bytes([(pb * 5 + lp) * 9 + lc]) + struct.pack("<I", 1 << 20)
    open(os.path.join(out, name + ".lzmap"), "wb").write(props + c)
    # Exomizer backwards (what rawdecrs/exodecr.c decodes)
    w = qlpaths.WSL_QL + "/build/codecs/out/" + name
    subprocess.run(["wsl", "bash", "-lc", "~/codecs/exomizer/src/exomizer raw -q -b %s -o %s.exob" % (w, w)],
                   env=dict(os.environ, MSYS_NO_PATHCONV="1"), capture_output=True)
    return data, (lc, lp, pb)


def main():
    for name in sys.argv[1:]:
        data, lzp = prepare(name)
        print("%s (%d bytes); LZMA lc%d lp%d pb%d" % ((name, len(data)) + lzp))
        print("  %-22s %8s %8s %10s %9s %s" % ("decoder", "packed", "dec bytes", "cycles", "seconds", "check"))
        for dname, ext, dbin, kind, dbytes, ram in DECODERS:
            p = os.path.join(D, "out", "%s.%s" % (name, ext))
            if not os.path.exists(p) or not os.path.exists(os.path.join(DEC, dbin)):
                print("  %-22s (missing)" % dname)
                continue
            comp = open(p, "rb").read()
            try:
                out, cyc = run(dbin, kind, comp, len(data))
                ok = "OK" if out == data else "DIFFERS (%d bytes)" % sum(1 for a, b in zip(out, data) if a != b)
            except Exception as e:
                out, cyc, ok = b"", 0, "ERROR %s" % e
            size = dbytes or os.path.getsize(os.path.join(DEC, dbin))
            print("  %-22s %8d %8d %10d %9.2f %s" % (dname, len(comp), size, cyc, cyc / (cyclest.MHZ * 1e6), ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())

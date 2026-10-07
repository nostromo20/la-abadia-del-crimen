#!/usr/bin/env python3
"""Static 68000 alignment scan of the compiled C/C++ (every STT_FUNC symbol of the image).

GCC 13 for m68k, even with -m68000 (-mstrict-align on), merged byte loads/stores into word
accesses at odd addresses (store-merging and the bswap pass) - an address error on a real
68008. The build now passes -fno-store-merging -fdisable-tree-bswap; this scan fails the
build if any word/long access with an ODD absolute address or an ODD offset from A7 is left.
(Odd offsets from other address registers cannot be judged statically; qlrun --align-check
covers what runs.)

  alignscan.py image.raw image.sym
"""
import re, sys
import capstone

md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)


def main():
    raw = open(sys.argv[1], "rb").read()
    funcs = []
    for line in open(sys.argv[2]):
        p = line.split()
        if len(p) >= 4 and int(p[3]) == 2 and int(p[2]) > 0:      # STT_FUNC with a size
            funcs.append((p[0], int(p[1], 16), int(p[2])))
    bad = []
    n = 0
    for name, start, size in funcs:
        for ins in md.disasm(raw[start:start + size], start):
            n += 1
            base, _, suf = ins.mnemonic.partition(".")
            if suf not in ("w", "l") or base in ("lea", "pea", "movem") or base.startswith(("b", "db", "j")):
                continue
            for op in ins.op_str.split(","):
                op = op.strip()
                m = re.match(r"^\$([0-9a-f]+)\.[wl]$", op)                 # absolute
                if m and int(m.group(1), 16) & 1:
                    bad.append((name, ins.address, ins.mnemonic, ins.op_str))
                m = re.match(r"^(-?\$?[0-9a-f]+)\(a7\)$", op)              # d16(a7)
                if m:
                    v = m.group(1)
                    d = -int(v.lstrip("-$"), 16) if v.startswith("-") else int(v.lstrip("$"), 16)
                    if d & 1:
                        bad.append((name, ins.address, ins.mnemonic, ins.op_str))
    for b in bad[:30]:
        print("alignscan: %s+%06x  %s %s" % b)
    if bad:
        print("alignscan: FAILED, %d odd word/long accesses in compiled code" % len(bad))
        return 1
    print("alignscan: %d functions, %d instructions, no odd absolute/stack word or long accesses" % (len(funcs), n))
    return 0


if __name__ == "__main__":
    sys.exit(main())

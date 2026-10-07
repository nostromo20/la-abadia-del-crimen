#!/usr/bin/env python3
"""Save files: the fork's text format <-> the compact format of cpp/port/ql_stream.h.

Text (before 2026-10-05): every value Serializar writes as a decimal number followed by a comment
("1// dia"), one per line, plus comment-only lines ("// SPR"), which the reader skips.
Compact: "ABQS", version 1, then each value as a 32-bit zigzag integer in little-endian base 128.

  savefmt.py --to-compact TEXT OUT      convert a text save
  savefmt.py --show FILE                the values (and the format)

As a module: values_of_text(bytes) / to_compact(values) / values_of_compact(bytes).
"""
import argparse, re, sys

MAGIC, VERSION = b"ABQS", 1


def values_of_text(data):
    vals = []
    for line in data.decode("latin-1").split("\n"):
        m = re.match(r"\s*([-+]?\d+)", line)
        if m:
            vals.append(int(m.group(1)))
    return vals


def zz(v):
    v = ((v + (1 << 31)) % (1 << 32)) - (1 << 31)       # as a 32-bit int, as the C++ does
    return ((v << 1) ^ (v >> 31)) & 0xFFFFFFFF


def to_compact(vals):
    out = bytearray(MAGIC + bytes([VERSION]))
    for v in vals:
        u = zz(v)
        while u >= 0x80:
            out.append((u & 0x7F) | 0x80)
            u >>= 7
        out.append(u)
    return bytes(out)


def values_of_compact(data):
    assert data[:4] == MAGIC and data[4] == VERSION, "not a compact save (version %d)" % VERSION
    vals, u, sh = [], 0, 0
    for c in data[5:]:
        u |= (c & 0x7F) << sh
        sh += 7
        if not c & 0x80:
            vals.append((u >> 1) ^ -(u & 1))
            u, sh = 0, 0
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to-compact", nargs=2, metavar=("TEXT", "OUT"))
    ap.add_argument("--show")
    a = ap.parse_args()
    if a.to_compact:
        src, dst = a.to_compact
        vals = values_of_text(open(src, "rb").read())
        c = to_compact(vals)
        assert values_of_compact(c) == vals
        open(dst, "wb").write(c)
        print("%s: %d values, %d bytes -> %s: %d bytes" % (src, len(vals), len(open(src, "rb").read()), dst, len(c)))
    if a.show:
        d = open(a.show, "rb").read()
        vals = values_of_compact(d) if d[:4] == MAGIC else values_of_text(d)
        print("%s: %s, %d bytes, %d values" % (a.show, "compact" if d[:4] == MAGIC else "text", len(d), len(vals)))
        print(" ".join(str(v) for v in vals))
    return 0


if __name__ == "__main__":
    sys.exit(main())

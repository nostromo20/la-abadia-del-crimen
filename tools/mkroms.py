#!/usr/bin/env python3
"""Builds VIGASOCO's "romsPtr" image (0x24000 bytes) from the CPC disk image, exactly as
AbadiaDriver::filesLoaded() does (tracks read with DskReader, each 16 KB bank byte-reversed).

The compiled logic indexes it as roms = romsPtr + 0x4000. Layout:
  0x00000 abadia0 (title screen)   0x04100 abadia1 (0x3f00)   0x08000 abadia2
  0x0c000 abadia3                  0x14000 abadia5            0x18000 abadia6
  0x1c000 abadia7                  0x20000 abadia8            (0x10000-0x13fff unused)

Also cross-checks the result against the extracted banks in data/ABADIA*.BIN.
"""
import argparse, os, sys
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
DEFAULT_DSK = qlpaths.DSK


class Dsk:
    def __init__(self, data):
        self.d = bytearray(data)
        assert self.d[:21] == b"EXTENDED CPC DSK File", "not an extended DSK"
        self.ntracks = self.d[0x30]

    def track_offset(self, n):
        off = 0x100
        for i in range(n):
            off += self.d[0x34 + i] * 256
        return off

    def track(self, n, size=0x0f00):
        s = self.track_offset(n)
        sector_size = self.d[s + 0x14] * 256
        nsec = self.d[s + 0x15]
        nbytes = min(nsec * sector_size, size)
        return bytes(self.d[s + 0x100:s + 0x100 + nbytes]).ljust(size, b"\0")


def build(dsk_bytes):
    dsk = Dsk(dsk_bytes)
    rom = bytearray(0x24000)

    def tracks(a, b):
        buf = bytearray(0xff00 + 0x1000)
        for i in range(a, b + 1):
            t = dsk.track(i)
            buf[(i - a) * 0x0f00:(i - a) * 0x0f00 + 0x0f00] = t
        return buf

    def reorder(src, off, dst, size):
        for i in range(size):
            rom[dst + size - i - 1] = src[off + i]

    aux = tracks(0x01, 0x11)
    reorder(aux, 0x0000, 0x00000, 0x4000)   # abadia0
    reorder(aux, 0x4000, 0x0c000, 0x4000)   # abadia3
    reorder(aux, 0x8000, 0x20000, 0x4000)   # abadia8
    reorder(aux, 0xc000, 0x04100, 0x3f00)   # abadia1
    reorder(tracks(0x12, 0x16), 0, 0x1c000, 0x4000)   # abadia7
    reorder(tracks(0x17, 0x1b), 0, 0x18000, 0x4000)   # abadia6
    reorder(tracks(0x1c, 0x21), 0, 0x14000, 0x4000)   # abadia5
    reorder(tracks(0x21, 0x25), 0, 0x08000, 0x4000)   # abadia2
    return rom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsk", default=DEFAULT_DSK)
    ap.add_argument("--out", default=os.path.join(QL, "build", "roms.bin"))
    a = ap.parse_args()
    rom = build(open(a.dsk, "rb").read())
    # cross-check with the banks already extracted for the asm tools
    checks = [("ABADIA0.BIN", 0x00000, 0x4000), ("ABADIA1.BIN", 0x04100, 0x3f00),
              ("ABADIA2.BIN", 0x08000, 0x4000), ("ABADIA3.BIN", 0x0c000, 0x4000),
              ("ABADIA6.BIN", 0x18000, 0x4000), ("ABADIA7.BIN", 0x1c000, 0x4000),
              ("ABADIA8.BIN", 0x20000, 0x4000)]
    bad = 0
    for name, off, size in checks:
        p = os.path.join(QL, "data", name)
        if not os.path.exists(p):
            continue
        ref = open(p, "rb").read()[:size]
        diff = sum(1 for i in range(len(ref)) if ref[i] != rom[off + i])
        print("%-12s vs roms[0x%05x]: %s" % (name, off, "identical" if diff == 0 else "%d bytes differ" % diff))
        bad += diff != 0
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "wb").write(rom)
    print("wrote", a.out, len(rom), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

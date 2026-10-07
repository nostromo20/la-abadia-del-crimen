#!/usr/bin/env python3
"""Microdrive cartridge images in the QLay .mdv format (Q-emuLator mounts these; 255 sectors x 686
bytes = 174,930 bytes), written the way QDOS lays out a cartridge.

  mkmdv.py OUT.mdv --name ABADIA [--good 255] FILE[=QLNAME][:exe:DATASPACE] ...
  mkmdv.py --list IMG.mdv              # map, directory, checksums
  mkmdv.py --selftest IMG.mdv          # re-create a QDOS-written image from its own files: must be identical

Sector layout (686 bytes, in tape order: sector 0, then 254, 253 ... 1):
  0   10 x 00, FF FF          sector header preamble
  12  FF, sector number, medium name (10, space padded), random word, checksum (LE)
  28  10 x 00, FF FF          block header preamble
  40  file number, block number, checksum (LE)
  44  6 x 00, FF FF           data preamble
  52  512 data bytes, checksum (LE)
  566 84 bytes of AA 55, 19 3B, 34 x 00   (QLay's filler, the same in every sector)
Checksums are $0F0F + the byte sum (16 bits, little-endian).

QDOS cartridge: sector 0 is the map (file F8): one (file, block) pair per sector; FD 00 = free,
FF 00 = unusable (beyond the formatted length), and the last word is twice the sector last
allocated. The directory is file 0: a 64-byte header (length = 64 + 64 x files), then each
file's 64-byte header; every file's block 0 starts with that same header, so a file of n bytes
takes ceil((n + 64) / 512) sectors. Files are allocated as QDOS does on an empty cartridge: the
directory in the highest good sector, then every 9th sector going down the tape, wrapping, which
lets the driver read consecutive blocks as they pass the head (the wrap stays within sectors
1 .. good-1). --selftest checks this against cartridges QDOS and Q-emuLator wrote (interleave 8 and 9).
"""
import argparse, os, struct, sys

SECT = 686
NAME_LEN = 36


def cks(b):
    return (0x0F0F + sum(b)) & 0xFFFF


def sector(num, name, rnd, fil, blk, data):
    assert len(data) == 512 and len(name) == 10
    h = bytes([0xFF, num]) + name + struct.pack(">H", rnd)
    bh = bytes([fil, blk])
    s = (bytes(10) + b"\xff\xff" + h + struct.pack("<H", cks(h))
         + bytes(10) + b"\xff\xff" + bh + struct.pack("<H", cks(bh))
         + bytes(6) + b"\xff\xff" + data + struct.pack("<H", cks(data))
         + b"\xaa\x55" * 42 + b"\x19\x3b" + bytes(34))
    assert len(s) == SECT
    return s


def qdos_header(name, length, typ=0, dataspace=0, extra=0):
    """The 64-byte QDOS file header (length includes these 64 bytes)."""
    nb = name.encode("latin-1")
    assert len(nb) <= NAME_LEN, name
    return (struct.pack(">IBBII", length, 0, typ, dataspace, extra) + struct.pack(">H", len(nb))
            + nb.ljust(NAME_LEN, b"\0") + bytes(12))


def build(files, medium, good=255, rnd=0x2026, interleave=9):
    """files: list of (qlname, data, type, dataspace). Returns (image bytes, info)."""
    name = medium.encode("latin-1")[:10].ljust(10, b" ")
    owner = {}                                   # sector -> (file, block)
    owner[0] = (0xF8, 0)
    free = set(range(1, good))
    last = None

    def take(want):
        # the first free sector at or below `want`, going down the tape (wrapping)
        s = want
        for _ in range(good):
            if s < 1:
                s += good - 1                    # sectors 1 .. good-1 (0 is the map)
            if s in free:
                free.discard(s)
                return s
            s -= 1
        raise SystemExit("cartridge full")

    hdrs = [qdos_header(n, len(d) + 64, t, ds) for n, d, t, ds in files]
    dirdata = struct.pack(">I", 64 + 64 * len(files)) + bytes(60) + b"".join(hdrs)
    contents = [dirdata] + [h + d for h, (n, d, t, ds) in zip(hdrs, files)]
    data = {}
    pos = good - 1
    for fno, c in enumerate(contents):
        nblk = (len(c) + 511) // 512
        if nblk > 255:
            raise SystemExit("file %d too long" % fno)
        for b in range(nblk):
            s = take(pos)
            owner[s] = (fno, b)
            data[s] = c[b * 512:(b + 1) * 512].ljust(512, b"\0")
            last = s
            pos = s - interleave
    # the directory is written last by QDOS (each file close updates it)
    dsec = [s for s, (f, b) in owner.items() if f == 0][0]
    m = bytearray(512)
    for s in range(255):
        f, b = owner.get(s, (0xFD, 0) if s < good else (0xFF, 0))
        m[2 * s], m[2 * s + 1] = f, b
    m[510:512] = struct.pack(">H", 2 * dsec)
    data[0] = bytes(m)
    out = bytearray()
    for s in [0] + list(range(254, 0, -1)):
        f, b = owner.get(s, (0xFD, 0) if s < good else (0xFF, 0))
        if s == 0:
            f = 0x80                             # the map's own block header
        out += sector(s, name, rnd, f, b, data.get(s, bytes(512)))
    used = len(owner)
    return bytes(out), dict(used=used, good=good, free=good - used, last=last)


def parse(img):
    assert len(img) == 255 * SECT, len(img)
    secs = {}
    bad = []
    for i in range(255):
        s = img[i * SECT:(i + 1) * SECT]
        num = s[13]
        for a, b, what in ((12, 26, "hdr"), (40, 42, "blk"), (52, 564, "data")):
            if struct.unpack("<H", s[b:b + 2])[0] != cks(s[a:b]):
                bad.append((num, what))
        secs[num] = s
    m = secs[0][52:564]
    owner = {s: (m[2 * s], m[2 * s + 1]) for s in range(255)}

    def filedata(f):
        bl = sorted((b, s) for s, (ff, b) in owner.items() if ff == f and s != 0)
        return b"".join(secs[s][52:564] for b, s in bl), [s for b, s in bl]

    d, dsec = filedata(0)
    n = struct.unpack(">I", d[:4])[0] // 64 - 1
    files = []
    for k in range(1, n + 1):
        e = d[k * 64:(k + 1) * 64]
        ln, acc, typ, ds, ex, nl = struct.unpack(">IBBIIH", e[:16])
        fd, ss = filedata(k)
        files.append(dict(name=e[16:16 + nl].decode("latin-1"), length=ln - 64, type=typ, dataspace=ds,
                          data=fd[64:ln], hdr_ok=fd[:64] == e, sectors=ss))
    vals = list(owner.values())
    return dict(medium=secs[0][14:24].decode("latin-1"), files=files, bad_checksums=bad,
                good=sum(1 for f, b in vals if f != 0xFF), free=sum(1 for f, b in vals if f == 0xFD),
                used=sum(1 for f, b in vals if f not in (0xFD, 0xFF)), last_word=m[510:512].hex(),
                random=struct.unpack(">H", secs[0][24:26])[0], dir_sector=dsec[0])


def lst(img):
    p = parse(img)
    print("medium '%s'  good sectors %d  used %d  free %d  checksum errors %d"
          % (p["medium"], p["good"], p["used"], p["free"], len(p["bad_checksums"])))
    for f in p["files"]:
        print("  %-20s %7d bytes  type %d  dataspace %7d  %3d sectors  header copy ok %s"
              % (f["name"], f["length"], f["type"], f["dataspace"], len(f["sectors"]), f["hdr_ok"]))
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--name", default="ABADIA")
    ap.add_argument("--good", type=int, default=255)
    ap.add_argument("--list")
    ap.add_argument("--selftest")
    a = ap.parse_args()
    if a.list:
        p = lst(open(a.list, "rb").read())
        return 1 if p["bad_checksums"] else 0
    if a.selftest:
        img = open(a.selftest, "rb").read()
        p = lst(img)
        il = p["dir_sector"] - p["files"][0]["sectors"][0]        # the writer's interleave
        new, info = build([(f["name"], f["data"], f["type"], f["dataspace"]) for f in p["files"]],
                          p["medium"], good=p["good"], rnd=p["random"], interleave=il)
        print("interleave %d" % il)
        same = new == img
        if not same:
            diff = [i for i in range(len(img)) if img[i] != new[i]]
            print("differs at %d bytes, first at sector index %d offset %d" % (len(diff), diff[0] // SECT, diff[0] % SECT))
        print("SELFTEST: re-created image identical: %s" % same)
        return 0 if same else 1
    files = []
    for spec in a.files:
        typ, ds = 0, 0
        if ":exe:" in spec:
            spec, ds = spec.split(":exe:")
            typ, ds = 1, int(ds)
        path, _, qn = spec.partition("=")
        files.append((qn or os.path.basename(path), open(path, "rb").read(), typ, ds))
    img, info = build(files, a.name, good=a.good)
    open(a.out, "wb").write(img)
    print("%s: %d sectors used of %d (%d free); vs 200: %d free, vs 220: %d free, vs 255: %d free"
          % (a.out, info["used"], info["good"], info["free"], 200 - info["used"], 220 - info["used"], 255 - info["used"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

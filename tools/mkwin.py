#!/usr/bin/env python3
"""Builds a QXL.WIN hard-disk container (QPC2, SMSQmulator, sQLux, Q-emuLator, QL-SD) holding
the release files of release/win/ (BOOT, abadia_title, abadia), so the game runs as win1_.

  mkwin.py [--src release/win] [--out release/abadia.win] [--mb 2] [--name ABADIA]

Layout (as SMSQ/E writes it, checked against containers made by QPC2 and QL-SD):
  group 0..        'QLWA' header (64 bytes) then the map: one word per group = the next group of
                   its chain, 0 = end of chain. The header + map groups are chained 0 -> 1 -> .. -> 0
  next group       the root directory: a file like any other, 64 reserved bytes then one 64-byte
                   entry per file (the QDOS header: length incl. the 64 bytes, access, type,
                   dataspace, extra, name, update date, version, first group)
  files            each file = 64 reserved (zero) bytes, then its data; length counts both
  free groups      chained from the header's first-free word, the last one 0

Source files written by Q-emuLator / tools/mkrelease.py may start with the 30-byte
"]!QDOS File Header" (access, type, dataspace, extra): it is stripped and its job type and
dataspace go into the directory entry, so EXEC works from the container.
"""
import argparse, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
QEMU_MAGIC = b"]!QDOS File Header"
SCTG = 4                        # sectors (512 bytes) a group, as QPC2 / QL-SD make them
G = SCTG * 512
QDOS_EPOCH = 283996800          # 1961-01-01 -> 1970-01-01 (seconds)


def read_source(path):
    data = open(path, "rb").read()
    typ, ds, extra = 0, 0, 0
    if data.startswith(QEMU_MAGIC):
        hlen = struct.unpack(">H", data[18:20])[0] * 2
        _acc, typ, ds, extra = struct.unpack(">BBII", data[20:30])
        data = data[hlen:]
    return data, typ, ds, extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(QL, "release", "win"))
    ap.add_argument("--out", default=os.path.join(QL, "release", "abadia.win"))
    ap.add_argument("--mb", type=int, default=2, help="container size in MB (1..60)")
    ap.add_argument("--name", default="ABADIA", help="medium name (up to 20 characters)")
    a = ap.parse_args()

    ngroup = a.mb * 1024 * 1024 // G
    assert 64 <= ngroup <= 0xffff, "size out of range"
    hdrmap = 64 + 2 * ngroup
    sctmap = (hdrmap + 511) // 512
    nmapg = (sctmap + SCTG - 1) // SCTG
    img = bytearray(ngroup * G)
    mp = [0] * ngroup
    for g in range(nmapg - 1):
        mp[g] = g + 1
    nxt = nmapg                 # next group to hand out

    def alloc(nbytes):
        nonlocal nxt
        n = max(1, (nbytes + G - 1) // G)
        first = nxt
        for i in range(n - 1):
            mp[first + i] = first + i + 1
        mp[first + n - 1] = 0
        nxt += n
        assert nxt <= ngroup, "container too small"
        return first

    def write_chain(first, body):
        g, off = first, 0
        while True:
            img[g * G:g * G + min(G, len(body) - off)] = body[off:off + G]
            off += G
            if off >= len(body):
                return
            g = mp[g]

    # BOOT first (as QDOS lists it), then the rest by name
    names = sorted(os.listdir(a.src), key=lambda n: (n.lower() != "boot", n.lower()))
    files = [n for n in names if os.path.isfile(os.path.join(a.src, n))]
    now = int(time.time()) + QDOS_EPOCH
    rlen = 64 + 64 * len(files)
    root = alloc(rlen)
    rootbody = bytearray(rlen)
    for i, n in enumerate(files):
        data, typ, ds, extra = read_source(os.path.join(a.src, n))
        qname = n.encode("latin-1")
        assert len(qname) <= 36, n
        body = bytes(64) + data
        first = alloc(len(body))
        write_chain(first, body)
        e = struct.pack(">IBBII", len(body), 0, typ, ds, extra) + struct.pack(">H", len(qname))
        e += qname.ljust(36, b"\0") + struct.pack(">IHHI", now & 0xffffffff, 1, first, 0)
        assert len(e) == 64
        rootbody[64 + 64 * i:128 + 64 * i] = e
        print("  %-14s %7d bytes  type %d  dataspace %d  groups from %d" % (n, len(data), typ, ds, first))
    write_chain(root, bytes(rootbody))

    free_first = nxt if nxt < ngroup else 0
    for g in range(nxt, ngroup - 1):
        mp[g] = g + 1
    if nxt < ngroup:
        mp[ngroup - 1] = 0
    name = a.name.encode("latin-1")[:20]
    hdr = b"QLWA" + struct.pack(">H", len(name)) + name.ljust(20, b" ")
    hdr += struct.pack(">HHHHHHHHHHHHHHI", 0, now & 0xffff, 0, 0, SCTG, 0, 0, 0, ngroup,
                       ngroup - nxt, sctmap, 1, free_first, root, rlen)
    hdr += struct.pack(">IH", 0, 0)
    assert len(hdr) == 64
    hm = hdr + b"".join(struct.pack(">H", x) for x in mp)
    write_chain(0, hm)
    try:
        open(a.out, "wb").write(img)
    except PermissionError:         # mounted in an emulator: as mkrelease.py does for the .mdv
        root_, ext = os.path.splitext(a.out)
        print("WARNING: %s is in use (mounted in an emulator?)" % a.out)
        a.out = root_ + "_new" + ext
        open(a.out, "wb").write(img)
    print("%s: %d KB, %d groups of %d bytes, %d free (%d KB)"
          % (a.out, len(img) // 1024, ngroup, G, ngroup - nxt, (ngroup - nxt) * G // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The release package (build_release.sh, docs/release.md) from the assembled jobs in build/rel:

  release/abadia.mdv      a microdrive cartridge image (QLay format: Q-emuLator mounts it)
                                with BOOT, abadia_title and abadia (QDOS file headers on the tape)
  release/win/            the same three files for a hard disk / floppy / emulator folder:
                                the two jobs carry Q-emuLator's 30-byte "]!QDOS File Header"
                                (Q-emuLator, QPC2 and sQLux read it; copying them to a real
                                floppy through any of them keeps the job type and dataspace)

The jobs' dataspace (in the QDOS header):
  abadia        DEST + NEED + 1024 + 512 - file length: the area must reach past the game's BSS
                (NEED, mkimage.py's RESPR figure, from DEST: where rel_main.s unpacks it) plus the
                QDOS job stack (the stub checks the same figure at run time)
  abadia_title  512 (the ZX0 decoder's stack)

  mkrelease.py --need N [--interleave 9]
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mkmdv

REL = os.path.join(QL, "build", "rel")
OUT = os.path.join(QL, "release")
STACK_KEEP = 1024


def qemulator_header(typ, dataspace, extra=0):
    """Q-emuLator's header prefix for files in a host folder: the ID, 0, the length in words
    (15 = 30 bytes), then bytes 4..13 of the QDOS header (access, type, dataspace, extra)."""
    return b"]!QDOS File Header" + bytes([0, 15]) + struct.pack(">BBII", 0, typ, dataspace, extra)


def boot(dev):
    # LF line endings (SuperBASIC); MODE 8 first (it clears the screen), then the picture job,
    # then the game: the picture is up while QDOS loads the game file.
    return ("10 dev$=\"%s\"\n"
            "20 MODE 8: EXEC_W dev$&\"abadia_title\": EXEC_W dev$&\"abadia\"\n"
            "30 MODE 4\n" % dev).encode("latin-1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--need", type=int, required=True, help="mkimage.py's RESPR figure for abadia_r_bin")
    ap.add_argument("--interleave", type=int, default=9)
    a = ap.parse_args()
    game = open(os.path.join(REL, "abadia"), "rb").read()
    title = open(os.path.join(REL, "abadia_title"), "rb").read()
    apl = open(os.path.join(REL, "abadia_r.apl"), "rb").read()
    dest = game.find(apl)
    assert dest > 0 and game.find(apl, dest + 1) < 0 and dest % 4 == 0, dest
    ds_game = dest + a.need + STACK_KEEP + 512 - len(game)
    ds_game = (ds_game + 15) & ~15
    ds_title = 512
    files = [("BOOT", boot("mdv1_"), 0, 0),
             ("abadia_title", title, 1, ds_title),
             ("abadia", game, 1, ds_game)]
    os.makedirs(os.path.join(OUT, "win"), exist_ok=True)
    img, info = mkmdv.build(files, "ABADIA", interleave=a.interleave)
    try:
        open(os.path.join(OUT, "abadia.mdv"), "wb").write(img)
    except PermissionError:
        # the image is open in an emulator (the author's own session: never closed by a tool)
        alt = os.path.join(OUT, "abadia_new.mdv")
        open(alt, "wb").write(img)
        print("WARNING: release/abadia.mdv is in use (mounted in an emulator?): written to %s" % alt)
    # host folders (Q-emuLator headers), one per drive: BOOT names the drive the files are on, so
    # copy the folder that matches (release/mdv to a real cartridge, release/flp to a floppy)
    for folder, dev in (("win", "win1_"), ("mdv", "mdv1_"), ("flp", "flp1_")):
        os.makedirs(os.path.join(OUT, folder), exist_ok=True)
        open(os.path.join(OUT, folder, "BOOT"), "wb").write(boot(dev))
        open(os.path.join(OUT, folder, "abadia_title"), "wb").write(qemulator_header(1, ds_title) + title)
        open(os.path.join(OUT, folder, "abadia"), "wb").write(qemulator_header(1, ds_game) + game)
    # the cartridge read back: every file, header and checksum
    p = mkmdv.parse(img)
    assert not p["bad_checksums"]
    for (n, d, t, ds), f in zip(files, p["files"]):
        assert (f["name"], f["data"], f["type"], f["dataspace"]) == (n, d, t, ds) and f["hdr_ok"], n
    print("abadia        %6d bytes (stub %d + aPLib %d), dataspace %d, job area %d" % (len(game), dest, len(apl), ds_game, len(game) + ds_game))
    print("abadia_title  %6d bytes, dataspace %d" % (len(title), ds_title))
    for (n, d, t, ds) in files:
        print("  %-13s %3d sectors" % (n, (len(d) + 64 + 511) // 512))
    u = info["used"]
    print("abadia.mdv: %d sectors used (map + directory + files); free: %d of 200, %d of 220, %d of 255"
          % (u, 200 - u, 220 - u, 255 - u))
    # the cartridge once the game has saved on it (MDV1_, the default device; home is MDV1_ too,
    # so the settings file goes there as well): a save of up to 960 bytes takes 2 sectors with
    # its QDOS header (measured saves: ~470-490 bytes), the settings file 1
    with_save = files + [("abadia_sav", bytes(960), 0, 0), ("abadia_cfg", bytes(16), 0, 0)]
    _, info2 = mkmdv.build(with_save, "ABADIA", interleave=a.interleave)
    u2 = info2["used"]
    print("with a save (abadia_sav, up to 960 bytes) and the settings file: %d sectors used; free: %d of 200, "
          "%d of 220, %d of 255" % (u2, 200 - u2, 220 - u2, 255 - u2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Changes the settings of a RELEASE package without rebuilding it (docs/release.md).

The game job (abadia) has a settings block at a fixed offset of the FILE (src/release/rel_main.s,
+16 from the job's start, after the job name), which the job copies into the game's header
after unpacking:
  +16 "ABCF"
  +20 sound: 0 detect QSound, 1 off (the beeper), 2 force QSound    -> header +28
  +21 flags: bit 1 skip the intro                                    -> header +31
  +22 the start-up save device: a QDOS string (its part up to the first _) -> header +1312;
      used only when no settings file abadia_cfg is found (docs/release.md)

  relpatch.py TARGET [--sound detect|off|force] [--save mdv2_abadia_sav] [--intro on|off]

TARGET is the abadia file (plain, or with Q-emuLator's "]!QDOS File Header" as in
release/win/) or a cartridge image (.mdv: the file is patched and the sectors rewritten
with their checksums, the layout kept). Without options it shows the current settings.
"""
import argparse, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mkmdv

SOUND = {"detect": 0, "off": 1, "force": 2}
CFG = 16


def show(code):
    assert code[CFG:CFG + 4] == b"ABCF", "not the release game job (no settings block)"
    n = struct.unpack(">H", code[CFG + 6:CFG + 8])[0]
    return dict(sound=[k for k, v in SOUND.items() if v == code[CFG + 4]][0],
                intro="off" if code[CFG + 5] & 2 else "on",
                save=code[CFG + 8:CFG + 8 + n].decode("latin-1"))


def patch(code, a):
    c = bytearray(code)
    show(code)
    if a.sound:
        c[CFG + 4] = SOUND[a.sound]
    if a.intro:
        c[CFG + 5] = (c[CFG + 5] & ~2) | (2 if a.intro == "off" else 0)
    if a.save is not None:
        nb = a.save.encode("latin-1")
        if not 1 <= len(nb) <= 40:
            raise SystemExit("the save file name must have 1 to 40 characters")
        c[CFG + 6:CFG + 48] = struct.pack(">H", len(nb)) + nb.ljust(40, b"\0")
    return bytes(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--sound", choices=sorted(SOUND))
    ap.add_argument("--save")
    ap.add_argument("--intro", choices=("on", "off"))
    a = ap.parse_args()
    data = open(a.target, "rb").read()
    change = a.sound or a.save is not None or a.intro
    if a.target.lower().endswith(".mdv"):
        p = mkmdv.parse(data)
        files = [(f["name"], f["data"], f["type"], f["dataspace"]) for f in p["files"]]
        k = [i for i, f in enumerate(files) if f[0] == "abadia"][0]
        print("before:", show(files[k][1]))
        if change:
            files[k] = (files[k][0], patch(files[k][1], a), files[k][2], files[k][3])
            il = p["dir_sector"] - p["files"][0]["sectors"][0]
            img, _ = mkmdv.build(files, p["medium"].strip(), good=p["good"], rnd=p["random"], interleave=il)
            open(a.target, "wb").write(img)
            print("after: ", show(files[k][1]))
        return 0
    off = 30 if data[:18] == b"]!QDOS File Header" else 0
    print("before:", show(data[off:]))
    if change:
        new = data[:off] + patch(data[off:], a)
        open(a.target, "wb").write(new)
        print("after: ", show(new[off:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

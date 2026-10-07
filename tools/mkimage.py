#!/usr/bin/env python3
"""Turns the linked hybrid ELF (linked at 0 with --emit-relocs) into the QL load image.

  image = objcopy'd binary (text..data) + relocation table
  table = dc.l count, then dc.l offset for every R_68K_32 against a relocatable symbol

Checks (any failure aborts the build):
  - every relocated longword is at an EVEN offset (68008 address error otherwise)
  - no absolute 16/8-bit relocation against a relocatable symbol (would be silently wrong)
  - the image starts with the 'ABQL' header

Also writes the SuperBASIC loader (LF line endings, default device win1_) reserving
max(image + table, image + BSS) bytes, rounded up to even, and a symbol map for the harness.
"""
import argparse, os, struct, sys

R_68K_32, R_68K_16, R_68K_8 = 1, 2, 3
R_68K_PC32, R_68K_PC16, R_68K_PC8 = 4, 5, 6
SHN_UNDEF, SHN_ABS = 0, 0xfff1


class Elf:
    def __init__(self, data):
        self.d = data
        assert data[:4] == b"\x7fELF" and data[4] == 1 and data[5] == 2, "need ELF32 big-endian"
        (self.e_shoff,) = struct.unpack_from(">I", data, 0x20)
        self.e_shentsize, self.e_shnum, self.e_shstrndx = struct.unpack_from(">HHH", data, 0x2e)
        self.sh = []
        for i in range(self.e_shnum):
            o = self.e_shoff + i * self.e_shentsize
            name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from(">IIIIIIIIII", data, o)
            self.sh.append(dict(name=name, type=typ, flags=flags, addr=addr, off=off, size=size,
                                link=link, info=info, entsize=entsize))
        strtab = self.sh[self.e_shstrndx]
        for s in self.sh:
            s["sname"] = self.cstr(strtab["off"] + s["name"])

    def cstr(self, o):
        e = self.d.index(b"\0", o)
        return self.d[o:e].decode("latin-1")

    def section(self, name):
        for s in self.sh:
            if s["sname"] == name:
                return s
        return None

    def symbols(self):
        st = self.section(".symtab")
        strs = self.sh[st["link"]]
        out = []
        for i in range(st["size"] // 16):
            name, value, size, info, other, shndx = struct.unpack_from(">IIIBBH", self.d, st["off"] + i * 16)
            out.append(dict(name=self.cstr(strs["off"] + name), value=value, size=size, info=info, shndx=shndx))
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("raw", help="objcopy -O binary output")
    ap.add_argument("out", help="QL image (raw + relocation table)")
    ap.add_argument("--loader", help="SuperBASIC loader to write")
    ap.add_argument("--map", help="symbol map to write (name hex-offset)")
    ap.add_argument("--binname", default="abadia_h_bin")
    a = ap.parse_args()

    elf = Elf(open(a.elf, "rb").read())
    raw = open(a.raw, "rb").read()
    syms = elf.symbols()
    byname = {s["name"]: s for s in syms if s["name"]}
    image_end = byname["__image_end"]["value"]
    bss_end = byname["__bss_end"]["value"]
    assert len(raw) == image_end, "objcopy size %d != __image_end %d" % (len(raw), image_end)
    assert raw[4:8] == b"ABQL", "missing ABQL header at +4"

    relocs = set()
    errors = []
    for s in elf.sh:
        if s["type"] != 4:          # SHT_RELA
            continue
        target = elf.sh[s["info"]]
        if not (target["flags"] & 2):   # SHF_ALLOC
            continue
        for i in range(s["size"] // 12):
            off, info, addend = struct.unpack_from(">IIi", elf.d, s["off"] + i * 12)
            typ = info & 0xff
            sym = syms[info >> 8]
            if typ in (R_68K_PC32, R_68K_PC16, R_68K_PC8, 0):
                continue
            if sym["shndx"] == SHN_ABS:
                continue
            if sym["shndx"] == SHN_UNDEF:
                errors.append("undefined symbol %s in reloc at %06x" % (sym["name"], off))
                continue
            if typ == R_68K_32:
                if off >= image_end:
                    errors.append("reloc outside image at %06x (%s)" % (off, target["sname"]))
                elif off & 1:
                    errors.append("ODD relocation offset %06x (%s, sym %s)" % (off, target["sname"], sym["name"]))
                else:
                    relocs.add(off)
            else:
                errors.append("absolute %d-bit relocation at %06x against %s (%s)"
                              % (16 if typ == R_68K_16 else 8, off, sym["name"], target["sname"]))
    if errors:
        for e in errors[:40]:
            print("mkimage ERROR:", e)
        print("mkimage: %d errors" % len(errors))
        return 1

    relocs = sorted(relocs)
    table = struct.pack(">I", len(relocs)) + b"".join(struct.pack(">I", r) for r in relocs)
    image = raw + table
    open(a.out, "wb").write(image)
    need = max(len(image), bss_end)
    need = (need + 1) & ~1
    print("image %d bytes (+%d reloc table, %d relocs), BSS to %d -> RESPR(%d)"
          % (len(raw), len(table), len(relocs), bss_end, need))

    if a.loader:
        lines = [
            "100 REMark La Abadia del Crimen - QL port, hybrid build (asm + compiled C++)",
            "110 REMark generated by tools/mkimage.py - image %d bytes, needs %d" % (len(image), need),
            '120 dev$="win1_"',
            # loading screen (loadscreen/A4S_scr, the author's choice, copied to abadia_scr by
            # build_hybrid.sh): shown in Mode 8 while the game image loads; the game's own
            # MT.DMODE/clear replaces it when it starts
            '125 MODE 8: LBYTES dev$&"abadia_scr",131072',
            "130 a=RESPR(%d)" % need,
            '140 LBYTES dev$&"%s",a' % a.binname,
            "145 REMark sound: add POKE a+28,1 for no QSound, POKE a+28,2 to force it (default: detect)",
            "146 REMark diagnostics: add POKE a+29,1 for the heartbeat blocks at the bottom of the screen",
            # the save file (header +1312, QDOS string, up to 40 characters; the image's default
            # is mdv2_abadia_sav): the dev loader saves beside the game, on dev$
            '147 s$=dev$&"abadia_sav": POKE_W a+1312,LEN(s$): FOR i=1 TO LEN(s$): POKE a+1313+i,CODE(s$(i))',
            "150 CALL a",
            "160 MODE 4",
        ]
        with open(a.loader, "w", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    if a.map:
        with open(a.map, "w", newline="\n") as fh:
            for s in sorted(syms, key=lambda s: s["value"]):
                if s["name"] and s["shndx"] not in (SHN_UNDEF, SHN_ABS) and not s["name"].startswith("."):
                    fh.write("%s %06x %d %d\n" % (s["name"], s["value"], s["size"], s["info"] & 0xf))
    return 0


if __name__ == "__main__":
    sys.exit(main())

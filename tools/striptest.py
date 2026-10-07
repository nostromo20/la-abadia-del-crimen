#!/usr/bin/env python3
"""The text strip under the panel (QL lines 228-255, cpp/port/ql_strip.cpp) and the save device,
in the QL harness: every state of the strip is read back from the QL screen and compared,
pixel for pixel, with the text rendered here from the game's font (roms 0xb400, the same
mapping and the extra glyphs), then saved as a PNG in build/striptest/.

The harness file emulation (qlrun) plays the drives: Runner.devices (drives with a medium),
Runner.readonly (write-protected), Runner.files (what is on them).

  striptest.py      exit 1 on any failure
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qlrun, pngout

# every trap #2/#3 first goes to the runner's open_cb (if any), then to the file emulation
_orig_trap23 = qlrun.Runner.on_trap23


def _trap23(self, mu, addr, size, data):
    cb = getattr(self, "open_cb", None)
    if cb:
        cb(mu, addr)
    _orig_trap23(self, mu, addr, size, data)


qlrun.Runner.on_trap23 = _trap23

OUT = os.path.join(QL, "build", "striptest")
ROMS = open(os.path.join(QL, "build", "roms.bin"), "rb").read()[0x4000:]
GLYPHS = {"W": [0x00, 0x66, 0xe6, 0xc6, 0xd6, 0xd6, 0xfe, 0x66],
          "-": [0x00, 0x00, 0x00, 0x00, 0x3e, 0x7c, 0x00, 0x00],
          "/": [0x00, 0x03, 0x06, 0x0c, 0x18, 0x30, 0x60, 0xc0],
          "_": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe],
          " ": [0] * 8}
RED, WHITE = 2, 7
fails = []


def glyph(c):
    c = c.upper()
    if c in GLYPHS:
        return GLYPHS[c]
    o = {",": 0x3c, ".": 0x3d}.get(c, ord(c))
    assert 0x30 <= o <= 0x5a, c
    return list(ROMS[0xb400 + 8 * (o - 0x2d):][:8])


def expected(lines):
    """28 x 256 pixel booleans for 1 line (middle) or 3 lines of text"""
    rows = [[False] * 256 for _ in range(28)]
    ls = [None, lines[0], None] if len(lines) == 1 else lines
    for k, t in enumerate(ls):
        if not t:
            continue
        x0 = (256 - 8 * len(t)) // 2
        for i, ch in enumerate(t):
            g = glyph(ch)
            for r in range(8):
                for b in range(8):
                    if g[r] & (0x80 >> b):
                        rows[2 + 8 * k + r][x0 + 8 * i + b] = True
    return rows


def strip_of(screen):
    return pngout.ql_mode8_to_indices(screen)[228:256]


def check_strip(name, screen, lines, colour=RED, png=True):
    got = strip_of(screen)
    exp = expected(lines) if lines else [[False] * 256 for _ in range(28)]
    bad = 0
    for y in range(28):
        for x in range(256):
            want = colour if exp[y][x] else 0
            if got[y][x] != want:
                bad += 1
    ok = bad == 0
    if png:
        slug = "".join(c if c.isalnum() else "_" for c in name).strip("_")
        pngout.ql_rows_to_png(os.path.join(OUT, slug + ".png"), pngout.ql_mode8_to_indices(screen), 2)
    print("%-4s %-46s %s" % ("ok" if ok else "FAIL", name, " | ".join(lines) if lines else "(empty)")
          + ("" if ok else "   (%d pixels differ)" % bad))
    if not ok:
        fails.append(name)
    return ok


def runner(lines, savename="win1_abadia_sav", env=None, files=None, devices=None, readonly=(), intro=False):
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    script = os.path.join(QL, "build", "tmp", "striptest_script.txt")
    open(script, "w").write("\n".join("%d %d %s" % l for l in lines) + "\n")
    for k in ("INTRO", "QEMU_KEYS", "FORCE_NIGHT", "FORCE_MIRROR", "SAVENAME"):
        os.environ.pop(k, None)
    os.environ["SAVENAME"] = savename
    if intro:
        os.environ["INTRO"] = "1"
    os.environ.update(env or {})
    r = qlrun.Runner(image, syms, qlrun.BASE, qlrun.load_script(script), realq=True, sv164=0xC1000)
    r.files.update(files or {})
    if devices is not None:
        r.devices = set(devices)
    r.readonly = set(readonly)
    shots = {}
    r.png_ticks = set()

    def cb(rr):
        if rr.tick in rr.png_ticks:
            shots[rr.tick] = rr.screen()
    r.tick_cb = cb
    # the screen at the moment a save/load file is opened (the "...ING" message must be up)
    opens = []

    def open_cb(mu, addr):
        if addr == r.base + r.syms["do_trap2"] and mu.reg_read(qlrun.M.UC_M68K_REG_D0) & 0xff == 1:
            nm = r.qstr(mu.reg_read(qlrun.M.UC_M68K_REG_A0)).lower()
            if nm.endswith("abadia_sav") or nm.endswith("abadia_cfg"):
                opens.append((r.tick, nm, mu.reg_read(qlrun.M.UC_M68K_REG_D3) & 0xff, r.screen()))
    r.open_cb = open_cb
    return r, shots, opens


def help_lines(dev):
    """the F5 help (2026-10-05 wording): line 1 is 31 characters with any 5-character device"""
    return ["F1-SAVE F2-LOAD F3-DEVICE:" + dev, "ARROW L/R-TURN UP-WALK DOWN-ADSO", "SPACE-DROP ITEM F5-HIDE"]


def glyph_sheet():
    """the added glyphs ('-' '/' '_', and the fork's W) beside the font's own, 8x scale"""
    text = "F5-HELP S/N RAM1_ WAVE AZ019:,."
    w = 8 * len(text)
    rows = [[0] * w for _ in range(12)]
    for i, ch in enumerate(text):
        g = glyph(ch)
        own = ch in GLYPHS and ch != " "
        for r in range(8):
            for b in range(8):
                if g[r] & (0x80 >> b):
                    rows[2 + r][8 * i + b] = 6 if own else 7     # added: yellow, the font: white
    pngout.ql_rows_to_png(os.path.join(OUT, "glyphs_added_yellow.png"), rows, 8)


def main():
    os.makedirs(OUT, exist_ok=True)
    glyph_sheet()
    walk = [(5, 5, "LEFT"), (6, 40, "UP")]

    HELP_W = help_lines("WIN1_")

    # 1. F5-HELP for the first ~5 s of play, then blank; F5 shows and hides the help; day/night colours
    r, shots, _ = runner(walk + [(50, 50, "F5"), (60, 60, "F5")])
    r.png_ticks = {20, 45, 54, 64}
    r.run(66)
    check_strip("F5-HELP (day, start of play)", shots[20], ["F5-HELP"])
    check_strip("blank after ~5 s of play", shots[45], [])
    check_strip("help (F5)", shots[54], HELP_W)
    check_strip("help hidden (F5 again): blank", shots[64], [])
    states_f5 = r.states[:66]
    r0, s0, _ = runner(walk)
    r0.png_ticks = set()
    r0.run(66)
    same = states_f5 == r0.states[:66]
    print("%-4s F5 changes no game state (66 steps)" % ("ok" if same else "FAIL"))
    if not same:
        fails.append("F5 state")
    r, shots, _ = runner(walk + [(30, 30, "F5")], env={"FORCE_NIGHT": "1"})
    r.png_ticks = {20, 34}
    r.run(40)
    check_strip("F5-HELP (night)", shots[20], ["F5-HELP"], colour=WHITE)
    check_strip("help (night)", shots[34], HELP_W, colour=WHITE)
    # the default device, with no settings file and an empty header field: MDV1_
    r, shots, _ = runner(walk + [(10, 10, "F5")], savename="")
    r.png_ticks = {14}
    r.run(16)
    check_strip("help on the default MDV1_", shots[14],
                help_lines("MDV1_"))

    # 2. F3 through every device (from the header's WIN1_), then the help shows the device chosen
    order = ["WIN2_", "RAM1_", "MDV1_", "MDV2_", "FLP1_", "FLP2_", "WIN1_"]
    presses = [10 + 20 * i for i in range(len(order))]
    r, shots, _ = runner(walk + [(t, t, "F3") for t in presses] + [(160, 160, "F5"), (170, 170, "F3")],
                         files={"win1_abadia_h_bin": b"x"})
    r.png_ticks = {t + 2 for t in presses} | {t + 19 for t in presses[:1]} | {164, 190}
    r.run(192)
    for t, d in zip(presses, order):
        check_strip("F3 %s" % d, shots[t + 2], ["SAVE DEVICE: %s" % d])
    check_strip("F3 message gone after ~2 s: blank", shots[presses[0] + 19], [])
    check_strip("help after F3 (WIN1_)", shots[164], HELP_W)
    check_strip("a message ends while the help is up: the help", shots[190],
                help_lines("WIN2_"))

    # 3. save / load messages
    def saveload(name, key, savename, files=None, devices=None, readonly=(), want_busy=None, want=None):
        r, shots, opens = runner(walk + [(30, 30, key)], savename=savename, files=files, devices=devices, readonly=readonly)
        r.png_ticks = {33}
        r.run(36)
        o = [x for x in opens if x[1].endswith("abadia_sav")]
        if want_busy:
            if o:
                check_strip(name + " (during the file call)", o[0][3], [want_busy])
            else:
                print("FAIL %s: no file call" % name)
                fails.append(name)
        check_strip(name, shots[33], [want])
        return r
    r = saveload("F1 save OK", "F1", "win1_abadia_sav", want_busy="SAVING TO WIN1_...", want="GAME SAVED")
    saved = r.files.get("win1_abadia_sav", b"")
    import savefmt
    nv = len(savefmt.values_of_compact(saved))
    nt = len(savefmt.values_of_text(open(os.path.join(QL, "tests", "arch28_sav.txt"), "rb").read()))
    print("%-4s the save holds the same %d values as an old text save (%d): no value from a comment line"
          % ("ok" if nv == nt else "FAIL", nv, nt))
    if nv != nt:
        fails.append("save values")
    ok = saved[:5] == b"ABQS\x01" and len(saved) + 64 <= 3 * 512
    print("%-4s the save: compact format, %d bytes (+ the 64-byte QDOS header: %d sectors; the old text save: 14)"
          % ("ok" if ok else "FAIL", len(saved), (len(saved) + 64 + 511) // 512))
    if not ok:
        fails.append("save size")
    saveload("F1 write-protected WIN1_", "F1", "win1_abadia_sav", readonly={"win1_"},
             want_busy="SAVING TO WIN1_...", want="WIN1_ IS WRITE PROTECTED")
    saveload("F1 write-protected MDV1_", "F1", "", readonly={"mdv1_"},
             want_busy="SAVING TO MDV1_...", want="MDV1_ IS WRITE PROTECTED")
    saveload("F1 no cartridge in MDV2_", "F1", "mdv2_abadia_sav",
             devices={"win1_", "mdv1_"}, want_busy="SAVING TO MDV2_...", want="INSERT MDV2_ SAVE CARTRIDGE")
    rw, shots, _ = runner(walk + [(30, 30, "F1")])
    rw.fail_write = True
    rw.png_ticks = {33}
    rw.run(36)
    check_strip("F1 write error (drive full)", shots[33], ["SAVE FAILED: WIN1_"])
    saveload("F2 load OK (compact round trip)", "F2", "win1_abadia_sav", files={"win1_abadia_sav": saved},
             want_busy="LOADING FROM WIN1_...", want="GAME LOADED")
    saveload("F2 no saved game", "F2", "win1_abadia_sav", want_busy="LOADING FROM WIN1_...",
             want="NO SAVED GAME ON WIN1_")
    saveload("F2 no cartridge in MDV2_", "F2", "mdv2_abadia_sav", devices={"win1_"},
             want_busy="LOADING FROM MDV2_...", want="INSERT MDV2_ SAVE CARTRIDGE")
    old_text = open(os.path.join(QL, "tests", "arch28_sav.txt"), "rb").read()
    saveload("F2 old text-format save", "F2", "win1_abadia_sav", files={"win1_abadia_sav": old_text},
             want_busy="LOADING FROM WIN1_...", want="LOAD FAILED")
    saveload("F2 corrupt save", "F2", "win1_abadia_sav", files={"win1_abadia_sav": saved[:200]},
             want_busy="LOADING FROM WIN1_...", want="LOAD FAILED")
    # a rejected save leaves the game as it was: put back from a snapshot taken just before, so
    # the states equal a save + load round trip at the same step (F1 and F2 together)
    rt, _, _ = runner(walk + [(30, 30, "F1"), (30, 30, "F2")])
    rt.run(50)
    for what, data in (("old text save", old_text), ("truncated save", saved[:200])):
        rc, _, _ = runner(walk + [(30, 30, "F2")], files={"win1_abadia_sav": data})
        rc.run(50)
        same = rc.states[:50] == rt.states[:50]
        print("%-4s %s rejected: the game state is the one before the load (50 steps)" % ("ok" if same else "FAIL", what))
        if not same:
            fails.append("restore " + what)
    r, shots, _ = runner(walk + [(30, 30, "F1")])
    r.png_ticks = {50, 60}
    r.run(62)
    check_strip("save message gone after ~2.6 s: blank", shots[60], [])

    # 4. the settings file across runs: WIN1_ chosen (home WIN1_), then MDV2_; highest counter wins
    files = {"win1_abadia_h_bin": b"x"}
    r, _, opens = runner(walk + [(10, 10, "F3"), (12, 12, "F3"), (14, 14, "F3"), (16, 16, "F3")],
                         savename="", files=files)                 # MDV1_ -> MDV2_ FLP1_ FLP2_ WIN1_
    r.run(40)
    c1 = r.files.get("win1_abadia_cfg", b"")
    w = [(o[0], o[1]) for o in opens if o[1].endswith("abadia_cfg") and o[2] == 2]
    ok = c1[:4] == b"ABDV" and struct.unpack(">I", c1[4:8])[0] == 1 and c1[8:9 + c1[8]] == b"\x05win1_" \
        and len(w) == 1 and w[0][0] >= 16 + 14
    print("%-4s run 1: F3 x4 to WIN1_ -> ONE write %s, ~2 s after the last F3 (step 16): win1_abadia_cfg, "
          "counter 1, device win1_ (%s)" % ("ok" if ok else "FAIL", w, c1.hex()))
    if not ok:
        fails.append("cfg run 1")
    files = dict(r.files)
    r, shots, opens = runner(walk + [(20, 20, "F1"), (30, 30, "F3"), (32, 32, "F3"), (34, 34, "F3"), (36, 36, "F3")],
                             savename="", files=files)              # starts on WIN1_; -> WIN2_ RAM1_ MDV1_ MDV2_
    r.run(60)
    sv = [o[1] for o in opens if o[1].endswith("abadia_sav") and o[2] == 2]
    c2 = r.files.get("mdv2_abadia_cfg", b"")
    ok = sv == ["win1_abadia_sav"] and c2[:4] == b"ABDV" and struct.unpack(">I", c2[4:8])[0] == 2 \
        and c2[8:9 + c2[8]] == b"\x05mdv2_"
    print("%-4s run 2: starts on WIN1_ (F1 saved to %s); F3 to MDV2_ -> mdv2_abadia_cfg, counter 2"
          % ("ok" if ok else "FAIL", sv))
    if not ok:
        fails.append("cfg run 2")
    files = dict(r.files)
    r, shots, opens = runner(walk + [(20, 20, "F1"), (24, 24, "F5")], savename="win2_abadia_sav", files=files)
    r.png_ticks = {28}
    r.run(30)
    sv = [o[1] for o in opens if o[1].endswith("abadia_sav") and o[2] == 2]
    ok = sv == ["mdv2_abadia_sav"]
    print("%-4s run 3: both files (win1_ counter 1, mdv2_ counter 2): MDV2_ wins over the header's WIN2_ (F1 saved to %s)"
          % ("ok" if ok else "FAIL", sv))
    if not ok:
        fails.append("cfg run 3")
    check_strip("help on MDV2_ (from the settings file)", shots[28],
                help_lines("MDV2_"))

    # 5. the settings file cannot be written
    r, shots, _ = runner(walk + [(10, 10, "F3"), (12, 12, "F3")], savename="", files={"win1_abadia_h_bin": b"x"},
                         readonly={"win1_"})                      # MDV1_ -> MDV2_ -> FLP1_: to home WIN1_
    r.png_ticks = {30}
    r.run(32)
    check_strip("settings: home write-protected", shots[30], ["WIN1_ IS WRITE PROTECTED"])
    r, shots, _ = runner(walk + [(10, 10, "F3"), (12, 12, "F3")], savename="", files={"win1_abadia_h_bin": b"x"},
                         devices={"win1_", "mdv1_", "mdv2_", "flp1_"})
    r.fail_write = True                                           # the write itself fails (drive full)
    r.png_ticks = {30}
    r.run(32)
    check_strip("settings not saved (write error)", shots[30], ["SETTING NOT SAVED"])
    r, shots, _ = runner(walk + [(10, 10, "F3")], savename="ram1_abadia_sav",
                         devices={"win1_", "ram1_"})               # RAM1_ -> MDV1_ (no home): no cartridge
    r.png_ticks = {28}
    r.run(30)
    check_strip("settings: no cartridge in MDV1_", shots[28], ["INSERT MDV1_ SAVE CARTRIDGE"])
    r, shots, _ = runner(walk + [(10, 10, "F3")], savename="mdv1_abadia_sav", readonly={"mdv2_"})
    r.png_ticks = {28}                                            # MDV1_ -> MDV2_: settings to MDV2_
    r.run(30)
    check_strip("settings: MDV2_ write-protected", shots[28], ["MDV2_ IS WRITE PROTECTED"])
    # no drive at all answers: start-up probing and the game go on
    r, shots, _ = runner(walk + [(20, 20, "F1")], savename="", devices=set())
    r.png_ticks = {23}
    r.run(25)
    ok = r.stop_reason == "tick limit"
    print("%-4s no drive at all: start-up and F1 do not stop the game (%s)" % ("ok" if ok else "FAIL", r.stop_reason))
    if not ok:
        fails.append("no drives")
    check_strip("F1 with no drive at all (MDV1_)", shots[23], ["INSERT MDV1_ SAVE CARTRIDGE"])

    # 6. the intro parchment: PRESS SPACE in red once the page is up; gone in the game
    r, shots, _ = runner([(200, 200, "SPACE")], intro=True)
    r.png_ticks = {5, 150, 230}
    r.run(232)
    check_strip("intro: PRESS SPACE TO CONTINUE", shots[150], ["PRESS SPACE TO CONTINUE"])
    check_strip("intro ended (SPACE): F5-HELP", shots[230], ["F5-HELP"])

    # 7. the ending parchment: no strip
    r, shots, _ = runner([(5, 5, "F5")])
    r.png_ticks = {20, 120}
    syms = r.syms

    def poke(rr):
        if rr.tick == 30:
            jp = struct.unpack(">I", bytes(rr.mu.mem_read(rr.base + syms["_ZL5juego"], 4)))[0]
            rr.mu.mem_write(jp + 7, b"\x01")          # Juego::enFinal (as romusage.py)
        if rr.tick in rr.png_ticks:
            shots[rr.tick] = rr.screen()
    r.tick_cb = poke
    r.run(122)
    check_strip("ending parchment: no strip", shots[120], [])

    print("STRIP: %d failures (PNGs in %s)" % (len(fails), OUT))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

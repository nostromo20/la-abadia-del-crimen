#!/usr/bin/env python3
"""In-emulator test harness for the hybrid build (header flags and src/qltest.s).

  qltest.py qpc   SCRIPT [--secs N] [--sound 0|1|2] [--diag] [--intro] [--every K] [--end STEP]
  qltest.py sqlux SCRIPT [--rom minerva|js] (same options; no QSound in sQLux)
  qltest.py unicorn SCRIPT (same flags, runs tools/qlrun.py's model; for checking the harness)
  qltest.py decode LOGFILE

The game runs itself: header byte +30 bit 0 makes scan_keyrows read the key script (tests/*.txt
format) from the image's script area, bit 1 makes it rewrite a log file (32-byte records) every
K steps. A freeze therefore leaves the log up to the freeze; the launcher kills the emulator after
--secs (or when the log stops growing for --stall seconds), takes one window screenshot (the
diagnostic heartbeat is at the bottom of the screen), and decodes the log.

QPC2: the author's QPC.INI and WIN containers are NOT touched. The launcher copies the WIN1
container to build/qltest/qpc/test.WIN, replaces its BOOT file there, and starts QPC2 with
-ini build/qltest/qpc/qpc_test.ini (DOS1_ = build/qltest/qpc, file extension conversion off).
The BOOT ends with QPC_EXIT, so a run that reaches its end step closes QPC2 itself.
"""
import argparse, ctypes, os, shutil, struct, subprocess, sys, time
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)

QPC_EXE = qlpaths.QPC_EXE
QPC_INI_SRC = qlpaths.QPC_INI
WIN_SRC = qlpaths.QPC_WIN
SQLUX_DIR = qlpaths.SQLUX_DIR
SQLUX_ROMS = qlpaths.SQLUX_ROMS            # MIN198.rom (Minerva), JS.rom
OUT = os.path.join(QL, "build", "qltest")
KEYS = ["UP", "DOWN", "LEFT", "RIGHT", "SPACE", "Q", "R", "S", "N", "ESC", "F1", "F2", "F3", "F5", "Y"]
SCRIPT_OFF = 288


# ---------------------------------------------------------------- script / log formats
def make_script(path, every, end, logname):
    entries = []
    for raw in open(path):
        raw = raw.split("#")[0].split()
        if len(raw) < 2:
            continue
        mask = 0
        for k in raw[2:]:
            mask |= 1 << KEYS.index(k)
        entries.append((int(raw[0]), int(raw[1]), mask))
    nm = logname.encode("ascii")
    assert len(nm) <= 30
    b = struct.pack(">HHH", every, end, len(nm)) + nm.ljust(30, b"\0")
    for e in entries:
        b += struct.pack(">HHH", *e)
    b += b"\xff\xff"
    assert len(b) <= 1024, "script too long"
    return b


REC = struct.Struct(">IIBBHIBBBBBBBBIHH")


def decode(data, show=12):
    recs = [REC.unpack_from(data, i) for i in range(0, len(data) - 31, 32)]
    if not recs:
        return "log: empty"
    out = ["log: %d records, steps %d..%d" % (len(recs), recs[0][0], recs[-1][0])]
    names = "step frames phase estado keys fault pant gx gy gh go ax ay flags polls silmax beeps"

    def fmt(r):
        return ("step %5d fr %6d ph %02x est %d keys %03x fault %08x pant %02x G %02x,%02x h%02x o%d "
                "abad %02x,%02x fl %x polls %6d silence max %d beeps %d" % r)
    # first records, any change of interest, last records
    lines = []
    prev = None
    for r in recs:
        key = (r[3], r[5], r[6], r[13])
        if prev is None or key != prev:
            lines.append(fmt(r))
        prev = key
    out += lines[:show]
    if len(lines) > show:
        out.append("...")
    out += ["last: " + fmt(r) for r in recs[-3:]]
    last = recs[-1]
    out.append("frames/step at end: %.2f, polls %d vs frames %d, longest main-loop silence %d frames"
               % (last[1] / max(1, last[0]), last[14], last[1], max(r[15] for r in recs)))
    return "\n".join(out)


# ---------------------------------------------------------------- QXL.WIN container BOOT patch
def put_boot(win_path, text):
    """Replace the BOOT file of a QXL.WIN container copy (root directory, single-group file)."""
    d = bytearray(open(win_path, "rb").read())
    assert d[:4] == b"QLWA"
    sctg = struct.unpack(">H", d[0x22:0x24])[0]
    G = sctg * 512
    root = struct.unpack(">H", d[0x34:0x36])[0]
    rlen = struct.unpack(">I", d[0x36:0x3a])[0]
    assert struct.unpack(">H", d[0x40 + 2 * root:0x42 + 2 * root])[0] == 0 and rlen <= G
    body = text.encode("latin-1")
    for i in range(64, rlen, 64):
        e = root * G + i
        nl = struct.unpack(">H", d[e + 14:e + 16])[0]
        if bytes(d[e + 16:e + 16 + nl]).lower() == b"boot":
            fid = struct.unpack(">H", d[e + 58:e + 60])[0]
            assert struct.unpack(">H", d[0x40 + 2 * fid:0x42 + 2 * fid])[0] == 0, "BOOT spans groups"
            assert len(body) + 64 <= G
            d[fid * G + 64:fid * G + G] = body.ljust(G - 64, b"\0")
            struct.pack_into(">I", d, e, len(body) + 64)
            open(win_path, "wb").write(d)
            return
    raise SystemExit("no BOOT in the container")


def boot_text(size, sound, diag, flags, dev):
    lines = [
        "100 REMark Abadia in-emulator test (tools/qltest.py)",
        "110 a=RESPR(%d)" % size,
        '120 LBYTES "%sabadia_h_bin",a' % dev,
        '130 LBYTES "%sscript_bin",a+%d' % (dev, SCRIPT_OFF),
        "140 POKE a+28,%d: POKE a+29,%d: POKE a+30,%d" % (sound, diag, flags),
        # the save file on the dev device (header +1312; the image's default is mdv2_abadia_sav)
        '145 s$="%sabadia_sav": POKE_W a+1312,LEN(s$): FOR i=1 TO LEN(s$): POKE a+1313+i,CODE(s$(i))' % dev,
        "150 CALL a",
    ]
    return lines


def image_size():
    for line in open(os.path.join(QL, "boot_h_bas")):
        if "RESPR(" in line:
            return int(line.split("RESPR(")[1].split(")")[0])
    raise SystemExit("no RESPR in boot_h_bas")


# ---------------------------------------------------------------- window helpers (ctypes)
user32 = ctypes.windll.user32 if os.name == "nt" else None


def window_of(pid):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, lp):
        p = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            found.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def screenshot(pid, path):
    from PIL import ImageGrab
    hwnd = window_of(pid)
    if not hwnd:
        return None
    r = (ctypes.c_long * 4)()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), r)
    user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    time.sleep(0.4)
    try:
        img = ImageGrab.grab(all_screens=True)
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)   # virtual screen origin
        img = img.crop((r[0] - vx, r[1] - vy, r[2] - vx, r[3] - vy))
        img.save(path)
        return path
    except Exception as e:
        print("screenshot failed:", e)
        return None


def click_ok_in_config_dialog(pid, timeout=15):
    """QPC2 shows its configuration dialog at start; press its OK button (BM_CLICK)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        dialogs = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(h, lp):
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(h), ctypes.byref(p))
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(ctypes.c_void_p(h), cls, 64)
            if p.value == pid and cls.value == "#32770" and user32.IsWindowVisible(ctypes.c_void_p(h)):
                dialogs.append(h)
            return True
        user32.EnumWindows(cb, 0)
        for dlg in dialogs:
            ok = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def cb2(h, lp):
                buf = ctypes.create_unicode_buffer(64)
                user32.GetWindowTextW(ctypes.c_void_p(h), buf, 64)
                if buf.value == "&OK":
                    ok.append(h)
                return True
            user32.EnumChildWindows(ctypes.c_void_p(dlg), cb2, 0)
            if ok:
                user32.SendMessageW(ctypes.c_void_p(ok[0]), 0x00F5, 0, 0)   # BM_CLICK
                return True
        time.sleep(0.3)
    return False


def run_emulator(cmd, cwd, logfile, secs, stall, shot, qpc=False):
    if os.path.exists(logfile):
        os.remove(logfile)          # the harness's own output from the previous run
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=cwd)
    last_size, last_change, reason = -1, time.time(), "timeout"
    try:
        if qpc:
            print("config dialog dismissed" if click_ok_in_config_dialog(proc.pid) else "no config dialog seen")
        while True:
            if proc.poll() is not None:
                reason = "emulator exited"
                break
            if time.time() - t0 > secs:
                break
            size = os.path.getsize(logfile) if os.path.exists(logfile) else 0
            if size != last_size:
                last_size, last_change = size, time.time()
            elif size > 0 and time.time() - last_change > stall:
                reason = "log stalled for %ds" % stall
                break
            time.sleep(0.5)
        if proc.poll() is None and shot:
            time.sleep(0.3)
            screenshot(proc.pid, shot)
    finally:
        if proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            proc.wait(timeout=10)
    return reason, time.time() - t0


def prepare(a, dev):
    """test dir with the binary and the script; returns (dir, flags)"""
    d = os.path.join(OUT, a.mode)
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(os.path.join(QL, "abadia_h_bin"), os.path.join(d, "abadia_h_bin"))
    end = a.end
    open(os.path.join(d, "script_bin"), "wb").write(make_script(a.script, a.every, end, dev + "abadia_log"))
    return d


def cmd_qpc(a):
    d = prepare(a, "dos1_")
    win = os.path.join(d, "test.WIN")
    shutil.copyfile(WIN_SRC, win)
    lines = boot_text(image_size(), a.sound, 1 if a.diag else 0, 3, "dos1_")
    lines += ["160 QPC_EXIT"]
    put_boot(win, "\r\n".join(lines) + "\r\n")
    ini = open(QPC_INI_SRC, encoding="latin-1").read()
    rep = {"WIN1=": "WIN1=" + win, "DOS1=": "DOS1=" + d + "\\", "ConvertFileExtension=": "ConvertFileExtension=0",
           "BootFromWIN=": "BootFromWIN=1", "BootFromFLP=": "BootFromFLP=0", "ShowDialog=": "ShowDialog=0"}
    out = []
    for line in ini.splitlines():
        for k, v in rep.items():
            if line.startswith(k):
                line = v
        out.append(line)
    inipath = os.path.join(d, "qpc_test.ini")
    open(inipath, "w", encoding="latin-1").write("\r\n".join(out) + "\r\n")
    logf = os.path.join(d, "abadia_log")
    shot = os.path.join(d, "shot.png")
    if os.path.exists(shot):
        os.remove(shot)
    reason, dt = run_emulator([QPC_EXE, "-ini", inipath], d, logf, a.secs, a.stall, shot, qpc=True)
    report(reason, dt, logf, shot)


def cmd_sqlux(a):
    d = prepare(a, "win1_")
    rom = {"minerva": "MIN198.rom", "js": "JS.rom"}[a.rom]
    bootdir = os.path.join(d, "boot")
    os.makedirs(bootdir, exist_ok=True)
    lines = boot_text(image_size(), a.sound, 1 if a.diag else 0, 3, "win1_")
    lines += ["160 KILL_UQLX"]
    open(os.path.join(bootdir, "BOOT"), "w", newline="\n").write("\n".join(lines) + "\n")
    ini = "\n".join(["SYSROM = %s" % rom, "ROMDIR = %s\\" % SQLUX_ROMS, "RAMTOP = 768", "FAST_STARTUP = 1",
                     "DEVICE = MDV1,%s\\,qdos-like" % bootdir, "DEVICE = WIN1,%s\\,qdos-like" % d,
                     "BOOT_DEVICE = MDV1", "WIN_SIZE = 1x", "SPEED = 1", "SOUND = 0"]) + "\n"
    inipath = os.path.join(d, "sqlux.ini")
    open(inipath, "w").write(ini)
    logf = os.path.join(d, "abadia_log")
    shot = os.path.join(d, "shot.png")
    if os.path.exists(shot):
        os.remove(shot)
    # with no visible desktop (e.g. a remote session): the default SDL video driver still runs
    # (dummy/offscreen are not in this sQLux build); no audio
    os.environ.pop("SDL_VIDEODRIVER", None)
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    reason, dt = run_emulator([os.path.join(SQLUX_DIR, "sqlux.exe"), "-f", inipath], d, logf, a.secs, a.stall, shot)
    report(reason, dt, logf, shot)


def cmd_unicorn(a):
    import qlrun
    d = prepare(a, "win1_")
    image = open(os.path.join(QL, "abadia_h_bin"), "rb").read()
    syms = qlrun.load_symbols(os.path.join(QL, "build", "abadia_h.sym"))
    r = qlrun.Runner(image, syms, qlrun.BASE, [], realq=True, sv164=0xC1000 if a.sound != 1 else 0)
    r.mu.mem_write(qlrun.BASE + SCRIPT_OFF, open(os.path.join(d, "script_bin"), "rb").read())
    r.mu.mem_write(qlrun.BASE + 28, bytes([a.sound, 1 if a.diag else 0, 3, 0 if a.intro else 2]))
    r.run(a.end + 5 if a.end else 3000)
    data = r.files.get("win1_abadia_log", b"")
    open(os.path.join(d, "abadia_log"), "wb").write(data)
    print("unicorn:", r.stop_reason, "steps", r.tick)
    r.report()
    print(decode(data))


def report(reason, dt, logf, shot):
    print("run ended: %s after %.0f s" % (reason, dt))
    if os.path.exists(shot):
        print("screenshot:", shot)
    if os.path.exists(logf):
        print(decode(open(logf, "rb").read()))
    else:
        print("no log file written")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["qpc", "sqlux", "unicorn", "decode"])
    ap.add_argument("script")
    ap.add_argument("--secs", type=int, default=150)
    ap.add_argument("--stall", type=int, default=20)
    ap.add_argument("--sound", type=int, default=0, help="header +28: 0 detect, 1 off, 2 force QSound")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--intro", action="store_true", help="(unicorn only: the emulators always show it)")
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--end", type=int, default=0, help="step from which the autopilot holds ESC")
    ap.add_argument("--rom", default="minerva")
    a = ap.parse_args()
    if a.mode == "decode":
        print(decode(open(a.script, "rb").read()))
        return 0
    {"qpc": cmd_qpc, "sqlux": cmd_sqlux, "unicorn": cmd_unicorn}[a.mode](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())

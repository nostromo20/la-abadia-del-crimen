#!/usr/bin/env python3
"""Drive the author's Q-emuLator with real key presses and read the game's self-log.

Copies a test folder (image + script + loader + BOOT) to build/qltest/qemu, writes a copy of
your .qcf with microdrive slot 1 pointing there (your own .qcf is never touched), starts
Q-emuLator on it, waits for the game, then sends key-down/key-up events with SendInput to the
Q-emuLator window only (every send checks that it is the foreground window), and finally kills
the emulator and decodes build/qltest/qemu/abadia_log.

  qemu_drive.py [--qcf my_config.qcf] [--boot-wait 25] [--plan "UP:2000,wait:1500,LEFT:100,wait:1500,ESC:100,wait:3000"]

A plan item KEY:ms holds KEY down for ms milliseconds; wait:ms just waits.
"""
import argparse, ctypes, os, shutil, subprocess, sys, time
import qlpaths  # local tool paths (tools/qlpaths.py)
from ctypes import wintypes

QL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = qlpaths.QEMULATOR_EXE
TEST = os.path.join(QL, "build", "qltest", "qemu")

user32 = ctypes.WinDLL("user32", use_last_error=True)

# scan codes (set 1); E = extended
KEYS = {"UP": (0x48, True), "DOWN": (0x50, True), "LEFT": (0x4B, True), "RIGHT": (0x4D, True),
        "SPACE": (0x39, False), "ESC": (0x01, False), "F1": (0x3B, False), "F2": (0x3C, False),
        "ENTER": (0x1C, False), "SHIFT": (0x2A, False),
        "W": (0x11, False), "A": (0x1E, False), "D": (0x20, False)}
VK = {"UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "SPACE": 0x20, "ESC": 0x1B,
      "F1": 0x70, "F2": 0x71, "ENTER": 0x0D, "SHIFT": 0x10, "W": 0x57, "A": 0x41, "D": 0x44}

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8


def send_key(name, up):
    scan, ext = KEYS[name]
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0) | (KEYEVENTF_KEYUP if up else 0)
    inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(wVk=VK[name], wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)))
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise OSError("SendInput failed: %d" % ctypes.get_last_error())


def type_text(text):
    """type letters, digits, space and '_' as scan codes (UK/US layout)"""
    sc = {c: v for c, v in zip("1234567890", range(2, 12))}
    sc.update({c: v for c, v in zip("qwertyuiop", range(0x10, 0x1A))})
    sc.update({c: v for c, v in zip("asdfghjkl", range(0x1E, 0x27))})
    sc.update({c: v for c, v in zip("zxcvbnm", range(0x2C, 0x33))})
    sc[" "] = 0x39
    for ch in text:
        shift = ch.isupper() or ch == "_"
        code = 0x0C if ch == "_" else sc[ch.lower()]
        if shift:
            send_key("SHIFT", False)
        for up in (False, True):
            inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(wVk=0, wScan=code,
                        dwFlags=KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0), time=0, dwExtraInfo=0)))
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.03)
        if shift:
            send_key("SHIFT", True)
        time.sleep(0.03)


def windows_of(pid):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            out.append((h, buf.value))
        return True
    user32.EnumWindows(cb, 0)
    return out


def main_window(pid):
    for h, title in windows_of(pid):
        if "QemuLator" in title or "Q-emuLator" in title:
            return h
    w = windows_of(pid)
    return w[0][0] if w else None


def fg_pid():
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(p))
    return p.value


def ensure_foreground(h, pid):
    if fg_pid() == pid:
        return True
    user32.ShowWindow(h, 9)
    # the Alt-key trick lets SetForegroundWindow succeed from a background process
    user32.keybd_event(0x12, 0, 0, 0)
    user32.SetForegroundWindow(h)
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.3)
    return fg_pid() == pid


def prepare(qcf, image, script, log_every, typed_lrun=False, diag=None, sound=None, intro=False, nobeep=False, diag31=0, autopilot=None):
    os.makedirs(TEST, exist_ok=True)
    for f in ("abadia_log",):
        p = os.path.join(TEST, f)
        if os.path.exists(p):
            os.replace(p, p + ".prev")
    shutil.copyfile(image, os.path.join(TEST, "abadia_h_bin"))
    # the loader (test_bas line 105) shows the loading screen first: without it LBYTES fails
    shutil.copyfile(os.path.join(QL, "abadia_scr"), os.path.join(TEST, "abadia_scr"))
    if autopilot:               # keys from a tests/*.txt script inside the game (header +30 bit 0)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import qltest
        open(os.path.join(TEST, "script_bin"), "wb").write(qltest.make_script(autopilot, log_every, 0, "win1_abadia_log"))
        script = os.path.join(TEST, "script_bin")
    b = bytearray(open(script, "rb").read())
    b[0:2] = log_every.to_bytes(2, "big")
    open(os.path.join(TEST, "script_bin"), "wb").write(b)
    import re
    loader = open(os.path.join(QL, "build", "qltest", "user", "test_bas"), "rb").read().decode("latin-1")
    respr = re.search(r"RESPR\(\d+\)", open(os.path.join(QL, "boot_h_bas"), "rb").read().decode("latin-1")).group(0)
    loader = re.sub(r"RESPR\(\d+\)", respr, loader, count=1)   # sized for THIS image
    if diag is not None:        # the heartbeat draws every frame: off for timing runs
        loader, n = re.subn(r"POKE a\+29,\d+", "POKE a+29,%d" % diag, loader)
        assert n == 1, "no POKE a+29 in the loader"
    if sound is not None:       # 0 detect QSound, 1 never use it (beeper music), 2 force it
        loader, n = re.subn(r"POKE a\+28,\d+", "POKE a+28,%d" % sound, loader)
        assert n == 1, "no POKE a+28 in the loader"
    if autopilot:
        loader, n = re.subn(r"POKE a\+30,\d+", "POKE a+30,3", loader)
        assert n == 1, "no POKE a+30 in the loader"
    if "POKE a+31" not in loader:   # the author's loader may run with the intro (no a+31 POKE): add one
        loader, n = re.subn(r"(POKE a\+30,\d+)", r"\1: POKE a+31,0", loader, count=1)
        assert n == 1, "no POKE a+30 in the loader"
    if True:                        # a+31: bit 1 skips the intro parchment, bit 2 = no BEEP IPC,
        v = (0 if intro else 2) | (4 if nobeep else 0) | diag31   # bit 3 no KEYROW, bit 4 no con_ drain
        loader, n = re.subn(r"POKE a\+31,\d+", "POKE a+31,%d" % v, loader)
        assert n == 1, "no POKE a+31 in the loader"
    open(os.path.join(TEST, "test_bas"), "wb").write(loader.encode("latin-1"))
    # QDOS boots mdv1_BOOT (slot 1); it runs the same loader the author runs
    boot = b"10 PRINT 1\n" if typed_lrun else b"10 LRUN win1_test_bas\n"
    open(os.path.join(TEST, "BOOT"), "wb").write(boot)
    lines = open(qcf, "rb").read().decode("latin-1").splitlines()
    lines = ["Slot1=" + TEST if l.startswith("Slot1=") else l for l in lines]
    tq = os.path.join(TEST, "drive.qcf")
    open(tq, "wb").write(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return tq


class Recorder:
    """WASAPI loopback of the default output (pyaudiowpatch), as the PoP sQLux verifier does.
    Records EVERYTHING the machine plays: keep it quiet during the run."""
    def __init__(self, path):
        import pyaudiowpatch as pyaudio
        self.pa = pyaudio.PyAudio()
        lb = self.pa.get_default_wasapi_loopback()
        self.rate, self.ch, self.path, self.chunks = int(lb["defaultSampleRate"]), int(lb["maxInputChannels"]), path, []
        self.t0 = time.time()

        def cb(d, n, t, st):
            self.chunks.append(d)
            return (None, pyaudio.paContinue)
        self.stream = self.pa.open(format=pyaudio.paFloat32, channels=self.ch, rate=self.rate, input=True,
                                   input_device_index=lb["index"], frames_per_buffer=2048, stream_callback=cb)
        self.stream.start_stream()

    def stop(self):
        import array, wave
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()
        f = array.array("f")
        f.frombytes(b"".join(self.chunks))
        mono = [sum(f[i:i + self.ch]) / self.ch for i in range(0, len(f) - self.ch + 1, self.ch)]
        pcm = array.array("h", (max(-32767, min(32767, int(x * 32767))) for x in mono))
        with wave.open(self.path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(pcm.tobytes())
        print("captured %.1f s of audio to %s" % (len(mono) / float(self.rate), self.path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qcf", default=qlpaths.QEMU_QCF)
    ap.add_argument("--image", default=os.path.join(QL, "abadia_h_bin"))
    ap.add_argument("--script", default=os.path.join(QL, "build", "qltest", "user", "script_bin"))
    ap.add_argument("--log-every", type=int, default=1)
    ap.add_argument("--boot-wait", type=float, default=25)
    ap.add_argument("--plan", default="UP:2000,wait:1500,LEFT:100,wait:1500,ESC:100,wait:3000")
    ap.add_argument("--diag", type=int, default=None, help="override the loader's POKE a+29 (0 = no heartbeat)")
    ap.add_argument("--sound", type=int, default=None, help="override the loader's POKE a+28 (1 = no QSound)")
    ap.add_argument("--diag31", type=int, default=0, help="diagnostics: extra bits for POKE a+31 (8 no KEYROW, 16 no con_ drain)")
    ap.add_argument("--autopilot", default=None, help="tests/*.txt script: keys from inside the game (no SendInput)")
    ap.add_argument("--nobeep", action="store_true", help="diagnostics: the game issues no BEEP IPC")
    ap.add_argument("--intro", action="store_true", help="show the intro parchment")
    ap.add_argument("--capture", default=None, help="record the Windows audio output (WASAPI loopback) to this WAV")
    ap.add_argument("--keep", action="store_true", help="leave the emulator running")
    ap.add_argument("--type-lrun", action="store_true", help="boot to BASIC, then TYPE the LRUN command")
    ap.add_argument("--typematic", type=float, default=0, help="host auto-repeat rate (per second), 0 = off")
    ap.add_argument("--typematic-delay", type=float, default=500, help="ms before host auto-repeat starts")
    a = ap.parse_args()

    tq = prepare(a.qcf, a.image, a.script, a.log_every, a.type_lrun, a.diag, a.sound, a.intro, a.nobeep, a.diag31, a.autopilot)
    rec = Recorder(a.capture) if a.capture else None
    proc = subprocess.Popen([EXE, tq], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    events = []
    try:
        h = None
        t0 = time.time()
        while time.time() - t0 < 20 and not h:
            time.sleep(0.5)
            h = main_window(proc.pid)
        if not h:
            print("no Q-emuLator window"); return 1
        print("window:", [t for _, t in windows_of(proc.pid)])
        if a.type_lrun:         # as the author does: type the command at the BASIC prompt
            time.sleep(12)
            if not ensure_foreground(h, proc.pid):
                print("could not focus Q-emuLator to type LRUN"); return 1
            type_text("LRUN win1_test_bas")
            send_key("ENTER", False); time.sleep(0.05); send_key("ENTER", True)
        time.sleep(a.boot_wait)
        log = os.path.join(TEST, "abadia_log")
        print("log after boot wait:", os.path.getsize(log) if os.path.exists(log) else "none")
        start = time.time()
        for item in a.plan.split(","):
            k, ms = item.split(":")
            ms = int(ms)
            if k == "wait":
                time.sleep(ms / 1000.0)
                continue
            if not ensure_foreground(h, proc.pid):
                print("could not focus Q-emuLator - stopping before sending", k); return 1
            send_key(k, False)
            events.append((round(time.time() - start, 2), k, "down"))
            if a.typematic:     # like a physical key: Windows repeats key-down while it is held
                t_end = time.time() + ms / 1000.0
                time.sleep(min(a.typematic_delay / 1000.0, ms / 1000.0))
                reps = 0
                while time.time() < t_end:
                    send_key(k, False)
                    reps += 1
                    time.sleep(1.0 / a.typematic)
                events.append((round(time.time() - start, 2), k, "%d repeats" % reps))
            else:
                time.sleep(ms / 1000.0)
            if fg_pid() != proc.pid:
                print("focus lost while holding", k)
            send_key(k, True)
            events.append((round(time.time() - start, 2), k, "up"))
        print("events:", events)
    finally:
        if rec:
            rec.stop()
        if not a.keep:
            proc.kill()
            proc.wait(5)
            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

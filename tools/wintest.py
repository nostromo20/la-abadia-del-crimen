#!/usr/bin/env python3
"""Boots a COPY of the release QXL.WIN container (tools/mkwin.py) as WIN1_ in QPC2 (SMSQ/E's own
QXL.WIN driver) and screenshots the emulator window at the given times: the container must mount,
BOOT must run from it and EXEC the jobs (loading screen, then the game's intro parchment).

  wintest.py [--win release/abadia.win] [--at 6,12,20] [--out build/wintest/shot]

The author's qpc.ini and containers are not touched (a copy of qpc.ini: WIN1 = the copy,
BootFromWIN=1, no dialog). Kills only the QPC2 it started.
"""
import argparse, ctypes, os, shutil, subprocess, sys, time
import qlpaths  # local tool paths (tools/qlpaths.py)
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qemu_drive as qd
from PIL import ImageGrab

QPC_EXE = qlpaths.QPC_EXE
QPC_INI_SRC = qlpaths.QPC_INI


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win", default=os.path.join(QL, "release", "abadia.win"))
    ap.add_argument("--at", default="6,12,20")
    ap.add_argument("--out", default=os.path.join(QL, "build", "wintest", "shot"))
    ap.add_argument("--keys", default="", help="t:KEY,... taps (qemu_drive key names) at t seconds")
    a = ap.parse_args()
    d = os.path.join(QL, "build", "wintest")
    os.makedirs(d, exist_ok=True)
    win = os.path.join(d, "test.win")
    shutil.copyfile(a.win, win)
    rep = {"WIN1=": "WIN1=" + win, "BootFromWIN=": "BootFromWIN=1", "BootFromFLP=": "BootFromFLP=0",
           "ShowDialog=": "ShowDialog=0"}
    out = []
    for line in open(QPC_INI_SRC, encoding="latin-1").read().splitlines():
        for k, v in rep.items():
            if line.startswith(k):
                line = v
        out.append(line)
    ini = os.path.join(d, "qpc_test.ini")
    open(ini, "w", encoding="latin-1").write("\r\n".join(out) + "\r\n")
    proc = subprocess.Popen([QPC_EXE, "-ini", ini], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    t0 = time.time()
    try:
        import qltest
        print("config dialog dismissed" if qltest.click_ok_in_config_dialog(proc.pid) else "no config dialog seen")
        h = None
        while time.time() - t0 < 20 and not h:
            time.sleep(0.5)
            h = qd.main_window(proc.pid)
        if not h:
            print("no window"); return 1
        qd.ensure_foreground(h, proc.pid)
        taps = sorted((float(k.split(":")[0]), k.split(":")[1]) for k in a.keys.split(",") if k)
        for t in [float(x) for x in a.at.split(",")]:
            while time.time() - t0 < t:
                if taps and time.time() - t0 >= taps[0][0]:
                    qd.ensure_foreground(h, proc.pid)
                    qd.send_key(taps[0][1], False); time.sleep(0.15); qd.send_key(taps[0][1], True)
                    print("tapped", taps.pop(0))
                time.sleep(0.05)
            r = wintypes.RECT()
            qd.user32.GetWindowRect(h, ctypes.byref(r))
            if r.right <= r.left or r.bottom <= r.top:
                print("window has no area at %.1fs: %r" % (t, (r.left, r.top, r.right, r.bottom))); continue
            img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
            p = "%s_%04.1fs.png" % (a.out, t)
            img.save(p)
            print("saved", p, img.size)
    finally:
        proc.kill()
        proc.wait(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())

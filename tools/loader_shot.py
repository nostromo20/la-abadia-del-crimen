#!/usr/bin/env python3
"""Boot the real release loader (boot_h_bas) in the author's Q-emuLator (a COPY of their .qcf) and grab
screenshots of the emulator window at given times, e.g. to see the loading screen.

  loader_shot.py [--qcf my_config.qcf] [--at 4,8,14] [--out build/run/loader]

Uses tools/qemu_drive.py's window helpers; kills only the emulator it started.
"""
import argparse, os, shutil, subprocess, sys, time
import qlpaths  # local tool paths (tools/qlpaths.py)
HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import qemu_drive as qd
from PIL import ImageGrab
import ctypes
from ctypes import wintypes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qcf", default=qlpaths.QEMU_QCF)
    ap.add_argument("--at", default="4,8,14")
    ap.add_argument("--out", default=os.path.join(QL, "build", "run", "loader"))
    a = ap.parse_args()
    test = os.path.join(QL, "build", "qltest", "loader")
    os.makedirs(test, exist_ok=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    for f in ("abadia_h_bin", "abadia_scr", "boot_h_bas"):
        shutil.copyfile(os.path.join(QL, f), os.path.join(test, f))
    open(os.path.join(test, "BOOT"), "wb").write(b"10 LRUN win1_boot_h_bas\n")
    lines = open(a.qcf, "rb").read().decode("latin-1").splitlines()
    lines = ["Slot1=" + test if l.startswith("Slot1=") else l for l in lines]
    tq = os.path.join(test, "shot.qcf")
    open(tq, "wb").write(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    proc = subprocess.Popen([qd.EXE, tq], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    t0 = time.time()
    try:
        h = None
        while time.time() - t0 < 20 and not h:
            time.sleep(0.5)
            h = qd.main_window(proc.pid)
        if not h:
            print("no window"); return 1
        qd.ensure_foreground(h, proc.pid)
        for t in [float(x) for x in a.at.split(",")]:
            while time.time() - t0 < t:
                time.sleep(0.1)
            r = wintypes.RECT()
            qd.user32.GetWindowRect(h, ctypes.byref(r))
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

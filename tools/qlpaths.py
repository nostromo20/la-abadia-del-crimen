"""qlpaths.py -- where the tools find things outside the repository. Every value can be set in the
environment; the defaults are the usual install locations.

  ABBEY_SRC       a clone of github.com/Samuel85/Abbey (only for tools/import_*.py, which re-import
                  the VIGASOCO sources)                       default: ../abbey_src next to this repo
  QEMULATOR_EXE   Q-emuLator (tools/qemu_drive.py, loader_shot.py)
  QEMU_QCF        your Q-emuLator configuration (.qcf) to copy for a test run
  QPC_EXE, QPC_INI, QPC_WIN   QPC2, its qpc.ini, and a QXL.WIN container to copy (tools/qltest.py qpc,
                  tools/wintest.py)
  SQLUX_DIR, SQLUX_ROMS       sQLux and its ROM directory (tools/qltest.py sqlux)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
# this repository as seen from WSL (the C++ oracle and the m68k tools run there)
# (computed, never taken from the environment: Git Bash rewrites /mnt/... values it passes on to
# Windows programs into "C:/Program Files/Git/mnt/...")
WSL_QL = "/mnt/" + QL[0].lower() + QL[2:].replace("\\", "/")

DSK = os.path.join(QL, "data", "abadia.dsk")                 # the CPC disk image (data/README.md)
DOS_OVL = os.path.join(QL, "data", "dos", "ABADIA1.OVL")     # the DOS version's sounds: NOT included (data/README.md)

ABBEY_SRC = os.environ.get("ABBEY_SRC", os.path.join(os.path.dirname(QL), "abbey_src"))
ABBEY_VIGASOCO = os.path.join(ABBEY_SRC, "vigasoco")

QEMULATOR_EXE = os.environ.get("QEMULATOR_EXE", r"C:\Program Files (x86)\QemuLator\QemuLator 4\QemuLator.exe")
QEMU_QCF = os.environ.get("QEMU_QCF", "")
QPC_EXE = os.environ.get("QPC_EXE", r"C:\Program Files (x86)\QPC2\QPC2.exe")
QPC_INI = os.environ.get("QPC_INI", r"C:\ProgramData\QPC\qpc.ini")
QPC_WIN = os.environ.get("QPC_WIN", "")
SQLUX_DIR = os.environ.get("SQLUX_DIR", "")
SQLUX_ROMS = os.environ.get("SQLUX_ROMS", "")

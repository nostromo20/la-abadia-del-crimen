# config.sh -- local tool locations for the build and test scripts (sourced by build_hybrid.sh,
# build_release.sh and tools/*.sh). Set these in the environment, or edit the defaults here.
#
#   PY    a Windows Python 3 (with pillow, unicorn, z80 for the tests)
#   VASM  vasmm68k_mot.exe (Motorola syntax), Windows build
#
# QLW / QLL are this repository as a Windows path and as seen from WSL (the C++ is compiled in WSL
# with m68k-linux-gnu-g++; the packers apultra and salvador are built in WSL under ~/codecs).
: "${PY:=python}"
: "${VASM:=vasmm68k_mot.exe}"
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QLW="$(cygpath -m "$_here" 2>/dev/null || echo "$_here")"
_drive="$(echo "${QLW:0:1}" | tr 'A-Z' 'a-z')"
QLL="/mnt/${_drive}${QLW:2}"
export PY VASM QLW     # (QLL stays a shell variable: Git Bash would rewrite it for Windows programs)

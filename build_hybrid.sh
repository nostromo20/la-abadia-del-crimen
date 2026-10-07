#!/bin/bash
# Build script for the HYBRID QL build: asm platform (vasm -Felf) + VIGASOCO C++ (GCC m68k).
# Output: abadia_h_bin + boot_h_bas in the repo root (load with LRUN win1_boot_h_bas).
# The all-asm room viewer is still built by build.sh.
set -e
. "$(dirname "$0")/config.sh"           # QLW, QLL, VASM, PY (edit config.sh)
cd "$(dirname "$0")"
mkdir -p build/obj build/tmp

[ -f build/roms.bin ] || "$PY" tools/mkroms.py

BUILD_ID=$(date +%s)
echo "== palette"
"$PY" tools/mkpalette.py
echo "== tile composition data (QL_TILE_COMPOSE: cpp/port/ql_compose_data.h from build/roms.bin)"
"$PY" tools/tilecompose.py --gen || exit 1
echo "== vasm"
powershell.exe -Command "& '$VASM' -Felf -m68000 -no-opt -DBUILD_ID=$BUILD_ID -L '$QLW/build/qlmain.lst' -I '$QLW/src' -o '$QLW/build/obj/qlmain.o' '$QLW/src/qlmain.s' 2>&1 | Out-String" > build/vasm.log
cat build/vasm.log | grep -v '^vasm\|^$\|(c) 20' || true
if grep -qi "error" build/vasm.log; then echo "BUILD FAILED (vasm error)"; exit 1; fi
if grep -q "warning 2047" build/vasm.log; then echo "BUILD FAILED (vasm warning 2047: bsr became jsr)"; exit 1; fi

echo "== g++ m68k"
MSYS_NO_PATHCONV=1 wsl bash "$QLL/cpp/compile_m68k.sh" "$QLL" "${IDIOMA:-1}"
echo "== ld"
MSYS_NO_PATHCONV=1 wsl bash "$QLL/cpp/link_m68k.sh" "$QLL"
echo "== image"
"$PY" tools/mkimage.py build/abadia_h.elf build/abadia_h.raw abadia_h_bin --loader boot_h_bas --map build/abadia_h.sym
# loading screen shown by boot_h_bas (A4S, the chosen one: CPC title, hand-tuned, stretched to 256x256)
cp loadscreen/A4S_scr abadia_scr
"$PY" tools/oddcheck.py build/qlmain.lst build/abadia_h.sym
"$PY" tools/alignscan.py build/abadia_h.raw build/abadia_h.sym
echo "Build OK: $(wc -c < abadia_h_bin) bytes"

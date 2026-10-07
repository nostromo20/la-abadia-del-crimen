#!/bin/bash
# The RELEASE build (docs/release.md): the microdrive package, separate from the dev build.
#   - the same sources with RELEASE (vasm) / QL_RELEASE (g++/gcc): no test hooks, heartbeat,
#     harness sequences or reference kernels; the CPC data trimmed (build/roms_trim.bin,
#     tools/romtrim.py); objects in build/rel/obj, so the dev build (build_hybrid.sh: build/obj,
#     abadia_h_bin, boot_h_bas) is untouched
#   - the image (build/rel/abadia_r_bin) packed with aPLib (apultra), the loading screen with ZX0
#     (salvador), both in WSL (~/codecs, tools/codecs/)
#   - two QDOS jobs (vasm -Fbin): build/rel/abadia (src/release/rel_main.s: unpacks and runs the
#     game) and build/rel/abadia_title (src/release/rel_title.s: unpacks the picture)
#   - tools/mkrelease.py: release/abadia.mdv + release/win/
# Never run at the same time as build_hybrid.sh (shared generated sources).
set -e
. "$(dirname "$0")/config.sh"           # QLW, QLL, VASM, PY (edit config.sh)
cd "$(dirname "$0")"
mkdir -p build/rel/obj build/tmp release

[ -f build/roms.bin ] || "$PY" tools/mkroms.py
if [ ! -f build/roms_trim.bin ]; then
  [ -f build/romusage.bin ] || "$PY" tools/romusage.py
  "$PY" tools/romtrim.py
fi
# IDIOMA=1 (the default): the English-only release (docs/size_budget.md): no Spanish texts in the
# C++ (QL_SOLO_INGLES) and the CPC data's Spanish parchment texts zeroed (romtrim.py --english)
LANGC=""; LANGA=""
if [ "${IDIOMA:-1}" = 1 ]; then
  if [ ! -f build/roms_trim_en.bin ] || [ tools/romtrim.py -nt build/roms_trim_en.bin ]; then
    "$PY" tools/romtrim.py --english --out build/roms_trim_en.bin > /dev/null
  fi
  LANGC="-DQL_SOLO_INGLES"; LANGA="-DENGLISH_ONLY=1"
fi

BUILD_ID=$(date +%s)
echo "== palette, tile composition data (shared with the dev build; both deterministic)"
"$PY" tools/mkpalette.py
"$PY" tools/tilecompose.py --gen || exit 1
echo "== vasm (RELEASE)"
powershell.exe -Command "& '$VASM' -Felf -m68000 -no-opt -DBUILD_ID=$BUILD_ID -DRELEASE=1 $LANGA -L '$QLW/build/rel/qlmain.lst' -I '$QLW/src' -o '$QLW/build/rel/obj/qlmain.o' '$QLW/src/qlmain.s' 2>&1 | Out-String" > build/rel/vasm.log
cat build/rel/vasm.log | grep -v '^vasm\|^$\|(c) 20' || true
if grep -qi "error\|warning" build/rel/vasm.log; then echo "BUILD FAILED (vasm error or warning)"; exit 1; fi

echo "== g++ m68k (QL_RELEASE)"
MSYS_NO_PATHCONV=1 wsl env QL_OBJ="$QLL/build/rel/obj" QL_XFLAGS="-DQL_RELEASE $LANGC -ffunction-sections -fdata-sections" \
  bash "$QLL/cpp/compile_m68k.sh" "$QLL" "${IDIOMA:-1}"
echo "== ld"
MSYS_NO_PATHCONV=1 wsl env QL_OBJ="$QLL/build/rel/obj" QL_OUT="$QLL/build/rel" QL_NAME=abadia_r QL_RELEASE=1 \
  bash "$QLL/cpp/link_m68k.sh" "$QLL"
echo "== image"
"$PY" tools/mkimage.py build/rel/abadia_r.elf build/rel/abadia_r.raw build/rel/abadia_r_bin --map build/rel/abadia_r.sym | tee build/rel/mkimage.log
NEED=$(sed -n 's/.*RESPR(\([0-9]*\)).*/\1/p' build/rel/mkimage.log)
ILEN=$(wc -c < build/rel/abadia_r_bin)
"$PY" tools/oddcheck.py build/rel/qlmain.lst build/rel/abadia_r.sym
"$PY" tools/alignscan.py build/rel/abadia_r.raw build/rel/abadia_r.sym

echo "== pack (aPLib: the image; ZX0: the loading screen)"
cp loadscreen/A4S_scr build/rel/title_scr
rm -f build/rel/abadia_r.apl build/rel/title.zx0
MSYS_NO_PATHCONV=1 wsl bash -lc "~/codecs/apultra/apultra $QLL/build/rel/abadia_r_bin $QLL/build/rel/abadia_r.apl && ~/codecs/salvador/salvador $QLL/build/rel/title_scr $QLL/build/rel/title.zx0" | grep -v "^$" || true
[ -s build/rel/abadia_r.apl ] && [ -s build/rel/title.zx0 ] || { echo "BUILD FAILED (packing)"; exit 1; }

echo "== jobs (vasm -Fbin)"
for j in main:abadia title:abadia_title; do
  src=${j%%:*}; out=${j##*:}
  powershell.exe -Command "& '$VASM' -Fbin -m68000 -no-opt -DNEED=$NEED -DIMAGE_LEN=$ILEN -L '$QLW/build/rel/rel_$src.lst' -I '$QLW/src/release' -I '$QLW/build/rel' -o '$QLW/build/rel/$out' '$QLW/src/release/rel_$src.s' 2>&1 | Out-String" > build/rel/vasm_$src.log
  if grep -qi "error\|warning" build/rel/vasm_$src.log; then cat build/rel/vasm_$src.log; echo "BUILD FAILED (job $out)"; exit 1; fi
done

echo "== package"
"$PY" tools/mkrelease.py --need $NEED
# the same three files in a QXL.WIN hard-disk container (QPC2, SMSQmulator, sQLux, Q-emuLator, QL-SD)
"$PY" tools/mkwin.py
echo "Release OK: image $ILEN bytes (RESPR $NEED), packed $(wc -c < build/rel/abadia_r.apl), screen $(wc -c < build/rel/title.zx0)"

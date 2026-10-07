#!/bin/bash
# Compiles the VIGASOCO logic + QL port layer for the 68000 (run inside WSL).
# Usage: compile_m68k.sh <QL repo dir (Linux path)> [idioma]
set -e
QL="$1"
IDIOMA="${2:-1}"
OBJ="${QL_OBJ:-$QL/build/obj}"          # build_release.sh: its own object directory
mkdir -p "$OBJ"
# -fno-store-merging -fdisable-tree-bswap: GCC 13 m68k otherwise merges byte accesses into
# word accesses at ODD addresses even with -m68000 (address error on a real 68008)
NOMERGE="-fno-store-merging -fdisable-tree-bswap"
CXXFLAGS="$NOMERGE -m68000 -Os -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-pic -fno-use-cxa-atexit \
 -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -DNDEBUG -DQL_IDIOMA=$IDIOMA -DQL_ASM_KERNELS -DQL_PACKED_MIX -DQL_ASM_ROUTES -DQL_ASM_GRID -DQL_ASM_TILES -DQL_BEEPER -DQL_CHARCOL -DQL_HGRID_CACHE -DQL_TILE_COMPOSE -DQL_INTRO_DISSOLVE -DQL_ASM_GEN -DQL_INTERLEAVE $QL_XFLAGS -w \
 -I $QL/cpp/port -I $QL/cpp/vigasoco"
CFLAGS="$NOMERGE -m68000 -Os -fno-pic -fno-asynchronous-unwind-tables -DNDEBUG $QL_XFLAGS -I $QL/cpp/port"
fail=0
while read -r src; do
  [ -z "$src" ] && continue
  name=$(basename "$src")
  if ! m68k-linux-gnu-g++ $CXXFLAGS -c "$QL/cpp/$src.cpp" -o "$OBJ/$name.o" 2> "$OBJ/$name.err"; then
    echo "FAIL $src"; head -20 "$OBJ/$name.err"; fail=1
  fi
done < "$QL/cpp/cxx_sources.txt"
# runtime: must not be turned back into calls to itself
m68k-linux-gnu-g++ $CXXFLAGS -fno-builtin -fno-tree-loop-distribute-patterns -fno-strict-aliasing -c "$QL/cpp/port/ql_runtime.cpp" -o "$OBJ/ql_runtime.o" || fail=1
m68k-linux-gnu-gcc $CFLAGS -c "$QL/cpp/port/ql_rand.c" -o "$OBJ/ql_rand.o" || fail=1
m68k-linux-gnu-gcc $CFLAGS -DQL_FAST_SOUND -DQL_BEEPER -c "$QL/cpp/port/ql_sound.c" -o "$OBJ/ql_sound.o" || fail=1
m68k-linux-gnu-gcc $CFLAGS -c "$QL/cpp/port/ql_beeper.c" -o "$OBJ/ql_beeper.o" || fail=1
m68k-linux-gnu-gcc $CFLAGS -fno-builtin -fno-tree-loop-distribute-patterns -c "$QL/cpp/port/ql_kernels.c" -o "$OBJ/ql_kernels.o" || fail=1
exit $fail

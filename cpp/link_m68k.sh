#!/bin/bash
# Links the hybrid image (run inside WSL). Usage: link_m68k.sh <QL repo dir (Linux path)>
set -e
QL="$1"
# build_release.sh sets QL_OBJ, QL_OUT, QL_NAME and QL_RELEASE=1 (no harness entry points kept)
OBJ="${QL_OBJ:-$QL/build/obj}"
OUT="${QL_OUT:-$QL/build}"
NAME="${QL_NAME:-abadia_h}"
KEEP="-u abadia_show_screen -u abadia_tilebuf -u abadia_game_over -u abadia_ending -u c_combina_tile -u c_sprite_blit -u c_fill -u c_and_mask"
[ "$QL_RELEASE" = 1 ] && KEEP=""
m68k-linux-gnu-ld -T "$QL/link/abadia.ld" -q --gc-sections -nostdlib -z noexecstack --no-warn-rwx-segments \
  $KEEP \
  -Map "$OUT/$NAME.map" -o "$OUT/$NAME.elf" \
  "$OBJ/qlmain.o" $(sed 's#.*/##; s#$#.o#; s#^#'"$OBJ"'/#' "$QL/cpp/cxx_sources.txt" | grep -v '^'"$OBJ"'/.o$') \
  "$OBJ/ql_runtime.o" "$OBJ/ql_rand.o" "$OBJ/ql_kernels.o" "$OBJ/ql_sound.o" "$OBJ/ql_beeper.o"
m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .init_array -j .data "$OUT/$NAME.elf" "$OUT/$NAME.raw"
m68k-linux-gnu-size -A "$OUT/$NAME.elf" | grep -E '^\.(text|rodata|init_array|data|bss) '

#!/bin/bash
# Builds the HOST-ONLY scene recorder for tools/colour_mapper.html (run inside WSL):
# the PC oracle with QL_HOST_CLASSES, which also records which source (terrain, characters,
# lamp, panel) drew each pixel. Never used for hdiff/sndtest; the regular oracle is
# build_oracle.sh. Usage: build_oracle_scenes.sh <QL repo dir (Linux path)> [idioma]
set -e
QL="$1"
IDIOMA="${2:-1}"
OBJ="$QL/build/host/scenes"
mkdir -p "$OBJ"
FLAGS="-O1 -fno-exceptions -fno-rtti -DNDEBUG -DQL_IDIOMA=$IDIOMA -DQL_HOST_CLASSES -DQL_TILE_COMPOSE -w -I $QL/cpp/port -I $QL/cpp/vigasoco"
objs=""
while read -r src; do
  [ -z "$src" ] && continue
  name=$(basename "$src")
  g++ $FLAGS -c "$QL/cpp/$src.cpp" -o "$OBJ/$name.o"
  objs="$objs $OBJ/$name.o"
done < "$QL/cpp/cxx_sources.txt"
gcc -O1 -I $QL/cpp/port -c "$QL/cpp/port/ql_rand.c" -o "$OBJ/ql_rand.o"
gcc -O1 -I $QL/cpp/port -c "$QL/cpp/port/ql_kernels.c" -o "$OBJ/ql_kernels.o"
gcc -O1 -I $QL/cpp/port -c "$QL/cpp/port/ql_sound.c" -o "$OBJ/ql_sound.o"
g++ $FLAGS -c "$QL/cpp/host/host_main.cpp" -o "$OBJ/host_main.o"
g++ -o "$QL/build/host/oracle_scenes" $objs "$OBJ/ql_rand.o" "$OBJ/ql_kernels.o" "$OBJ/ql_sound.o" "$OBJ/host_main.o"
echo "built: $QL/build/host/oracle_scenes"

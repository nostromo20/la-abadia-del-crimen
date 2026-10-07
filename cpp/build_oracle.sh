#!/bin/bash
# Builds the native PC oracle (run inside WSL). Usage: build_oracle.sh <QL repo dir (Linux path)> [idioma]
set -e
QL="$1"
IDIOMA="${2:-1}"
OBJ="$QL/build/host"
mkdir -p "$OBJ"
FLAGS="-O1 -fno-exceptions -fno-rtti -DNDEBUG -DQL_IDIOMA=$IDIOMA -DQL_TILE_COMPOSE -w -I $QL/cpp/port -I $QL/cpp/vigasoco"
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
g++ -o "$OBJ/oracle" $objs "$OBJ/ql_rand.o" "$OBJ/ql_kernels.o" "$OBJ/ql_sound.o" "$OBJ/host_main.o"
echo "oracle built: $OBJ/oracle"

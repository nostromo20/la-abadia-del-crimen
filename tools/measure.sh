#!/bin/bash
# Real timing in the author's Q-emuLator (tools/qemu_drive.py, heartbeat off): idle 20 s + 3 s UP,
# then a long walk with turns. qemu_drive kills only the emulator it started - never kill by image
# name here, that would close the author's own Q-emuLator sessions.
cd "$(dirname "$0")/.." && . ./config.sh
echo "== idle 20 s + UP 3 s"
timeout 150 $PY tools/qemu_drive.py --diag 0 --typematic 30 --plan "wait:20000,UP:3000,wait:2000,ESC:100,wait:3000" > /dev/null 2>&1
$PY tools/qemu_log.py build/qltest/qemu/abadia_log | tail -3
echo "== long walk with turns"
timeout 200 $PY tools/qemu_drive.py --diag 0 --typematic 30 --plan "wait:6000,UP:2500,LEFT:120,wait:400,UP:6000,RIGHT:120,wait:400,UP:6000,LEFT:120,wait:400,UP:6000,wait:1500,ESC:100,wait:3000" > /dev/null 2>&1
$PY tools/qemu_log.py build/qltest/qemu/abadia_log | tail -3
true

#!/bin/bash
# QEMU_KEYS run (keys only as typed characters, as Q-emuLator over RDP delivered them):
# must turn, walk, turn, walk, exit. Prints "WALKS AND TURNS: yes".
cd "$(dirname "$0")/.." && . ./config.sh
mkdir -p build/tmp
QEMU_KEYS=1 $PY tools/qlrun.py --script tests/qemu_keys.txt --ticks 200 --realq --state build/tmp/keys_state.bin 2>&1 | grep stopped
$PY - <<'PYEOF'
d = open("build/tmp/keys_state.bin", "rb").read()
S = 256
st = [d[i:i + S] for i in range(0, len(d) - S + 1, S)]
prev = None
moves = turns = 0
for t, b in enumerate(st):
    g = (b[20], b[21], b[23])            # Guillermo x, y, orientation
    if prev and g[:2] != prev[:2]: moves += 1
    if prev and g[2] != prev[2]:
        turns += 1
        print("tick %d: orientation %d -> %d at x %02x y %02x" % (t, prev[2], g[2], g[0], g[1]))
    prev = g
print("ticks %d, steps with a position change %d, turns %d, start %s end %s" % (len(st), moves, turns, (st[0][20], st[0][21], st[0][23]), prev))
# (moves >= 10: with the real auto-repeat (2026-10-05: 300 ms delay, qlrun models it) each walk
# leg starts with a pause; it was >= 20 with a character typed every frame)
print("WALKS AND TURNS: %s" % ("yes" if moves >= 10 and turns >= 2 else "NO"))
PYEOF

#!/bin/bash
# hdiff of the RELEASE image as the job unpacks it (tools/reltest.py writes build/rel/unpacked_bin)
# against the PC oracle, which runs the full CPC data (docs/release.md). Run after build_release.sh.
cd "$(dirname "$0")/.." && . ./config.sh
R="--realq --sv164 0xC1000 --image build/rel/unpacked_bin --sym build/rel/abadia_r.sym"
echo "== reltest"; $PY tools/reltest.py | grep -E "^FAIL|^RELTEST"
cmp build/rel/unpacked_bin build/rel/abadia_r_bin && echo "unpacked image identical to the pre-pack release build"
for t in walk1 enter saveload; do echo "== release hdiff $t 900"; $PY tools/hdiff.py --script tests/$t.txt --ticks 900 --every 10 $R 2>&1 | tail -2; done
echo "== release hdiff walk1 4000"; $PY tools/hdiff.py --script tests/walk1.txt --ticks 4000 --every 100 $R 2>&1 | tail -2
echo "== release hdiff intro 400"; $PY tools/hdiff.py --script tests/idle.txt --ticks 400 --every 40 $R --intro 2>&1 | tail -2
echo "== release hdiff intro -> game"; for s in intro intro_skip_early intro_skip_turn; do $PY tools/hdiff.py --script tests/$s.txt --ticks 400 --every 10 $R --intro 2>&1 | tail -1; done

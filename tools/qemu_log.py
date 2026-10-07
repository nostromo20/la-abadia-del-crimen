#!/usr/bin/env python3
"""Per-step view of a self-log written with 'log every 1' (tools/qemu_drive.py)."""
import struct, sys
REC = struct.Struct(">IIBBHIBBBBBBBBIHH")
d = open(sys.argv[1], "rb").read()
recs = [REC.unpack_from(d, i) for i in range(0, len(d) - 31, 32)]
print("%d records, steps %d..%d, frames %d..%d, longest main-loop silence %d frames" %
      (len(recs), recs[0][0], recs[-1][0], recs[0][1], recs[-1][1], recs[-1][15]))
prev = None
for r in recs:
    if prev is None or r[4] != prev[4] or (r[7], r[8], r[10]) != (prev[7], prev[8], prev[10]) \
            or r[1] - prev[1] > 10 or r is recs[-1]:
        print("step %4d fr %5d dfr %3s keys %03x fault %08x G %02x,%02x o%d" %
              (r[0], r[1], (r[1] - prev[1]) if prev else "-", r[4], r[5], r[7], r[8], r[10]))
    prev = r


def stats(label, xs):
    if not xs:
        print("%-8s no steps" % label); return
    s = sorted(xs)
    print("%-8s %4d steps  frames/step mean %5.2f  p90 %3d  max %3d  (target 6.5)" %
          (label, len(s), sum(s) / len(s), s[min(len(s) - 1, int(len(s) * 0.9))], s[-1]))


# idle = no key in this step or the one before; walking = a key held this step and the one before
# (the first steps after the start of the log are left out: they include the room's first draw)
idle, walk = [], []
for i in range(6, len(recs)):
    a, b = recs[i - 1], recs[i]
    if b[0] != a[0] + 1:
        continue
    d = b[1] - a[1]
    if a[4] == 0 and b[4] == 0:
        idle.append(d)
    elif a[4] and b[4]:
        walk.append(d)
stats("idle", idle)
stats("walking", walk)
# spikes: steps (after the first 6) longer than 10 frames, idle or walking
sp = [recs[i][1] - recs[i - 1][1] for i in range(6, len(recs)) if recs[i][0] == recs[i - 1][0] + 1]
big = [d for d in sp if d > 10]
print("spikes   %4d steps > 10 frames of %d, max %d" % (len(big), len(sp), max(sp) if sp else 0))
print("BEEPs    %4d issued by the last record (record +30)" % recs[-1][16])

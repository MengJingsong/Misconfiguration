#!/usr/bin/env bash
# B1 main cycle arms, interleaved, 3 repeats each: S (v5 1 MB), H4 (v4 1 MB), H5s (v5 100 kB), I (patched, v5 1 MB).
# 12 cycles x 200 requests, window 4, idle 20 s, heap 2G, direct 2G.
H=$(cd "$(dirname "$0")" && pwd)
for n in 1 2 3; do
  bash "$H/run-arm.sh" S-$n   unmod   5 1000000 12 200 2G 2G 4 20
  bash "$H/run-arm.sh" H4-$n  unmod   4 1000000 12 200 2G 2G 4 20
  bash "$H/run-arm.sh" H5s-$n unmod   5 100000  12 200 2G 2G 4 20
  bash "$H/run-arm.sh" I-$n   patched 5 1000000 12 200 2G 2G 4 20
done
echo BATCH-DONE

#!/bin/bash
# B3e for commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous (as amended 2026-10-23, B2i.7): n = 8, 32, 64 MiB (mmap,
# total space 1024 MiB, stress n = 2,000,000), the LZ4 series at 32, and the positive control (32 MiB, total space 256).
# Usage: bash cluster-chain.sh <outroot> [n]
OUT=${1:?}; N=${2:-2000000}; H=$(cd "$(dirname "$0")" && pwd)
echo "EXPECTED: mmap arms: no file > n, largest observed == n, ratios 1:4:8; peak live files about 1024/n + 1..2 (129-130, 33-34, 17-18; overshoot is not a refutation); rolls >= ~30; LZ4: files within n+n/255+32/sync, TotalCommitLogSize below the volume written; control (n=32, total 256): peak files about 8-10"
for a in "n8:8:mmap:1024:$N:stress" "n32:32:mmap:1024:$N:stress" "n64:64:mmap:1024:$N:stress" "lz4-n32:32:lz4:1024:$N:stress" "ctl-n32-t256:32:mmap:256:$N:stress"; do
  IFS=: read -r L S M T NN LD <<<"$a"
  bash $H/cluster-run.sh "$OUT" "$L" "$S" "$M" "$T" "$NN" "$LD" || { echo "arm $L FAILED"; exit 1; }
done
touch "$OUT/CHAIN_DONE"

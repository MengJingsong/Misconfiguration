#!/bin/bash
# B3e order: S=8, 32, 128 (mmap, total 4096), the positive control (S=8, total 64), the LZ4 arm (S=32, stress), the compressible arm
# (S=32, loader) and the idle baseline. Usage: bash cluster-chain.sh <outroot> [n]
OUT=${1:?}; N=${2:-600000}; H=$(cd "$(dirname "$0")" && pwd)
echo "EXPECTED: mmap arms: no file > S, largest observed == S, ratios 1:4:16, rolls ~ 600MiB/S (75, 19, 5), dir total is a multiple of S not S; control: S=8,total=64 -> peak dir <= ~80 MiB, uncontrolled S=8 well above 64; LZ4: files within S+S/255+32/sync, compressible far below S; idle: files at rest"
for a in "s8:8:mmap:4096:$N:stress" "s32:32:mmap:4096:$N:stress" "s128:128:mmap:4096:$N:stress" "ctl-s8-t64:8:mmap:64:$N:stress" \
         "lz4-s32:32:lz4:4096:$N:stress" "lz4zero-s32:32:lz4:4096:$N:loader" "idle-s32:32:mmap:4096:0:none"; do
  IFS=: read -r L S M T NN LD <<<"$a"
  bash $H/cluster-run.sh "$OUT" "$L" "$S" "$M" "$T" "$NN" "$LD" || { echo "arm $L FAILED"; exit 1; }
done
touch "$OUT/CHAIN_DONE"

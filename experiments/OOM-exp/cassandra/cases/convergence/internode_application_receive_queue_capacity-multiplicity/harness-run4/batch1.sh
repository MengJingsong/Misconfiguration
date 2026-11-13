#!/usr/bin/env bash
# Run-4 batch 1: N sweep at direct 2048 (natural path, R=500/s), then OOM stage at 512.
H=$(cd "$(dirname "$0")" && pwd)
run(){ local name=$1; shift; [ -f /mydata/c1r4/runs/$name/outcome.txt ] && { echo "skip $name"; return; }
  # wait while foreign load is heavy (1-min loadavg > 24 with no c1r4 java running)
  for _ in $(seq 20); do l=$(cut -d' ' -f1 /proc/loadavg); [ "${l%.*}" -lt 24 ] && break; echo "$(date +%T) waiting, loadavg $l"; sleep 30; done
  "$H/arm.sh" "$name" "$@"; }
for spec in "$@"; do run $spec; done

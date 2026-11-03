#!/usr/bin/env bash
# Stage-4 harness: memtable_heap_space-LeafBuilder-allocated--autonomous, cluster tier run 1: the eight runs of C2 in order,
# with C3's n_main and C5's n_tail. Each run is cluster-run.sh on a fresh node; the chain stops if a run leaves a daemon behind.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
while read -r label var hs mode nmain ntail; do
  [ -z "$label" ] && continue
  echo "=== $label $(date '+%F %T')"
  "$H/cluster-run.sh" "$label" "$var" "$hs" "$mode" "$nmain" "$ntail"
  echo "=== $label exit=$? $(date '+%F %T')"
  if ps -eo command | grep -q '[C]assandraDaemon'; then echo "ABORT: daemon left after $label"; exit 1; fi
done <<'RUNS'
v0-64-single V0 64MiB single 5000000 53000
v0-64-batch V0 64MiB batch 40000 415
v0-256-single V0 256MiB single 5000000 212000
v0-256-batch V0 256MiB batch 40000 1660
v0-def-single V0 unset single 5000000 425000
v0-def-batch V0 unset batch 40000 3320
v1-64-single V1 64MiB single 5000000 53000
v1-64-batch V1 64MiB batch 40000 415
RUNS
echo "=== chain done $(date '+%F %T')"

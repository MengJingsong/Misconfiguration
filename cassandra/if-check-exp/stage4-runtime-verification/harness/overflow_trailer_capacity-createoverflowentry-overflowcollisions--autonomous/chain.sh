#!/usr/bin/env bash
# usage: chain.sh   (the whole cluster tier B3e as amended 2026-10-28)
set -uo pipefail
HARN=$(cd "$(dirname "$0")" && pwd)
for spec in "g8 collide 2 4" "g9 collide 3 3" "r1e5 rows 100000" "r1e6 rows 1000000" "m1 mem 1" "m100 mem 100"; do
  bash "$HARN/cluster-run.sh" $spec > "$HOME/stage4-logs/b34/overflow-$(echo $spec | cut -d' ' -f1).out" 2>&1
  echo "chain: $spec done rc=$? daemons=$(ps -eo cmd | grep -c '[C]assandraDaemon')"
done
# extra control (not in C4): 108 ordinary rows, no collisions, same index: the 0-slot comparator for B3g's "SI size at 8 slots" row
EXTRA=108 bash "$HARN/cluster-run.sh" g0 collide 0 0 > "$HOME/stage4-logs/b34/overflow-g0.out" 2>&1; echo "chain: g0 done rc=$?"

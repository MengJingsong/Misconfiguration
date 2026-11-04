#!/usr/bin/env bash
# usage: chain.sh   (the whole cluster tier B3e as amended 2026-10-28, arms in the order of C2/C4; s16 is subject to the disk guard in cluster-run.sh)
set -uo pipefail
HARN=$(cd "$(dirname "$0")" && pwd)
# arm rows index heap format commitlogMiB
for spec in "s1 1000000 yes 2G big 1024" "n1 1000000 no 2G big 1024" "h1 1000000 yes 4G big 1024" "b1 1000000 yes 2G bti 1024" "p1 1000000 yes 2G big 64" "s4 4000000 yes 2G big 1024" "s16 16000000 yes 2G big 1024"; do
  bash "$HARN/cluster-run.sh" $spec > "$HOME/stage4-logs/b34/maxoffset-$(echo $spec | cut -d' ' -f1).out" 2>&1
  echo "chain: $spec done rc=$? daemons=$(ps -eo cmd | grep -c '[C]assandraDaemon') $(date -u +%T)"
done

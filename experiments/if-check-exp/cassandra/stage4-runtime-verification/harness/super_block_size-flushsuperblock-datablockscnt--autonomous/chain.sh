#!/usr/bin/env bash
# usage: chain.sh   (the whole cluster tier B3e as amended 2026-10-28; arms of C3)
set -uo pipefail
HARN=$(cd "$(dirname "$0")" && pwd)
# arm option constant mode
for spec in "o64c64 64 64 SPARSE" "o8c64 8 64 SPARSE" "o512c64 512 64 SPARSE" "o64c16 64 16 SPARSE" "o64c256 64 256 SPARSE" "pfx64 64 64 PREFIX"; do
  bash "$HARN/cluster-run.sh" $spec > "$HOME/stage4-logs/b34/superblock-$(echo $spec | cut -d' ' -f1).out" 2>&1
  echo "chain: $spec done rc=$? daemons=$(ps -eo cmd | grep -c '[C]assandraDaemon') $(date -u +%T)"
done

#!/usr/bin/env bash
# Cluster run 1 (B3b order, amended 2026-10-24): default (unset), 2MiB, 8MiB, then the 2048MiB start. One node start at a time.
# usage: cluster-chain.sh [outdir-name]  (default cluster-run1)    Needs: source ~/Library/Caches/stage4/env.sh
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); OUT=${1:-cluster-run1}; L=$W/logs/native_transport_max_frame_size-applySimpleConfig/$OUT
mkdir -p "$L"; : > "$L/chain.log"
for spec in "default unset" "s2 2MiB" "s8 8MiB" "startup-2048MiB 2048MiB"; do
  set -- $spec
  echo "[$(date '+%F %T')] start $1 ($2)" >> "$L/chain.log"
  "$H/cluster-run.sh" "$OUT" "$1" "$2" >> "$L/chain.log" 2>&1; echo "[$(date '+%F %T')] $1 rc=$?" >> "$L/chain.log"
  ps -eo command | grep -q '[C]assandraDaemon' && { echo "ABORT: CassandraDaemon left after $1" >> "$L/chain.log"; exit 1; }
done
echo "[$(date '+%F %T')] chain done" >> "$L/chain.log"

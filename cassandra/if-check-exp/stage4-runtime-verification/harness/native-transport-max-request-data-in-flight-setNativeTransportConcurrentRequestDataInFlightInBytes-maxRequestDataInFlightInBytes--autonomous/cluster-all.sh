#!/usr/bin/env bash
# Cluster tier run 1: pass 1 = 4 L values x 3 arms, then the live arm, then pass 2 = L 16MiB x 3 arms (repeat). One node start per arm.
# Stops at the first arm that does not end with a summary (a step that could not run as written).
# usage: bash cluster-all.sh   (log ~/s4-b8-cr-logs/cluster/all.log)
H=$HOME/s4-b8-cr-harness; LOGD=$HOME/s4-b8-cr-logs/cluster; LOG=$LOGD/all.log
mkdir -p "$LOGD"
while read -r label L arm live; do
  echo "[$(date +%s%3N)] begin $label" >> "$LOG"
  bash "$H/cluster-run.sh" "$label" "$L" "$arm" $live > /dev/null 2>&1
  if [ -s "$LOGD/$label/summary.txt" ]; then
    echo "[$(date +%s%3N)] done $label" >> "$LOG"
  else
    echo "[$(date +%s%3N)] STOP: $label ended without a summary" >> "$LOG"; exit 1
  fi
done <<'RUNS'
p1-16MiB-v4-256k 16MiB v4-256k
p1-16MiB-v5-100k 16MiB v5-100k
p1-16MiB-v5-256k 16MiB v5-256k
p1-64MiB-v4-256k 64MiB v4-256k
p1-64MiB-v5-100k 64MiB v5-100k
p1-64MiB-v5-256k 64MiB v5-256k
p1-default-v4-256k default v4-256k
p1-default-v5-100k default v5-100k
p1-default-v5-256k default v5-256k
p1-1GiB-v4-256k 1GiB v4-256k
p1-1GiB-v5-100k 1GiB v5-100k
p1-1GiB-v5-256k 1GiB v5-256k
p1-live-v4-256k 1GiB v4-256k live
p2-16MiB-v4-256k 16MiB v4-256k
p2-16MiB-v5-100k 16MiB v5-100k
p2-16MiB-v5-256k 16MiB v5-256k
RUNS
echo "[$(date +%s%3N)] ALL DONE" >> "$LOG"

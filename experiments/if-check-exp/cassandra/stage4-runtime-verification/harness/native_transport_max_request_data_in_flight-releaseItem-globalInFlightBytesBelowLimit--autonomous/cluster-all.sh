#!/usr/bin/env bash
# Cluster tier run 1: the seven runs of B3e (audit amendment order), one after another; stops at the first run
# that does not end with a summary (a step that could not run as written).
# usage: bash cluster-all.sh   (log ~/stage4-logs/pv5/cluster/all.log)
T=$HOME/stage4-harness-run/pv5; LOG=$HOME/stage4-logs/pv5/cluster/all.log
mkdir -p "$(dirname "$LOG")"
while read -r label L C TH MODE; do
  echo "[$(date +%s%3N)] begin $label" >> "$LOG"
  bash "$T/cluster-run.sh" "$label" "$L" "$C" "$TH" "$MODE" > /dev/null 2>&1
  if [ -s "$HOME/stage4-logs/pv5/cluster/$label/summary.txt" ]; then
    echo "[$(date +%s%3N)] done $label" >> "$LOG"
  else
    echo "[$(date +%s%3N)] STOP: $label ended without a summary" >> "$LOG"; exit 1
  fi
done <<'RUNS'
r1-64MiB-C1-T0 64MiB 1 0 group
r2-256MiB-C1-T0 256MiB 1 0 group
r3-default-C1-T0 default 1 0 group
r4-4GiB-C1-T0 4GiB 1 0 group
r5-64MiB-C32-T0 64MiB 32 0 group
r6-64MiB-C1-T1 64MiB 1 1 group
r7-4GiB-C1-T0-periodic 4GiB 1 0 periodic
RUNS
echo "[$(date +%s%3N)] ALL DONE" >> "$LOG"

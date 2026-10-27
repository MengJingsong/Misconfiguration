#!/usr/bin/env bash
# Cluster tier run 1: runs r1..r9 of B3e (audit amendment R18), one after another; stops at the first run without a summary.
# usage: bash cluster-all.sh   (log ~/s4-b8-pi-logs/cluster/all.log)
T=$HOME/s4-b8-pi-harness; LOG=$HOME/s4-b8-pi-logs/cluster/all.log
mkdir -p "$(dirname "$LOG")"
while read -r label proto gl pi th per extra; do
  echo "[$(date +%s%3N)] begin $label" >> "$LOG"
  ( eval "$extra"; export SRC2THREADS JMXSET TAIL_S; bash "$T/cluster-run.sh" "$label" "$proto" "$gl" "$pi" "$th" "$per" > /dev/null 2>&1 )
  if [ -s "$HOME/s4-b8-pi-logs/cluster/$label/summary.txt" ]; then
    echo "[$(date +%s%3N)] done $label" >> "$LOG"
  else
    echo "[$(date +%s%3N)] STOP: $label ended without a summary" >> "$LOG"; exit 1
  fi
done <<'RUNS'
r1-v5-8MiB 5 1GiB 8MiB 64 8 TAIL_S=120
r2-v5-32MiB 5 1GiB 32MiB 64 8 TAIL_S=30
r3-v5-128MiB 5 1GiB 128MiB 64 8 TAIL_S=30
r4-v4-8MiB 4 1GiB 8MiB 64 8 TAIL_S=30
r5-v4-32MiB 4 1GiB 32MiB 64 8 TAIL_S=30
r6-v4-128MiB 4 1GiB 128MiB 64 8 TAIL_S=30
r7-v5-global16MiB 5 16MiB 128MiB 64 8 TAIL_S=30
r8-v5-twoIP-32MiB 5 1GiB 32MiB 32 8 SRC2THREADS=32;TAIL_S=30
r9-v5-jmx-128to8MiB 5 1GiB 128MiB 64 16 JMXSET=8388608;TAIL_S=30
RUNS
echo "[$(date +%s%3N)] ALL DONE" >> "$LOG"

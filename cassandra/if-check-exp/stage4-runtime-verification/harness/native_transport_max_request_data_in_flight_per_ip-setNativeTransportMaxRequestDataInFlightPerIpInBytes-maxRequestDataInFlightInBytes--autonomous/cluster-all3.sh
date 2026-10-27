#!/usr/bin/env bash
# Continuation after r1 (r2 attempt 1 was invalid: one client connection hung in the driver's connect phase, the barrier broke, no load was sent;
# loadgen.py and cluster-run.sh now fail a run without a RESULT line). Runs r2..r9; a run that ends without a summary is retried (max 3 attempts, logged).
T=$HOME/s4-b8-pi-harness; LOG=$HOME/s4-b8-pi-logs/cluster/all.log
while read -r label proto gl pi th per extra; do
  for att in 1 2 3; do
    echo "[$(date +%s%3N)] begin $label attempt $att" >> "$LOG"
    ( eval "$extra"; export SRC2THREADS JMXSET TAIL_S; bash "$T/cluster-run.sh" "$label" "$proto" "$gl" "$pi" "$th" "$per" > /dev/null 2>&1 )
    if [ -s "$HOME/s4-b8-pi-logs/cluster/$label/summary.txt" ]; then echo "[$(date +%s%3N)] done $label" >> "$LOG"; break; fi
    echo "[$(date +%s%3N)] no summary: $label attempt $att" >> "$LOG"; mv "$HOME/s4-b8-pi-logs/cluster/$label" "$HOME/s4-b8-pi-logs/cluster/$label-attempt$att-INVALID"
    [ $att = 3 ] && { echo "[$(date +%s%3N)] STOP: $label" >> "$LOG"; exit 1; }
  done
done <<'RUNS'
r2-v5-32MiB 5 1GiB 32MiB 64 8 TAIL_S=30
r3-v5-128MiB 5 1GiB 128MiB 64 8 TAIL_S=30
r4-v4-8MiB 4 1GiB 8MiB 64 8 TAIL_S=30
r5-v4-32MiB 4 1GiB 32MiB 64 8 TAIL_S=30
r6-v4-128MiB 4 1GiB 128MiB 64 8 TAIL_S=30
r7-v5-global16MiB 5 16MiB 128MiB 64 4 TAIL_S=30
r8-v5-twoIP-32MiB 5 1GiB 32MiB 32 8 SRC2THREADS=32;TAIL_S=30
r9-v5-jmx-128to8MiB 5 1GiB 128MiB 64 4 JMXSET=8388608;TAIL_S=30
RUNS
echo "[$(date +%s%3N)] ALL DONE" >> "$LOG"

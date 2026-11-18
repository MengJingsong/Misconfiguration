#!/usr/bin/env bash
# Run a list of U3 runs one after another; each line of <specfile>: <run-id> <heap|unset> <guard> <table> <mode> <c> [extra-yaml|-]
# Stops before starting a run after the no-new-run time (02:05 EST = 00:05 node local MST) and when a file STOP exists in $R.
# usage: bash seq.sh <specfile> <batch-name>   (a batch named cal* stops after the first run that ends in OOM; hs* stops after the first run that does not)
set -uo pipefail
R=/mydata/s4/u3-w1; H=$R/harness; SPEC=$1; B=$2
LOG=$R/seq-$B.log
while read -r RID HEAP GUARD TABLE MODE CC XY; do
  [ -z "$RID" ] && continue; case $RID in \#*) continue;; esac
  [ -e "$R/STOP" ] && { echo "$(date) STOP file: not starting $RID" >> "$LOG"; break; }
  NOWNY=$(TZ=America/New_York date +%H%M)
  if [ "$NOWNY" -ge 0205 ] && [ "$NOWNY" -lt 1200 ]; then echo "$(date) past 02:05 EST: not starting $RID" >> "$LOG"; break; fi
  echo "$(date) start $RID" >> "$LOG"
  bash "$H/run.sh" "$RID" "$HEAP" "$GUARD" "$TABLE" "$MODE" "$CC" "${XY:--}" < /dev/null > "$R/runs-$RID.nohup" 2>&1
  python3 -I "$H/analyze.py" "$R/runs/$RID/logs" < /dev/null > "$R/runs/$RID/logs/analysis.txt" 2>&1
  echo "$(date) end $RID: $(grep -m1 '^OUTCOME' "$R/runs/$RID/logs/analysis.txt")" >> "$LOG"
  # calibration batches (name starts with cal) stop at the first heap OOM: c_f is the smallest failing c
  case $B in cal*) grep -q '^OUTCOME OOM' "$R/runs/$RID/logs/analysis.txt" && { echo "$(date) calibration: first OOM at $RID, stop" >> "$LOG"; break; };;
    hs*) grep -q '^OUTCOME OOM' "$R/runs/$RID/logs/analysis.txt" || { echo "$(date) heap search: $RID did not OOM, stop climbing" >> "$LOG"; break; };; esac
done < "$SPEC"
echo "$(date) batch $B done" >> "$LOG"

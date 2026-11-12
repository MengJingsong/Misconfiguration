#!/usr/bin/env bash
# B7 batch: run the arm list in priority order (design §4-5), one arm at a time; parse each dump in the background
# (nice 19, python3 -I, standard library) while the next arm runs. Stops starting arms after the wall-time limit.
# Usage: run-batch.sh <arm-list-file>   (lines: name build heap cache keyBytes fill  |  mixed name heap)
set -uo pipefail
B=/mydata/b7; H=$B/harness
DEADLINE=$(date -d '2026-11-12 02:45' +%s)
n=0
while read -r a1 a2 a3 a4 a5 a6; do
  [ -z "$a1" ] && continue; case "$a1" in \#*) continue;; esac
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then echo "[$(date '+%F %T')] deadline reached, not starting $a1 $a2"; break; fi
  n=$((n+1)); [ "$n" -gt 50 ] && { echo "arm limit reached"; break; }
  if [ "$a1" = mixed ]; then
    echo "[$(date '+%F %T')] START mixed $a2 $a3"
    timeout 2700 "$H/b7-run.sh" mixed "$a2" "$a3" > "$B/logs/$a2.out" 2>&1; echo "[$(date '+%F %T')] END $a2 rc=$?"
    name=$a2
  else
    echo "[$(date '+%F %T')] START $a1 $a2 $a3 $a4 $a5 $a6"
    timeout 2700 "$H/b7-run.sh" arm "$a1" "$a2" "$a3" "$a4" "$a5" "$a6" > "$B/logs/$a1.out" 2>&1; echo "[$(date '+%F %T')] END $a1 rc=$?"
    name=$a1
  fi
  if [ -s "$B/dumps/$name.hprof" ]; then
    ( nice -n 19 python3 -I "$H/hprof_holders.py" "$B/dumps/$name.hprof" 25 > "$B/logs/$name/hprof-report.txt" 2> "$B/logs/$name/hprof-report.err" ) &
  fi
done < "$1"
wait
echo "[$(date '+%F %T')] batch done ($n arms)"

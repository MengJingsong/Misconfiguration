#!/usr/bin/env bash
# Resume variant of seq.sh (2026-11-18): run-r.sh; endpoint by a2.py (A2 rule); no new run after 06:30 EST (task deadline 07:30 EST,
# replacing §2.7's 02:05, which belonged to the interrupted session's time plan; amendment A3). hs* stops climbing at the first survivor.
set -uo pipefail
R=/mydata/s4/u3-w1; H=$R/harness; SPEC=$1; B=$2
LOG=$R/seq-$B.log
while read -r RID HEAP GUARD TABLE MODE CC XY; do
  [ -z "$RID" ] && continue; case $RID in \#*) continue;; esac
  [ -e "$R/STOP" ] && { echo "$(date) STOP file: not starting $RID" >> "$LOG"; break; }
  NOWNY=$(TZ=America/New_York date +%H%M)
  if [ "$NOWNY" -ge 0630 ] && [ "$NOWNY" -lt 1200 ]; then echo "$(date) past 06:30 EST: not starting $RID" >> "$LOG"; break; fi
  echo "$(date) start $RID" >> "$LOG"
  bash "$H/run-r.sh" "$RID" "$HEAP" "$GUARD" "$TABLE" "$MODE" "$CC" "${XY:--}" < /dev/null > "$R/runs-$RID.nohup" 2>&1
  python3 -I "$H/analyze.py" "$R/runs/$RID/logs" < /dev/null > "$R/runs/$RID/logs/analysis.txt" 2>&1
  python3 -I "$H/a2.py" "$R/runs/$RID/logs/analysis.txt" >> "$R/runs/$RID/logs/analysis.txt" 2>&1
  echo "$(date) end $RID: $(grep -m1 '^OUTCOME' "$R/runs/$RID/logs/analysis.txt") | $(grep -m1 '^A2OUTCOME' "$R/runs/$RID/logs/analysis.txt")" >> "$LOG"
  case $B in hs*) grep -q '^A2OUTCOME OOM' "$R/runs/$RID/logs/analysis.txt" || { echo "$(date) heap search: $RID did not OOM, stop climbing" >> "$LOG"; break; };; esac
done < "$SPEC"
echo "$(date) batch $B done" >> "$LOG"

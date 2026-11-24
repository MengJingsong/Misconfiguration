#!/usr/bin/env bash
# R14 3-b: scan the run's hprof as stage 2 did (thread holding the error; MultiCBuilder traces; class histogram), then
# delete the hprof.   scan-dump.sh <label>
set -uo pipefail
ROOT=/mydata/s4/3b-R14; H=$ROOT/h; R=$ROOT/runs/$1
F=$(ls "$R"/*.hprof 2>/dev/null | head -1)
[ -z "$F" ] && { echo "no hprof in $R"; exit 1; }
echo "[$(date -u '+%FT%TZ')] scan $F ($(stat -c %s "$F") B)"
nice -n 19 python3 "$H/hs_full.py" "$F" OutOfMemoryError > "$R/hprof-stack-oom.txt" 2>&1
nice -n 19 python3 "$H/hs_full.py" "$F" MultiCBuilder > "$R/hprof-stack-multicbuilder.txt" 2>&1
echo "[$(date -u '+%FT%TZ')] stacks done"
nice -n 19 python3 "$H/hprofhist.py" "$F" 20 > "$R/hist.txt" 2>&1
echo "[$(date -u '+%FT%TZ')] histogram done"
echo "$(date -u '+%FT%TZ') deleted $F $(stat -c %s "$F") B after hprof-stack-oom.txt, hprof-stack-multicbuilder.txt, hist.txt" >> "$ROOT/runs/hprof-deleted.log"
rm -f "$F"
echo "[$(date -u '+%FT%TZ')] END scan $1"

#!/usr/bin/env bash
# U9 batch (pc91): batch.sh <label:arm:heap:direct:R> ...   runs the lifetimes in order, one at a time.
# No new lifetime at or after 17:40 America/New_York (design 2.7); a STOP file in $ROOT stops the batch between lifetimes.
ROOT=/mydata/s4/u9-w4
for spec in "$@"; do
  IFS=: read -r L A HP D R <<< "$spec"
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 1740 ]; then echo "[$(TZ=America/New_York date '+%T')] SKIP $L (past 17:40)"; continue; fi
  [ -f "$ROOT/STOP" ] && { echo "[$(TZ=America/New_York date '+%T')] STOP file, skip $L"; continue; }
  echo "[$(TZ=America/New_York date '+%T')] BEGIN $L $A $HP $D $R"
  "$ROOT/harness/run-arm.sh" "$L" "$A" "$HP" "$D" "$R" > "$ROOT/runs/$L.console" 2>&1
  echo "[$(TZ=America/New_York date '+%T')] END $L: $(grep -m1 '^outcome=' "$ROOT/runs/$L/result.txt" 2>/dev/null)"
done
echo "[$(TZ=America/New_York date '+%T')] BATCH DONE"

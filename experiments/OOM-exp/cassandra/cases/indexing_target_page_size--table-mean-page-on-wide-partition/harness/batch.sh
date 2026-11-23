#!/usr/bin/env bash
# B20 batch: batch.sh "<label> <arm> <heap> <direct> [nodump]" ... ; runs lifetimes serially; no lifetime starts after
# 13:15 EST (design time plan); stops if the file /mydata/s4/b20/STOP exists.
ROOT=/mydata/s4/b20
for spec in "$@"; do
  [ -f "$ROOT/STOP" ] && { echo "STOP file; skipping $spec"; continue; }
  now=$(TZ=America/New_York date +%H%M); [ "$now" -ge 1315 ] && { echo "after 13:15 EST; skipping $spec"; continue; }
  echo "[$(TZ=America/New_York date '+%F %T %Z')] batch: $spec"
  set -- $spec
  bash "$ROOT/harness/run-arm.sh" "$@" > "$ROOT/runs/$1.out" 2>&1
  echo "[$(TZ=America/New_York date '+%F %T %Z')] batch: $1 -> $(grep -m1 '^outcome=' "$ROOT/runs/$1/result.txt" 2>/dev/null)"
done
echo "[$(TZ=America/New_York date '+%F %T %Z')] batch done"

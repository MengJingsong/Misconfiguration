#!/usr/bin/env bash
# 3-b confirm B20 batch (pc75): batch.sh <deadline epoch> "<label> <dump|nodump>" ... ; runs serially; no run starts
# after the deadline (per-case 4 h cap) or if /mydata/s4/3b-B20/STOP exists.
ROOT=/mydata/s4/3b-B20; DL=$1; shift
for spec in "$@"; do
  [ -f "$ROOT/STOP" ] && { echo "STOP file; skipping $spec"; continue; }
  [ "$(date +%s)" -ge "$DL" ] && { echo "past deadline; skipping $spec"; continue; }
  echo "[$(TZ=America/New_York date '+%F %T %Z')] batch: $spec"
  set -- $spec
  bash "$ROOT/harness/run-3b.sh" "$@" > "$ROOT/runs/$1.out" 2>&1
  echo "[$(TZ=America/New_York date '+%F %T %Z')] batch: $1 -> $(grep -h '^outcome=' "$ROOT/runs/$1-a/result.txt" "$ROOT/runs/$1-r/result.txt" 2>/dev/null | tr '\n' ' ')"
done
echo "[$(TZ=America/New_York date '+%F %T %Z')] batch done"

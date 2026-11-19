#!/usr/bin/env bash
# B18: wait (bounded, until 17:20 America/New_York) for the previous plan's "PLAN DONE" line, then run the next plan.
# usage: after.sh <previous plan .out> <next plan file>
W=/mydata/s4/b18-w4
while ! grep -q "PLAN DONE" "$1"; do
  [ "$(TZ=America/New_York date +%H%M)" -ge 1720 ] && { echo "$(date +%s) after.sh: deadline, not starting $2"; exit 0; }
  sleep 5
done
exec bash $W/harness/plan.sh "$2"

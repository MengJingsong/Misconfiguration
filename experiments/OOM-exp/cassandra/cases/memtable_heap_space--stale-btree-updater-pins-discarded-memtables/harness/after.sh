#!/usr/bin/env bash
# R21: wait (bounded, until 06:45 America/New_York) for the previous plan's "PLAN DONE" line, then run the next plan.
# usage: after.sh <previous plan .out> <next plan file>
W=/mydata/s4/r21
while ! grep -q "PLAN DONE" "$1"; do
  n=$(TZ=America/New_York date +%H%M); [ "$n" -ge 645 ] && [ "$n" -lt 1200 ] && { echo "$(date +%s) after.sh: deadline, not starting $2"; exit 0; }
  sleep 5
done
exec bash $W/harness/plan.sh "$2"

#!/usr/bin/env bash
# U17 sequential arm runner: batch.sh <list-file>; each line: <label> <A|I> <heap> <payload> <N> <R> <D> [ENV=..]
# Skips labels already in out/; stops on $ROOT/batch.stop; no new run after the stage-2 cut-off (T0 + 4 h = 13:16 EST).
ROOT=/mydata/s4/u17; CUT=$(date -d '2026-11-24 13:16 EST' +%s)
while read -r L A HP P N R D E; do
  [ -z "$L" ] && continue; [[ $L == \#* ]] && continue
  [ -f $ROOT/batch.stop ] && { echo "batch.stop"; break; }
  [ "$(date +%s)" -ge "$CUT" ] && { echo "cut-off reached; $L not started"; break; }
  [ -f $ROOT/out/$L/outcome ] && { echo "skip $L (done)"; continue; }
  env ${E:-X=1} bash $ROOT/harness/run-arm.sh "$L" "$A" "$HP" "$P" "$N" "$R" "$D" > $ROOT/runs-$L.log 2>&1
  echo "$(TZ=America/New_York date '+%T') $L: $(cat $ROOT/out/$L/outcome 2>/dev/null)"
done < "$1"

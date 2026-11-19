#!/usr/bin/env bash
# U5 sequencer: run lifetimes one after another (one measured experiment on the node at a time).
#   seq.sh <name> <stop-on-oom 0|1> "<run-arm args>" ["<run-arm args>" ...]
# Launch as ( setsid nohup bash seq.sh ... < /dev/null > $ROOT/runs/seq-<name>.log 2>&1 & ); poll for "SEQ END".
# A file $ROOT/seq.halt makes it stop before the next lifetime (deadline control).
ROOT=/mydata/s4/u5-w4; NAME=$1; STOP=$2; shift 2
for spec in "$@"; do
  [ -f "$ROOT/seq.halt" ] && { echo "SEQ HALTED before: $spec"; break; }
  set -- $spec; L=$1
  bash "$ROOT/h/run-arm.sh" $spec > "$ROOT/runs/$L.driver.log" 2>&1
  echo "$(grep '^\[.*END' "$ROOT/runs/$L.driver.log" | tail -1)"
  if [ "$STOP" = 1 ] && grep -q '^OOM' "$ROOT/runs/$L/outcome" 2>/dev/null; then echo "SEQ stop-on-OOM after $L"; break; fi
done
echo "SEQ END $NAME"

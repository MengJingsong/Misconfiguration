#!/usr/bin/env bash
# R14 sequencer (from U5 seq.sh): lifetimes one after another (one measured experiment on the node at a time).
#   seq.sh <name> "<run-arm args: label arm heap cond k1 k2 W G>" ...
# A lifetime starts only if now + 300 s (start, schema, send) + W + G ends by 16:55 EST (design hard limit).
# A file $ROOT/seq.halt makes it stop before the next lifetime. Poll runs/seq-<name>.log for "SEQ END".
ROOT=/mydata/s4/r14; NAME=$1; shift
for spec in "$@"; do
  [ -f "$ROOT/seq.halt" ] && { echo "SEQ HALTED before: $spec"; break; }
  set -- $spec; L=$1; W=$7; G=$8
  now=$(date +%s); lim=$(TZ=America/New_York date -d "today 16:55" +%s)
  if [ $(( now + 300 + W + G )) -gt $lim ]; then echo "SEQ SKIP $L: cannot end by 16:55 EST"; continue; fi
  bash "$ROOT/h/run-arm.sh" $spec > "$ROOT/runs/$L.driver.log" 2>&1
  echo "$(grep '^\[.*END' "$ROOT/runs/$L.driver.log" | tail -1 | cut -c1-400)"
done
echo "SEQ END $NAME"

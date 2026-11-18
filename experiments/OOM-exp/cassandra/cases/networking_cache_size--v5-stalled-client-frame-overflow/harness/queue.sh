#!/usr/bin/env bash
# Run arms from a queue file, one per line: the arm.sh arguments. Stops on /mydata/s4/b13-w3/STOP.
# Refuses to start an arm after the design's cutoff (10:25 America/New_York, 2026-11-18).
H=$(cd "$(dirname "$0")" && pwd); ROOT=/mydata/s4/b13-w3
CUTOFF=$(TZ=America/New_York date -d '2026-11-18 10:25' +%s)
mkdir -p $ROOT/runs
while read -r name rest; do
  [ -z "$name" ] && continue; case $name in \#*) continue ;; esac
  [ -f $ROOT/STOP ] && { echo "STOP file, skipping $name"; continue; }
  [ "$(date +%s)" -ge "$CUTOFF" ] && { echo "cutoff passed, skipping $name"; continue; }
  echo "$(TZ=America/New_York date +%T) start $name"
  "$H/arm.sh" "$name" $rest > $ROOT/runs/$name.out 2>&1 < /dev/null
  echo "$(TZ=America/New_York date +%T) end $name: $(tail -1 $ROOT/runs/$name.out)"
done < "$1"
echo "QUEUE DONE $(TZ=America/New_York date +%T)"

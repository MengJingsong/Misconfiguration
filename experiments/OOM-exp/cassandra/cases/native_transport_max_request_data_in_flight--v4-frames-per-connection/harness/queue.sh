#!/usr/bin/env bash
# Run arms from a queue file, one per line: "<name> <direct> <W> <P> <Q> [window] [xmx] [dump]". Stops on /mydata/s4/b9-w1/STOP.
# Refuses to start an arm after the design's cutoff (01:50 America/New_York, 2026-11-18).
H=$(cd "$(dirname "$0")" && pwd); ROOT=/mydata/s4/b9-w1
CUTOFF=$(TZ=America/New_York date -d '2026-11-18 01:50' +%s)
while read -r name d w p q win xmx dump; do
  [ -z "$name" ] && continue; case $name in \#*) continue ;; esac
  [ -f $ROOT/STOP ] && { echo "STOP file, skipping $name"; continue; }
  [ "$(date +%s)" -ge "$CUTOFF" ] && { echo "cutoff passed, skipping $name"; continue; }
  echo "$(TZ=America/New_York date +%T) start $name"
  "$H/arm.sh" "$name" "$d" "$w" "$p" "$q" "${win:-45}" "${xmx:-4096M}" "${dump:-0}" > $ROOT/runs/$name.out 2>&1
  echo "$(TZ=America/New_York date +%T) end $name: $(tail -1 $ROOT/runs/$name.out)"
done < "$1"
echo "QUEUE DONE $(TZ=America/New_York date +%T)"

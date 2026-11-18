#!/usr/bin/env bash
# C5 stage 2 run queue (ms0604). One line per run: <run> <D> <k> <lz4|none> <btm> <patch> <dump>. Stops at 02:12 EST
# (no run starts later) or when /mydata/s4/c5-w1/STOP exists.
. /mydata/s4/c5-w1/h/env.sh
while read -r run d k mode btm patch dump; do
  [ -z "$run" ] && continue
  [ -f $ROOT/STOP ] && { log "STOP file: skip $run"; continue; }
  now=$(TZ=America/New_York date +%H%M); [ "$now" -ge 0212 ] && [ "$now" -lt 1200 ] && { log "after 02:12: skip $run"; continue; }
  log "queue: start $run"; $H/run.sh $run $d $k $mode $btm $patch $dump; log "queue: end $run: $(cut -c1-300 $RUNS/$run/outcome.txt 2>/dev/null)"
done < "$1"
log "QUEUE DONE"

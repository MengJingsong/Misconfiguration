#!/usr/bin/env bash
# Run U16 runs one at a time (from R12's). Each arg: the run.sh arguments as one string.
# No new run starts after $CUTOFF (stage-2 wall-clock cap: 13:15 America/New_York 2026-11-24, tighter than the design's
# 7 h after SEED). STOP file honoured. Log: $W/series.log
W=/mydata/s4/u16
CUTOFF=$(TZ=America/New_York date -d '2026-11-24 13:15' +%s)
for spec in "$@"; do
  if [ "$(date +%s)" -ge "$CUTOFF" ]; then echo "$(date +%FT%T) cutoff reached; not starting: $spec" >> $W/series.log; continue; fi
  if [ -e $W/STOP ]; then echo "$(date +%FT%T) STOP file; not starting: $spec" >> $W/series.log; continue; fi
  echo "$(date +%FT%T) start: $spec" >> $W/series.log
  bash $W/harness/run.sh $spec
  set -- $spec; echo "$(date +%FT%T) end: $1 $(grep END $W/runs/$1/driver.txt | tail -1)" >> $W/series.log
done
echo "$(date +%FT%T) series done" >> $W/series.log

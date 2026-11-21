#!/usr/bin/env bash
# Run R12 runs one at a time (from B11's). Each arg: the run.sh arguments as one string.
# No new run starts after 16:30 America/New_York on 2026-11-20 (design §2.7). STOP file honoured. Log: $W/series.log
W=/mydata/s4/r12-w5
CUTOFF=$(TZ=America/New_York date -d '2026-11-20 16:30' +%s)
for spec in "$@"; do
  if [ "$(date +%s)" -ge "$CUTOFF" ]; then echo "$(date +%FT%T) cutoff reached; not starting: $spec" >> $W/series.log; continue; fi
  if [ -e $W/STOP ]; then echo "$(date +%FT%T) STOP file; not starting: $spec" >> $W/series.log; continue; fi
  echo "$(date +%FT%T) start: $spec" >> $W/series.log
  bash $W/harness/run2.sh $spec
  set -- $spec; echo "$(date +%FT%T) end: $1 $(grep END $W/runs/$1/driver.txt | tail -1)" >> $W/series.log
done
echo "$(date +%FT%T) series done" >> $W/series.log

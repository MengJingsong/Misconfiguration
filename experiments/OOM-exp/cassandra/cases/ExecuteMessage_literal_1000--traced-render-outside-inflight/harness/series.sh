#!/usr/bin/env bash
# Run B11 runs one at a time. Each arg: "<run-id> <base|iv> <heap> <on|off> <fixed:N> <hold-s>".
# No new run starts after 01:55 America/New_York on 2026-11-18 (design §2.7). Log: $W/series.log
W=/mydata/s4/b11-w1
CUTOFF=$(TZ=America/New_York date -d '2026-11-18 01:55' +%s)
for spec in "$@"; do
  if [ "$(date +%s)" -ge "$CUTOFF" ]; then echo "$(date +%FT%T) cutoff reached; not starting: $spec" >> $W/series.log; continue; fi
  if [ -e $W/STOP ]; then echo "$(date +%FT%T) STOP file; not starting: $spec" >> $W/series.log; continue; fi
  echo "$(date +%FT%T) start: $spec" >> $W/series.log
  $W/harness/run.sh $spec
  set -- $spec; echo "$(date +%FT%T) end: $1 $(grep END $W/runs/$1/driver.txt | tail -1)" >> $W/series.log
done
echo "$(date +%FT%T) series done" >> $W/series.log

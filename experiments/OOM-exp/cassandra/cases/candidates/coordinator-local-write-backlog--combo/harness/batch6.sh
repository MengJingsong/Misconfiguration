#!/usr/bin/env bash
# S2 batch 6 (queued 14:45 EST, before batch-5 readings): equal-heap replica check, R heap 2 GiB, endpoint condition A otherwise. Reduced to 1 arm at 15:15 EST for time.
cd /mydata/s2-evidence; export STALL=0 LOAD=90 FILL=0 FLUSH=0 RX=2G
while pgrep -f "[b]atch5.sh" >/dev/null; do sleep 5; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 1520 ]; }
for r in 1; do late || ./arm6.sh Eeq-blob-2G-r$r blob 2G 2>&1 | tail -1; done
echo BATCH6_DONE

#!/usr/bin/env bash
# S2 batch 4 (queued 14:29 EST, before st2/st3 readings): if st3-map-8G-r1 reached the endpoint, repeat it x2 and
# repeat the stage-2 (blob) control once; otherwise one stage-3 map arm at 8 GiB without the stacked layers
# (FILL=0 FLUSH=0) to separate the gap from the layers, then one more st3 repeat. Stop starting arms after 15:22 EST.
cd /mydata/s2-evidence; export STALL=0 LOAD=90
while pgrep -f "[b]atch3.sh" >/dev/null; do sleep 5; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 1522 ]; }
if grep -q V_DEAD runs/st3-map-8G-r1/arm.log; then
  late || FILL=1 FLUSH=1 ./arm.sh st3-map-8G-r2 map 8G 2>&1 | tail -1
  late || FILL=1 FLUSH=1 ./arm.sh st3-map-8G-r3 map 8G 2>&1 | tail -1
  late || FILL=1 FLUSH=1 ./arm.sh st2-blob-8G-r2 blob 8G 2>&1 | tail -1
else
  late || FILL=0 FLUSH=0 ./arm.sh st1-map-8G-r1 map 8G 2>&1 | tail -1
  late || FILL=1 FLUSH=1 ./arm.sh st3-map-8G-r2 map 8G 2>&1 | tail -1
fi
echo BATCH4_DONE

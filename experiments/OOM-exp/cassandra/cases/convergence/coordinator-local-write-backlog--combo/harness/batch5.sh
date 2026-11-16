#!/usr/bin/env bash
# S2 batch 5 (amendment A3, 14:43 EST): stage 2 (caches filled to default caps + flush at 85 s) at the boundary heap 4 GiB, blob.
# Stop starting arms after 15:24 EST.
cd /mydata/s2-evidence; export STALL=0 LOAD=90 FILL=1 FLUSH=1
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 1524 ]; }
for r in 1 2 3; do late || ./arm.sh st2-blob-4G-r$r blob 4G 2>&1 | tail -1; done
echo BATCH5_DONE

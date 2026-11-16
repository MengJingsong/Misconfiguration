#!/usr/bin/env bash
# S2 batch 3 (14:18 EST, after E-blob-8G-r1 survived): repeat the largest failing heap (4 GiB) x2, then at 8 GiB
# stage 2 (caches filled to default caps + nodetool flush at 85 s, blob) and stage 3 (same + map tiny-cell payload, B6 gap).
cd /mydata/s2-evidence; export STALL=0 LOAD=90
FILL=0 FLUSH=0 ./arm.sh E-blob-4G-r2 blob 4G 2>&1 | tail -1
FILL=0 FLUSH=0 ./arm.sh E-blob-4G-r3 blob 4G 2>&1 | tail -1
FILL=1 FLUSH=1 ./arm.sh st2-blob-8G-r1 blob 8G 2>&1 | tail -1
FILL=1 FLUSH=1 ./arm.sh st3-map-8G-r1 map 8G 2>&1 | tail -1

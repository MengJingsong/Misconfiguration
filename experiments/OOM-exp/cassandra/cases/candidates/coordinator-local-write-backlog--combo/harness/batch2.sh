#!/usr/bin/env bash
# S2 batch 2 (amendment A1 heap search): blob endpoint condition at 4 GiB and 8 GiB, one each.
cd /mydata/s2-evidence; export FILL=0 FLUSH=0 STALL=0 LOAD=90
while pgrep -f "[b]atch1.sh" >/dev/null; do sleep 5; done
./arm.sh E-blob-4G-r1 blob 4G 2>&1 | tail -1
./arm.sh E-blob-8G-r1 blob 8G 2>&1 | tail -1

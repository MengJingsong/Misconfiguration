#!/usr/bin/env bash
# B8 batch 1 (2026-11-16): 2 GiB heap, container 4 GiB; P64 r2-r3 (cal1 = r1), P10, P256, matched blob.
cd /mydata/b8
A=harness/arm.sh; export REPLAY_TIMEOUT=900
$A p64-2g-r2 2048 map 5900 150 64
$A p64-2g-r3 2048 map 5900 150 64
$A p10-2g-r1 2048 map 930 150 256
$A p256-2g-r1 2048 map 23700 150 16
$A blob64-2g-r1 2048 blob 65200 150 64

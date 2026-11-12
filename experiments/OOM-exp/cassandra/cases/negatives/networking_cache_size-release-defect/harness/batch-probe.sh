#!/usr/bin/env bash
# B1 arm P (OOM probe / budget search): v5 1 MB, 8 connections x 4 in flight, 600 s, no forced GC during load.
H=$(cd "$(dirname "$0")" && pwd)
bash "$H/run-probe.sh" P-2G-1   unmod 5 1000000 8 4 600 2G 2G
for n in 1 2 3; do bash "$H/run-probe.sh" P-512M-$n unmod 5 1000000 8 4 600 2G 512M; done
echo PROBE-DONE

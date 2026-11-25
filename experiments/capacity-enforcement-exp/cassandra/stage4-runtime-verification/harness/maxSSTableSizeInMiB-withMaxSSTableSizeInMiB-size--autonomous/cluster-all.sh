#!/usr/bin/env bash
# o114 client-process tier (B3e steps 1-3 as written; S4-A1 paths). Logged with set -x.
set -x
export WORK=/mydata/jingsong-cass-s4/o114; R=$WORK/probe/run.sh
date -u +%FT%TZ; nproc; free -g; df -h $WORK; uptime
# 1. measurement runs
for L in 16 64 unset 256 1024; do
  HEAPOPTS="-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc*:file=$WORK/logs/p-u-$L-gc.log" $R p-u-$L unsorted $L 524288 1024 8192 insert
done
for L in 16 256; do
  HEAPOPTS="-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc*:file=$WORK/logs/p-s-$L-gc.log" $R p-s-$L sorted $L 524288 1024 8192 insert
done
# 3. heap-ceiling runs
for L in 16 256; do HEAPOPTS="-Xmx320m -XX:+UseG1GC" $R p-oom-$L unsorted $L 524288 1024 0 insert; done
pgrep -f MaxSizeProbe || echo "no probe left"
date -u +%FT%TZ; echo CLUSTER-DONE

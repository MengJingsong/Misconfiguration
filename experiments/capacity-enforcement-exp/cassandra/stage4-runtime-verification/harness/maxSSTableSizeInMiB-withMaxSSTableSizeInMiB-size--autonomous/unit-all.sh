#!/usr/bin/env bash
# o114 unit tier (B2e as written; S4-A1 paths). Every command is echoed (set -x) into the driver log.
set -x
export WORK=/mydata/jingsong-cass-s4/o114 HEAPOPTS="-Xmx2g"; R=$WORK/probe/run.sh
date -u +%FT%TZ; date +%s%3N; nproc; free -g; df -h $WORK; java -version 2>&1
# 1. unsorted, insert
for L in 1 4 16; do $R u-ins-$L unsorted $L 65536 1024 0 insert; done
# 2. default handling (above 128 MiB of data)
for L in unset 0 -1; do $R u-def-$L unsorted $L 196608 1024 0 insert; done
for L in unset 0 -1; do $R s-def-$L sorted   $L 196608 1024 0 insert; done
# 3. sorted, insert
for L in 1 4 16; do $R s-ins-$L sorted $L 65536 1024 0 insert; done
# 4. bypass probe: delete-only (valueBytes ignored)
$R u-del-1 unsorted 1 262144 0 0 delete
# 5. nothing left running
pgrep -f MaxSizeProbe || echo "no probe left"
date -u +%FT%TZ; echo UNIT-DONE

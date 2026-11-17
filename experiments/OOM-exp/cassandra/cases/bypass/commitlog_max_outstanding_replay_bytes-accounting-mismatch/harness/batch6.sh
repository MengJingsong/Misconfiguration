#!/usr/bin/env bash
# B8 batch 6 (2026-11-16): diagnostic S repetitions at 1 GiB (first OOM's dump kept in s-p64-1g-r1; repeats run
# with -XX:-HeapDumpOnOutOfMemoryError to save time), intervention and blob repeats, one S arm at 2 GiB.
cd /mydata/b8
while ps -eo args | grep -q '^bash harness/\(batch5\|arm[0-9]*\)\.sh'; do sleep 10; done
export REPLAY_TIMEOUT=900 DROP_SSTABLES=1 KEEP_DUMP=0
BM=/mydata/b8/cassandra/build/lib/jars/byteman-4.0.20.jar
FS="-javaagent:$BM=boot:$BM,script:/mydata/b8/harness/flush-stall.btm -Db8.flushdelay=10000"
ND="-XX:-HeapDumpOnOutOfMemoryError"
harness/arm3.sh s-p64-1g-r2 1024 map 5900 150 64 $FS $ND
harness/arm3.sh s-int64-1g-r2 1024 map 5900 150 64 $FS -Dcassandra.commitlog_max_outstanding_replay_count=64
harness/arm3.sh s-blob-1g-r2 1024 blob 65200 150 64 $FS
harness/arm3.sh s-p64-1g-r3 1024 map 5900 150 64 $FS $ND
harness/arm3.sh s-int64-1g-r3 1024 map 5900 150 64 $FS -Dcassandra.commitlog_max_outstanding_replay_count=64
harness/arm3.sh s-blob-1g-r3 1024 blob 65200 150 64 $FS
harness/arm3.sh s-p64-2g-r1 2048 map 5900 150 64 $FS $ND

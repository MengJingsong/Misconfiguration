#!/usr/bin/env bash
# (Stopped after d-p64-8g-bm at 20:20; d-int64-8g-bm and d-blob-8g-bm were not run: replaced by the 2 GiB arms of batch4.sh.)
# B8 batch 2 (2026-11-16): waits for batch 1, then (a) downward heap search at defaults (1 GiB, 512 MiB;
# container 2 x heap), then (b) diagnostic ledger arms with a Byteman delay on every replay task
# (replay-delay.btm) so the replayer's queue fills to its bound; mid-replay class histograms.
cd /mydata/b8
while pgrep -f 'harness/batch1.sh' >/dev/null; do sleep 10; done
export REPLAY_TIMEOUT=900
harness/arm.sh p64-1g-r1 1024 map 5900 150 64
harness/arm.sh p256-1g-r1 1024 map 23700 150 16
harness/arm.sh p64-512m-r1 512 map 5900 150 64
harness/arm.sh p256-512m-r1 512 map 23700 150 16
BM=/mydata/b8/cassandra/build/lib/jars/byteman-4.0.20.jar
BMO="-javaagent:$BM=boot:$BM,script:/mydata/b8/harness/replay-delay.btm -Db8.delay=1000"
HISTO_AFTER="15 30" KEEP_DUMP=1 harness/arm2.sh d-p64-2g-bm 2048 map 5900 150 64 $BMO
CONT_MIB=16384 HISTO_AFTER="20 45" harness/arm2.sh d-p64-8g-bm 8192 map 5900 150 64 $BMO
CONT_MIB=16384 HISTO_AFTER="20 45" harness/arm2.sh d-int64-8g-bm 8192 map 5900 150 64 $BMO -Dcassandra.commitlog_max_outstanding_replay_count=64
CONT_MIB=16384 HISTO_AFTER="20 45" harness/arm2.sh d-blob-8g-bm 8192 blob 65200 150 64 $BMO

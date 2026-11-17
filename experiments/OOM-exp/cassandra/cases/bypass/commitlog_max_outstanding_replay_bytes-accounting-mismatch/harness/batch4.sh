#!/usr/bin/env bash
# B8 batch 4 (2026-11-16, replaces the rest of batch 2 and batch 3 after d-p64-8g-bm): restore emulation at
# 2 GiB defaults, then the 2 GiB diagnostic ledger arms (intervention count=64, blob), all with Byteman where named.
cd /mydata/b8
while ps -eo args | grep -q '^bash harness/arm[0-9]*\.sh'; do sleep 10; done
export REPLAY_TIMEOUT=900
BM=/mydata/b8/cassandra/build/lib/jars/byteman-4.0.20.jar
BMO="-javaagent:$BM=boot:$BM,script:/mydata/b8/harness/replay-delay.btm -Db8.delay=1000"
DROP_SSTABLES=1 HISTO_AFTER="25" harness/arm3.sh x-p64-2g-drop-r1 2048 map 5900 150 64
HISTO_AFTER="15 30" harness/arm2.sh d-int64-2g-bm 2048 map 5900 150 64 $BMO -Dcassandra.commitlog_max_outstanding_replay_count=64
HISTO_AFTER="15 30" harness/arm2.sh d-blob-2g-bm 2048 blob 65200 150 64 $BMO

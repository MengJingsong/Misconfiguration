#!/usr/bin/env bash
# B8 batch 5 (2026-11-16): condition X (restore emulation, DROP_SSTABLES=1) repetitions at defaults, then the
# diagnostic S arms: X + Byteman flush stall (flush-stall.btm, 10 s per b8 flush) during the restart only;
# intervention (replay count 64) and blob controls.
cd /mydata/b8
while ps -eo args | grep -q '^bash harness/\(batch4\|arm[0-9]*\)\.sh'; do sleep 10; done
export REPLAY_TIMEOUT=900 DROP_SSTABLES=1
HISTO_AFTER="8 16" harness/arm3.sh x-p64-2g-drop-r2 2048 map 5900 150 64
HISTO_AFTER="8 16" harness/arm3.sh x-p64-2g-drop-r3 2048 map 5900 150 64
HISTO_AFTER="8 16" harness/arm3.sh x-p64-1g-drop-r1 1024 map 5900 150 64
BM=/mydata/b8/cassandra/build/lib/jars/byteman-4.0.20.jar
FS="-javaagent:$BM=boot:$BM,script:/mydata/b8/harness/flush-stall.btm -Db8.flushdelay=10000"
export KEEP_DUMP=1
HISTO_AFTER="20" harness/arm3.sh s-p64-1g-r1 1024 map 5900 150 64 $FS
KEEP_DUMP=0 HISTO_AFTER="20" harness/arm3.sh s-int64-1g-r1 1024 map 5900 150 64 $FS -Dcassandra.commitlog_max_outstanding_replay_count=64
KEEP_DUMP=0 HISTO_AFTER="20" harness/arm3.sh s-blob-1g-r1 1024 blob 65200 150 64 $FS

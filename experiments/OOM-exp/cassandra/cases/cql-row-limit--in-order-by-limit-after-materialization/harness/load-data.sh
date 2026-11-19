#!/usr/bin/env bash
# B17 lifetime LOAD (heap 8G / direct 4096M; not a reading): schema, 16 x 1,024 x 262,144 B rows at 16 concurrent
# inserts (CL ONE, <= 5 retries each), flush, major compaction, drain, stop; then the template every measured lifetime
# is cloned from.
set -uo pipefail
ROOT=/mydata/s4/b17-w4; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
R=$ROOT/runs/LOAD
$V start LOAD LOAD 8G 4096M && $V ready LOAD || exit 1
bash $H/client.sh LOAD schema 127.0.0.1
time bash $H/client.sh LOAD load 127.0.0.1 16 1024 262144 16
$NT flush b17; time $NT compact b17
$NT tablestats b17.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions|Compression"
$V stop LOAD
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf /dev/shm/b17-w4-commitlog
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/b17/*/

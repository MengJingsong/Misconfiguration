#!/usr/bin/env bash
# U10 lifetime LOAD (8192M/4096M; not a reading): schema, 8 x 65,536 x 16,384 B rows (Random(1000+pk)) at 64 async
# inserts (CL ONE, 5 retries), flush, major compaction, drain, stop; then the template every measured lifetime is cloned from.
set -uo pipefail
ROOT=/mydata/s4/u10-w4; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
R=$ROOT/runs/LOAD
$V start LOAD LOAD 8192M 4096M && $V ready LOAD || exit 1
bash $H/load.sh LOAD schema 127.0.0.1
time bash $H/load.sh LOAD load 127.0.0.1 8 65536 16384
$NT flush u10; time $NT compact u10
$NT tablestats u10.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions|Local write count"
$V stop LOAD
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/u10/*/

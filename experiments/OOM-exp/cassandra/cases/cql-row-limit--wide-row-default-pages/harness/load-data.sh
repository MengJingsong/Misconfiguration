#!/usr/bin/env bash
# U4 lifetime LOAD (heap 8G; not a reading): schema, 16 x 5,000 x 49,152 B rows at 32 async inserts (CL ONE),
# flush, major compaction, drain, stop; then the template every measured lifetime is cloned from.
set -uo pipefail
ROOT=/mydata/s4/u4-w1; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
R=$ROOT/runs/LOAD
$V start LOAD LOAD 8G auto && $V ready LOAD || exit 1
bash $H/load.sh LOAD schema 127.0.0.1
time bash $H/load.sh LOAD load 127.0.0.1 16 5000 49152 0
$NT flush u4; time $NT compact u4
$NT tablestats u4.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions"
$V stop LOAD
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/u4/*/

#!/usr/bin/env bash
# B17 lifetime FILL (added 2026-11-18 14:05 EST; heap 8G / direct 4096M; not a reading): on a clone of the template, insert
# the rows the LOAD could not write after 5 retries (same deterministic values), flush, major compaction, drain, stop;
# then the template is rebuilt from it. Commit log on tmpfs as in LOAD.
set -uo pipefail
ROOT=/mydata/s4/b17-w4; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
R=$ROOT/runs/FILL
$V start FILL FILL 8G 4096M && $V ready FILL || exit 1
bash $H/client.sh FILL fill 127.0.0.1
$NT flush b17; time $NT compact b17
$NT tablestats b17.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions|Compression"
$V stop FILL
rm -rf /dev/shm/b17-w4-commitlog
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/b17/*/

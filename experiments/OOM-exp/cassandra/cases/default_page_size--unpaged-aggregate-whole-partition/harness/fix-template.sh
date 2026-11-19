#!/usr/bin/env bash
# U10 template fix (not a reading; added 2026-11-18 after 57 inserts of pk 7 failed with WriteTimeout after 5 retries in
# LOAD): one lifetime (8192M/4096M) on a clone of the template; re-insert the failed rows with their original bytes,
# VERIFY all 8 partitions, flush, major compaction, drain, stop; the node becomes the template.
set -uo pipefail
ROOT=/mydata/s4/u10-w4; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
$V start FIX A 8192M 4096M && $V ready FIX || exit 1
bash $H/load.sh FIX reload 127.0.0.1 65536 16384 "$(cat $ROOT/runs/load-fails.txt)"
bash $H/load.sh FIX verify 127.0.0.1 8 | grep '^verify'
$NT flush u10; time $NT compact u10
$NT tablestats u10.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions"
$V stop FIX
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/u10/*/

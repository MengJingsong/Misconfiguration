#!/usr/bin/env bash
# B22 lifetime LOAD (not a reading): both nodes (n1 8G, n2 16G), schema, wide 6,000 x 20,480 B and small 6,000 x 2,048 B rows
# in partition k=0 at CL ALL, flush both, tablestats, CL ALL count read-back, drain, stop; then template-n1|n2 that every
# measured lifetime is cloned from.
set -uo pipefail
ROOT=/mydata/s4/b22; H=$ROOT/harness; V="bash $H/ctl.sh"; C="bash $H/client.sh"
$V prep LOAD LOAD || exit 1
$V start LOAD 1 8G auto && $V ready LOAD 1 || exit 1
$V start LOAD 2 16G auto && $V ready LOAD 2 || exit 1
$V ring LOAD || exit 1
$C LOAD schema 127.0.0.1
time $C LOAD load 127.0.0.1 wide 6000 20480
time $C LOAD load 127.0.0.1 small 6000 2048
for i in 1 2; do $V nt $i flush b22; done
for i in 1 2; do echo "== n$i"; $V nt $i tablestats b22 | grep -E "Table: |SSTable count|Space used \(live\)|Number of partitions|Compacted partition maximum"; done
$C LOAD count 127.0.0.1 wide; $C LOAD count 127.0.0.1 small
for i in 1 2; do echo "n$i hints: $(ls $ROOT/n$i/hints | wc -l)"; done
$V stop LOAD
grep -c "OutOfMemoryError" $ROOT/runs/LOAD/n1/logs/system.log $ROOT/runs/LOAD/n2/logs/system.log
for i in 1 2; do rm -rf $ROOT/template-n$i; cp -a $ROOT/n$i $ROOT/template-n$i; rm -rf $ROOT/template-n$i/saved_caches/*; done
du -sh $ROOT/template-n1 $ROOT/template-n2

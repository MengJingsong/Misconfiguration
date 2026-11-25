#!/usr/bin/env bash
# R24 lifetime LOAD (not a reading; design §2.5 step 2), from B22's load-data.sh: both nodes (n1 8G, n2 16G), schema, tables
# w2k/w4k/w8k/w12k (64 KiB pad) and s2k/s4k/s8k/s12k (2 KiB pad), one partition k=0, N = 2,048/4,096/8,192/12,288 rows, CL ALL;
# flush + compact both; tablestats; CL ALL count read-back; drain, stop; then template-n1|n2 that every measured lifetime is cloned from.
set -uo pipefail
ROOT=/mydata/s4/r24; H=$ROOT/harness; V="bash $H/ctl.sh"; C="bash $H/client.sh"
$V prep LOAD LOAD || exit 1
$V start LOAD 1 8G auto && $V ready LOAD 1 || exit 1
$V start LOAD 2 16G auto && $V ready LOAD 2 || exit 1
$V ring LOAD || exit 1
$C LOAD schema 127.0.0.1
for n in 2 4 8 12; do
  time $C LOAD load 127.0.0.1 w${n}k $((n*1024)) 65536
  time $C LOAD load 127.0.0.1 s${n}k $((n*1024)) 2048
done
for i in 1 2; do $V nt $i flush r24; done
for i in 1 2; do time $V nt $i compact r24; done
for i in 1 2; do echo "== n$i"; $V nt $i tablestats r24 | grep -E "Table: |SSTable count|Space used \(live\)|Number of partitions|Compacted partition maximum"; done
for n in 2 4 8 12; do $C LOAD count 127.0.0.1 w${n}k; $C LOAD count 127.0.0.1 s${n}k; done
for i in 1 2; do echo "n$i hints: $(ls $ROOT/n$i/hints | wc -l)"; done
$V stop LOAD
grep -c "OutOfMemoryError" $ROOT/runs/LOAD/n1/logs/system.log $ROOT/runs/LOAD/n2/logs/system.log
for i in 1 2; do rm -rf $ROOT/template-n$i; cp -a $ROOT/n$i $ROOT/template-n$i; rm -rf $ROOT/template-n$i/saved_caches/*; done
du -sh $ROOT/template-n1 $ROOT/template-n2

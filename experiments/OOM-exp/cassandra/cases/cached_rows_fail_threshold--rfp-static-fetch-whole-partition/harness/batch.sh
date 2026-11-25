#!/usr/bin/env bash
# B29 stage-2 readings after DIAG, T1, T2 (2026-11-24): sequential, one lifetime at a time on pc72; after each OOM lifetime the
# dump is summarised (nice 19, between lifetimes) and then deleted (bulk data); budget search per design §2.9; O-thr optional last.
ROOT=/mydata/s4/b29; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-static-fetch-whole-partition/logs
dump(){ local L=$1 F; F=$(ls $ROOT/runs/$L/n1/*.hprof 2>/dev/null | head -1); [ -n "$F" ] || return 0
  nice -n 19 python3 $H/hprofhist.py "$F" 20 > "$REPO/$L/hprofhist.txt" 2>&1
  nice -n 19 python3 $H/hprofstacks.py "$F" OutOfMemoryError > "$REPO/$L/oom-stack-from-hprof.txt" 2>&1
  ls -la "$F" >> "$REPO/$L/hprof.ls"; rm -f "$F"; }
arm(){ local L=$1; shift; bash $H/run-arm.sh "$L" "$@" > $ROOT/runs/$L.log 2>&1; grep "END $L" $ROOT/runs/$L.log; dump "$L"; }
for f in T1 T2; do [ -f $ROOT/runs/$f/n1/*.hprof ] && dump $f; done
arm T3 TA 8 2G auto
for i in 1 2 3; do arm CA$i TB 8 2G auto; done
for i in 1 2 3; do arm CQ$i TA 2 2G auto; done
for i in 1 2 3; do TREE=tree-I arm I$i TA 8 2G auto; done
arm S4G TA 16 4G auto
arm S8G TA 32 8G auto
arm S15872M TA 64 15872M auto
EXTRA_YAML='# B29 arm O-thr (optional, diagnostic): constraints changed in this arm only\nread_thresholds_enabled: true\nlocal_read_size_fail_threshold: 64MiB' arm O1 TA 8 2G auto
echo BATCH-END

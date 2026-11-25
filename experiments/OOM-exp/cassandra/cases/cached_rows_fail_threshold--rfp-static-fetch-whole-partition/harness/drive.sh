#!/usr/bin/env bash
# B29 stage-2 driver on pc72 (2026-11-24 evening rerun, after the pc99 attempt was stopped). Detached (setsid nohup); its PID is in
# /mydata/s4/DRIVER-B29.pid and the session stops it before finishing. Phases, run one at a time:
#   drive.sh setup   : setup.sh, load-data.sh TA, load-data.sh TB
#   drive.sh main    : DIAG, T1-T3, CA1-CA3, CQ1-CQ3, I1-I3 (batch.sh's arm/dump functions)
#   drive.sh qstep   : pre-declared Q step (T at Q=12 x3) — only if T survives at Q=8
#   drive.sh search  : budget search (design 2.9) and the optional O-thr arm
#   drive.sh refine  : one bisect point of the budget search (12 GiB, Q=48)
ROOT=/mydata/s4/b29; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-static-fetch-whole-partition/logs
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
dump(){ local L=$1 F; F=$(ls $ROOT/runs/$L/n1/*.hprof 2>/dev/null | head -1); [ -n "$F" ] || return 0
  nice -n 19 python3 $H/hprofhist.py "$F" 20 > "$REPO/$L/hprofhist.txt" 2>&1
  nice -n 19 python3 $H/hprofstacks.py "$F" OutOfMemoryError > "$REPO/$L/oom-stack-from-hprof.txt" 2>&1
  # added before the search phase (2026-11-24 21:20 EST): threads whose stack holds an RFP completion fetch at the dump
  echo "threads with fetchFromSource in stack: $(nice -n 19 python3 $H/hprofstacks.py "$F" fetchFromSource 2>/dev/null | grep -c '^--- thread')" >> "$REPO/$L/hprof.ls"
  ls -la "$F" >> "$REPO/$L/hprof.ls"; rm -f "$F"; }
arm(){ local L=$1; shift; bash $H/run-arm.sh "$L" "$@" > $ROOT/runs/$L.log 2>&1; grep "END $L" $ROOT/runs/$L.log; dump "$L"; }
mkdir -p $ROOT/runs
case $1 in
  setup)
    bash $H/setup.sh || { log "setup failed"; exit 1; }
    bash $H/load-data.sh TA > $ROOT/runs-loadTA.log 2>&1 || { log "load TA failed rc=$?"; tail -5 $ROOT/runs-loadTA.log; exit 1; }
    bash $H/load-data.sh TB > $ROOT/runs-loadTB.log 2>&1 || { log "load TB failed"; exit 1; }
    log "SETUP-END";;
  main)
    TRACEK=10 arm DIAG TA 1 2G auto diag 0 10
    for i in 1 2 3; do arm T$i TA 8 2G auto; done
    for i in 1 2 3; do arm CA$i TB 8 2G auto; done
    for i in 1 2 3; do arm CQ$i TA 2 2G auto; done
    for i in 1 2 3; do TREE=tree-I arm I$i TA 8 2G auto; done
    log "MAIN-END";;
  qstep)
    for i in 1 2 3; do arm TQ12-$i TA 12 2G auto; done; log "QSTEP-END";;
  search)
    arm S4G TA 16 4G auto
    arm S8G TA 32 8G auto
    arm S15872M TA 64 15872M auto
    EXTRA_YAML='# B29 arm O-thr (optional, diagnostic): constraints changed in this arm only\nread_thresholds_enabled: true\nlocal_read_size_fail_threshold: 64MiB' arm O1 TA 8 2G auto
    log "SEARCH-END";;
  refine)   # added 2026-11-24 21:33 EST after 8 GiB OOM / 15,872 MiB survived: one bisect point (protocol step 4, V7 search upward)
    arm S12G TA 48 12G auto; log "REFINE-END";;
esac

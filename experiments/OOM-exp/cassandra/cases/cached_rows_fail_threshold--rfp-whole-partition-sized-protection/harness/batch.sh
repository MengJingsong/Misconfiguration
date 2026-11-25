#!/usr/bin/env bash
# R24 stage-2 batch on pc82: the frozen arm list in order (design §2.7-§2.11, after calibration: N* = 2,048 (w2k), Q_T = 7, F = 128),
# with the time guard: no lifetime starts after S + 4 h 15 min = 13:31 EST 2026-11-24 (S = 09:16 EST).
#   batch.sh [from-phase]   phases: t c1 i cs s4 s8   (load and calibration run separately)
set -uo pipefail
ROOT=/mydata/s4/r24; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-whole-partition-sized-protection
LAST=$(date -d '2026-11-24 13:31 EST' +%s)
TB=w2k; QT=7
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
hp(){ # background hprof analysis of a run's dump (nice 19)
  if ls $ROOT/runs/$1/n1/*.hprof >/dev/null 2>&1; then
    ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/n1/*.hprof; do python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; done; cp $ROOT/runs/$1/hprofhist.txt $REPO/logs/$1/; grep -B1 -A16 'OutOfMemory\|ReplicaFilteringProtection\|ReadResponse\|DataOutputBuffer' $ROOT/runs/$1/hprofstacks-all.txt | head -200 > $REPO/logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
  fi; }
run(){ # label table CL Q heap direct [steps] [build]
  if [ "$(date +%s)" -ge "$LAST" ]; then log "SKIP $1 (after 13:31 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$@" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  cp $ROOT/runs/$1.out $REPO/logs/$1/run-arm.out 2>/dev/null
  hp "$1"; return 0
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
noom(){ local n=0 x; for x in "$@"; do isoom $x && n=$((n+1)); done; echo $n; }
P=${1:-t}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P"
if at t; then
  run T-1 $TB QUORUM $QT 2G auto; run T-2 $TB QUORUM $QT 2G auto
  if [ "$(noom T-1 T-2)" = 0 ]; then
    QS=$((QT + (QT + 1) / 2)); log "T survived 2 runs at Q=$QT: pre-declared Q step to $QS"; echo $QS > $ROOT/Q
    run TS-1 $TB QUORUM $QS 2G auto; run TS-2 $TB QUORUM $QS 2G auto; run TS-3 $TB QUORUM $QS 2G auto
  else
    run T-3 $TB QUORUM $QT 2G auto; echo $QT > $ROOT/Q
    n=$(noom T-1 T-2 T-3); if [ "$n" = 1 ] || [ "$n" = 2 ]; then log "mixed ($n/3): +2"; run T-4 $TB QUORUM $QT 2G auto; run T-5 $TB QUORUM $QT 2G auto; fi
  fi
fi
Q=$(cat $ROOT/Q 2>/dev/null || echo $QT); PFX=$([ "$Q" = "$QT" ] && echo "" || echo "S")
if at c1; then for k in 1 2 3; do run C1$PFX-$k $TB ONE $Q 2G auto; done; fi
if at i; then for k in 1 2 3; do run I$PFX-$k $TB QUORUM $Q 2G auto "1:20,$Q:160" patched; done; fi
if at cs; then for k in 1 2 3; do run CS$PFX-$k s${TB:1} QUORUM $Q 2G auto; done; fi
if at s4; then run B4G-1 $TB QUORUM $((2*Q)) 4G auto; fi
if at s8; then Q8=$((4*Q)); [ $Q8 -gt 32 ] && Q8=32; run B8G-1 $TB QUORUM $Q8 8G auto; fi
log "batch done"; cat $ROOT/batch.outcomes

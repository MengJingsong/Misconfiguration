#!/usr/bin/env bash
# B22 stage-2 batch on pc82: the frozen arm list in order (design §2.7-§2.11), with the time guards:
# a lifetime starts only if it is estimated to end by 13:15 + its length and it starts before 13:15 EST 2026-11-21.
#   batch.sh [from-phase]   phases: t c1 i cs tq6 s4 s8 e2  (load and diag run separately)
set -uo pipefail
ROOT=/mydata/s4/b22; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-counts-versions-not-bytes
LAST=$(date -d '2026-11-21 13:15 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
run(){ # label table CL T Q heap direct
  if [ "$(date +%s)" -ge "$LAST" ]; then log "SKIP $1 (after 13:15 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$@" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  cp $ROOT/runs/$1.out $REPO/logs/$1/run-arm.out 2>/dev/null
  if ls $ROOT/runs/$1/n1/*.hprof >/dev/null 2>&1; then
    ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/n1/*.hprof; do python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; done; cp $ROOT/runs/$1/hprofhist.txt $REPO/logs/$1/; grep -B1 -A16 'OutOfMemory\|ReplicaFilteringProtection\|ReadResponse\|DataOutputBuffer' $ROOT/runs/$1/hprofstacks-all.txt | head -160 > $REPO/logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
  fi
  return 0
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
noom(){ local n=0 x; for x in "$@"; do isoom $x && n=$((n+1)); done; echo $n; }
P=${1:-t}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P"
Q=5
if at t; then
  run T-1 wide QUORUM 32000 5 2G auto; run T-2 wide QUORUM 32000 5 2G auto
  if [ "$(noom T-1 T-2)" = 0 ]; then log "T survived 2 runs at Q=5: pre-declared Q step to 6"; Q=6; echo 6 > $ROOT/Q; run T6-1 wide QUORUM 32000 6 2G auto; run T6-2 wide QUORUM 32000 6 2G auto; run T6-3 wide QUORUM 32000 6 2G auto
  else run T-3 wide QUORUM 32000 5 2G auto; echo 5 > $ROOT/Q; fi
fi
Q=$(cat $ROOT/Q 2>/dev/null || echo 5); PFX=$([ "$Q" = 6 ] && echo "6" || echo "")
if at c1; then for k in 1 2 3; do run C1$PFX-$k wide ONE 32000 $Q 2G auto; done; fi
if at i; then for k in 1 2 3; do run I$PFX-$k wide QUORUM 2000 $Q 2G auto; done; fi
if at cs; then for k in 1 2 3; do run CS$PFX-$k small QUORUM 32000 $Q 2G auto; done; fi
log "batch (readings arms) done"; cat $ROOT/batch.outcomes

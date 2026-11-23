#!/usr/bin/env bash
# B22 follow-on batch (2026-11-21 08:50 EST). batch.sh (phase t) ran T-1, T-2 (both survived at Q=5) and started the
# pre-declared Q=6 step; its later phases would have run I and C-small at Q=6, but the frozen design (§2.7) moves only T and
# C-ONE to Q=6. batch.sh was stopped by PID while T6-2 ran; this script waits for that lifetime, then runs the rest in the
# design's order with the design's Q per arm: T6-3, C-ONE Q=6 x3, I Q=5 x3, C-small Q=5 x3; then, if T has >= 2 OOMs, the
# budget search (4 GiB/Q 10, 8 GiB/Q 20); else E2 (2 GiB heap / 1,024 MiB direct, T at Q=6) x3 in the slack window.
# No lifetime starts at or after 13:15 EST.
set -uo pipefail
ROOT=/mydata/s4/b22; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-counts-versions-not-bytes
LAST=$(date -d '2026-11-21 13:15 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH2 $*"; }
run(){ # label table CL T Q heap direct
  if [ "$(date +%s)" -ge "$LAST" ]; then log "SKIP $1 (after 13:15 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$@" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  cp $ROOT/runs/$1.out $REPO/logs/$1/run-arm.out 2>/dev/null
  awk -F, -v r="$1" '$7==r' $ROOT/netpoll.csv > $REPO/logs/$1/netpoll.csv 2>/dev/null
  if ls $ROOT/runs/$1/n1/*.hprof >/dev/null 2>&1; then
    ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/n1/*.hprof; do python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; done; cp $ROOT/runs/$1/hprofhist.txt $REPO/logs/$1/; grep -B1 -A16 'OutOfMemory\|ReplicaFilteringProtection\|ReadResponse\|DataOutputBuffer' $ROOT/runs/$1/hprofstacks-all.txt | head -160 > $REPO/logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
  fi
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
while pgrep -f "run-arm.sh T6-2" > /dev/null; do sleep 5; done
log "T6-2 ended: $(cat $ROOT/runs/T6-2/outcome)"; echo "T6-2 $(cat $ROOT/runs/T6-2/outcome)" >> $ROOT/batch.outcomes
cp $ROOT/runs/T6-2.out $REPO/logs/T6-2/run-arm.out 2>/dev/null; awk -F, '$7=="T6-2"' $ROOT/netpoll.csv > $REPO/logs/T6-2/netpoll.csv
awk -F, '$7=="T6-1"' $ROOT/netpoll.csv > $REPO/logs/T6-1/netpoll.csv
run T6-3 wide QUORUM 32000 6 2G auto
for k in 1 2 3; do run C16-$k wide ONE 32000 6 2G auto; done
for k in 1 2 3; do run I-$k wide QUORUM 2000 5 2G auto; done
for k in 1 2 3; do run CS-$k small QUORUM 32000 5 2G auto; done
n=0; for x in T-1 T-2 T6-1 T6-2 T6-3; do isoom $x && n=$((n+1)); done
if [ $n -ge 2 ]; then log "T OOMs=$n: budget search"; run S4G wide QUORUM 32000 10 4G auto; run S8G wide QUORUM 32000 20 8G auto
else log "T OOMs=$n: no budget search (needs >= 2); slack -> E2"; for k in 1 2 3; do run E2-$k wide QUORUM 32000 6 2G 1024M; done; fi
log "batch2 done"; cat $ROOT/batch.outcomes

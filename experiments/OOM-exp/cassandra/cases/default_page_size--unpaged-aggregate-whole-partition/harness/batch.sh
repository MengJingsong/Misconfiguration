#!/usr/bin/env bash
# U10 stage-2 batch on pc82: the frozen label list in order, with the design's time guards (a lifetime runs only if it is
# estimated to end by 17:30 EST 2026-11-18). hprof summaries run afterwards in the background at nice 19.
#   NT=<n_T> batch.sh [from-phase]   phases: cal t m i1 textra cal4 cal8 cal16 cal31 i2 rep pgrs
# Budget-search sweeps carry the design's "+1 step if no OOM" as their last step (the sweep stops at the first OOM anyway).
set -uo pipefail
ROOT=/mydata/s4/u10-w4; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/default_page_size--unpaged-aggregate-whole-partition
END=$(date -d '2026-11-18 17:30 EST' +%s)
N=${NT:?set NT}
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
fits(){ [ $(( $(date +%s) + $1 )) -le $END ]; }
run(){ # label arm heap direct fetch kind steps est_secs
  if ! fits "$8"; then log "SKIP $1 (would end after 17:30 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" "$6" "$7" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  cp $ROOT/runs/$1.out $REPO/logs/$1/run-arm.out 2>/dev/null
  ls $ROOT/runs/$1/*.hprof >/dev/null 2>&1 && ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/*.hprof; do sz=\$(stat -c %s \$f); [ \$sz -gt 9000000000 ] && { echo \"hprof \$sz B > 9e9: histogram skipped\" > $ROOT/runs/$1/hprofhist.txt; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; continue; }; python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; done; cp $ROOT/runs/$1/hprofhist.txt $REPO/logs/$1/ 2>/dev/null; grep -B1 -A14 'LocalDataResponse\|DataOutputBuffer\|AggregationQueryPager\|OutOfMemory' $ROOT/runs/$1/hprofstacks-all.txt | head -150 > $REPO/logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
  return 0
}
cT(){ sed -n 's/^OOM c=\([0-9]*\) n=\([0-9]*\) .*/\1/p' $ROOT/runs/$1/outcome 2>/dev/null; }
nAt(){ sed -n 's/^OOM c=\([0-9]*\) n=\([0-9]*\) .*/\2/p' $ROOT/runs/$1/outcome 2>/dev/null; }
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
P=${1:-cal}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P n_T=$N"
if at cal; then
  run CAL-2G A 2048M 1024M off agg "1:4096:20,1:16384:40,1:32768:40,1:$N:40,2:$N:40,3:$N:40,4:$N:40,6:$N:40" 480
  if ! isoom CAL-2G; then grep -q SURVIVED $ROOT/runs/CAL-2G/outcome || { log "CAL-2G neither OOM nor survived: stop for inspection"; exit 1; }
    run CAL-2G-x A 2048M 1024M off agg "8:$N:40,12:$N:40,16:$N:40,24:$N:40,32:$N:40" 380; fi
fi
C=$(cT CAL-2G); TN=$(nAt CAL-2G); [ -z "$C" ] && { C=$(cT CAL-2G-x); TN=$(nAt CAL-2G-x); }
# c_T rule: smallest c at n_T reaching OOM; if CAL-2G OOMs at a smaller n with c = 1, c_T = 1 (and the T arms keep n_T)
[ -n "${CT_OVERRIDE:-}" ] && C=$CT_OVERRIDE
echo "c_T=$C (OOM step n=$TN) n_T=$N" > $ROOT/c_T; log "c_T=${C:-none} (OOM step n=${TN:-none})"
if [ -z "$C" ]; then log "no c_T: no OOM up to the sweep's end; T/M/I not run"; exit 0; fi
if at t; then for k in 1 2 3; do run T-2G-$k A 2048M 1024M off agg "1:4096:20,$C:$N:160" 330; done; fi
if at m; then for k in 1 2 3; do run M-2G-$k A 2048M 1024M 5000 agg "1:4096:20,$C:$N:160" 330; done; fi
if at i1; then for k in 1 2 3; do run I1-2G-$k I1 2048M 1024M off agg "1:4096:20,$C:$N:160" 330; done; fi
if at textra; then n=0; for k in 1 2 3; do isoom T-2G-$k && n=$((n+1)); done
  if [ $n = 2 ]; then for k in 4 5; do run T-2G-$k A 2048M 1024M off agg "1:4096:20,$C:$N:160" 330; done; fi; fi
if at cal4; then run CAL-4G A 4096M 2048M off agg "1:4096:20,1:$N:40,2:$N:40,3:$N:40,4:$N:40,6:$N:40,8:$N:40" 450; fi
if at cal8; then run CAL-8G A 8192M 4096M off agg "1:4096:20,2:$N:40,3:$N:40,4:$N:40,6:$N:40,8:$N:40,10:$N:40,12:$N:40" 500; fi
if at cal16; then run CAL-16G A 16384M 8192M off agg "1:4096:20,4:$N:40,6:$N:40,8:$N:40,10:$N:40,12:$N:40,16:$N:40,20:$N:40" 560; fi
if at cal31; then run CAL-31G A 31744M 15872M off agg "1:4096:20,8:$N:40,12:$N:40,16:$N:40,20:$N:40,24:$N:40,32:$N:40,40:$N:40,48:$N:40" 780; fi
if at i2; then
  [ -f $ROOT/tree-i2/build/classes/main/org/apache/cassandra/service/pager/AggregationQueryPager.class ] || { log "no I2 build"; }
  for k in 1 2 3; do run I2-2G-$k I2 2048M 1024M off agg "1:4096:20,$C:$N:160" 330; done
fi
if at rep; then
  for X in CAL-31G:31744M:15872M:600 CAL-16G:16384M:8192M:420 CAL-8G:8192M:4096M:360 CAL-4G:4096M:2048M:340; do
    IFS=: read -r lab hp dm est <<< "$X"
    if isoom $lab; then c=$(cT $lab); for k in 1 2; do run REP-$hp-$k A $hp $dm off agg "1:4096:20,$c:$N:160" $est; done; break; fi
  done
fi
if at pgrs; then run P-GRS A 2048M 1024M off grs "1:16384:40,1:32768:40,1:65536:40" 280; fi
log "batch done"; cat $ROOT/batch.outcomes

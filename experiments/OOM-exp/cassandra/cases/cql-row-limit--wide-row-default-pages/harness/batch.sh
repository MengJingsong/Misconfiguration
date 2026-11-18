#!/usr/bin/env bash
# U4 stage-2 batch on pc75: the frozen arm list in order, with the design's time guards.
# Each lifetime runs only if it is estimated to end by 02:10 EST 2026-11-18 (no new lifetime after 01:55 unless it ends
# by 02:10). hprof summaries run afterwards in the background at nice 19.
#   batch.sh [from-phase]   phases: load ic cal t m i textra cal4 cal8 calauto rep e2
set -uo pipefail
ROOT=/mydata/s4/u4-w1; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cql-row-limit--wide-row-default-pages
END=$(date -d '2026-11-18 02:10 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
fits(){ [ $(( $(date +%s) + $1 )) -le $END ]; }
run(){ # label arm heap direct fetch steps est_secs
  if ! fits "$7"; then log "SKIP $1 (would end after 02:10 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" "$6" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  cp $ROOT/runs/$1.out $REPO/logs/$1/run-arm.out 2>/dev/null
  ls $ROOT/runs/$1/*.hprof >/dev/null 2>&1 && ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/*.hprof; do python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; done; cp $ROOT/runs/$1/hprofhist.txt $REPO/logs/$1/; grep -B1 -A14 'LocalDataResponse\|DataOutputBuffer\|ResultSetBuilder\|OutOfMemory' $ROOT/runs/$1/hprofstacks-all.txt | head -120 > $REPO/logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
  return 0
}
cT(){ sed -n 's/^OOM c=\([0-9]*\) .*/\1/p' $ROOT/runs/$1/outcome 2>/dev/null; }
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
P=${1:-load}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P"
if at load; then bash $H/load-data.sh > $ROOT/runs/LOAD.out 2>&1; log "LOAD done"; tail -5 $ROOT/runs/LOAD.out; mkdir -p $REPO/logs/LOAD; cp $ROOT/runs/LOAD.out $REPO/logs/LOAD/; fi
if at ic; then
  # IC (instrument check, not a reading): one first-page read at fetch 5000 and 500 before the 1:30 load
  run IC A 2G auto 5000 "1:30" 300
fi
if at cal; then
  run CAL-2G A 2G auto 5000 "1:60,2:60,3:60,4:60,6:60,8:60" 560
  if ! isoom CAL-2G; then grep -q SURVIVED $ROOT/runs/CAL-2G/outcome || { log "CAL-2G neither OOM nor survived: stop for inspection"; exit 1; }
    run CAL-2G-x A 2G auto 5000 "12:60,16:60,24:60,32:60" 440; fi
fi
C=$(cT CAL-2G); [ -z "$C" ] && C=$(cT CAL-2G-x)
[ -n "${CT_OVERRIDE:-}" ] && C=$CT_OVERRIDE
echo "c_T=$C" > $ROOT/c_T; log "c_T=${C:-none}"
if [ -z "$C" ]; then log "no c_T: no OOM up to the sweep's end; T/M/I not run"; exit 0; fi
if at t; then for k in 1 2 3; do run T-2G-$k A 2G auto 5000 "1:20,$C:160" 300; done; fi
if at m; then for k in 1 2 3; do run M-2G-$k A 2G auto 500 "1:20,$C:160" 300; done; fi
if at i; then for k in 1 2 3; do run I-2G-$k I 2G auto 5000 "1:20,$C:160" 300; done; fi
if at textra; then n=0; for k in 1 2 3; do isoom T-2G-$k && n=$((n+1)); done
  if [ $n = 2 ]; then for k in 4 5; do run T-2G-$k A 2G auto 5000 "1:20,$C:160" 300; done; fi; fi
if at cal4; then run CAL-4G A 4G 2048M 5000 "4:60,6:60,7:60,8:60,10:60,12:60,16:60,20:60" 700; fi
if at cal8; then run CAL-8G A 8G 4096M 5000 "10:60,12:60,14:60,16:60,20:60,24:60,32:60" 660; fi
if at calauto; then run CAL-auto A 15872M 7936M 5000 "20:60,24:60,28:60,32:60,40:60,48:60,64:60" 720; fi
if at rep; then
  for X in CAL-auto:15872M:7936M CAL-8G:8G:4096M CAL-4G:4G:2048M; do
    IFS=: read -r lab hp dm <<< "$X"
    if isoom $lab; then c=$(cT $lab); for k in 1 2; do run REP-$hp-$k A $hp $dm 5000 "1:20,$c:160" 360; done; break; fi
  done
fi
if at e2; then for k in 1 2 3; do run E2-2G1G-$k A 2G 1024M 5000 "1:20,$C:160" 300; done; fi
log "batch done"; cat $ROOT/batch.outcomes

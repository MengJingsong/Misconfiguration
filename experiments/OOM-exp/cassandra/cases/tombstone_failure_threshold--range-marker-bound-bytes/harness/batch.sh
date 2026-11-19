#!/usr/bin/env bash
# B16 stage-2 batch on ms0611: the frozen arm list in priority order, with the design's time guards
# (a lifetime runs only if it is estimated to end by 17:45 EST 2026-11-18; everything stopped by 17:50).
# hprof summaries run afterwards in the background at nice 19, one at a time (flock), then the hprof is deleted.
#   batch.sh [from-phase]   phases: ic cal t m i ert1 budget ert23 i2 calm rep
set -uo pipefail
ROOT=/mydata/s4/b16-w4; H=$ROOT/harness
END=$(date -d '2026-11-18 17:45 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
fits(){ [ $(( $(date +%s) + $1 )) -le $END ]; }
est(){ local s=0 x; for x in ${1//,/ }; do s=$(( s + ${x#*:} )); done; echo $(( s + 15 + 150 )); }
run(){ # label arm heap tbl steps
  local e; e=$(est "$5")
  if ! fits "$e"; then log "SKIP $1 (est ${e}s, would end after 17:45 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  mkdir -p $ROOT/repo-logs/$1; cp $ROOT/runs/$1.out $ROOT/repo-logs/$1/run-arm.out 2>/dev/null
  if ls $ROOT/runs/$1/*.hprof >/dev/null 2>&1; then
    ( setsid nohup flock $ROOT/hprof.lock nice -n 19 bash -c "for f in $ROOT/runs/$1/*.hprof; do ls -l \$f > $ROOT/repo-logs/$1/hprof.ls; python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; rm -f \$f; done; cp $ROOT/runs/$1/hprofhist.txt $ROOT/repo-logs/$1/; grep -B1 -A14 'expandToFit\|LocalDataResponse\|OutOfMemory' $ROOT/runs/$1/hprofstacks-all.txt | head -120 > $ROOT/repo-logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
  fi
  return 0
}
cT(){ sed -n 's/^OOM c=\([0-9]*\) .*/\1/p' $ROOT/runs/$1/outcome 2>/dev/null; }
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
P=${1:-ic}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P"
if at ic; then run IC R 8G t "" ; fi
if at cal; then
  run CAL-2G A 2G t "1:90,2:60,3:60"
  if ! isoom CAL-2G; then grep -q SURVIVED $ROOT/runs/CAL-2G/outcome || { log "CAL-2G neither OOM nor survived: stop for inspection"; exit 1; }
    run CAL-2G-x A 2G t "4:60,6:60,8:60"; fi
fi
C=$(cT CAL-2G); [ -z "$C" ] && C=$(cT CAL-2G-x)
[ -n "${CT_OVERRIDE:-}" ] && C=$CT_OVERRIDE
echo "c_T=$C" > $ROOT/c_T; log "c_T=${C:-none}"
if [ -z "$C" ]; then log "no c_T: no OOM up to c=8 at 2G; T/M/I not run (false-positive rule: extend once to 12..32)"
  run CAL-2G-x2 A 2G t "12:60,16:60,24:60,32:60"; log "batch done"; cat $ROOT/batch.outcomes; exit 0; fi
if at t; then for k in 1 2 3; do run T-2G-$k A 2G t "$C:120"; done
  n=0; for k in 1 2 3; do isoom T-2G-$k && n=$((n+1)); done
  if [ $n = 2 ]; then for k in 4 5; do run T-2G-$k A 2G t "$C:120"; done; fi; fi
if at m; then for k in 1 2 3; do run M-2G-$k A 2G m "$C:120"; done; fi
if at i; then for k in 1 2 3; do run I-2G-$k I 2G t "$C:120"; done; fi
if at ert1; then run E-RT-2G-1 R 2G t "$C:120"; fi
if at budget; then
  run CAL-4G A 4G t "1:90,2:60,3:60,4:60"
  run CAL-8G A 8G t "2:60,3:60,4:60,6:60,8:60"
  run CAL-16G A 16384M t "3:90,4:90,6:90,8:90,12:90"
  run CAL-31744M A 31744M t "6:90,8:90,12:90,16:90,24:90,32:90"
fi
if at ert23; then for k in 2 3; do run E-RT-2G-$k R 2G t "$C:120"; done; fi
if at i2; then
  if [ -f $ROOT/tree-i2/build/apache-cassandra-5.0.9-SNAPSHOT.jar ]; then for k in 1 2 3; do run I2-2G-$k I2 2G t "$C:120"; done
  else log "I2 build missing: I2 not run"; fi
fi
if at calm; then run CAL-M-2G A 2G m "2:60,4:60,6:60,8:60,12:60,16:60,24:60,32:60"; fi
if at rep; then
  for X in CAL-31744M:31744M CAL-16G:16384M CAL-8G:8G CAL-4G:4G; do
    IFS=: read -r lab hp <<< "$X"
    if isoom $lab; then c=$(cT $lab); for k in 1 2; do run REP-$hp-$k A $hp t "$c:120"; done; break; fi
  done
fi
log "batch done"; cat $ROOT/batch.outcomes

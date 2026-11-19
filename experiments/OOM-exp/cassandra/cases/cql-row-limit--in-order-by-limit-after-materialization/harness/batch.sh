#!/usr/bin/env bash
# B17 stage-2 batch on pc72 after CAL-2G (k_T = 4, c_T = 1 from CAL-2G; k5 = 8, k_c = 6 from PROBE): the frozen arm list in
# order, with the design's time guard (no lifetime starts after 17:15 EST unless it is estimated to end by 17:30 EST).
# hprof summaries run afterwards in the background at nice 19 (heaps <= 8 GiB only).
#   batch.sh [from-phase]   phases: t m i textra cal4 cal8 cal31 rep i2
set -uo pipefail
ROOT=/mydata/s4/b17-w4; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cql-row-limit--in-order-by-limit-after-materialization
LAST=$(date -d '2026-11-18 17:15 EST' +%s); END=$(date -d '2026-11-18 17:30 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
WU="sweep:M:4:5:1000;sweep:T:1:1:0;idle:20000"
hp(){ # background hprof summary of lifetime $1
  ls $ROOT/runs/$1/*.hprof >/dev/null 2>&1 || return 0
  ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/*.hprof; do python3 $H/hprofhist.py \$f 30 > $ROOT/runs/$1/hprofhist.txt 2>&1; python3 $H/hprofstacks.py \$f > $ROOT/runs/$1/hprofstacks-all.txt 2>&1; done; cp $ROOT/runs/$1/hprofhist.txt $REPO/logs/$1/; grep -B1 -A14 'LocalDataResponse\|DataOutputBuffer\|ResultSetBuilder\|SelectStatement\|OutOfMemory' $ROOT/runs/$1/hprofstacks-all.txt | head -150 > $REPO/logs/$1/hprofstacks.txt" < /dev/null > /dev/null 2>&1 & )
}
run(){ # label arm heap direct spec est_secs [hprof:yes|no]
  local now; now=$(date +%s)
  if [ $now -gt $LAST ] && [ $(( now + $6 )) -gt $END ] || [ $(( now + $6 )) -gt $END ]; then log "SKIP $1 (time guard)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> ${o:0:120}"
  cp $ROOT/runs/$1.out $REPO/logs/$1/run-arm.out 2>/dev/null
  [ "${7:-yes}" = yes ] && hp "$1"
  return 0
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
P=${1:-t}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P"
if at t; then for k in 1 2 3; do run T-2G-$k A 2G 1024M "$WU;sweep:T:4:3:10000" 240; done; fi
if at m; then for k in 1 2 3; do run M-2G-$k A 2G 1024M "$WU;sweep:M:4:3:10000;run:M:4:4/120" 330; done; fi
if at i; then for k in 1 2 3; do run I-2G-$k A 2G 1024M "$WU;sweep:I:4:3:10000" 240; done; fi
if at textra; then n=0; for k in 1 2 3; do isoom T-2G-$k && n=$((n+1)); done
  if [ $n = 2 ]; then for k in 4 5; do run T-2G-$k A 2G 1024M "$WU;sweep:T:4:3:10000" 240; done; fi; fi
if at cal4; then run CAL-4G A 4G 2048M "sweep:T:6,7,8,9,10:3:10000" 420; fi
if at cal8; then run CAL-8G A 8G 4096M "run:T:6:4/45,6/45,8/45,12/45,16/45,24/45,32/45" 480; fi
if at cal31; then run CAL-31G A 31744M 15872M "run:T:6:12/45,16/45,24/45,32/45,48/45,64/45,96/45" 600 no; fi
if at rep; then
  for X in CAL-31G:31744M:15872M CAL-8G:8G:4096M CAL-4G:4G:2048M; do
    IFS=: read -r lab hp dm <<< "$X"
    if isoom $lab; then
      if [ $lab = CAL-4G ]; then
        k=$(sed -n 's/.*"Q":"T","k":\([0-9]*\).*/\1/p' $ROOT/runs/$lab/client.out | tail -1); sp="sweep:T:$k:3:10000"
      else
        c=$(grep '^S [0-9]' $ROOT/runs/$lab/client.out | tail -1 | cut -d, -f2); sp="run:T:6:$c/120"
      fi
      log "REP at $lab: $sp"
      for k2 in 1 2; do run REP-$hp-$k2 A $hp $dm "$WU;$sp" 420 $([ $hp = 31744M ] && echo no || echo yes); done; break
    fi
  done
fi
if at i2; then for k in 1 2 3; do run I2-2G-$k I2 2G 1024M "$WU;sweep:T:4:3:10000" 240; done; fi
log "batch done"; cat $ROOT/batch.outcomes

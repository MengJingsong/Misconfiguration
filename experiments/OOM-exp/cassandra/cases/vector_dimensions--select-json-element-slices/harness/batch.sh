#!/usr/bin/env bash
# U8 stage-2 batch on ms0640: the frozen arm list in order, with the design's time guards (no new lifetime after
# 17:35 EST 2026-11-18). Pre-declared dials: T at N=2, raise to 3 then 4 if the first T run survives.
#   batch.sh <phase...>   phases: d1 t c1 i c2 b4 b8 b16 brep
set -uo pipefail
ROOT=/mydata/s4/u8-w4; H=$ROOT/harness
LAST=$(TZ=America/New_York date -d '2026-11-18 17:35' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
run(){ # label arm heap mode N R
  if [ "$(date +%s)" -gt $LAST ]; then log "SKIP $1 (after 17:35 EST)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$@" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> $o"
  cp $ROOT/runs/$1.out $ROOT/out/$1/run-arm.out 2>/dev/null
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
NS=$(cat $ROOT/Nstar 2>/dev/null || echo 2)
for P in "$@"; do
  case $P in
    d1) run D1-8G A 8G json 1 3;;
    t) run T-2G-N2-1 A 2G json 2 5
       if isoom T-2G-N2-1; then NS=2; else
         run T-2G-N3-1 A 2G json 3 5; if isoom T-2G-N3-1; then NS=3; else run T-2G-N4-1 A 2G json 4 5; isoom T-2G-N4-1 && NS=4 || NS=none; fi; fi
       echo $NS > $ROOT/Nstar; log "N*=$NS"
       [ "$NS" = none ] && { log "no OOM up to N=4 at 2 GiB"; exit 0; }
       for k in 2 3; do run T-2G-N$NS-$k A 2G json $NS 5; done;;
    c1) for k in 1 2 3; do run C1-2G-N$NS-$k A 2G plain $NS 5; done;;
    i)  for k in 1 2 3; do run I-2G-N$NS-$k I 2G json $NS 5; done;;
    c2) for k in 1 2 3; do run C2-2G-N1-$k A 2G json 1 5; done;;
    b4) run B-4G-N6-1 A 4G json 6 3;;
    b8) run B-8G-N11-1 A 8G json 11 3;;
    b16) run B-16G-N21-1 A 16G json 21 3;;
    brep) for X in 16G:21 8G:11 4G:6; do IFS=: read -r hp n <<< "$X"
            if isoom B-$hp-N$n-1; then for k in 2 3; do run B-$hp-N$n-$k A $hp json $n 3; done; break; fi; done;;
    *) log "bad phase $P";;
  esac
done
log "batch done"; cat $ROOT/batch.outcomes

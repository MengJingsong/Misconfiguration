#!/usr/bin/env bash
# B21 stage-2 batch on ms0604 after CAL-2G: the frozen lifetime list in order, with the design's time guard (no lifetime
# starts after 13:15 EST) and drop order (IC-OVER -> REP -> CAL-15872M -> IL-2G -> CAL-8G -> histogram probes -> CAL-4G).
#   batch.sh <c_T> <phase,phase,...>   phases: t m i textra cal4 cal8 il cal15872 rep
# Warm-up per design: 3 single queries of the arm's variant, 20 s idle; then c_T for 120 s.
set -uo pipefail
CT=$1; PH=",$2,"
ROOT=/mydata/s4/b21; H=$ROOT/harness
LAST=$(date -d '2026-11-21 13:15 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
run(){ # label arm heap spec hist [nodump]
  if [ $(date +%s) -gt $LAST ]; then log "SKIP $1 (13:15 EST guard)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  if [ "${6:-}" = nodump ]; then NODUMP=1 bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" > $ROOT/runs/$1.out 2>&1
  else bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" > $ROOT/runs/$1.out 2>&1; fi
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> ${o:0:140}"
  cp $ROOT/runs/$1.out $ROOT/out/$1/run-arm.out 2>/dev/null
  return 0
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
on(){ [[ $PH == *",$1,"* ]]; }
WT="one:T:1000:100:3:0;idle:20000"; WM="one:M:1000:100:3:0;idle:20000"; WL="one:T:250:100:3:0;idle:20000"
log "start c_T=$CT phases=$2"
if on t; then for k in 1 2 3; do h=0; [ $k = 3 ] && h=$CT:30; run T-2G-$k A 2G "$WT;run:T:1000:100:$CT/120" $h; done; fi
if on m; then for k in 1 2 3; do h=0; [ $k = 3 ] && h=$CT:30; run M-2G-$k A 2G "$WM;run:M:1000:100:$CT/120" $h; done; fi
if on i; then for k in 1 2 3; do run I-2G-$k I 2G "$WT;run:T:1000:100:$CT/120" 0; done; fi
if on textra; then n=0; for k in 1 2 3; do isoom T-2G-$k && n=$((n+1)); done
  if [ $n = 2 ]; then for k in 4 5; do run T-2G-$k A 2G "$WT;run:T:1000:100:$CT/120" 0; done; fi; fi
if on cal4; then run CAL-4G A 4G "run:T:1000:100:8/45,10/45,13/45,16/45,24/45,32/45" 0; fi
if on cal8; then fr=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9); nd=""; [ "$fr" -lt 12 ] && nd=nodump
  run CAL-8G A 8G "run:T:1000:100:16/45,24/45,32/45,48/45,64/45" 0 $nd; fi
if on il; then for k in 1 2 3; do run IL-2G-$k A 2G "$WL;run:T:250:100:$CT/120" 0; done; fi
if on cal15872; then fr=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9); nd=""; [ "$fr" -lt 20 ] && nd=nodump
  run CAL-15872M A 15872M "run:T:1000:100:32/45,48/45,64/45,96/45,128/45" 0 $nd; fi
if on rep; then
  for X in CAL-15872M:15872M CAL-8G:8G CAL-4G:4G; do
    IFS=: read -r lab hp <<< "$X"
    if isoom $lab; then
      c=$(grep '^S [0-9]' $ROOT/runs/$lab/client.out | tail -1 | cut -d, -f2)
      nd=""; [ $hp != 4G ] && nd=nodump
      log "REP at $lab: c=$c"
      for k2 in 1 2; do run REP-$hp-$k2 A $hp "$WT;run:T:1000:100:$c/120" 0 $nd; done; break
    fi
  done
fi
log "batch done"; cat $ROOT/batch.outcomes

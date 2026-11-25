#!/usr/bin/env bash
# B26 stage-2 batch on pc91 after VERIFY+PROBE and CAL-RET-8G (c = 4 kept: PROBE p99 with sampling < 400 ms; default
# 10 s window kept: 35-45 sampled S16 reads/s >= 25, 69.9 unsampled S30 reads/s >= 30). Frozen arm list, T/M/I
# interleaved, then the upward search; time guard: no lifetime starts after T0 + 3 h 30 min (15:21 EST).
# hprof summaries (bigarrays.py, retainers.py) run afterwards in the background at nice 19.
#   batch.sh [from-phase]   phases: tmi textra cal4 cal8 cal15 bnd dose auto
set -uo pipefail
ROOT=/mydata/s4/b26; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/profileload-capacity--local-read-time-sampler-cql-strings
LAST=$(date -d '2026-11-24 15:21 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
hp(){ # background hprof summary of lifetime $1, shape length $2; delete the dump afterwards when $3 = del
  ls $ROOT/runs/$1/*.hprof >/dev/null 2>&1 || return 0
  ( setsid nohup nice -n 19 bash -c "for f in $ROOT/runs/$1/*.hprof; do python3 $H/bigarrays.py \$f 8388608 > $ROOT/runs/$1/bigarrays.txt 2>&1; python3 $H/retainers.py \$f byte $2 6 > $ROOT/runs/$1/retainers.txt 2>&1; done; cp $ROOT/runs/$1/bigarrays.txt $ROOT/runs/$1/retainers.txt $REPO/logs/$1/; [ '$3' = del ] && rm -f $ROOT/runs/$1/*.hprof; echo done > $ROOT/runs/$1/hp.done" < /dev/null > /dev/null 2>&1 & )
}
run(){ # label arm heap shape tables c "session" hprof-len [del]
  if [ $(date +%s) -gt $LAST ]; then log "SKIP $1 (time guard)"; echo "$1 skipped-time" >> $ROOT/batch.outcomes; return 1; fi
  bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" "$6" "$7" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch.outcomes; log "$1 -> ${o:0:150}"
  grep -v CompileCommand $ROOT/runs/$1.out > $REPO/logs/$1/run-arm.out 2>/dev/null
  hp "$1" "$8" "${9:-keep}"
  return 0
}
isoom(){ grep -q '^OOM' $ROOT/runs/$1/outcome 2>/dev/null; }
P=${1:-tmi}; go=0
at(){ [ "$P" = "$1" ] && go=1; [ $go = 1 ]; }
log "start phase $P"
if at tmi; then for k in 1 2 3; do
  run T-2G-$k A 2G S16 t1 4 "profileload b26 t1" 16008088
  run M-2G-$k A 2G S16 t1 4 "tpstats" 16008088
  run I-2G-$k IV 2G S16 t1 4 "profileload b26 t1" 16008088
done; fi
if at textra; then n=0; for k in 1 2 3; do isoom T-2G-$k && n=$((n+1)); done
  if [ $n = 2 ]; then for k in 4 5; do run T-2G-$k A 2G S16 t1 4 "profileload b26 t1" 16008088; done; fi; fi
if at cal4; then run CAL-4G A 4G S16 t1 4 "profileload b26 t1" 16008088; fi
if at cal8; then run CAL-8G A 8G S30 t1 4 "profileload b26 t1" 30015088 del; fi
if at cal15; then run CAL-15872M A 15872M S30 t1,t2 8 "profileload b26 * 60000" 30015088 del; fi
if at bnd; then run BND-15872M-1T A 15872M S30 t1 8 "profileload b26 t1 60000" 30015088 del; fi
if at dose; then for k in 1 2 3; do run D-2G-$k A 2G S16 t1 4 "profileload b26 t1 -s 32" 16008088; done; fi
if at auto; then run CAL-AUTO A AUTO S30 t1,t2,t3,t4 8 "profileload b26 * 60000" 30015088 del; fi
log "batch done"; cat $ROOT/batch.outcomes

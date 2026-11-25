#!/usr/bin/env bash
# B26 stage-2 retry session (2026-11-24, T0 15:01:46 EST): second batch on pc91, upward search only.
#  - CAL-15872M and CAL-AUTO again: the first attempt's lifetimes ran no session (bin/nodetool globbed '*', fixed in
#    run-arm.sh); their folders were renamed to <label>-try1-invalid.
#  - CAL-4G-REP1/2 and CAL-8G-REP1/2: the frozen "+2 REP if time" of CAL-4G / CAL-8G (both survived once).
# Order = reverse of the frozen drop order among what is left. Time guard: no lifetime starts after T0 + 3 h 30 min.
# hprof summaries with the real rendered lengths (S16 16,008,071/072 B; S30 30,015,071/072 B: pk with 1 or 2 digits).
set -uo pipefail
ROOT=/mydata/s4/b26; H=$ROOT/harness
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/profileload-capacity--local-read-time-sampler-cql-strings
LAST=$(date -d '2026-11-24 18:31 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH2 $*"; }
hp(){ # hprof summary of lifetime $1 (shape length $2 = the 2-digit-pk length), dump deleted afterwards when $3 = del
  ls $ROOT/runs/$1/*.hprof >/dev/null 2>&1 || return 0
  for f in $ROOT/runs/$1/*.hprof; do
    nice -n 10 python3 -I $H/bigarrays.py $f 8388608 > $ROOT/runs/$1/bigarrays.txt 2>&1
    nice -n 10 python3 -I $H/hprof_oome_thread.py $f 30 > $ROOT/runs/$1/oome-thread.txt 2>&1
    nice -n 10 python3 -I $H/retainers.py $f byte $2 7 > $ROOT/runs/$1/retainers.txt 2>&1
  done
  cp $ROOT/runs/$1/bigarrays.txt $ROOT/runs/$1/retainers.txt $ROOT/runs/$1/oome-thread.txt $REPO/logs/$1/
  ls -la $ROOT/runs/$1/*.hprof > $REPO/logs/$1/hprof.ls
  [ "$3" = del ] && rm -f $ROOT/runs/$1/*.hprof
  return 0
}
run(){ # label arm heap shape tables c "session" hprof-len [del]
  if [ $(date +%s) -gt $LAST ]; then log "SKIP $1 (time guard)"; echo "$1 skipped-time" >> $ROOT/batch2.outcomes; return 1; fi
  bash $H/run-arm.sh "$1" "$2" "$3" "$4" "$5" "$6" "$7" > $ROOT/runs/$1.out 2>&1
  local o; o=$(cat $ROOT/runs/$1/outcome 2>/dev/null || echo "NO-OUTCOME")
  echo "$1 $o" >> $ROOT/batch2.outcomes; log "$1 -> ${o:0:150}"
  grep -v CompileCommand $ROOT/runs/$1.out > $REPO/logs/$1/run-arm.out 2>/dev/null
  hp "$1" "$8" "${9:-del}"
  return 0
}
log "start"
run CAL-15872M     A 15872M S30 t1,t2       8 "profileload b26 * 60000" 30015072 del
run CAL-4G-REP1    A 4G     S16 t1          4 "profileload b26 t1"      16008072 del
run CAL-4G-REP2    A 4G     S16 t1          4 "profileload b26 t1"      16008072 del
run CAL-8G-REP1    A 8G     S30 t1          4 "profileload b26 t1"      30015072 del
run CAL-8G-REP2    A 8G     S30 t1          4 "profileload b26 t1"      30015072 del
run CAL-AUTO       A AUTO   S30 t1,t2,t3,t4 8 "profileload b26 * 60000" 30015072 del
log "batch2 done"; cat $ROOT/batch2.outcomes

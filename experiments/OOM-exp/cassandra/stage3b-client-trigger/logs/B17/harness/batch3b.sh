#!/usr/bin/env bash
# B17 3-b confirm batch (pc75, 2026-11-23): the verified test arm T-2G under auth, as the data role, one clean lifetime per
# label (fresh template copy each), each followed by the dump scan (analyze.sh deletes the .hprof).
#   batch3b.sh <label,label,...>   label T-AUTH-2G-<k> (role attacker) or TSEL-AUTH-2G-<k> (role reader, SELECT only)
# Per lifetime exactly as stage 2's T-2G: heap 2G / direct 1024M, warm-up M k=4 x5 (1 s apart), T k=1 x1, 20 s idle; then
# T k=4 x3, 10 s apart (the first T k=4 query draws pks 15, 10, 1, 8). Arm AUTH. Victim tenant 60 s before, 30 s after.
set -uo pipefail
ROOT=/mydata/s4/3b-B17; H=$ROOT/harness
LAST=$(date -d '2026-11-23 21:00 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
WU="sweep:M:4:5:1000;sweep:T:1:1:0;idle:20000"
for L in ${1//,/ }; do
  if [ $(date +%s) -gt $LAST ]; then log "SKIP $L (wall-clock cap)"; echo "$L skipped-time" >> $ROOT/batch.outcomes; continue; fi
  role=attacker; [[ $L == TSEL-* ]] && role=reader
  ATK_ROLE=$role bash $H/run-arm.sh "$L" AUTH 2G 1024M "$WU;sweep:T:4:3:10000" 0 > $ROOT/runs/$L.out 2>&1
  o=$(cat $ROOT/runs/$L/outcome 2>/dev/null || echo NO-OUTCOME)
  echo "$L role=$role $o" >> $ROOT/batch.outcomes; log "$L -> ${o:0:160}"
  cp $ROOT/runs/$L.out $ROOT/out/$L/run-arm.out 2>/dev/null
  bash $H/analyze.sh "$L" >> $ROOT/runs/$L.out 2>&1
  rm -rf $ROOT/node
done
log "batch done"; cat $ROOT/batch.outcomes

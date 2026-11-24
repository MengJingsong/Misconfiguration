#!/usr/bin/env bash
# B21 3-b confirm batch (pc72, 2026-11-23): the verified test arm T-2G under auth, as the data role, 3 clean lifetimes
# (fresh template copy each), each followed by the dump scan (analyze.sh deletes the .hprof). Optional extra labels
# with ATK_ROLE=reader (SELECT only).   batch3b.sh <label,label,...>   label T-AUTH-2G-<k> or TSEL-AUTH-2G-<k>
# Per lifetime as stage 2's T-2G: warm-up 3 single T queries + 20 s idle, then c = 12 for 120 s; heap 2G; arm AUTH.
set -uo pipefail
ROOT=/mydata/s4/3b-B21; H=$ROOT/harness
LAST=$(date -d '2026-11-23 20:00 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH $*"; }
WT="one:T:1000:100:3:0;idle:20000"
for L in ${1//,/ }; do
  if [ $(date +%s) -gt $LAST ]; then log "SKIP $L (wall-clock cap)"; echo "$L skipped-time" >> $ROOT/batch.outcomes; continue; fi
  role=attacker; [[ $L == TSEL-* ]] && role=reader
  ATK_ROLE=$role bash $H/run-arm.sh "$L" AUTH 2G "$WT;run:T:1000:100:12/120" 0 > $ROOT/runs/$L.out 2>&1
  o=$(cat $ROOT/runs/$L/outcome 2>/dev/null || echo NO-OUTCOME)
  echo "$L role=$role $o" >> $ROOT/batch.outcomes; log "$L -> ${o:0:160}"
  cp $ROOT/runs/$L.out $ROOT/out/$L/run-arm.out 2>/dev/null
  bash $H/analyze.sh "$L" >> $ROOT/runs/$L.out 2>&1
  rm -rf $ROOT/node
done
log "batch done"; cat $ROOT/batch.outcomes

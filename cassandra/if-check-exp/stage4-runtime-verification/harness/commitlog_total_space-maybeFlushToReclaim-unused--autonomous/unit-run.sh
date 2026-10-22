#!/bin/bash
# Unit tier (B2e, as amended 2026-10-21 R1-R2) of commitlog_total_space-maybeFlushToReclaim-unused--autonomous.
# Usage: bash unit-run.sh <outdir> [N] [arms...]   arms are "MiB:sleepMs"; default the five filed arms.
# Runs each arm in a fresh forked JVM from ~/cassandra-cts, clearing build/test/cassandra and build/test/logs first.
set -u
OUT=${1:?outdir}; N=${2:-300}; shift 2 || true
ARMS=("$@"); [ ${#ARMS[@]} -eq 0 ] && ARMS=("15:10" "25:10" "50:10" "100000:10" "25:0")
CLONE=$HOME/cassandra-cts
TEST=org.apache.cassandra.db.commitlog.CommitLogTotalSpaceCapTest
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T%z)] $*" | tee -a "$LOG"; }
run() { log "+ $*"; "$@" >>"$LOG" 2>&1; local rc=$?; log "rc=$rc"; return $rc; }

log "unit-run start N=$N arms=${ARMS[*]} clone=$CLONE head=$(git -C $CLONE rev-parse HEAD)"
log "EXPECTED: B2f (S=5 MiB): 15:10 peak<=35MiB final<=20MiB sw>=15 | 25:10 peak<=45 final<=30 sw>=10 | 50:10 peak<=70 final<=55 sw>=5 | 100000:10 peak~375-400 rising, sw=0 | 25:0 45<peak<150 final<=30 sw>=5; COMMITLOG_DIRTY>0 in capped arms, 0 in control (R2/R3)"
cd $CLONE || exit 1
for arm in "${ARMS[@]}"; do
  MIB=${arm%%:*}; SL=${arm##*:}; L="cap${MIB}-s${SL}"; D=$OUT/$L; mkdir -p "$D"
  log "=== arm $L"
  run rm -rf build/test/cassandra build/test/logs
  rm -f build/test/output/TEST-$TEST.xml
  log "+ CLCAP_MIB=$MIB CLCAP_SLEEP_MS=$SL CLCAP_N=$N CLCAP_OUT=$D/cap.csv ant testsome -Dtest.name=$TEST -Dno-build-test=true"
  t0=$(date +%s)
  CLCAP_MIB=$MIB CLCAP_SLEEP_MS=$SL CLCAP_N=$N CLCAP_OUT=$D/cap.csv \
    ant testsome -Dtest.name=$TEST -Dno-build-test=true </dev/null > "$D/ant.log" 2>&1
  rc=$?; log "ant rc=$rc ($(( $(date +%s) - t0 )) s); $(grep -E 'Tests run:|BUILD' $D/ant.log | tr '\n' ' ')"
  cp build/test/output/TEST-$TEST.xml "$D/" 2>/dev/null
  # raw test log tree (DEBUG, may be rolled to .gz)
  mkdir -p "$D/testlogs"; cp -r build/test/logs/. "$D/testlogs/" 2>/dev/null
  # zgrep -r does not recurse here (found in the shakedown): read every file, plain or .gz, with zcat -f
  tl() { find "$D/testlogs" -type f -print0 | sort -z | xargs -0 zcat -f; }
  {
    echo "COMMITLOG_DIRTY $(tl | grep -c 'Enqueuing flush of CLCapKS.t, Reason: COMMITLOG_DIRTY')"
    echo "MEMTABLE_LIMIT $(tl | grep -c 'Enqueuing flush of CLCapKS.t, Reason: MEMTABLE_LIMIT')"
    echo "ALL_REASONS_T $(tl | grep -c 'Enqueuing flush of CLCapKS.t, Reason:')"
    tl | grep -oE 'Enqueuing flush of [^,]+, Reason: [A-Z_]+' | sort | uniq -c | sed 's/^/REASON /'
    echo "SEGMENT_UNUSED_LINES $(tl | grep -c 'Commit log segment .* is unused')"
    echo "ERRORS $(tl | grep -c '^ERROR')"
  } > "$D/reasons.txt"
  cat "$D/cap.csv.summary" "$D/reasons.txt" 2>/dev/null | tee -a "$LOG"
done
log "unit-run end"
touch "$OUT/DONE"

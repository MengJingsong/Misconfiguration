#!/bin/bash
# Unit tier (B2e, as amended 2026-10-21 R1, R2, R5) of commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.
# Usage: bash unit-run.sh <outdir> [N] [arms...]   arm = "label:T:sleepMs:mode:nobreak"
# Default arms: the filed B2e steps 2-3, then B2i's M and M-nobreak. Each arm: a fresh `ant testsome` JVM in ~/cassandra-cl2,
# build/test/cassandra and build/test/logs cleared first.
set -u
OUT=${1:?outdir}; N=${2:-256}; shift 2 || true
ARMS=("$@")
[ ${#ARMS[@]} -eq 0 ] && ARMS=("T3-s20:3:20:single:false" "T4-s20:4:20:single:false" "T8-s20:8:20:single:false" \
  "T1024-s20:1024:20:single:false" "T4-s0:4:0:single:false" "T1024-s0:1024:0:single:false" \
  "M:8:20:M:false" "M-nobreak:8:20:M:true")
CLONE=$HOME/cassandra-cl2
TEST=org.apache.cassandra.db.commitlog.CommitLogTotalSpaceTest
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T%z)] $*" | tee -a "$LOG"; }

log "unit-run start N=$N arms=${ARMS[*]} clone=$CLONE head=$(git -C $CLONE rev-parse HEAD)"
log "EXPECTED: B2f (S=1MiB): T3 peak<=5MiB settled<=3 CLD>=4 | T4 peak<=6 settled<=4 CLD>=4 | T8 peak<=10 settled<=8 CLD>=2 | T1024 ~17-18MiB rising, CLD=0 | T4-s0 peak<=T+4S=8 settled<=4 | M (B2i) >=4 SELECT; every SELECT stop259&minimal or k=older; >=1 stop259 with k<older; switching M* tables per SELECT <= k+1; onDisk>=5MiB from first SELECT to end of write; settled in [5,8] MiB | M-nobreak: k=older always; >=1 SELECT switching >=3 M* tables; trough<=3MiB; peak<=10MiB"
cd $CLONE || exit 1
for arm in "${ARMS[@]}"; do
  IFS=: read -r L T SL MODE NB <<<"$arm"; D=$OUT/$L; mkdir -p "$D"
  log "=== arm $L T=$T sleep=$SL mode=$MODE nobreak=$NB"
  rm -rf build/test/cassandra build/test/logs; rm -f build/test/output/TEST-$TEST.xml "$D"/cap.csv*
  JA="-Dclcap.totalMiB=$T -Dclcap.sleepMs=$SL -Dclcap.n=$N -Dclcap.mode=$MODE -Dclcap.nobreak=$NB -Dclcap.out=$D/cap.csv"
  log "+ ant testsome -Dtest.name=$TEST -Dno-build-test=true -Dtest.jvm.args=\"$JA\""
  t0=$(date +%s)
  ant testsome -Dtest.name=$TEST -Dno-build-test=true -Dtest.jvm.args="$JA" </dev/null > "$D/ant.log" 2>&1
  rc=$?; log "ant rc=$rc ($(( $(date +%s) - t0 )) s); $(grep -E 'Tests run:|BUILD' $D/ant.log | tr '\n' ' ')"
  cp build/test/output/TEST-$TEST.xml "$D/" 2>/dev/null
  mkdir -p "$D/testlogs"; cp -r build/test/logs/. "$D/testlogs/" 2>/dev/null
  tl() { find "$D/testlogs" -type f -print0 | sort -z | xargs -0 zcat -f; }
  {
    echo "COMMITLOG_DIRTY_CLCap $(tl | grep -cE 'Enqueuing flush of CLCap\.[A-Za-z0-9]+, Reason: COMMITLOG_DIRTY')"
    echo "MEMTABLE_LIMIT_CLCap $(tl | grep -cE 'Enqueuing flush of CLCap\.[A-Za-z0-9]+, Reason: MEMTABLE_LIMIT')"
    echo "MEMTABLE_PERIOD_EXPIRED_CLCap $(tl | grep -cE 'Enqueuing flush of CLCap\.[A-Za-z0-9]+, Reason: MEMTABLE_PERIOD_EXPIRED')"
    tl | grep -oE 'Enqueuing flush of [^,]+, Reason: [A-Z_]+' | sort | uniq -c | sed 's/^/REASON /'
    echo "SEGMENT_DELETED_LINES $(tl | grep -c 'is no longer active and will be deleted')"
    echo "BYTEMAN_LINES $(tl | grep -ciE 'byteman|Rule\.execute|TypeException' )"
    echo "ERRORS $(tl | grep -c '^ERROR')"
  } > "$D/reasons.txt"
  [ -f "$D/cap.csv.trace" ] && echo "TRACE CHECK=$(grep -c '^CHECK' $D/cap.csv.trace) SELECT=$(grep -c '^SELECT' $D/cap.csv.trace) FLUSH=$(grep -c '^FLUSH' $D/cap.csv.trace)" >> "$D/reasons.txt"
  cat "$D/cap.csv.summary" "$D/reasons.txt" 2>/dev/null | tee -a "$LOG"
done
log "unit-run end"
touch "$OUT/DONE"

#!/bin/bash
# Unit tier (B2, as amended 2026-10-23 B2i) of commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.
# Usage: bash unit-run.sh <tree> <outdir> [arm ...]     arm = label:n_MiB:mode   (mode mmap|lz4|direct)
# One `ant testsome` JVM per arm in <tree>; per-arm yaml = test/conf/cassandra.yaml with the segment size, mode, a 1 h sync period
# and a memtable limit above the workload (so no flush recycles a segment before the census).
set -u
TREE=${1:?tree}; OUT=${2:?outdir}; shift 2
ARMS=("$@")
[ ${#ARMS[@]} -eq 0 ] && ARMS=(mmap-1:1:mmap mmap-4:4:mmap mmap-32:32:mmap lz4-1:1:lz4 lz4-4:4:lz4 lz4-32:32:lz4 direct-1:1:direct direct-4:4:direct direct-32:32:direct mmap-4-rep:4:mmap)
TEST=org.apache.cassandra.db.commitlog.SegmentCapProbeTest
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T%z)] $*" | tee -a "$LOG"; }
cd "$TREE" || exit 1
log "unit-run start tree=$TREE head=$(git rev-parse HEAD) arms=${ARMS[*]}"
log "EXPECTED (B2f as amended B2i): every arm: capacity==n*2^20 (direct too: exactly); every returned end and every retired endOfBuffer < capacity; violations=0; mmap fileLength==onDiskSize==n*2^20; lz4 fileLength<=n*2^20+ceil(n*2^20/255)+32*blocks+64; direct fileLength<=n*2^20 and a multiple of 4096; retired segments: isStillAllocating false, allocatePosition==capacity+1, endOfBuffer<capacity; the active one: true, allocatePosition<endOfBuffer==capacity; more than one segment per arm (64 adds of n/16 = 4n); max-accepted ok; oversize throws MutationExceededMaxSizeException oversized+1 allocatePositionDelta=0; capacity scales 1:4:32; assertion capacity==(n+1)MiB false"
for arm in "${ARMS[@]}"; do
  IFS=: read -r L S MODE <<<"$arm"; D=$OUT/$L; mkdir -p "$D"
  Y=$D/arm.yaml
  sed -e "s/^commitlog_segment_size: .*/commitlog_segment_size: ${S}MiB/" -e "s/^commitlog_sync_period: .*/commitlog_sync_period: 1h/" test/conf/cassandra.yaml > $Y
  {
    echo "memtable_heap_space: 600MiB"; echo "memtable_cleanup_threshold: 0.95"
    [ "$MODE" = lz4 ] && printf 'commitlog_compression:\n    - class_name: LZ4Compressor\n'
  } >> $Y
  [ "$MODE" = direct ] && sed -i "s/^commitlog_disk_access_mode: .*/commitlog_disk_access_mode: direct/" $Y
  for k in commitlog_segment_size commitlog_sync_period memtable_heap_space memtable_cleanup_threshold; do
    [ "$(grep -c "^$k:" $Y)" = 1 ] || { log "FAIL key $k count $(grep -c "^$k:" $Y)"; exit 1; }; done
  grep -q '^max_mutation_size' $Y && { log "FAIL max_mutation_size set"; exit 1; }
  [ "$MODE" = lz4 ] && { [ "$(grep -c '^commitlog_compression:' $Y)" = 1 ] || { log "FAIL compression key"; exit 1; }; }
  log "=== arm $L n=${S}MiB mode=$MODE"
  rm -rf build/test/cassandra build/test/logs; rm -f build/test/output/TEST-$TEST.xml
  JA="-Dcassandra.config=file://$Y -Dseg.out=$D/seg -Dseg.payload=$(( S * 1048576 / 16 )) -Dseg.adds=64 -Dseg.roll=false -Dseg.edge=false"
  t0=$(date +%s)
  ant testsome -Dtest.name=$TEST -Dno-build-test=true -Dtest.jvm.args="$JA" </dev/null > "$D/ant.log" 2>&1
  rc=$?; log "ant rc=$rc ($(( $(date +%s) - t0 )) s); $(grep -E 'Tests run:|BUILD' $D/ant.log | tr '\n' ' ')"
  cp build/test/output/TEST-$TEST.xml "$D/" 2>/dev/null
  mkdir -p "$D/testlogs"; cp -r build/test/logs/. "$D/testlogs/" 2>/dev/null
  tl() { find "$D/testlogs" -type f -print0 | sort -z | xargs -0 zcat -f; }
  {
    echo "FLUSHES $(tl | grep -c 'Enqueuing flush of SegCap')"
    echo "SEGMENT_DELETED_LINES $(tl | grep -c 'is no longer active and will be deleted')"
    echo "ERRORS $(tl | grep -c '^ERROR')"
    echo "CONFIG $(tl | grep -oE 'commitlog_disk_access_mode resolved to: [a-z]+' | head -1)"
  } > "$D/reasons.txt"
  cat "$D/seg.summary" "$D/reasons.txt" 2>/dev/null | tee -a "$LOG"
done
log "unit-run end"
touch "$OUT/DONE"

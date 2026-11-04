#!/bin/bash
# Unit tier (B2, as amended 2026-10-23 B2i) of commitlog_segment_size-allocate-endOfBuffer--autonomous.
# Usage: bash unit-run.sh <tree> <outdir> [arm ...]     arm = label:S_MiB:mode:E_bytes:fill   (mode mmap|lz4)
# One `ant testsome` JVM per arm in <tree>; per-arm yaml = test/conf/cassandra.yaml with the segment size, mode, a 1 h sync period
# and a memtable limit above the workload (so no flush recycles a segment before the census).
set -u
TREE=${1:?tree}; OUT=${2:?outdir}; shift 2
ARMS=("$@")
[ ${#ARMS[@]} -eq 0 ] && ARMS=(s1-mmap:1:mmap:65536:random s2-mmap:2:mmap:65536:random s8-mmap:8:mmap:65536:random s32-mmap:32:mmap:65536:random \
  s1-lz4:1:lz4:65536:random s2-lz4:2:lz4:65536:random s8-lz4:8:lz4:65536:random s32-lz4:32:lz4:65536:random \
  s8-mmap-E16k:8:mmap:16384:random s8-lz4-zero:8:lz4:65536:zero s8-mmap-rep:8:mmap:65536:random)
TEST=org.apache.cassandra.db.commitlog.SegmentSizeCapTest
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T%z)] $*" | tee -a "$LOG"; }
cd "$TREE" || exit 1
log "unit-run start tree=$TREE head=$(git rev-parse HEAD) arms=${ARMS[*]}"
log "EXPECTED: every arm: capacity==S*2^20; every returned end and every retired endOfBuffer < capacity; violations=0; mmap fileLength==S*2^20; lz4 fileLength<=S*2^20+ceil(S*2^20/255)+32*blocks+64 (zero fill far below S); retired allocatePosition==capacity+1; segments>=ceil(3*S/E-ish)+; max-accepted ok; oversize throws MutationExceededMaxSizeException oversized+1 allocatePositionDelta=0; edge-a stayed=true allocPosAfter=capacity-1; edge-b rolled=true oldEndOfBuffer=capacity-remaining; capacity scales 1:2:8:32"
for arm in "${ARMS[@]}"; do
  IFS=: read -r L S MODE E FILL <<<"$arm"; D=$OUT/$L; mkdir -p "$D"
  Y=$D/arm.yaml
  sed -e "s/^commitlog_segment_size: .*/commitlog_segment_size: ${S}MiB/" -e "s/^commitlog_sync_period: .*/commitlog_sync_period: 1h/" test/conf/cassandra.yaml > $Y
  {
    echo "memtable_heap_space: 600MiB"; echo "memtable_cleanup_threshold: 0.95"
    [ "$MODE" = lz4 ] && printf 'commitlog_compression:\n    - class_name: LZ4Compressor\n'
  } >> $Y
  for k in commitlog_segment_size commitlog_sync_period memtable_heap_space memtable_cleanup_threshold; do
    [ "$(grep -c "^$k:" $Y)" = 1 ] || { log "FAIL key $k count $(grep -c "^$k:" $Y)"; exit 1; }; done
  grep -q '^max_mutation_size' $Y && { log "FAIL max_mutation_size set"; exit 1; }
  [ "$MODE" = lz4 ] && { [ "$(grep -c '^commitlog_compression:' $Y)" = 1 ] || { log "FAIL compression key"; exit 1; }; }
  log "=== arm $L S=${S}MiB mode=$MODE E=$E fill=$FILL"
  rm -rf build/test/cassandra build/test/logs; rm -f build/test/output/TEST-$TEST.xml
  JA="-Dcassandra.config=file://$Y -Dseg.out=$D/seg -Dseg.entry=$E -Dseg.fill=$FILL -Dseg.edge=true"
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

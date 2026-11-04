#!/usr/bin/env bash
# The whole cluster tier (B3b as amended C2): seven arms one after another. Output: $OUT/<arm>/ and $OUT/chain.log.
H=$(cd "$(dirname "$0")" && pwd); export OUT=${OUT:-$HOME/stage4-logs/ros/run1/cluster}; mkdir -p "$OUT"
{
# label knob n_keys alloc shards memtable
for arm in "a16 16 60000 offheap_buffers 1 trie" "a64 64 240000 offheap_buffers 1 trie" "adef default 1000000 offheap_buffers 1 trie" \
           "a2048 2048 1000 offheap_buffers 1 trie" "h16 16 60000 heap_buffers 1 trie" "s16 16 600000 offheap_buffers default trie" \
           "c64 64 240000 offheap_buffers 1 skiplist"; do
  set -- $arm
  echo "#### arm $1 $(date -u +%FT%TZ)"
  "$H/cluster-run.sh" "$@" > "$OUT/arm-$1.out" 2>&1; echo "arm $1 rc=$?"
  tail -n 3 "$OUT/arm-$1.out"
done
echo "#### chain done $(date -u +%FT%TZ)"
} 2>&1 | tee "$OUT/chain.log"

#!/usr/bin/env bash
# Stage-4 harness: memtable_heap_space-LeafBuilder-allocated--autonomous, build variant V1 (B2b, amendment U1, 2026-10-27).
# usage: v1-patch.sh <clone> apply|revert|show
# V1 replaces the two target additions BTree.java:2683 and :2736 by `allocated += 0;` (a no-op that keeps bytecode on the
# same line, so the observe-only counter rules still fire there). Nothing else changes; line numbers are unchanged.
set -euo pipefail
C=$1; F=$C/src/java/org/apache/cassandra/utils/btree/BTree.java
case $2 in
  apply)
    grep -q 'allocated += ObjectSizes.sizeOfReferenceArray(newPredecessorCount | 1);' <(sed -n 2683p "$F")
    grep -q 'allocated += ObjectSizes.sizeOfReferenceArray(MAX_KEYS);' <(sed -n 2736p "$F")
    sed -i '' -e '2683s/allocated += ObjectSizes.sizeOfReferenceArray(newPredecessorCount | 1);/allocated += 0; \/\/ stage4 V1: was allocated += ObjectSizes.sizeOfReferenceArray(newPredecessorCount | 1);/' \
              -e '2736s/allocated += ObjectSizes.sizeOfReferenceArray(MAX_KEYS);/allocated += 0; \/\/ stage4 V1: was allocated += ObjectSizes.sizeOfReferenceArray(MAX_KEYS);/' "$F"
    ;;
  revert) git -C "$C" checkout -- src/java/org/apache/cassandra/utils/btree/BTree.java ;;
  show) ;;
esac
echo "2683: $(sed -n 2683p "$F" | sed 's/^ *//')"
echo "2736: $(sed -n 2736p "$F" | sed 's/^ *//')"
git -C "$C" diff --stat

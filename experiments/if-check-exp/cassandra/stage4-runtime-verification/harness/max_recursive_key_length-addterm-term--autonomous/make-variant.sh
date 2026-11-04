#!/usr/bin/env bash
# usage: make-variant.sh <built copy ~/s4-b34>   (cluster tier C2, 2026-10-28). Makes ~/s4-b34-vZ: a cp -a copy of the built tree whose jar (the node runs from the jar) is updated with the
# TrieMemoryIndex classes of overlay-z0 (MAX_RECURSIVE_KEY_LENGTH = 0, see make-overlays.sh). Nothing is written into the repository.
set -euo pipefail
S=${1:?built copy}; D=${S}-vZ
[ -d "$S/build/overlay-z0" ] || { echo "run make-overlays.sh first"; exit 1; }
[ -e "$D" ] && { echo "$D exists"; exit 0; }
cp -a "$S" "$D"
(cd $D/build && jar uf apache-cassandra-5.0.9-SNAPSHOT.jar -C overlay-z0 org/apache/cassandra/index/sai/memory)
for J in $S $D; do echo "$J:"; javap -p -c -cp $J/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.index.sai.memory.TrieMemoryIndex | grep -A30 'void addTerm' | grep -E 'sipush|bipush|ifgt|if_icmpgt|iconst_0|invokevirtual.*putRecursive|invokevirtual.*apply' | head -6; done

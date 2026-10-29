#!/usr/bin/env bash
# usage: make-variants.sh <built copy ~/s4-b34>   (cluster tier C1, 2026-10-28). Makes ~/s4-b34-vA (128), -vB (1024, unedited), -vC (16384) as cp -a copies of the built tree;
# for A and C line 96 of BlockBalancedTreeWriter.java is edited in the COPY's src/ and BlockBalancedTreeWriter + NumericIndexWriter (which inlines the constant) are recompiled
# with javac into the copy's build/classes/main and into the copy's jar (the node runs from the jar); stage4.Alloc (Byteman helper) is compiled into every copy. Nothing is written into the repository.
set -euo pipefail
S=${1:?built copy}; H=$(cd "$(dirname "$0")" && pwd)
for v in A:128 B:1024 C:16384; do
  n=${v%%:*}; m=${v##*:}; D=${S}-v$n
  [ -e "$D" ] && { echo "$D exists, skipping"; continue; }
  cp -a "$S" "$D"
  if [ "$m" != 1024 ]; then
    W=$D/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree
    sed -i "s/DEFAULT_MAX_POINTS_IN_LEAF_NODE = 1024;/DEFAULT_MAX_POINTS_IN_LEAF_NODE = $m;/" $W/BlockBalancedTreeWriter.java
    grep -n "DEFAULT_MAX_POINTS_IN_LEAF_NODE =" $W/BlockBalancedTreeWriter.java
    javac -nowarn -cp "$D/build/classes/main:$D/build/lib/jars/*:$D/lib/*" -d $D/build/classes/main $W/BlockBalancedTreeWriter.java $W/NumericIndexWriter.java 2>&1 | grep -v '^Note:' || true
  fi
  mkdir -p $D/build/classes/main
  javac -nowarn -cp "$D/build/classes/main:$D/build/lib/jars/*" -d $D/build/classes/main $H/Alloc.java
  # the node runs from build/apache-cassandra-*.jar (bin/cassandra.in.sh), not from build/classes/main: update the jar with the recompiled classes and the helper
  (cd $D/build && jar uf apache-cassandra-5.0.9-SNAPSHOT.jar -C classes/main org/apache/cassandra/index/sai/disk/v1/bbtree -C classes/main stage4)
  echo "variant $n (M=$m): $(javap -constants -p -cp $D/build/classes/main org.apache.cassandra.index.sai.disk.v1.bbtree.NumericIndexWriter | grep MAX_POINTS_IN_LEAF_NODE)"
done

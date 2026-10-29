#!/usr/bin/env bash
# usage: make-variant.sh <built copy ~/s4-b34>   (cluster tier C1, 2026-10-28). Makes ~/s4-b34-vS: a cp -a copy of the built tree in which SegmentBuilder.java:46 (in the COPY's src/) is changed to
# 10_000L, recompiled with javac into the copy's build/classes/main and into the copy's jar (the node runs from the jar, bin/cassandra.in.sh). Nothing is written into the repository.
set -euo pipefail
S=${1:?built copy}; D=${S}-vS
[ -e "$D" ] && { echo "$D exists"; exit 0; }
cp -a "$S" "$D"
F=$D/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java
sed -i 's|public static final long LAST_VALID_SEGMENT_ROW_ID = (Integer.MAX_VALUE / 2) - 1L;|public static final long LAST_VALID_SEGMENT_ROW_ID = 10_000L;|' $F
grep -n "LAST_VALID_SEGMENT_ROW_ID =" $F
javac -nowarn -cp "$D/build/classes/main:$D/build/lib/jars/*:$D/lib/*" -d $D/build/classes/main $F 2>&1 | grep -v '^Note:' || true
(cd $D/build && jar uf apache-cassandra-5.0.9-SNAPSHOT.jar -C classes/main org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.class $(cd classes/main && ls org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder*.class | sed 's/^/-C classes\/main /' | tr '\n' ' '))
javap -constants -p -cp $D/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.index.sai.disk.v1.segment.SegmentBuilder | grep LAST_VALID

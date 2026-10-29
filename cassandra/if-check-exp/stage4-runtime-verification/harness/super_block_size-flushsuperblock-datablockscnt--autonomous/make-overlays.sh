#!/usr/bin/env bash
# usage: make-overlays.sh   (B2 amendment U2). From the run copy, compiles OnDiskIndexBuilder.java and OnDiskIndex.java with line 129
# (SUPER_BLOCK_SIZE) set to 16 / 64 / 256, in two flavours: ovN (constant only) and ovNp (constant + one print line in flushSuperBlock).
# The run copy's tree is not modified: sources are copied to $OV/src. Output: $OV/ov16 ov16p ov64 ov64p ov256 ov256p, javap -constants in $OV/javap-*.txt.
set -euo pipefail
C=${CASSANDRA_HOME:-$HOME/s4-b34/c}; OV=${OV:-$HOME/s4-b34/ov}; rm -rf "$OV"; mkdir -p "$OV"
CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
D=org/apache/cassandra/index/sasi/disk
for N in 16 64 256; do for P in "" p; do
  S=$OV/src/ov$N$P; mkdir -p $S/$D $OV/ov$N$P
  cp $C/src/java/$D/OnDiskIndexBuilder.java $C/src/java/$D/OnDiskIndex.java $S/$D/
  sed -i "129s/SUPER_BLOCK_SIZE = 64;/SUPER_BLOCK_SIZE = $N;/" $S/$D/OnDiskIndexBuilder.java
  grep -n "int SUPER_BLOCK_SIZE" $S/$D/OnDiskIndexBuilder.java
  if [ -n "$P" ]; then
    python3 - "$S/$D/OnDiskIndexBuilder.java" <<'PY'
import sys
f = sys.argv[1]; s = open(f).read()
old = "                alignToBlock(out);\n\n                dataBlocksCnt = 0;"
new = ("                alignToBlock(out);\n"
       "                if (System.getProperty(\"sb.log\") != null) { System.gc(); Runtime r = Runtime.getRuntime(); System.out.println(\"SBFLUSH dataBlocksCnt=\" + dataBlocksCnt + \" tokens=\" + superBlockTree.getTokenCount() + \" treeBytes=\" + superBlockTree.serializedSize() + \" liveHeap=\" + (r.totalMemory() - r.freeMemory())); }\n\n"
       "                dataBlocksCnt = 0;")
assert s.count(old) == 1
open(f, 'w').write(s.replace(old, new))
PY
  fi
  javac -nowarn -proc:none -d $OV/ov$N$P -cp "$CP" $S/$D/OnDiskIndexBuilder.java $S/$D/OnDiskIndex.java 2>&1 | grep -v "^Note" || true
  javap -constants -cp $OV/ov$N$P org.apache.cassandra.index.sasi.disk.OnDiskIndexBuilder | grep SUPER_BLOCK_SIZE > $OV/javap-ov$N$P.txt
  echo "ov$N$P: $(cat $OV/javap-ov$N$P.txt)"
done; done

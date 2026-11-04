#!/usr/bin/env bash
# SUPPLEMENTARY diagnostic (not in B2; after run 1): what fills the 1 GiB test heap under M-first, S-even, L=128 MiB?
# usage: bash diag-first-histo.sh <out-name>      output ~/stage4-logs/lrt/<out-name>/
# Applies M-first to ~/cassandra-lrt-mut, rebuilds, runs u3CapEven alone at L=128MiB, and every 1 s takes
# `jcmd <pid> GC.class_histogram` (a full GC: live objects) of the test JVM, keeping the top 25 lines, plus the pool's
# accounted bytes from the probe file at the end. Only java processes of the clone are touched.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); MUT=$HOME/cassandra-lrt-mut; O=$HOME/stage4-logs/lrt/${1:-diag-first}; mkdir -p "$O"
SRC=src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
CLASS=org.apache.cassandra.db.memtable.FlushLargestSelectionTest
git -C "$MUT" checkout -- "$SRC" test/conf/cassandra.yaml
sed -i '274s/if (ratio > largestRatio)/if (largestMemtable == null \&\& ratio > 0f)/' "$MUT/$SRC"
git -C "$MUT" diff -- "$SRC" > "$O/M-first.diff"
( cd "$MUT" && ant build-test < /dev/null ) > "$O/build.log" 2>&1 || { echo build failed; exit 1; }
sed -i "/^memtable:/i memtable_heap_space: 128MiB" "$MUT/test/conf/cassandra.yaml"
cp "$H/FlushLargestSelectionTest.java" "$MUT/test/unit/org/apache/cassandra/db/memtable/"
rm -rf "$MUT/build/test/cassandra"; : > "$O/probe.txt"
( cd "$MUT" && timeout 900 ant testsome -Dtest.name=$CLASS -Dtest.methods=u3CapEven \
    -Dtest.jvm.args="-Dprobe.out=$O/probe.txt -Dprobe.mutant=M-first-diag -Xlog:gc:file=$O/gc.log" ) > "$O/ant.log" 2>&1 < /dev/null &
APID=$!
pid=""
for i in $(seq 1 120); do
  pid=$(ps -eo pid,args | awk -v c="$MUT/" '$2 ~ /java$/ && index($0, c) && /junit/ && /FlushLargestSelectionTest/ {print $1}' | head -1)
  [ -n "$pid" ] && break; sleep 1
done
echo "test JVM pid $pid" | tee "$O/histo.txt"
while kill -0 "$pid" 2>/dev/null; do
  { echo "=== $(date +%s%3N)"; jcmd "$pid" GC.class_histogram 2>&1 | head -28; } >> "$O/histo.txt"
  sleep 1
done
wait $APID
grep '^PROBE u3 ' "$O/probe.txt" | tee -a "$O/histo.txt"
git -C "$MUT" checkout -- "$SRC" test/conf/cassandra.yaml
echo "leftover: $(ps -eo args | awk '$1 ~ /java$/' | grep -c cassandra-lrt)"

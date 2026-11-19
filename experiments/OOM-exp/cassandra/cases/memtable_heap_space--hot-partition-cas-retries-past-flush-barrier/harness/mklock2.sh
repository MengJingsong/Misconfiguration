#!/usr/bin/env bash
# B18 optional diagnostic I2 (design §2.8): AtomicBTreePartition's waste-tracker lock made exclusive (4.0 semantics of
# CASSANDRA-15367): a per-partition ReentrantLock (AtomicBTreePartition$B18Lock) taken with tryLock(1 ms) in a loop that gives up
# (attempt unlocked) only when writeOp.isBlocking(). Builds into /mydata/s4/b18-w4/var/lock2 (separate class dir; the jar is
# untouched); saves the diff to logs/lock2.diff; writes var/lock2/include.sh for CASSANDRA_INCLUDE.
set -euo pipefail
W=/mydata/s4/b18-w4; C=$W/cassandra; V=$W/var/lock2; H=$(cd "$(dirname "$0")" && pwd)
rm -rf "$V"; mkdir -p "$V/src" "$V/classes"
F=src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java
cp "$C/$F" "$V/src/AtomicBTreePartition.java"
python3 -I "$H/lock2_patch.py" "$V/src/AtomicBTreePartition.java"
diff -u "$C/$F" "$V/src/AtomicBTreePartition.java" > "$W/logs/lock2.diff" || true
javac -nowarn -cp "$C/build/classes/main:$C/build/lib/jars/*" -d "$V/classes" "$V/src/AtomicBTreePartition.java" 2>&1 | grep -v "^Note:" || true
ls "$V/classes/org/apache/cassandra/db/partitions/"
printf '. "%s/bin/cassandra.in.sh"\nCLASSPATH="%s:$CLASSPATH"\n' "$C" "$V/classes" > "$V/include.sh"
cat "$V/include.sh"

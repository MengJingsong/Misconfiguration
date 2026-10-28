#!/usr/bin/env bash
# Positive control, B2e step 7: InMemoryTriePutTest.testOver1GSize with @Ignore removed, in the run copy only; heap 12g.
set -uo pipefail
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; OUT=${OUT:-$HOME/stage4-logs/trie2gb/run1/unit}; mkdir -p "$OUT" $HOME/stage4-tmp/ctl-classes
HARN=$(cd "$(dirname "$0")" && pwd)
CP="$C/build/test/classes:$C/build/classes/main:$C/build/classes/thrift:$C/build/classes/stress:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
T=$C/test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java
cp "$T" "$HOME/stage4-tmp/InMemoryTriePutTest.java.orig"
sed -i '/^    @Ignore$/d' "$T"; diff "$HOME/stage4-tmp/InMemoryTriePutTest.java.orig" "$T" | tee "$OUT/control.diff"
javac -d $HOME/stage4-tmp/ctl-classes -cp "$CP" "$T" "$HARN/RunOne.java" 2>&1 | tail -5
cp "$HOME/stage4-tmp/InMemoryTriePutTest.java.orig" "$T"      # restore the copy's source
echo "== control $(date -u +%FT%TZ)" | tee "$OUT/control.log"
java -Xmx12g -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/storage \
  -cp "$HOME/stage4-tmp/ctl-classes:$CP" RunOne org.apache.cassandra.db.tries.InMemoryTriePutTest testOver1GSize 2>&1 | tee -a "$OUT/control.log" | tail -5
echo "== exit ${PIPESTATUS[0]} $(date -u +%FT%TZ)" | tee -a "$OUT/control.log"

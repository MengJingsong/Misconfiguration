#!/usr/bin/env bash
# Unit tier driver for partition-key-max-size-descend-data-length--autonomous.
# Usage: bash unit-run.sh <src-tree> <outdir> [quick]
# Compiles PkStackTest outside the tree and runs it in separate JVMs (the trie threshold is read in a static initialiser).
set -u
SRC=$1; OUT=$2; QUICK=${3:-}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT/classes"
CP="$SRC/build/classes/main:$SRC/build/lib/jars/*:$SRC/conf"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/command.log"; }
log "javac PkStackTest"
javac -d "$OUT/classes" -cp "$CP" "$HERE/PkStackTest.java" >> "$OUT/command.log" 2>&1 || { log "COMPILE FAILED"; exit 1; }
JOPT="-Xmx2g -Xss4m -Dcassandra.config=file://$SRC/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
run() { # name args...
  local name=$1; shift
  log "run $name: java $*"
  java $JOPT -cp "$OUT/classes:$CP" "$@" > "$OUT/$name.tsv" 2> "$OUT/$name.err"; local rc=$?
  log "run $name exit $rc ($(wc -l < "$OUT/$name.tsv") lines)"
  [ $rc -eq 0 ] || { log "FAILED: $name"; tail -5 "$OUT/$name.err" | tee -a "$OUT/command.log"; return 1; }
}
if [ "$QUICK" = quick ]; then
  run lengths-quick org.apache.cassandra.db.tries.PkStackTest lengths 15,16,127,128,1024 1 || exit 1
  exit 0
fi
LS=15,16,127,128,1024,16384,65535,65536,65545
run lengths org.apache.cassandra.db.tries.PkStackTest lengths $LS 3 || exit 1
run lengths-ro1 -Dcassandra.memtable.row_overhead_size=1 org.apache.cassandra.db.tries.PkStackTest lengths 16,1024,65535 1 || exit 1
run bulk-default org.apache.cassandra.db.tries.PkStackTest bulk 1000000 16 || exit 1
run bulk-ro1 -Dcassandra.memtable.row_overhead_size=1 org.apache.cassandra.db.tries.PkStackTest bulk 1000000 16 || exit 1
run depth org.apache.cassandra.db.tries.PkStackTest depth 32,100,127,128,200,1000,16000,60000,65535 || exit 1
log "unit tier done"

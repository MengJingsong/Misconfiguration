#!/bin/bash
# Usage: unit-run.sh <tree> <outdir> [compile-only]
# Copies LeveledManifestL0Test.java into <tree>, runs it with `ant testsome`, keeps readings in <outdir>.
# Logs every command. Never builds in the repository copy: <tree> must come from copy-source.sh and must not run a node.
set -u
TREE=${1:?tree}; OUT=${2:?outdir}; HERE=$(cd "$(dirname "$0")" && pwd)
CLASS=LeveledManifestL0Test
mkdir -p "$OUT"; exec > >(tee -a "$OUT/unit-run.log") 2>&1
echo "== $(date -Is) unit-run $CLASS tree=$TREE"
cp "$HERE/$CLASS.java" "$TREE/test/unit/org/apache/cassandra/db/compaction/$CLASS.java" || exit 1
cd "$TREE" || exit 1
if [ "${3:-}" = compile-only ]; then ant build-test </dev/null; echo "exit $?"; exit; fi
rm -f "$OUT/readings.txt"
export L0_OUT="$OUT/readings.txt"
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.$CLASS -Dtest.timeout=2400000 </dev/null > "$OUT/ant.log" 2>&1
echo "ant exit $?"; tail -15 "$OUT/ant.log"
cp build/test/output/TEST-*$CLASS*.xml "$OUT/" 2>/dev/null
echo "== done $(date -Is) readings: $(wc -l < "$OUT/readings.txt" 2>/dev/null) lines"

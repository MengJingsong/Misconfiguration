#!/usr/bin/env bash
# usage: prep-data.sh <rows> <valueBytes>      (case B3c/B3e steps 1-4, amended 2026-10-27)
# Starts node A alone, creates ks (RF 2) with two tables of one wide partition each: wide_cdc (cdc = true) and wide_plain (cdc = false),
# loads <rows> rows of <valueBytes> random bytes into each with LoadWide, flushes, compacts to one sstable per table, drains, stops,
# and copies A's data directory to $R/A-backup (restored before each arm). Output: $OUT/prep/.
set -uo pipefail
rows=${1:?rows}; vb=${2:?valueBytes}
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/c4-mrb}; R=${R:-$HOME/stage4-mrb}; OUT=${OUT:-$HOME/stage4-logs/mrb/run1}/prep
mkdir -p "$OUT"; cd "$C"; exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
echo "== prep rows=$rows valueBytes=$vb $(date -u +%FT%TZ)"
"$H/node.sh" stop A; "$H/node.sh" stop B; echo "daemons before: $("$H/node.sh" status)"
rm -rf "$R/A" "$R/B" "$R/A-backup"; "$H/make-node.sh" A; "$H/make-node.sh" B
"$H/node.sh" start A || exit 1
CQL="bin/cqlsh 127.0.0.2"
$CQL -e "CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE ks.wide_cdc (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH cdc = true; CREATE TABLE ks.wide_plain (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH cdc = false; DESCRIBE TABLE ks.wide_cdc; DESCRIBE TABLE ks.wide_plain" > "$OUT/schema.txt" 2>&1; grep -E "cdc|CREATE" "$OUT/schema.txt"
mkdir -p "$H/cls"; javac -cp "$C/lib/cassandra-driver-core-3.12.1-shaded.jar:$C/build/lib/jars/*" -d "$H/cls" "$H/LoadWide.java" || exit 1
for t in wide_cdc wide_plain; do
  java -cp "$H/cls:$C/lib/cassandra-driver-core-3.12.1-shaded.jar:$C/build/lib/jars/*" LoadWide 127.0.0.2 ks.$t $rows $vb | tee -a "$OUT/load.txt" || { echo LOAD FAILED; "$H/node.sh" stop A; exit 1; }
done
bin/nodetool -p 7102 flush ks; bin/nodetool -p 7102 compact ks; bin/nodetool -p 7102 tablestats ks > "$OUT/tablestats-A.txt" 2>&1
grep -E "Table:|SSTable count|Space used \(live\)|Number of partitions|Compacted partition maximum" "$OUT/tablestats-A.txt"
bin/nodetool -p 7102 drain; "$H/node.sh" stop A
cp -a "$R/A/data" "$R/A-backup"; du -sh "$R/A-backup" | tee "$OUT/backup-size.txt"
echo "daemons after: $("$H/node.sh" status)"; echo "== prep end $(date -u +%FT%TZ)"

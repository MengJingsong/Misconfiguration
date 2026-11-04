#!/usr/bin/env bash
# usage: histo.sh <pid> <out-file>      (case 9c "histo.sh", 9d "Real resource")
# jcmd <pid> GC.class_histogram (live objects only: it runs a full collection first) to <out-file>, then prints one line:
#   epoch_ms=<ms> jcmd_ms=<jcmd duration> B_inst=<n> B_bytes=<n> cached_inst=<n> cached_bytes=<n> sizeonly_inst=<n> sizeonly_bytes=<n> mutation_inst=<n>
# B = the [B row (every byte array on the heap); cached = org.apache.cassandra.db.Mutation$CachedSerialization;
# sizeonly = org.apache.cassandra.db.Mutation$SizeOnlyCacheableSerialization; mutation = org.apache.cassandra.db.Mutation (recorded only).
set -euo pipefail
pid=$1; out=$2
t0=$(date +%s%N)
jcmd "$pid" GC.class_histogram > "$out"
t1=$(date +%s%N)
row() { awk -v c="$1" '$4 == c { print $2, $3; f=1 } END { if (!f) print 0, 0 }' "$out" | head -1; }
read -r bi bb <<< "$(row '[B')"
read -r ci cb <<< "$(row 'org.apache.cassandra.db.Mutation$CachedSerialization')"
read -r si sb <<< "$(row 'org.apache.cassandra.db.Mutation$SizeOnlyCacheableSerialization')"
read -r mi mb <<< "$(row 'org.apache.cassandra.db.Mutation')"
lines=$(grep -c '^ *[0-9]*:' "$out" || true)
[ "$lines" -gt 10 ] || { echo "histo.sh: cannot parse $out ($lines rows)" >&2; exit 2; }
echo "epoch_ms=$((t0 / 1000000)) jcmd_ms=$(( (t1 - t0) / 1000000 )) B_inst=$bi B_bytes=$bb cached_inst=$ci cached_bytes=$cb sizeonly_inst=$si sizeonly_bytes=$sb mutation_inst=$mi"

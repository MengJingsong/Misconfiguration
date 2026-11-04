#!/usr/bin/env bash
# usage: histo.sh <pid> <out-file>      (case 9c "entry-census.sh", amended 2026-10-14; 9d "Disallow evidence", "Real resource")
# jcmd <pid> GC.class_histogram (live objects only: it runs a full collection first) to <out-file>, then jcmd GC.heap_info, and prints one line:
#   epoch_ms=<ms> jcmd_ms=<ms> indexed_inst=<n> indexed_bytes=<n> shallow_inst=<n> shallow_bytes=<n> indexinfo_inst=<n> indexinfo_bytes=<n>
#   rie_inst=<n> heap_used_kb=<n>
# indexed = RowIndexEntry$IndexedEntry, shallow = RowIndexEntry$ShallowIndexedEntry, indexinfo = org.apache.cassandra.io.sstable.IndexInfo,
# rie = RowIndexEntry (single-block entries); heap_used_kb = the "used" figure of GC.heap_info, taken right after the collection.
set -euo pipefail
pid=$1; out=$2
t0=$(date +%s%N)
jcmd "$pid" GC.class_histogram > "$out"
t1=$(date +%s%N)
jcmd "$pid" GC.heap_info > "$out.heap"
row() { awk -v c="$1" '$4 == c { print $2, $3; f=1 } END { if (!f) print 0, 0 }' "$out" | head -1; }
P=org.apache.cassandra.io.sstable
read -r ii ib <<< "$(row "$P.format.big.RowIndexEntry\$IndexedEntry")"
read -r si sb <<< "$(row "$P.format.big.RowIndexEntry\$ShallowIndexedEntry")"
read -r xi xb <<< "$(row "$P.IndexInfo")"
read -r ri rb <<< "$(row "$P.format.big.RowIndexEntry")"
used=$(grep -o 'used [0-9]*K' "$out.heap" | head -1 | tr -dc 0-9)
lines=$(grep -c '^ *[0-9]*:' "$out" || true)
[ "$lines" -gt 10 ] || { echo "histo.sh: cannot parse $out ($lines rows)" >&2; exit 2; }
echo "epoch_ms=$((t0 / 1000000)) jcmd_ms=$(( (t1 - t0) / 1000000 )) indexed_inst=$ii indexed_bytes=$ib shallow_inst=$si shallow_bytes=$sb indexinfo_inst=$xi indexinfo_bytes=$xb rie_inst=$ri heap_used_kb=${used:-0}"

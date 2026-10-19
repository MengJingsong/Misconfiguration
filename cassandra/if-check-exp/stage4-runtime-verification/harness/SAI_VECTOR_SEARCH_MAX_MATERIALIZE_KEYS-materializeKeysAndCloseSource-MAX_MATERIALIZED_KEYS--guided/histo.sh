#!/usr/bin/env bash
# usage: histo.sh <pid> <out-file>      (case 9d "Real resource, heap")
# jcmd <pid> GC.class_histogram (live objects only: it runs a full collection first) to <out-file>, then GC.heap_info, and prints:
#   epoch_ms=<ms> jcmd_ms=<ms> spk_inst=<n> spk_bytes=<n> bdk_inst=<n> bdk_bytes=<n> tok_inst=<n> tok_bytes=<n> hbb_inst=<n>
#   hbb_bytes=<n> B_inst=<n> B_bytes=<n> heap_used_kb=<n>
# spk = PrimaryKey$Factory$SkinnyPrimaryKey, bdk = BufferDecoratedKey, tok = Murmur3Partitioner$LongToken, hbb = java.nio.HeapByteBuffer,
# B = [B (the five classes of the case's section 7).
set -euo pipefail
pid=$1; out=$2
t0=$(date +%s%N)
jcmd "$pid" GC.class_histogram > "$out"
t1=$(date +%s%N)
jcmd "$pid" GC.heap_info > "$out.heap"
row() { awk -v c="$1" '$4 == c { print $2, $3; f=1 } END { if (!f) print 0, 0 }' "$out" | head -1; }
read -r si sb <<< "$(row 'org.apache.cassandra.index.sai.utils.PrimaryKey$Factory$SkinnyPrimaryKey')"
read -r di db <<< "$(row 'org.apache.cassandra.db.BufferDecoratedKey')"
read -r ti tb <<< "$(row 'org.apache.cassandra.dht.Murmur3Partitioner$LongToken')"
read -r hi hb <<< "$(row 'java.nio.HeapByteBuffer')"
read -r bi bb <<< "$(row '[B')"
used=$(grep -o 'used [0-9]*K' "$out.heap" | head -1 | tr -dc 0-9)
lines=$(grep -c '^ *[0-9]*:' "$out" || true)
[ "$lines" -gt 10 ] || { echo "histo.sh: cannot parse $out ($lines rows)" >&2; exit 2; }
echo "epoch_ms=$((t0 / 1000000)) jcmd_ms=$(( (t1 - t0) / 1000000 )) spk_inst=$si spk_bytes=$sb bdk_inst=$di bdk_bytes=$db tok_inst=$ti tok_bytes=$tb hbb_inst=$hi hbb_bytes=$hb B_inst=$bi B_bytes=$bb heap_used_kb=${used:-0}"

#!/usr/bin/env bash
# S2 sampler, runs ON V (apt140) until killed.  sample.sh <outdir>
# heap.log  every 5 s: GC.heap_info used (no forced GC)
# out.log   every 5 s: V outbound to R (pending_count, pending_bytes, reserve, overload, expired, sent)
# k.log     every 10 s: key/counter cache K (nodetool info), memtable K (tablestats b6/s2c memtable data size, heap)
set -uo pipefail
O=$1; B=$HOME/cassandra-b1; P=$(cat /mydata/s2/inst/V/cass.pid); mkdir -p "$O"; i=0
Q="SELECT address, pending_count, pending_bytes, using_reserve_bytes, overload_count, expired_count, sent_count FROM system_views.internode_outbound;"
while kill -0 "$P" 2>/dev/null; do
  t=$(date +%s)
  echo "$t $(timeout 4 jcmd $P GC.heap_info 2>/dev/null | grep -m1 -o 'total [0-9]*K, used [0-9]*K')" >> "$O/heap.log"
  timeout 5 $B/bin/cqlsh 10.10.1.1 -e "$Q" 2>&1 | awk -v t=$t '/10\.10\.1\.5/{print t" "$0}' >> "$O/out.log"
  if true; then
    { echo "== $t"; timeout 8 $B/bin/nodetool info 2>/dev/null | grep -E "Key Cache|Counter Cache|Heap Memory"
      timeout 8 $B/bin/nodetool tpstats 2>/dev/null | grep -E "^MutationStage|^Native-Transport|^HintsDispatcher"
      timeout 8 $B/bin/nodetool tablestats b6 s2c 2>/dev/null | grep -E "Table: |Memtable data size|Memtable cell count|Memtable off heap"; } >> "$O/k.log"
  fi
  i=$((i+1)); sleep 4
done
echo "$(date +%s) V_DEAD" >> "$O/heap.log"

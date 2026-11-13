#!/usr/bin/env bash
# qsample.sh <nIters> <sleepSec> <outfile>
B=~/cassandra-b1; V=7199
n=${1:-40}; s=${2:-0.5}; out=${3:-/mydata/c1r3/arms/sampler.txt}
: > "$out"
for i in $(seq 1 "$n"); do
  u=$($B/bin/cqlsh 10.10.1.1 -e "SELECT address,using_bytes,using_reserve_bytes,throttled_count FROM system_views.internode_inbound;" 2>/dev/null \
      | grep -E "10.10.1.(3|4|5)" | awk '{u+=$4; r+=$6; t+=$8} END{printf "using=%.0fMiB reserve=%.0fMiB throttled=%d", u/1048576, r/1048576, t}')
  p=$($B/bin/nodetool -h 127.0.0.1 -p $V tpstats 2>/dev/null | awk '/^MutationStage/{print $3}')
  h=$($B/bin/nodetool -h 127.0.0.1 -p $V info 2>/dev/null | awk '/Heap Memory/{printf "%.0f", $5}')
  echo "$(date +%T) $u MutPending=$p heapMiB=$h" >> "$out"
  sleep "$s"
done

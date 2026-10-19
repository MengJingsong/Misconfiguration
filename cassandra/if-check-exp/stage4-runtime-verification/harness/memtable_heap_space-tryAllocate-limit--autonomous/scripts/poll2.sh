#!/bin/bash
D=~/short-run/memtable_heap_space-tryAllocate-limit/cluster2/cass-src-cluster2
cd "$D"
while true; do
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) ==="
  bin/nodetool tablestats keyspace1.standard1 2>&1 | grep -i "memtable\|space used (live)"
  sleep 5
done

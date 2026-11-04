#!/bin/bash
BASE=~/short-run/memtable_heap_space-tryAllocate-limit/cluster1
D=$BASE/cass-src-cluster1
cd "$D"
while true; do
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) ==="
  bin/nodetool tablestats keyspace1.standard1 2>&1 | grep -i "memtable\|space used (live)"
  sleep 5
done

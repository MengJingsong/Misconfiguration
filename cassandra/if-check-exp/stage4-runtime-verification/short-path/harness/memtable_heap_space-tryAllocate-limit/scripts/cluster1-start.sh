#!/bin/bash
set -x
BASE=~/short-run/memtable_heap_space-tryAllocate-limit/cluster1
D=$BASE/cass-src-cluster1
cd "$D"
echo "pre-start daemon check:"
bash ~/short-run/memtable_heap_space-tryAllocate-limit/check-daemon.sh
export JVM_EXTRA_OPTS="-Xms512m -Xmx512m"
nohup bin/cassandra -f > "$BASE/node.log" 2>&1 &
disown
sleep 3
bash ~/short-run/memtable_heap_space-tryAllocate-limit/check-daemon.sh > "$BASE/pid.txt"
echo "post-start pid:"
cat "$BASE/pid.txt"

#!/bin/bash
# Run 1 (AI), unit tier, memtable_heap_space — case §9c commands.
set -x
cd ~/cassandra-run1
git rev-parse HEAD
cp /proj/misconfiguration-PG0/git-repos/misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/harness/memtable_heap_space-tryAllocate-limit/HeapPoolTest.java test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java
sha256sum /proj/misconfiguration-PG0/git-repos/misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/harness/memtable_heap_space-tryAllocate-limit/HeapPoolTest.java test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest; echo "HeapPoolTest ant exit=$?"
ant testsome -Dtest.name=org.apache.cassandra.db.memtable.MemtableSizeUnslabbedTest; echo "MemtableSizeUnslabbedTest ant exit=$?"

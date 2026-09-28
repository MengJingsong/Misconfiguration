# Harness — memtable_heap_space

| File | What it is | Where it goes in the local clone |
|---|---|---|
| `HeapPoolTest.java` | Unit test for the case's unit tier (§9c). Not upstream. | `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java` |

**Origin.** Restored verbatim from the Java block in
`git show e90423c^:cassandra/if-check-exp/memtable/memtable_heap_space-tryAllocate-limit.md`
(lines 245–403 of that file). It is the test run on 2026-09-16 on pc80.
The untracked copy in the shared `cassandra-src` clone differs from it in one
comment line only (an older case-file name); the code is identical.

**Not yet here:** the Byteman rule for scenario C (§9d, bypass volume).

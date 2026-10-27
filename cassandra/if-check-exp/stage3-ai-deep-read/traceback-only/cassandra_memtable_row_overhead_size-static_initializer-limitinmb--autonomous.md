# cassandra_memtable_row_overhead_size — trace-back only  <!-- file: traceback-only/cassandra_memtable_row_overhead_size-static_initializer-limitinmb--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:64` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** The check at `InMemoryTrie.java:64` (`limitInMB < 1 || limitInMB > 2047`) sits in the static initializer block of `InMemoryTrie` (`InMemoryTrie.java:59-68`), not in a named method. It validates the per-trie size threshold `ALLOCATED_SIZE_THRESHOLD` (declared `InMemoryTrie.java:58`, documented at `:52-56` as a threshold that stops tries from growing past the hard 2GB limit imposed by 32-bit pointers). It is a JVM system property, `cassandra.memtable.row_overhead_size`, declared as `MEMTABLE_OVERHEAD_SIZE` at `CassandraRelevantProperties.java:356` with the default string "-1". `InMemoryTrie.java:63` reads it with `getInt(2048 * 10 / 11)`, which returns that argument (1861) when the property is unset (`CassandraRelevantProperties.java:881-887`), so the default is 1861 MB. The comment at `InMemoryTrie.java:60-62` says this is about 2GB minus 10%. The unit is MB, and the code multiplies by 1024*1024 at `InMemoryTrie.java:67`. The allowed range is 1 to 2047 MB. Any other value throws an AssertionError at class initialization (`InMemoryTrie.java:64-66`). It is set with -D on the JVM command line, so a change needs a restart. I found no yaml key and no JMX setting for it. The same property is also read by `SkipListMemtable.java:75` as a row-overhead size in bytes (default -1 there), so one property carries two different meanings. At runtime, `reachedAllocatedSizeThreshold()` compares `allocatedPos >= ALLOCATED_SIZE_THRESHOLD` (`InMemoryTrie.java:951-953`). `TrieMemtable.java:192-195` uses that result to request a flush (reason MEMTABLE_LIMIT).

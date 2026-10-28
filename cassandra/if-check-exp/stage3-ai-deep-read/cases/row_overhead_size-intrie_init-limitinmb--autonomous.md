# Trie allocation threshold range guard (InMemoryTrie ALLOCATED_SIZE_THRESHOLD) — verification solution  <!-- file: cases/row_overhead_size-intrie_init-limitinmb--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`InMemoryTrie.java:64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L64) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: the guarded value becomes `ALLOCATED_SIZE_THRESHOLD`, and the memtable flushes when the trie's allocated bytes reach it, so trie memory follows the (range-limited) threshold. The `if` itself is only the range guard on that value. |
| Ground | — |

**Type:** non-config (hard-coded constant; the check also reads the JVM property `cassandra.memtable.row_overhead_size`, `MEMTABLE_OVERHEAD_SIZE`). The numeric literals `1` and `2047` and the default expression `2048 * 10 / 11` take part in the check (constant rule).

## A. Constraint trace

**A1. The constraint.** `limitInMB < 1 || limitInMB > 2047` rejects values outside the literal range 1..2047 (MB). The literal bounds are hard-coded: 2047 comes from the 32-bit-pointer 2GB trie limit (class javadoc, `InMemoryTrie.java:43`, and `InMemoryTrie.java:94`-ish exception doc). The value checked is `limitInMB`, read at [`InMemoryTrie.java:63`] from the JVM property `MEMTABLE_OVERHEAD_SIZE` (key `cassandra.memtable.row_overhead_size`, declared at `CassandraRelevantProperties.java:356`; read with `getInt(int)`, `CassandraRelevantProperties.java:881`, which returns the supplied default when the property is unset). Default `2048 * 10 / 11 = 1861` MB (the "threshold + 10% == 2GB" comment, `InMemoryTrie.java:60-61`). Set by `-Dcassandra.memtable.row_overhead_size=<MB>` only; needs a restart (static initializer, class load). The result is stored as `ALLOCATED_SIZE_THRESHOLD = 1024*1024*limitInMB` ([`InMemoryTrie.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L58), assigned line 67). Unit: MB in, bytes out. Oddity: the same property also sets the SkipListMemtable per-row heap overhead in bytes (`SkipListMemtable.java:75`); a property named for row overhead sizes the trie threshold here. A separate, unused-in-source constant `MEMTABLE_TRIE_SIZE_LIMIT` (`cassandra.trie_size_limit_mb`, `CassandraRelevantProperties.java:358`) has no readers in `src`.

**A2. What it caps.** Heap or off-heap memory (the trie buffers; `BufferType` on/off heap, `InMemoryTrie.java:72`) of one trie, i.e. one TrieMemtable shard. The quantity compared in the later check is `allocatedPos` (bytes allocated in 32-byte-ish blocks, `InMemoryTrie.java:158`) against `ALLOCATED_SIZE_THRESHOLD`. The `if` at line 64 only bounds the threshold to [1 MB, 2047 MB] so it cannot exceed the 2GB pointer limit.

**A3. Mechanism.** Static init: [`if (limitInMB < 1 || limitInMB > 2047)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L64). True: throws `AssertionError` in the static initializer, so `InMemoryTrie` fails to load (`ExceptionInInitializerError`, later `NoClassDefFoundError`), so TrieMemtable cannot be used. False: `ALLOCATED_SIZE_THRESHOLD` is set (line 67). Enforcement of the actual cap: `allocateBlock()` advances `allocatedPos` (`InMemoryTrie.java:144-158`); `reachedAllocatedSizeThreshold()` returns `allocatedPos >= ALLOCATED_SIZE_THRESHOLD` (`InMemoryTrie.java:951-953`); `TrieMemtable.put` checks it per write and calls `owner.signalFlushRequired(..., MEMTABLE_LIMIT)` once (`TrieMemtable.java:192-196`). Overshoot: the cap is soft; writes continue until the flush switches the memtable, and growth up to ~10% beyond is expected (javadoc `InMemoryTrie.java:945-950`); past 2GB `SpaceExhaustedException` (`InMemoryTrie.java:147-148`) becomes `IllegalStateException` (`TrieMemtable.java:202-204`). Callers of `reachedAllocatedSizeThreshold` outside the class: only `TrieMemtable.java:192`.

**A4. Other consumers.** Off the trie's allocatedPos: per-content object arrays (`REFERENCE_ARRAY_ON_HEAP_SIZE`, `InMemoryTrie.java:980`) and the cell/row objects held as trie contents (heap), which `allocatedPos` does not count; the memtable allocator's own limits (`memtable_heap_space`, `memtable_offheap_space`) also trigger flushes independently. The `-D` value is also read by SkipListMemtable with different meaning.

**A5. Evidence beyond the source.** Test `test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java:80` advances `allocatedPos` past `ALLOCATED_SIZE_THRESHOLD`; no test targets the range guard. `.git` is absent in the copy, so no history was read. none otherwise.

## B. Verification solution

**B1. Claim under test.** With `-Dcassandra.memtable.row_overhead_size=N` (1 <= N <= 2047), a TrieMemtable shard requests flush when its trie reaches about N MB of allocated bytes, so trie memory per shard stays near N MB (plus up to ~10% overshoot); values outside 1..2047 make `InMemoryTrie` fail to initialize.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy of the tag outside the shared tree (`rsync -a` then `ant jar`). A small test class in the package `org.apache.cassandra.db.tries` (needed for the package-private `ALLOCATED_SIZE_THRESHOLD` and `advanceAllocatedPos`, as `InMemoryTriePutTest.java:80` does) run with `ant testsome` or a plain `java -cp` using built classes. One fresh JVM per N, since the value is read once at class load.

**B2b. Knobs.** `-Dcassandra.memtable.row_overhead_size` = unset, 1, 64, 2047 (valid), and 0, 2048, -5 (invalid). Boundaries 1/2047 and 0/2048 test the literals exactly.

**B2c. Workload.** Create `new InMemoryTrie<>(BufferType.ON_HEAP)` (and OFF_HEAP). Print `ALLOCATED_SIZE_THRESHOLD`. Insert `putRecursive` with random 16-byte keys and a small value until `reachedAllocatedSizeThreshold()` is true; each key adds on the order of tens of bytes, so N=64 needs roughly 1-2 million keys. Continue 10% more writes to see overshoot.

**B2d. Observables and instruments.** `ALLOCATED_SIZE_THRESHOLD`; `trie.usedSizeOnHeap()/usedSizeOffHeap()` or `sizeOnHeap` accessors (`InMemoryTrie.java:971-980`); the first key count at which `reachedAllocatedSizeThreshold()` flips; the exception from class load for invalid values. Allocation bytes cannot be read from outside `allocatedPos` except via these accessors.

**B2e. Procedure.** For each N: `java -Dcassandra.memtable.row_overhead_size=N -cp <build/classes+libs> <TestMain>`; the test prints threshold, writes until flip, prints size at flip, then 10% more.

**B2f. Predictions.** Unset: threshold = 1024*1024*1861 = 1951432704. N valid: threshold = N*1048576 exactly; size at flip lies in [threshold, threshold + one block of growth per write] and later growth stays under ~1.1x. N=0, 2048, -5: `ExceptionInInitializerError` caused by `AssertionError` with message "... must be within 1 and 2047".

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Flip at size ~ N MB for every valid N | claim confirmed |
| Flip size independent of N | claim refuted (property not driving the threshold) |
| N=0 or 2048 loads without error | range guard not working as read; claim refuted for the boundary |
| N=1 or 2047 throws | literal bounds off by one; claim refuted |
| Flip never reached before memory runs out | cap not reached, nothing confirmed |

**B2h. Controls.** Same workload on ON_HEAP and OFF_HEAP; default (unset) run; run with `cassandra.trie_size_limit_mb` set to show it has no effect.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the tag copy; `memtable` configuration for a table using `TrieMemtable` (`memtable: trie` in `cassandra.yaml` `memtable.configurations`, `CREATE TABLE ... WITH memtable = 'trie'`); heap 4G, `memtable_allocation_type: offheap_objects` for one arm and `heap_buffers` for another; `memtable_flush_writers` default. JVM option `-Dcassandra.memtable.row_overhead_size=N` in `jvm11-server.options` copy.

**B3b. Knobs.** N = 16 and 64 (small enough to reach quickly), default as a third arm; invalid N=2048 to check startup failure (node fails when the first TrieMemtable is created).

**B3c. Workload.** `cassandra-stress` or CQL inserts into the trie table, 1 KB rows, until at least 3x the threshold is written per shard; with S shards (`cassandra.memtable.shard.count` default = cores) total data needed is about 3 * N MB * S; N=16, 8 shards: ~400 MB, minutes.

**B3d. Observables and instruments.** `nodetool tablestats` memtable data size and off-heap size, `jcmd <pid> GC.heap_info` or JMX `MemtableOnHeapSize`, system.log line "Scheduling flush due to trie size limit reached." (`TrieMemtable.java:194`), `ls` of data dir for flush file counts and sizes.

**B3e. Procedure.** Start node with N; create table; run stress in 100 MB steps; after each step record tablestats and grep the log; stop, wipe data dir, repeat for next N; `pkill -f CassandraDaemon` checks at end.

**B3f. Predictions.** The flush message appears when a shard's trie reaches about N MB; per-shard trie allocation never exceeds ~1.1 N MB before the flush; N=64 gives about 4x the flush interval (in bytes written) of N=16. N=2048 fails node use of the trie memtable with the assertion message.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Flush interval scales with N | claim confirmed |
| Same flush interval for N=16 and N=64 | claim refuted |
| Memtable size far above 1.1 N per shard with no flush message | cap not binding as designed |
| No flush message at all before heap pressure flush (`memtable_heap_space`) | other cap hit first; not confirmed |

**B3h. Controls.** The same workload on a skip-list memtable table with the same -D (SkipListMemtable reads it as row overhead bytes, `SkipListMemtable.java:75`), showing no trie-threshold behavior there; a default-N arm.

**B4. Risks and cleanup.** Disk: flushed sstables under a private data directory sized to a few GB; delete it afterward. Never build in the shared source tree. Stop the node and stress processes and verify no `CassandraDaemon` or `java` process of the run remains. Unit tier uses only the JVM heap (up to ~2 GB for N=2047; use N=2047 only on a machine with the room, or skip filling and check only the threshold).

## C. Sources read

- src/java/org/apache/cassandra/db/tries/InMemoryTrie.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/db/memtable/TrieMemtable.java
- src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java
- test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java (grep only)

## D. Stage-4 feedback

`none yet`

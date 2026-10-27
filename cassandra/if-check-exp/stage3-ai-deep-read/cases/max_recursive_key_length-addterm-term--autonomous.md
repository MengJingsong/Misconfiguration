# MAX_RECURSIVE_KEY_LENGTH — verification solution  <!-- file: cases/max_recursive_key_length-addterm-term--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`TrieMemoryIndex.java:228`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L228) (`if (term.limit() <= MAX_RECURSIVE_KEY_LENGTH)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant only selects between two insertion routines that build the same trie, so it does not cap memory or disk. |
| Ground | The constant is compared with the term length only to choose `putRecursive` (stack-recursive) or `apply(Trie.singleton(...))` (iterative); both write into the same `InMemoryTrie`, and nothing is rejected or evicted at this line. The memory-relevant bounds on this path are elsewhere (the SAI term-size guardrail, the memtable space settings). |

> **Link rule.** Followed: declaration (A1) and if statement (above, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `MAX_RECURSIVE_KEY_LENGTH`; kind: hard-coded constant (not a yaml key, JVM property, JMX or runtime-queried value). Declared at [`TrieMemoryIndex.java:64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L64): `private static final int MAX_RECURSIVE_KEY_LENGTH = 128;`. Unit: bytes of the (index-encoded) term, read as `term.limit()`. Default 128, a literal with no derivation. Changing it needs a source edit and rebuild. The earlier trace was checked against the source: declaration line 64, comparison line 228, `addTerm` at line 218 all hold. A different constant of the same name and value exists at `src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:98` (it is `public`, and used at `TrieMemtable.java:483`, `key.getKeyLength() < MAX_RECURSIVE_KEY_LENGTH`); it is a separate constant for the memtable partition-key path and is not the target. No comment at line 64 or 228 says why 128 was chosen; the Javadoc of `InMemoryTrie.putRecursive` says it "may run into stack overflow if the trie becomes too deep" (`src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:884-885`), which is the likely reason (inference, not stated for this constant).

**A2. What it caps.** Nothing in memory or disk. The compared quantity is the term length in bytes (`term.limit()`, line 228); the outcome is only the choice of insertion routine, i.e. it bounds the Java call-stack recursion depth of `putRecursive` (one frame per key byte, `InMemoryTrie.java:902-920`), a stack resource, not heap, off-heap or disk.

**A3. Mechanism.**
1. `TrieMemoryIndex.add(...)` (`TrieMemoryIndex.java:94-126`) encodes the value with `index.termType().asIndexBytes(value)`, records `data.sizeOnHeap()`, `data.sizeOffHeap()` and `primaryKeysReducer.heapAllocations()` before, calls `addTerm` once per analyzer token if an analyzer is configured, otherwise once for the value, and returns the sum of the three deltas (line 126).
2. `addTerm` ([`TrieMemoryIndex.java:218`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L218)) first calls `index.validateTermSize(primaryKey.partitionKey(), term, false, null)` at line 220. With `isClientMutation == false` this returns false (term skipped, warning logged through `noSpamLogger`) when `maxTermSizeGuardrail.failsOn(term.remaining(), state)` (`StorageAttachedIndex.java:823`, method at 815); otherwise true. The guardrail is the vector, frozen or string one chosen at `StorageAttachedIndex.java:207-210`; defaults for string and frozen: warn 1KiB, fail 8KiB; vector: warn 16KiB, fail 32KiB (`Config.java:941-946`; commented in `conf/cassandra.yaml:2246-2255`).
3. If accepted: min/max term updated (line 222), `ByteComparable` built (line 224).
4. The if statement: [`TrieMemoryIndex.java:228`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java#L228) `term.limit() <= MAX_RECURSIVE_KEY_LENGTH`.
   - True (term of 128 bytes or fewer): `data.putRecursive(comparableBytes, primaryKey, primaryKeysReducer)` (line 230), recursive descent through the key bytes (`InMemoryTrie.java:895-920`).
   - False (longer than 128 bytes): `data.apply(Trie.singleton(comparableBytes, primaryKey), primaryKeysReducer)` (line 234), the cursor-based iterative merge (`InMemoryTrie.java:822`).
5. `SpaceExhaustedException` from either call is wrapped in `RuntimeException` (`TrieMemoryIndex.java:237-239`). That exception comes from the trie's 2GB pointer limit, not from this constant.
Either outcome appends to the same `InMemoryTrie<PrimaryKeys>` created at the constructor (`TrieMemoryIndex.java:81`, `new InMemoryTrie<>(TrieMemtable.BUFFER_TYPE)`), so the allocated size grows by the trie's own allocation rules. No bypass or overshoot of a memory limit is related to this line. (Statement that the two routines produce identical node layouts is an inference from the shared API, not verified by reading `apply`'s full body; the unit tier tests it.)

**A4. Other consumers.** The trie's memory is bounded elsewhere: the trie's own soft threshold `ALLOCATED_SIZE_THRESHOLD` (default 2048*10/11 MB, tunable by `cassandra.memtable.row_overhead_size`, `InMemoryTrie.java:58-68`, `CassandraRelevantProperties.java:356`), checked by `reachedAllocatedSizeThreshold` (`InMemoryTrie.java:951-953`) and used for TrieMemtable shards at `TrieMemtable.java:192`; whether the SAI `TrieMemoryIndex` trie is itself checked for that threshold was not verified. The SAI memtable index size is returned from `add` and summed by `MemtableIndex.index` (`MemtableIndex.java:95-97`). Heap vs off-heap placement follows `memtable_allocation_type` (`TrieMemtable.java:94`, default `heap_buffers`, `conf/cassandra.yaml:825`). The memtable space limits `memtable_heap_space` / `memtable_offheap_space` (`conf/cassandra.yaml:797-799`) and flush thresholds govern total memtable memory.

**A5. Evidence beyond the source.** `none` (no external documents or issues relied on). Existing unit test file `test/unit/org/apache/cassandra/index/sai/memory/TrieMemoryIndexTest.java` exists in the tree; its contents were not read.

## B. Verification solution

**B1. Claim under test.** (Negative) Memory used by a `TrieMemoryIndex` (and by a node's SAI memtable) does not follow `MAX_RECURSIVE_KEY_LENGTH`: for the same amount of term data, crossing the 128-byte boundary changes neither the total memory per indexed byte beyond ordinary trie cost nor any ceiling, and nothing is rejected at length 128/129; only the term-size guardrail (positive control) rejects terms and stops memory growth.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), `cd $WORK/c509 && ant jar` (or `ant build-test`). Test source: a new test class placed in the copy at `test/unit/org/apache/cassandra/index/sai/memory/` (next to `TrieMemoryIndexTest.java`), reusing its approach of building a `StorageAttachedIndex` on a table with a text column (setup style not verified, read the existing test in the copy first). Run `ant testsome -Dtest.name=<YourTest>` with JVM `-Xmx2g -Xss512k`. For route confirmation make a second copy and add a static `AtomicLong` counter in each branch of `addTerm` (lines 230 and 234) in that copy only.

**B2b. Knobs.** Term length L in bytes, with ASCII text and a non-analyzed text index: 64, 128, 129, 256, 2048, 7000 (all below the 8KiB default fail threshold, `Config.java:942`). Constant value itself is a compile-time knob: second build with `MAX_RECURSIVE_KEY_LENGTH = 0` and one with `= 100000` (copy only), to see whether memory per term changes when all terms use one route. Control knob: `Guardrails` fail threshold `sai_string_term_size_fail_threshold` lowered (set through `DatabaseDescriptor`/guardrails config in the test) to 1KiB. Not verified: the exact setter API.

**B2c. Workload.** For each L, call `TrieMemoryIndex.add(key, Clustering.EMPTY, value)` with N = 20,000 distinct random-content terms of length L (distinct from the first byte so that each term creates its own path of about L trie bytes; no shared prefixes), one partition key each. Total term bytes N x L ranges from about 1.3 MB (L=64) to about 140 MB (L=7000), so the heap is not exhausted at -Xmx2g. Same total bytes variant: for each L, N = 2,000,000 / L terms.

**B2d. Observables and instruments.** Sum of returned values of `add` (this is the index's own usage-side quantity: on-heap delta + off-heap delta + reducer allocations, `TrieMemoryIndex.java:126`); `data.sizeOnHeap()` / `sizeOffHeap()` (`InMemoryTrie.java:969-978`) read via reflection on field `data`; a heap histogram (`jcmd <pid> GC.class_histogram`) after `System.gc()`. Route taken: the counters in the instrumented copy (cannot be observed in the unmodified build except via a debugger breakpoint on `InMemoryTrie.putRecursive(ByteComparable, Object, UpsertTransformer)`).

**B2e. Procedure.**
1. Build; run the instrumented copy once to confirm the counters show the 128 route for L<=128 and the apply route for L>128 (checks that the traced mechanism is real).
2. For each L (same-count and same-total-bytes variants), fresh `TrieMemoryIndex`; add terms; record sum of `add` returns, `sizeOnHeap`, `sizeOffHeap`.
3. Repeat in the builds with the constant 0 and 100000.
4. Control run: guardrail fail threshold 1KiB, add terms of 900 B, 1500 B, 7000 B; record returns and counters.
5. Repeat each measurement 3 times in fresh JVMs.

**B2f. Predictions (before any run).** Memory per indexed term (sum of returns / N) is a smooth, roughly linear-in-L function of L, with no step discontinuity at L=128 -> 129 beyond the one-byte difference; for the same total bytes, memory is within a few percent across the boundary. The builds with the constant 0 and 100000 give per-term memory equal to the default build at every L (same route in all cases changes nothing). Control: terms above the 1KiB threshold return 0 and leave `sizeOnHeap`/`sizeOffHeap` unchanged (no growth), terms below it grow normally.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Per-term memory is smooth across 128/129 and identical across the three constant values | Claim confirmed: constant does not affect memory |
| A step at 129 that disappears when the constant is changed (moves with it) | Claim refuted: the constant changes memory use, though still not a cap; report the size of the step |
| Memory per term cut off or terms rejected at 128/129 | Claim refuted: constant acts as a limit (not expected from the source) |
| Control terms over the guardrail return 0 and add no memory while the constant variants did not | Positive control worked; claim confirmed |
| Control terms above the guardrail still grow memory | Control failed: not confirmed (check threshold setter) |
| Counters show no use of one route at all, or L never exceeds 128 | Limit never exercised: not confirmed |

**B2h. Controls.** Fresh JVM per run and `System.gc()` before histogram; distinct random terms (no prefix sharing) so trie growth is comparable; same N and same total bytes variants; instrumented-copy counters prove which route ran; guardrail run is the positive control where a cap is known to bind.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`), data, commit log, hints and saved caches under a local directory on a disk with at least 20 GB free. JVM: `-Xms2g -Xmx2g` (MAX_HEAP_SIZE / HEAP_NEWSIZE in `conf/jvm-server.options` or env). cassandra.yaml changes: `memtable_allocation_type: heap_buffers` (run 2: `offheap_objects`), `memtable_heap_space: 1024MiB`, `memtable_offheap_space: 1024MiB`, `sai_string_term_size_fail_threshold: 1KiB` only in the control run. Two builds: stock, and a copy with `MAX_RECURSIVE_KEY_LENGTH = 0` at line 64 (instrumentation-free).

**B3b. Knobs.** Term length per row: 100, 128, 129, 400 bytes (same total payload per run). Constant value: 128 (stock) vs 0. Allocation type heap vs off-heap. Control: fail threshold 1KiB with 1500-byte terms.

**B3c. Workload.** Table `ks.t (id bigint primary key, v text)` with `CREATE CUSTOM INDEX ON ks.t(v) USING 'StorageAttachedIndex'`. Per run insert 400,000 rows with distinct random v of the target length (about 40 MB of term data for L=100, 160 MB for L=400; scale rows as 40,000,000 / L so total term bytes are equal), through cqlsh-free client (`cassandra-stress` user mode with a profile, or a CQL driver loop) with 16 threads; flushing disabled for the run by raising the memtable limits above total usage (heap sized so memtable stays below `memtable_heap_space`) and not calling nodetool flush until after readings. Duration: until all rows are acknowledged, then 60 s idle.

**B3d. Observables and instruments.** `nodetool tablestats ks.t` fields "Memtable cell count", "Memtable data size", "Memtable off heap memory used" (printed by `TableStatsPrinter.java:108-112`); SAI gauge `MemtableIndexBytes` (`IndexMetrics.java:58`) via JMX; `jcmd <pid> GC.class_histogram` and `jstat -gc <pid> 1000` after a forced `jcmd <pid> GC.run`; `/proc/<pid>/status` VmRSS for off-heap. Not observable directly: which insertion route was taken (no counter in the stock build).

**B3e. Procedure.**
1. Build stock and constant-0 copies; start node with clean local data dir.
2. Create keyspace (RF 1), table and index; record baseline tablestats / JMX / histogram.
3. Run the workload for L=100; read at end (and after GC.run).
4. Repeat for L=128, 129, 400 (drop and recreate the table between runs, wait for compaction/GC to settle, restart node).
5. Repeat the whole set on the constant-0 build and on `offheap_objects`.
6. Control run: threshold 1KiB, 1500-byte terms, same row count: record index memory and error/warning log counts.
7. Stop the node (`nodetool drain`, `kill`), confirm no Cassandra process remains (`pgrep -f CassandraDaemon`), delete the data directory.

**B3f. Predictions (before any run).** Memtable index bytes and heap/off-heap use scale with total term bytes, are about the same for L=128 and L=129 at equal total bytes (any difference attributable to per-term overhead, not a step), and are the same on the stock and constant-0 builds. Control: with 1KiB threshold the 1500-byte terms are not indexed (warning logs from `noSpamLogger`, `StorageAttachedIndex.java:823`) and `MemtableIndexBytes` stays near baseline while the table data still grows.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Memory for 128 vs 129 equal within noise, and stock = constant-0 | Claim confirmed |
| Memory differs between stock and constant-0 by more than run-to-run noise | Claim refuted: constant influences usage; quantify |
| Memory plateaus or ingestion fails at 128/129 | Claim refuted (not expected) |
| Control (guardrail) stops index growth while the constant variants do not | Positive control moved usage: claim confirmed |
| Control does not reduce index memory | Control failed: not confirmed |
| Memtable flushed during a run, or load never reached 128-byte terms with equal payload | Limit not exercised: not confirmed; rerun with larger limits |

**B3h. Controls.** Same row count and payload across L; repeat each run 3 times; flush and GC state recorded before each reading; heap and off-heap runs separated; clean data dir per run; the guardrail run is the positive control.

**B4. Risks and cleanup.** Unit tier: tests in a local copy only; 2 GB heap; delete `$WORK` afterwards. Cluster tier: at most a few hundred MB to a few GB of data on local disk (confirm free space first; never use shared storage); one node; at the end `nodetool drain`, stop, `pgrep -f CassandraDaemon` and `pgrep -f junit` must return nothing, remove data, commit log, hints and the local source copies. Never modify `/users/jason92/cassandra-5.0.9`.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/MemtableIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/TrieMemtable.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/metrics/IndexMetrics.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java (grep only)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep only)

## D. Stage-4 feedback

`none yet`

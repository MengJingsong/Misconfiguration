# SegmentRowIdOrdinalPairs capacity guard — verification solution  <!-- file: cases/sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java:55` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-25 |
| Estimate | `negative`. Line 55 is `if (size == capacity)`, a bounds check against a capacity that the caller chose and that the constructor allocated up front (`new int[capacity * 2]`, line 45). The "limit" equals the demand, so it cannot cap memory. |
| Ground | `capacity` is not a configured limit. It is the number of rows the caller is about to add (`nRows` at `VectorIndexSegmentSearcher.java:164`, `keysInRange.size()` at `:299`). Allocation size is therefore 8 x capacity + 16 bytes by construction. The only bounds on it are upstream gates (brute-force threshold, `MAX_MATERIALIZED_KEYS`, segment row-id ceiling), not this check. The one hard numeric limit on the class itself is the overflow assert at line 42, which is an int-overflow guard rather than a memory budget. |

## A. Constraint trace

**A1. The constraint.**
- Named by the entry: the field `private final int capacity` (`SegmentRowIdOrdinalPairs.java:33`), set in the constructor (`:40-46`) and compared at `:55` (`size == capacity` throws `ArrayIndexOutOfBoundsException`, `:56`).
- Kind: a per-instance constant derived at runtime from a constructor argument. It is not a yaml key, `-D` property or JMX value, and it cannot be set from outside the call site.
- First declared at `SegmentRowIdOrdinalPairs.java:33`; unit is pairs (one pair = 2 ints = 8 bytes). There is no default.
- Hard ceiling on the structure: `assert capacity < Integer.MAX_VALUE / 2` (`:42`), i.e. at most 1073741822 pairs (`Integer.MAX_VALUE / 2` is 1073741823 = 2^30-1, and the test is strict `<`) [Stage-4 audit amendment 2026-10-26: was "at most 1073741823"; 2^30-1 itself trips the assert]. It matches `SegmentBuilder.LAST_VALID_SEGMENT_ROW_ID = (Integer.MAX_VALUE / 2) - 1L` (`src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:46`). The assert is active only with `-ea`, which Cassandra's stock `conf/jvm-server.options` DOES enable (line 109, `-ea`, under "GENERAL JVM SETTINGS"; no `-da` in `jvm11-server.options`) [Stage-4 audit amendment 2026-10-26: the original text said it was off by default and unverified; the cluster tier therefore runs with the assert active, to be confirmed from the node's command line]. Without `-ea`, a capacity of 2^30 or more makes `capacity * 2` overflow to a negative value, and `new int[...]` throws `NegativeArraySizeException`; 2^30-1 gives an array length of 2^31-2, which HotSpot refuses (`OutOfMemoryError: Requested array size exceeds VM limit`, checked on this JDK 11.0.32.1 with a bare `new int[Integer.MAX_VALUE-1]`, whatever the heap), and the largest allocatable array is MAX_INT-3 elements here (2^30-2 pairs, 8,589,934,592 bytes (16 + 8N)).
- The values that actually flow into `capacity` are bounded by other knobs (A3).

**A2. What it caps.**
- Resource: Java heap (one `int[]` of 2 x capacity, plus later a `NeighborQueue` of the same count in `mapToSegmentRowIdScoreHeap` / `mapToIndexScoreIterator`, `SegmentRowIdOrdinalPairs.java:100-120`).
- What the check compares: `size` (pairs added so far) against `capacity`. It guards against writing past the array, and does not guard memory.

**A3. Mechanism.**
1. Constructor allocates `new int[capacity * 2]` (`:45`) with the full size reserved up front, so memory is spent before any check can fire.
2. `add()` (`:53-60`): if `size == capacity` (`:55`) it throws `ArrayIndexOutOfBoundsException` (`:56`); otherwise it stores row id and ordinal (`:57-58`) and increments `size` (`:59`). When the limit is reached it refuses the add, but the array is already allocated.
3. Call site 1, `VectorIndexSegmentSearcher.searchInternal`:
   - `nRows = Math.toIntExact(maxSSTableRowId - minSSTableRowId + 1)` (`VectorIndexSegmentSearcher.java:155`).
   - `maxBruteForceRows(limit, nRows, graph.size())` (`:156`), defined at `:353-365` as `max(limit, 0.25 * maximumNodeConnections * expectedNodesVisited)`; the factor is at `:363`, the return at `:364`. `maximumNodeConnections` defaults to 16 (`IndexWriterConfig.java:39`).
   - `shouldBruteForce = FORCE_BRUTE_FORCE_ANN == null ? nRows <= maxBruteForceRows : FORCE_BRUTE_FORCE_ANN` (`:161`). `FORCE_BRUTE_FORCE_ANN` is a `@VisibleForTesting` static (`:75-77`).
   - Only when `shouldBruteForce` is true does it run `new SegmentRowIdOrdinalPairs(Math.toIntExact(nRows))` (`:164`). The capacity is therefore at most `maxBruteForceRows`, which depends on `limit` (itself capped at `MAX_TOP_K`, default 1000: `CassandraRelevantProperties.java:479`, `IndexWriterConfig.java:57`, enforced `StorageAttachedIndex.java:503-504`) and on graph size via `VectorMemoryIndex.expectedNodesVisited` (`VectorMemoryIndex.java:275-286`, result clamped to `graphSize`).
   - Upper bound on the allocation is in practice 0.25 x 16 x graph.size() x 8 bytes = 32 bytes per graph node. The bound comes from the threshold, not from the structure.
4. Call site 2, hybrid `orderResultsBy` (`VectorIndexSegmentSearcher.java:284`):
   - `new SegmentRowIdOrdinalPairs(keysInRange.size())` at `:299`, where `keysInRange` is the slice of `results` that falls in the segment's `[minKey, maxKey]` (`:288-291`).
   - `results` comes from `QueryController.materializeKeysAndCloseSource`, which returns `null` once `MAX_MATERIALIZED_KEYS < ++count` (`QueryController.java:449-453`). Default 16000 (`CassandraRelevantProperties.java:476`, field at `QueryController.java:96`).
   - The caller then uses the order-then-filter path when `null` is returned (`QueryController.java:390-397`).
   - So this site is bounded by `cassandra.sai.vector_search.max_materialized_keys`, giving at most 16000 pairs, about 128 KB, per segment per query. Because the whole `keysInRange` is allocated even when many keys fall outside the segment's row range (the `break`/`continue` at `:307-312`), the array can be larger than the pairs actually stored: overshoot.
5. Bypass/overshoot: array capacity can exceed `size` (call site 2). Several SSTables/segments each allocate their own array for one query (`V1SSTableIndex.java:189-194`).

**A4. Other consumers.**
- Same heap, outside this check: the `NeighborQueue` built from the pairs (`SegmentRowIdOrdinalPairs.java:103,116`) and `BruteForceRowIdIterator`'s retained queue (`BruteForceRowIdIterator.java:59,77`).
- The materialized `List<PrimaryKey>` in `QueryController` (`:441`) and `keysInRange` list (`VectorIndexSegmentSearcher.java:288-291`).
- The per-thread `SparseFixedBitSet` cache (`:81,93`), the on-heap graph and PQ vectors, memtable heap, and SAI segment build buffers (`SEGMENT_BUILD_MEMORY_LIMIT`, `V1OnDiskFormat.java:126`).

**A5. Evidence beyond the source.** none (source-only trace).

## B. Verification solution

**B1. Claim under test.** Heap used by `SegmentRowIdOrdinalPairs` equals 16 + 8 x N bytes, N being the capacity the caller passes, regardless of anything the line-55 check does. The check only stops writes past the array. In a real query the allocation follows the upstream gates (brute-force threshold, `max_materialized_keys`), and is not bounded by the pairs class. Falsified if allocation is flat or smaller than 8N as N grows, or if some configured limit inside the class clamps it.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. Copy the tree to local disk first (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`; never build in the shared tree). Then run `ant jar` in the copy.
- Test source goes in the copy only, at `/local/scratch/c509/test/unit/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairsMemTest.java`. Alternatively a plain `main` class compiled against `build/classes/main` and `lib/*.jar` (jvector is required for `NeighborQueue`).
- JVM options: `-Xmx2g -XX:+UseSerialGC -ea` for most runs. Rerun the N = 2^30-1 and N = 2^30 cases without `-ea` (`-da`); the 2^30-2 case needs `-Xmx16g` [Stage-4 audit amendment 2026-10-26: was 2^30 only]. Use `-XX:-UseCompressedOops` as an optional second sweep to show 16-byte-per-pair headers do not change the slope.

**B2b. Knobs.** The only knob is the constructor argument N (the capacity). Values: 1, 1000, 16000 (the default `MAX_MATERIALIZED_KEYS`), 100000, 1000000, 10000000, 100000000, then boundary values 2^30-2 (8,589,934,592 bytes (16 + 8N); run with `-Xmx16g`, the node has 251 GiB), 2^30-1, 2^30 [Stage-4 audit amendment 2026-10-26: was 2^30-1 ("needs -Xmx10g") and 2^30; 2^30-1 can never be allocated, see A1]. Set by passing it in code. [Stage-4 runbook-defect fix 2026-10-26, run 1 unit shakedown: with `-XX:+UseSerialGC` an old generation is only 2/3 of `-Xmx`, so `-Xmx12g` gave `OutOfMemoryError: Java heap space` for the 8.0 GiB array (plain `int[2N]` too); use `-Xmx16g`. B2f's "-Xmx12g" is left as frozen; read it as "a heap that fits".]

**B2c. Workload.**
- For each N: construct the object, call `add(i, i)` N times, then once more (N+1th add), then call `mapToSegmentRowIdScoreHeap` with a trivial score function.
- Arithmetic: int[2N] = 16 + 8N bytes (aligned to 8). N=16000 gives about 128,016 bytes; N=10^7 gives about 80 MB; N=10^8 gives about 800 MB.

**B2d. Observables and instruments.**
- Allocated bytes for the constructing thread: `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())` read before and after the constructor (precision: exact to the byte, includes only this thread).
- Retained bytes: `System.gc()` x3 then `Runtime.totalMemory() - freeMemory()` before and after, holding a reference (coarse, use only for N >= 10^6).
- Exception outcome of the (N+1)th `add`.
- Cannot observe directly: the JIT's escape-analysis effects (stop it with `-XX:-DoEscapeAnalysis`, else small arrays may not be allocated on heap and the thread counter under-reports).

**B2e. Procedure.**
1. Copy source, `ant jar`.
2. Compile the harness against `build/classes/main:lib/*`.
3. Run `java -ea -Xmx2g -XX:+UseSerialGC -XX:-DoEscapeAnalysis -cp ... Harness` for N in the B2b list (up to 10^8); one JVM per N to avoid heap fragmentation.
4. Record allocated-bytes delta, retained-bytes delta, and the outcome of add(N+1).
5. Boundary runs [Stage-4 audit amendment 2026-10-26: replaces the original list, whose 2^30-1 arithmetic was wrong]: N = 2^30-2 with `-ea -Xmx16g` (expect no assert and a successful allocation of 8,589,934,592 bytes (16 + 8N)); N = 2^30-1 with `-ea` (expect `AssertionError: capacity is too large 1073741823`) and with `-da` (expect `OutOfMemoryError: Requested array size exceeds VM limit`); N = 2^30 with `-ea` (expect `AssertionError`) and with `-da` (expect `NegativeArraySizeException`).
6. Positive control (B2h): the same sweep on a plain `new int[2*N]`.

**B2f. Predictions (stated before any run).**
- Allocated-bytes delta = 16 + 8N plus the 24-byte object (12-byte header, two ints, one reference with compressed oops), i.e. delta - (16 + 8N) is between 0 and 24, for every N <= 10^8 [Stage-4 audit amendment 2026-10-26: the original "within 24 bytes" did not say whether the object itself is counted]. Linear, no plateau.
- The (N+1)th `add` throws `ArrayIndexOutOfBoundsException` with message N. No allocation happens at that point; the memory was spent in the constructor.
- [Stage-4 audit amendment 2026-10-26: replaces the original boundary prediction] N = 2^30-2 with `-ea -Xmx12g`: allocation succeeds, delta about 8,589,934,576 + 24 bytes, no assert. N = 2^30-1 with `-ea`: `AssertionError` (the assert is `capacity < 1073741823`); with `-da`: `OutOfMemoryError: Requested array size exceeds VM limit`. N = 2^30: `AssertionError` with `-ea`, `NegativeArraySizeException` with `-da`. An OOM for N >= 2^30-2 with `-Xmx2g` is expected and is not evidence against the claim.
- `mapToSegmentRowIdScoreHeap` additionally allocates a queue of at least 8N bytes (depends on jvector's `NeighborQueue` layout; read the jar's source/javap before comparing).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Delta matches 16 + 8N across N | Claim confirmed: usage follows the demand, not a limit inside the class |
| Delta flat or smaller than 8N for N >= 10^6 | Claim refuted (or the JIT removed the allocation; check -XX:-DoEscapeAnalysis) |
| Usage grows with N while `add` check works as above, and the plain `int[2N]` control grows identically | Claim confirmed |
| Plain `int[2N]` control fails to grow | Harness is not measuring; discard |
| Usage never reaches the largest N (OOM first) | Limit not reached for that N; treat as "not confirmed" for that N only |
| N = 2^30 behavior differs from B2f | The overflow guard is not as traced; amend A1 |

**B2h. Controls.** Positive control: a cap known to bind on this class is the `:42` assert, shown by the N = 2^30-1 and N = 2^30 runs with `-ea` (assert fires, no allocation) against the N = 2^30-2 run (allocates); the plain `int[2N]` is the baseline for the allocation slope. Run with `-XX:-DoEscapeAnalysis` and an object kept reachable to exclude optimizer artifacts. Repeat each N three times.

### B3. Cluster tier

**B3a. Environment and build.**
- One node, JDK 11, built from a local copy of the tag (`ant jar` in `/local/scratch/c509/`). Data, commitlog, saved_caches and hints go to a local disk directory of known size (>= 20 GB free); set `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` in a copied `cassandra.yaml` (`conf/cassandra.yaml` copied outside the tree).
- `-Xms4g -Xmx4g`, G1 default. Enable JFR via `JVM_EXTRA_OPTS="-XX:+FlightRecorder -XX:StartFlightRecording=filename=/local/scratch/run.jfr,settings=/local/scratch/alloc.jfc"`, with `alloc.jfc` enabling `jdk.ObjectAllocationInNewTLAB` and `jdk.ObjectAllocationOutsideTLAB` with `stackTrace=true` (JDK 11 has both events).
- SAI vector indexes require the 5.0 default `sai`; no yaml feature flag needed beyond defaults (verify with `CREATE CUSTOM INDEX ... 'StorageAttachedIndex'` succeeding).

**B3b. Knobs.**
- `-Dcassandra.sai.vector_search.max_materialized_keys` (`CassandraRelevantProperties.java:476`): 1000, 16000 (default), 64000. Set via `JVM_EXTRA_OPTS`; restart required (read once into the static `QueryController.java:96`).
- Query `LIMIT` (10, 100, 1000), within `MAX_TOP_K` = 1000 default (`CassandraRelevantProperties.java:479`; optionally raise with `-Dcassandra.sai.vector_search.max_top_k=10000` to widen the brute-force window).
- WHERE-clause selectivity (matching rows M): 500, 10000, 20000, 50000.

**B3c. Workload.**
- Table: `CREATE TABLE ks.t (pk int PRIMARY KEY, grp int, v vector<float, 16>)`, SAI indexes on `v` (`similarity_function` default) and on `grp`.
- Load 80,500 rows (500 + 10000 + 20000 + 50000; the original 60,000 did not add up [Stage-4 audit amendment 2026-10-26: ]) with `grp` values assigned so that exactly M rows share `grp = 1` for each tested M (e.g., one table, `grp` in {1: 500, 2: 10000, 3: 20000, 4: 50000}). Flush with `nodetool flush` so all data is in one SSTable and one segment (80,500 rows is far below `segment_write_buffer_size` 1024 MiB, `StorageAttachedIndexOptions.java:26,35`; so a single segment is expected; check the SAI logs).
- Added workload cell [Stage-4 audit amendment 2026-10-26; corrected after run 1 the same day, a note only, B3f/B3g untouched: the original note predicted from my own calculation that the 30000-row range at LIMIT 10 would exceed the brute-force threshold and give a no-allocation arm. The trace showed thresholds of 236,240 to 5.8 million for this 80,500-node graph (my calculation had omitted the observed-ratio factor and was wrong), so every range up to the whole segment is brute-force at this graph size, and the "above the threshold, no allocation" half of the token-range prediction is not exercisable here; the 30000-row LIMIT 10 cell was run and is one more brute-force cell. Token ranges select nRows = rows + 1 because the lower bound's own row is included.]
- Queries (hybrid, path 2): `SELECT pk FROM ks.t WHERE grp = ? ORDER BY v ANN OF ? LIMIT 10`, 200 executions per (M, knob) cell.
- Pure ANN with a token range restriction (path 1), to hit `VectorIndexSegmentSearcher.java:164`: `SELECT pk FROM ks.t WHERE token(pk) > ? AND token(pk) <= ? ORDER BY v ANN OF ? LIMIT 100`, choosing ranges that cover about 100, 1000, 5000, 30000 rows.
- Duration: a few minutes per cell. Arithmetic: path 2 allocation is about 8 x min(M, keys-in-segment-range) bytes (M = 16000 gives about 128 KB per query) only if M <= max_materialized_keys; otherwise zero for this class.

**B3d. Observables and instruments.**
- JFR allocation events with top-frame `org.apache.cassandra.index.sai.disk.v1.vector.SegmentRowIdOrdinalPairs.<init>` and class `[I`; read `allocationSize` per event and count (`jfr print --events ObjectAllocationOutsideTLAB run.jfr`, plus `jdk.ObjectAllocationInNewTLAB` for arrays under the TLAB threshold). Large arrays (over about 100 KB) usually fall outside the TLAB, and in-TLAB events are sampled, so treat counts as lower bounds and use sizes.
- Query trace (`TRACING ON`) message "WHERE clause generated more than N rows. Switching to ORDER BY then post filter." (`QueryController.java:451`) shows which path ran. Trace lines at `VectorIndexSegmentSearcher.java:159-160` show `nRows` and `max brute force rows`, which says whether line 164 was reached.
- Heap in use: `jstat -gc <pid> 1000` for context only. A per-query array of at most a few hundred KB is below the noise of a 4 GB heap, so the JFR size is the instrument; heap totals cannot resolve it.

**B3e. Procedure.**
1. Copy tree to local disk, `ant jar`, point yaml dirs at local scratch, check free space.
2. Start the node with the JFR option and default knobs; create schema, load the 80,500 rows, `nodetool flush`, `nodetool compact` is not needed.
3. Warm up: 50 queries per shape.
4. For each cell in (max_materialized_keys x M) run the hybrid query 200 times, then stop JFR dump (`jcmd <pid> JFR.dump filename=...`); extract `int[]` allocations with top frame `SegmentRowIdOrdinalPairs.<init>`.
5. Restart with the next `max_materialized_keys` value; repeat.
6. Run the token-range queries with default knobs; record the traced `nRows` and `max brute force rows` and the allocation sizes.
7. Stop the node (`nodetool drain`, then kill the pid), confirm no `CassandraDaemon` process remains (`pgrep -f CassandraDaemon`).

**B3f. Predictions (stated before any run).**
- Hybrid, `max_materialized_keys` = 16000: M = 500 and 10000 give one `int[]` of about 16 + 8 x M bytes per query per segment (4 KB, 80 KB); M = 20000 and 50000 give none from this class (trace shows the order-then-filter message).
- `max_materialized_keys` = 1000: only M = 500 allocates; the others fall back.
- `max_materialized_keys` = 64000: all four M allocate; M = 50000 gives about 400 KB per query.
- Token-range queries: allocation appears only when traced `nRows <= max brute force rows`, and its size is 16 + 8 x nRows. A range with nRows above the threshold goes to the bitset/graph path with no allocation from this class.
- No setting produces an allocation size that is capped by the `size == capacity` check; the size always equals 8 x the caller's count.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Allocation size = 16 + 8 x (traced count), changing with M and `max_materialized_keys` as predicted | Claim confirmed: usage follows the upstream gate; the class check bounds nothing |
| Same workload, M = 20000, moves from 0 to about 160 KB when `max_materialized_keys` goes 16000 to 64000 | Positive control: a cap known to bind (`max_materialized_keys`) moves the usage, so the harness can see it |
| Allocation size independent of the traced count, or clamped at a constant | Claim refuted: a limit exists in or around the class; amend A1/A3 |
| No `SegmentRowIdOrdinalPairs.<init>` events in any cell | Path not reached (e.g. sstable not flushed, or index served from memtable); not confirmed |
| Events appear but control cell stays flat | Control did not move; not confirmed |
| Allocation exceeds `8 x size` (capacity > pairs stored) | Confirms the overshoot noted in A3 item 4 |

**B3h. Controls.**
- Repeat each cell with the memtable unflushed (served by `VectorMemoryIndex`, no `SegmentRowIdOrdinalPairs`) to show events vanish.
- Run a baseline of the same queries with the JFR stack filter replaced by any other `int[]` allocation, to show the filter is specific.
- Hold `LIMIT`, vector and data fixed between cells; change only one knob at a time.

**B4. Risks and cleanup.**
- Disk: 80,500 x 16 floats is small (tens of MB including SAI files); put everything under a scratch directory on local disk, never on shared storage, and check `df` first.
- Memory: the N = 2^30-1 unit run would need roughly 9 GB; skip unless the machine has it.
- Processes: stop the Cassandra JVM and any harness JVM, then `pgrep -f "CassandraDaemon|Harness"` must return nothing.
- Cleanup: delete the scratch copy of the source, data, commitlog, JFR files; do not leave files in `~/cassandra-5.0.9`.

## C. Sources read

- `~/writeup-A/playbook-autonomous.md`
- `~/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java`
- `src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java`
- `src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java` (lines 41-50, 143-150, 225-241)
- `src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java` (105-200)
- `src/java/org/apache/cassandra/index/sai/plan/QueryController.java` (90-96, 367-457)
- `src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java` (grep and 275-286)
- `src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java` (grep)
- `src/java/org/apache/cassandra/index/sai/disk/v1/V1SSTableIndex.java` (grep)
- `src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java` (grep)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (470-480)
- `src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (5264-5267)
- `conf/cassandra.yaml` (1788-1796)

## D. Stage-4 feedback

2026-10-26, run 1 (results file `stage4-runtime-verification/results/sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous.md`): unit tier **Confirmed, does not cap**; cluster tier **Confirmed, does not cap**; outcome class true negative. The allocation is 16 + 8N bytes for the caller's count N at every value from 1 to 10^8 and at 2^30-2, before `add` runs; in a node the same size appears at both call sites (`VectorIndexSegmentSearcher.java:164` and `:299`) and moves with `max_materialized_keys` and M exactly as the gate predicts. Corrections to this file that came from stage 4, all dated 2026-10-26: before any reading, A1 (`-ea` is on in the stock `jvm-server.options:109`; largest accepted capacity 2^30-2), the B2 boundary list and the 80,500-row load; after the first unit readings, the heap for N = 2^30-2 (12g to 16g, a runbook defect; the unit tier was rerun from its start) and, after the first cluster readings, the note on the brute-force threshold. The frozen B2f-g and B3f-g text did not change (sha256 of those tables `c6394bcc...`). One thing not exercised: a range above the brute-force threshold.

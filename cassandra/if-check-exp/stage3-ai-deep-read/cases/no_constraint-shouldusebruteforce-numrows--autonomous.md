# no_constraint — verification solution  <!-- file: cases/no_constraint-shouldusebruteforce-numrows--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the if statement (the ternary that compares `numRows` with `maxBruteForceRows` in `shouldUseBruteForce`): [`VectorIndexSegmentSearcher.java:349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L349) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the check chooses between two ANN strategies for a candidate set that is already materialized; it does not cap heap, off-heap or disk. |
| Ground | `numRows` is the size of an in-memory list built before the check ([`VectorIndexSegmentSearcher.java:299`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L299) allocates the `int[2*n]` before line 326 evaluates the check), and the threshold is a cost heuristic (comparisons and disk reads), not a byte budget. Both branches allocate memory proportional to the candidate count (lines 253 and 331-332 below), so neither branch bounds usage. |

> **Link rule.** Applied: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** There is no memory or disk constraint on this line. The check is a query-planning heuristic. The nearest things that look like constraints:

- The threshold `maxBruteForceRows`, a local computed in [`VectorIndexSegmentSearcher.java:353-365`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L353-L365). It is `max(limit, 0.25 * getMaximumNodeConnections() * expectedNodesVisited)` (line 364). The `0.25` factor is a hard-coded local, [`VectorIndexSegmentSearcher.java:363`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L363), annotated at line 361 as "dramatically oversimplified". Unit: rows (a count). Not settable by yaml, `-D` or JMX; changing it needs a code change and rebuild. Note: the call at line 344 passes `topK` as the `limit` argument, not the query LIMIT, so the floor is `topK`. (The earlier A1 said `limit`; corrected.)
- The override [`FORCE_BRUTE_FORCE_ANN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L77), `public static Boolean`, annotated `@VisibleForTesting` (line 76). Within `src/` it is read only at lines 161, 349 and 350. In `test/` it is set at `test/unit/org/apache/cassandra/index/sai/cql/VectorTester.java:65`. Not settable by yaml, `-D` or JMX (grep of `src` and `test` found no other writer; other trees not searched).
- The input `getMaximumNodeConnections()` ([`IndexWriterConfig.java:83-85`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L83-L85)): the per-index option `maximum_node_connections` (name at line 37), default `DEFAULT_MAXIMUM_NODE_CONNECTIONS = 16` (line 39), valid range 1 to 512 (lines 38 and 132-133), set in `CREATE CUSTOM INDEX ... WITH OPTIONS` (parsed at lines 110-133) and fixed at index creation. It sizes the graph; it is not a resource cap.
- `expectedNodesVisited` ([`VectorIndexSegmentSearcher.java:367-371`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L367-L371)) multiplies `VectorMemoryIndex.expectedNodesVisited` (`VectorMemoryIndex.java:275-286`, a fitted power/log formula with a comment saying its constants came from observed comparison counts, lines 277-278) by the observed/expected ratio once `getUpdateCount() >= 10` (line 369).

Constraint type for this case: none (a runtime cost heuristic over a derived count).

**A2. What it caps.** Nothing in bytes. The compared quantity is `numRows` = `segmentOrdinalPairs.size()` (line 326), the number of (segmentRowId, ordinal) pairs that survived the primary-key-range filtering loop at lines 302-320, against a row-count threshold. The intended purpose (comment at lines 357-360) is to reduce disk accesses and comparisons, i.e. a latency trade, not a limit.

**A3. Mechanism.**
1. `orderResultsBy` ([`VectorIndexSegmentSearcher.java:284`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L284)) receives `results`, an already materialized `List<PrimaryKey>`, and copies the in-range part into `keysInRange` (lines 288-291).
2. It allocates `new SegmentRowIdOrdinalPairs(keysInRange.size())` (line 299), whose constructor allocates `new int[capacity * 2]` (`SegmentRowIdOrdinalPairs.java:45`). This happens before the check.
3. The loop at lines 302-320 fills it, skipping rows outside the segment (lines 307-312) or without a vector (line 318).
4. `topK = optimizeFor.topKFor(limit)` (line 323; `OptimizeFor.java:43-46`).
5. The check: [`VectorIndexSegmentSearcher.java:349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L349) `FORCE_BRUTE_FORCE_ANN == null ? numRows <= maxBruteForceRows : FORCE_BRUTE_FORCE_ANN`, called from line 326. It also emits a trace line (lines 345-348) with `numRows`, `maxBruteForceRows`, graph size and LIMIT.
6. True: `orderByBruteForce` (line 328; defined at 239). With compressed vectors and more than `topK` pairs it takes the two-pass path (lines 247-248), which builds a `NeighborQueue` of size `size()` (`SegmentRowIdOrdinalPairs.java:116`) and reads full vectors only for reranking (`BruteForceRowIdIterator`, line 85 creates a queue of `limit`). Otherwise it scores all pairs into a `NeighborQueue(size())` (lines 253 and `SegmentRowIdOrdinalPairs.java:103`).
7. False: builds a `SparseFixedBitSet` (line 331, from a thread-local cache created at line 87, sized `graph.size()`) and calls `graph.search` (line 336).
Bypass/overshoot: the check never rejects work. Both outcomes return results, and the pairs array (step 2) is allocated regardless of outcome. A separate, similar check exists at line 161 in `searchInternal` (key-range queries), using `nRows` from a row-id range.

**A4. Other consumers.** Heap: the `results` list and `keysInRange` list (lines 288-291), per-query iterators, jvector `NeighborQueue`s; the segment graph's memory is reported by `indexFileCacheSize()` = `graph.ramBytesUsed()` (lines 99-102), which is independent of this check. Disk/page cache: reading graph and vector files. Memtable vector graphs (`VectorMemoryIndex`) and the SAI segment write buffer (`segment_write_buffer_size`, commented in `conf/cassandra.yaml:1794`) are other consumers; not traced here.

**A5. Evidence beyond the source.** The code comments at lines 343, 357-362 and `VectorMemoryIndex.java:277-278`. Test hook use: `VectorTester.java:57-65` (parameterized on `forceBruteForceQueries`). No external docs or issues relied on.

## B. Verification solution

**B1. Claim under test.** The brute-force/graph choice at line 349 does not bound the node's memory or disk use: the working memory of a query's ordering step grows with the candidate count `numRows` on both sides of the threshold, and the threshold moves only with `topK`, graph size and `maximum_node_connections`, not with any byte budget. Falsified if working memory plateaus or drops at the point where the decision flips, or if the flip tracks a byte-size setting.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (for example `cp -r /users/jason92/cassandra-5.0.9 /local/c509`), never build in the shared tree. `ant jar` then `ant testsome -Dtest.name=<class>` (or `ant test-jvmdtest` style single-class run). Put a new test class `ShouldUseBruteForceProbeTest extends VectorTester` under `test/unit/org/apache/cassandra/index/sai/cql/` in the copy. JVM options: the default test JVM, plus `-Xmx2g`. Test config uses the repo `test/conf/cassandra.yaml`.

**B2b. Knobs.** (1) Candidate count `numRows` via the restricting predicate; values 50, 500, 5000, 50000 over a table of 50000 rows. (2) LIMIT: 10 and 100. (3) `maximum_node_connections`: 8, 16 (default), 64 at index creation. (4) `VectorIndexSegmentSearcher.FORCE_BRUTE_FORCE_ANN`: `null`, `true`, `false` (set directly in the test, as at `VectorTester.java:65`). The three values isolate the check from the two branches.

**B2c. Workload.** One table `(pk int primary key, g int, v vector<float, 64>)` with SAI indexes on `v` (cosine or default) and on `g`; insert 50000 random vectors, `g = pk % 1000` style buckets so that `WHERE g IN (...)` selects a chosen candidate count; flush so an on-disk segment exists (the check runs only in the on-disk searcher, [`VectorIndexSegmentSearcher.java:341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java#L341)). Query `SELECT pk FROM t WHERE g IN (...) ORDER BY v ANN OF ? LIMIT k`. Whether the planner routes this through `orderResultsBy` (line 284) rather than the line-111 `orderBy` path is not verified; the trace line at 345-348 appears only if it does, so check for it in each run and adjust the predicate until it does. The threshold is reached when `numRows <= max(topK, 0.25 * 16 * expectedNodesVisited)`; the exact crossover is read from the trace line, not computed in advance.

**B2d. Observables and instruments.** (a) The trace message "SAI materialized {} rows; max brute force rows is {} ..." (lines 347-348), read via `Tracing`/`TRACING ON` or by setting the logger `org.apache.cassandra.index.sai.disk.v1.segment.VectorIndexSegmentSearcher` to TRACE. It gives `numRows`, the threshold and the decision. (b) Per-query allocated bytes on the query thread: `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(Thread.currentThread().getId())` before and after the CQL call (the test thread runs the read path when executing through `QueryProcessor` internal execution; if the read runs on another executor, sum over that stage's threads, not verified). (c) Retained size is not observable here; only allocation.

**B2e. Procedure.**
1. Create the table and indexes with the chosen `maximum_node_connections`; insert; `flush()`; wait for index build.
2. For each (`FORCE_BRUTE_FORCE_ANN`, candidate count, LIMIT): warm up 5 queries, then run 20 queries, recording trace line values and allocated bytes per query (median).
3. Repeat for the three `maximum_node_connections` values (index rebuilt each time).
4. Print a table: forcing mode, `numRows`, threshold, decision, median allocated bytes.

**B2f. Predictions.** (stated before any run)
- With `FORCE_BRUTE_FORCE_ANN = null`, decision is brute force when and only when `numRows <= maxBruteForceRows` in the trace line; increasing `maximum_node_connections` raises the threshold (linear factor in line 356) and so moves the crossover to larger `numRows`.
- Allocated bytes per query grow monotonically with `numRows` in both forced modes (at least 8 bytes per candidate from the pairs array, line 45), with no step down or plateau at the crossover; the brute-force branch's extra allocation is also proportional to `numRows` (`NeighborQueue(size())`).
- Decision flips with `topK`/graph size/connections but never with any byte-denominated setting (none is consulted in lines 341-371).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Allocated bytes keep growing with `numRows` across the crossover, in both forced modes | Claim confirmed: the check does not bound memory |
| Allocated bytes flat or falling above the crossover while `numRows` rises | Claim refuted: something bounds working memory (find it) |
| Crossover moves with `maximum_node_connections` and graph size, not with heap or any size setting | Heuristic confirmed |
| Positive control (B2h) allocation rises with its knob and flattens at its known cap, while the check-side series keeps rising | Claim confirmed (usage does not follow the constraint) |
| Trace line never appears, or numRows never reaches the threshold, or the control does not move | Not confirmed; rework workload |

**B2h. Controls.** Positive control: a place where a cap is known to bind. Use the same inserts into a plain (non-vector) table with `memtable_heap_space` (`conf/cassandra.yaml:797`) lowered in the test config; memtable heap usage should rise then flush at the cap, showing the harness can see a bound. The two forced modes (`true`/`false`) rule out the heuristic as the cause of any allocation difference. A repeated run with a different random seed rules out data effects. Empty-segment case: a query with zero candidates shows the fixed baseline allocation.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`; `bin/cassandra -f`). `-Xms2g -Xmx2g` fixed, G1. Data, commitlog, hints and saved_caches on a local disk of known free size (at least 10 GB free; set all four directories in `cassandra.yaml` to `/local/c509-run/...`). Vector indexes require `cassandra.yaml` `default_secondary_index: sai` is not needed; plain `CREATE CUSTOM INDEX ... USING 'StorageAttachedIndex'`.

**B3b. Knobs.** `LIMIT` (10, 100, 1000), candidate count via predicate (about 100, 10000, 1000000 of 1000000 rows), `maximum_node_connections` (8, 16, 64), and heap size as a sanity axis (`-Xmx` 1g vs 2g). The `FORCE_BRUTE_FORCE_ANN` override cannot be set on a running node (static field, no setter outside tests); the alternative is to steer the decision through candidate count and `LIMIT`.

**B3c. Workload.** Table `(pk bigint primary key, g int, v vector<float, 128>)`, 1,000,000 rows (about 512 MB of vectors at 4 bytes x 128 per row, plus index), loaded with `cassandra-stress` or a driver script in batches, then `nodetool flush` and wait for index build (`nodetool compact` optional). Queries `... WHERE g IN (...) ORDER BY v ANN OF ? LIMIT k`, run single-threaded for 2 minutes per setting, then 8 threads for 2 minutes. Candidate arithmetic: with `g = pk % 100` each bucket is 10000 rows; `IN` of 1, 10, 100 buckets gives 10000, 100000, 1000000 candidates; `g = pk % 10000` gives 100 candidates per bucket. Whether the planner uses `orderResultsBy` for these shapes is not verified; confirm via `TRACING ON` showing the "SAI materialized" line.

**B3d. Observables and instruments.** (a) Decision and counts: `TRACING ON` in cqlsh, line "SAI materialized {} rows; max brute force rows is {} ..." (lines 347-348). (b) Heap: `jcmd <pid> GC.class_histogram` is too coarse; use `jstat -gc <pid> 1000` for young-gen allocation rate (EC delta plus collections) and JFR (`-XX:StartFlightRecording` with `jdk.ObjectAllocationSample`) for allocation by `SegmentRowIdOrdinalPairs`/`NeighborQueue` frames. Peak heap: `jstat -gc` after each query batch, `jcmd <pid> GC.heap_info`. (c) Disk reads: `/proc/<pid>/io` `read_bytes` deltas per batch, plus `iostat -x 1` on the data device. Page cache obscures reads; run each setting after `echo 3 > /proc/sys/vm/drop_caches` only if permitted (not allowed on a shared machine; otherwise use `read_bytes` and accept cache effects, and say so). (d) Off-heap: `nodetool info` (off-heap line) and RSS from `/proc/<pid>/status`.

**B3e. Procedure.**
1. Build, configure directories, start node, create keyspace/table/index with the chosen `maximum_node_connections`, load, flush, wait for index build (`nodetool describecluster`/`system_views.indexes` status).
2. Record baseline heap and RSS idle.
3. For each (candidate count, LIMIT): run one `TRACING ON` query to record numRows, threshold and decision; then run the 2-minute single-thread load while sampling `jstat -gc` at 1 s, `/proc/<pid>/io` at 5 s; repeat with 8 threads.
4. Repeat for the other `maximum_node_connections` values (drop and recreate the index) and the other heap.
5. Run the positive control (B3h).
6. `nodetool drain`, stop the node, `ps` check, remove run directories.

**B3f. Predictions.**
- Decision follows the trace-line rule `numRows <= maxBruteForceRows`; small candidate sets and large `maximum_node_connections` choose brute force.
- Per-query allocation (young-gen allocation rate divided by query rate) rises with candidate count on both sides of the crossover; peak heap during the 8-thread run rises with candidate count x threads and is not clipped at the crossover.
- Disk `read_bytes` per query is higher in the brute-force branch for the two-pass path only for reranking `topK`-sized subsets and in the graph branch for visited nodes; no byte budget limits either.
- Heap and RSS stay below `-Xmx` plus normal off-heap only because the JVM caps the heap, not because of this check; with 1 million candidates and 8 threads the pairs arrays alone are about 8 MB x 8 threads (line 45: 2 ints per candidate), which stays far below 2 GB, so a heap-exhaustion test is not expected to trigger. Falsified if heap ceiling plus the check clip allocation in a way that tracks the crossover.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Per-query allocation and peak heap rise with candidate count through the crossover, in line with B2 | Claim confirmed: the check does not cap usage |
| Allocation drops or plateaus at the point the decision flips from graph to brute force (or back) and stays so as candidates grow | Claim refuted |
| Crossover moves with `maximum_node_connections`/LIMIT but not with `-Xmx` | Heuristic only |
| Positive control heap usage plateaus at its cap while this series keeps rising | Claim confirmed |
| Trace line absent, candidate counts never straddle the threshold, or control flat | Not confirmed |

**B3h. Controls.** Positive control: same load phase with `memtable_heap_space` set to a small value (for example 256MiB, `conf/cassandra.yaml:797`) on a non-vector table; heap held by memtables should rise then drop at flush near the cap, showing the instruments see a cap that binds. A baseline run with queries idle isolates query-driven allocation. Same data, same node restart state, same query set across settings; warm up before sampling.

**B4. Risks and cleanup.** Unit tier: build in a local copy only; test data goes under the copy's `build/test`; delete the copy when done. Cluster tier: about 1 million vectors of 128 floats is about 0.5 GB raw plus the index, so allow at least 10 GB on local disk; no shared storage for data, commitlog or hints. Do not drop page caches on a shared host. Stop Cassandra, the load generator and any `jstat`/JFR/`iostat` loops; check with `ps -u $USER` that none remain; delete the run directory and JFR files.

## C. Sources read

- `src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java`
- `src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java` (lines 265-290)
- `src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java` (grep)
- `src/java/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java`
- `src/java/org/apache/cassandra/index/sai/disk/v1/vector/OptimizeFor.java`
- `src/java/org/apache/cassandra/index/sai/disk/v1/vector/BruteForceRowIdIterator.java` (grep)
- `src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java` (grep)
- `test/unit/org/apache/cassandra/index/sai/cql/VectorTester.java` (lines 55-65)
- `conf/cassandra.yaml` (grep)
- Input file `agent-in/150.md` (unreviewed trace, corrected above)
- All paths are under `/users/jason92/cassandra-5.0.9`.

## D. Stage-4 feedback

`none yet`

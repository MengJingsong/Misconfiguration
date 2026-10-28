# Brute-force vs graph-search cost switch (maxBruteForceRows) — verification solution  <!-- file: cases/vector_memory_index_cost_model-orderresultsby-maxbruteforcerows--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the if statement, as given: [`VectorMemoryIndex.java:229`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L229) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-27 |
| Estimate | `negative`: the check is a cost-model branch choice between two ways of ranking an already-materialized key list; it caps no memory or disk quantity, and the list it admits to brute force is already bounded elsewhere (16000 keys). |
| Ground | Both branches operate on `resultsInRange`, which was materialized and bounded before this method ran ([`QueryController.java:449`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449)). The threshold only decides CPU work (vector comparisons). The brute-force branch's transient list is at most `maxBruteForceRows <= max(limit, graphSize)`, short-lived and small (tens of KB to ~1 MB) next to the memtable graph. |

**Type:** non-config (query parameter + hard-coded constant; no yaml entry or JVM property is read in the check). Operand `maxBruteForceRows` = `max(limit, expectedNodesVisited(...))`: `limit` is the CQL `LIMIT` (a query parameter); `expectedNodesVisited` uses hard-coded numeric literals (0.7, 2, 0.33, 0.13). The JVM property `cassandra.sai.vector_search.max_materialized_keys` bounds the other operand's size upstream but does not take part in the check itself.

> Link rule applied to the declaration and the check.

## A. Constraint trace

**A1. The constraint.** No declared constraint constant; the compared values are:
- left: `resultsInRange.size()`, a runtime count of the materialized primary keys inside this memtable index's key bounds ([`VectorMemoryIndex.java:219-222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L219-L222)).
- right: `maxBruteForceRows`, from `maxBruteForceRows(limit, n, graphSize)` ([`VectorMemoryIndex.java:243-251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L243-L251)) = `max(limit, expectedNodesVisited(limit, n, graphSize))`. `limit` = `queryContext.limit()` = `readCommand.limits().count()` (`QueryContext.java:94-96`), the CQL `LIMIT`, capped at `MAX_TOP_K` (default 1000, JVM property `cassandra.sai.vector_search.max_top_k`, `CassandraRelevantProperties.java:479`; enforced at `StorageAttachedIndex.java:503`). `expectedNodesVisited` (`VectorMemoryIndex.java:277-288`) is a fitted formula with hard-coded numeric literals 0.7, 2, 0.33, 0.13 ("constants are computed by Code Interpreter", comment at lines 279-280), clamped to `[min(limit, graphSize), graphSize]`.
- Kind: query parameter + hard-coded literals + runtime values (`graph.size()`, key counts). Unit: rows/nodes (counts). Not settable by config. The literals cannot be changed without a code change.
- Upstream bound on the left operand: `MAX_MATERIALIZED_KEYS` ([`QueryController.java:96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L96)), JVM property `cassandra.sai.vector_search.max_materialized_keys`, default 16000 (`CassandraRelevantProperties.java:476`), read once at class load (restart needed).

**A2. What it caps.** Nothing in memory or disk directly. It selects the algorithm. Memory object the check could be argued to bound: the `scoredKeys` ArrayList plus PriorityQueue built in `orderByBruteForce` (`VectorMemoryIndex.java:253-267`), one `PrimaryKeyWithScore` per key with a vector. That object is transient (per query, per memtable) and at most `min(16000, max(limit, graphSize))` entries, because `resultsInRange.size() <= maxBruteForceRows` and the list was already materialized (the materialized list itself exists in both branches). The other branch allocates only a `KeyFilteringBits` view over the same list (`VectorMemoryIndex.java:352-359`) plus graph-search state (visited set, queue sized by `limit`), so the branch does not shrink the dominant allocation.

**A3. Mechanism.** Enclosing method `orderResultsBy(QueryContext, List<PrimaryKey>, Expression)` (`VectorMemoryIndex.java:204`); sole caller of interest: `QueryController.getTopKRows(List, view)` ([`QueryController.java:406`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L406)) via `MemtableIndex` for hybrid (WHERE + ANN ORDER BY) queries; reached only when materialization stayed within `MAX_MATERIALIZED_KEYS` (`QueryController.java:436-455`).
Steps: (1) trim `results` to this index's `keyBounds` (lines 210-214); (2) compute `maxBruteForceRows` (217); (3) trace (218-219); (4) return empty if nothing in range (221); (5) decode query vector (224-225); (6) the check, [`if (resultsInRange.size() <= maxBruteForceRows)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L229).
- True: `orderByBruteForce` scores every in-range key exactly (one vector comparison per key, `graph.vectorForKey`) and returns a PriorityQueue iterator.
- False: `graph.search(qv, limit, KeyFilteringBits)` visits roughly `expectedNodesVisited` graph nodes, returning the top `limit`.
- Bypass/overshoot: none to bound. A related sibling check at line 175 (`orderBy`, `Math.max(limit, bruteForceRows)`) is the same pattern for the range-restricted path. Both outcomes return results correct for the query; the choice affects CPU only.

**A4. Other consumers.** The memtable graph itself (`OnHeapGraph`, line 83) holds vectors and graph edges on heap, dominating memory, and is bounded by memtable flush thresholds (`memtable_heap_space`, `memtable_offheap_space`), not by this check. The materialized `List<PrimaryKey>` (<=16000 keys) is held by `QueryController` regardless of branch.

**A5. Evidence beyond the source.** Searched `src/java` for callers of `orderResultsBy`/`maxBruteForceRows`/`expectedNodesVisited` (callers above; `expectedNodesVisited` is also used from the on-disk searcher `VectorIndexSegmentSearcher`, same formula). Comment in `CassandraRelevantProperties.java:470-475` describes the materialize-key bound as a buffering bound enabling brute-force sorting or filtered graph traversal. Source comment at VectorMemoryIndex `maxBruteForceRows` states the goal is "minimize the number of vector comparisons", i.e. a CPU cost model. No docs or issues consulted; git history not inspected beyond tree contents.

## B. Verification solution

**B1. Claim under test.** The branch at line 229 does not bound memory: heap used by a hybrid ANN query is flat (within noise) as `maxBruteForceRows` moves the query between the brute-force and graph-search branches, because both operate on the same already-materialized list; the transient brute-force allocation is bounded by 16000 entries (<~2 MB).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. In a private copy of the tag: `ant jar`, then a JUnit/small main under `test/unit/org/apache/cassandra/index/sai/memory/` (copy pattern of `VectorMemoryIndexTest`) that constructs a `VectorMemoryIndex` over a `StorageAttachedIndex` with a `vector<float,64>` column, inserts N vectors, then calls `orderResultsBy` directly with a hand-built `QueryContext` (limit = L) and a `List<PrimaryKey>` of chosen size. JVM: `-Xmx2g -XX:+UseSerialGC` (deterministic GC accounting).

**B2b. Knobs.** The threshold itself is not directly settable (literals). Vary the operands instead: graph size `graphSize` in {1000, 5000, 20000}; `limit` in {10, 100, 1000}; `resultsInRange.size()` in {100, 1000, 5000, 16000}. These sweep both sides of the check: `expectedNodesVisited` rises with graphSize and with restriction, so for fixed limit the size at which brute force flips changes. Log `maxBruteForceRows` via the Tracing string or by calling the public static `expectedNodesVisited` to pre-compute the flip point per combination. Arm B (patched-literal build, optional): change the 0.7 coefficient to 0.0 (forcing brute-force never beyond `limit`) versus 1000.0 (forcing brute force up to graphSize) in a private copy, to move the flip without changing data.

**B2c. Workload.** Insert graphSize random vectors (seeded). For each (graphSize, limit, size) triple, call `orderResultsBy` 200 times with fresh query vectors and the same key list (size drawn as a contiguous run of inserted keys). Reaching the limit: pick `size` just below and just above the pre-computed `max(limit, expectedNodesVisited)`; e.g. graphSize 20000, limit 100 gives a flip at a value computable via `expectedNodesVisited(100, size, 20000)`; use sizes at 0.5x, 1x, 2x that value (cap 16000).

**B2d. Observables and instruments.** (1) Which branch ran: Tracing string or `ThreadMXBean`-free check by testing the returned iterator type (`PriorityQueueIterator` vs `NodeScoreToScoredPrimaryKeyIterator`). (2) Allocated bytes per call: `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(currentThread)` before/after consuming the whole iterator. (3) Retained heap: after a forced `System.gc()`, `Runtime.totalMemory()-freeMemory()` while holding the returned iterator unconsumed. Cannot observe: off-heap graph allocations inside jvector internals beyond what allocated-bytes shows.

**B2e. Procedure.** 1. Build jar. 2. Build the test harness. 3. For each graphSize, load graph once. 4. For each (limit, size) run warm-up 50 calls, then 200 measured calls recording branch, allocated bytes per call, and retained heap with the iterator held. 5. Repeat with arm B patched jar if used. 6. Positive control (below).

**B2f. Predictions (before any run).** (a) Branch flips exactly where `size <= max(limit, expectedNodesVisited)`. (b) Retained heap with iterator held: brute-force branch = O(size) objects, ~(48 to 80 B) x size, i.e. <= ~1.3 MB at size 16000; graph-search branch = small (O(limit)). (c) Allocated bytes per call differ by branch but both are bounded by O(16000) entries; no value exceeds ~3 MB per call. (d) Claim confirmed if the memory difference between branches stays under ~2 MB while the heap held by the graph (tens to hundreds of MB at graphSize 20000, 64 dims = 5 MB raw vectors plus edges) is unchanged.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Branch flips at the computed point; per-call retained/allocated bytes bounded by <~3 MB in both branches and not growing with graphSize beyond the list size | Claim confirmed: the check bounds no significant memory |
| Retained bytes in brute-force branch grow roughly linearly with size up to the threshold, then drop | Check does cap the transient list at maxBruteForceRows (small, <=1.3 MB); estimate stays negative only if the amount is insignificant. Record the figure; if it were comparable to graph memory, revise to positive |
| Memory scales with `limit` or graphSize far beyond the list size | Claim refuted |
| Positive control (see B2h) does not move, or size never reaches the flip | Not confirmed: rerun with other sizes |

**B2h. Controls.** Positive control: the cap `MAX_MATERIALIZED_KEYS` known to bind: run `QueryController`'s materialization (or a list-building loop equivalent, `QueryController.java:440-455`) with the property set to 1000 versus 16000 and show the held list size moves (1000 vs 16000 keys) while the line-229 branch moves nothing. Also fixed seed, same JVM, same GC, discard warm-up.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, build with `ant jar` from a private copy; `cassandra.yaml` defaults except `-Xms2g -Xmx2g`, `memtable_allocation_type: offheap_objects`? Keep default (`heap_buffers`) so memtable vectors count on heap. Data and logs in a private directory; `-Dcassandra.sai.vector_search.max_materialized_keys=16000` default (set explicitly).

**B3b. Knobs.** CQL `LIMIT` in {10, 100, 1000}; WHERE selectivity (number of rows matching the non-vector predicate) in {500, 5000, 15000} to give `resultsInRange.size()` on both sides of the threshold; memtable stays unflushed (disable auto flush by large memtable settings, `nodetool` not used until the end). Arm B (patched literal build) as in B2b to force branch.

**B3c. Workload.** Table `(id int PRIMARY KEY, grp int, v vector<float, 64>)`, SAI indexes on `v` (cosine) and `grp`. Insert 20000 rows, `grp` assigned so that each value matches the targeted selectivity; all stay in the memtable. Queries: `SELECT id FROM t WHERE grp = X ORDER BY v ANN OF [..] LIMIT L`, 2000 queries per (L, selectivity) cell with 4 client threads (cassandra-stress or a python driver script). Threshold computation: use `expectedNodesVisited` as in B2 to label each cell predicted-brute/predicted-graph.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.class_histogram` before/after each cell and `jstat -gc <pid> 1000` sampling; allocation rate from `jstat` (`EU` growth) or JFR (`jcmd JFR.start settings=profile`) allocation profile filtered to `PrimaryKeyWithScore` and `PriorityQueue`; tracing (`TRACING ON`) to confirm branch via "max brute force rows" message. Cannot isolate exact retained bytes of in-flight queries; use histogram instance counts.

**B3e. Procedure.** 1. Start node, create schema and indexes. 2. Insert data, verify rows in memtable. 3. For each cell: trace one query to record branch, take histogram, run workload with jstat sampling, take histogram. 4. Positive control: stop node, restart with `max_materialized_keys=1000`, rerun the 15000-selectivity cell (expect fall-back to "ORDER BY then post filter" trace message). 5. Shut down the node, delete data directory, confirm no `java` process left (`pgrep -f CassandraDaemon`).

**B3f. Predictions.** Max `PrimaryKeyWithScore` live instances during a query <= max(limit, flip size) <= 16000 and <= ~1.3 MB; steady-state heap after GC identical (within ~2%) across L and selectivity cells with unflushed data constant; branch per cell as predicted. With `max_materialized_keys=1000` the 15000-selectivity cell shifts to the post-filter path and the transient list is capped at 1001 keys (control moves).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Post-GC heap flat across cells; `PrimaryKeyWithScore` instances small and bounded by the list size; branch flips as predicted | Claim confirmed |
| Post-GC heap or live instance counts scale with `maxBruteForceRows` (L or graph size) beyond the list size | Claim refuted |
| Control (max_materialized_keys=1000) moves the list size but line-229 cells do not | Confirms the real cap is upstream, not this check |
| Control does not move, or no cell crosses the flip | Not confirmed |

**B3h. Controls.** Same data and unflushed memtable for all cells; restart-free sweep; warm-up queries discarded; GC forced before heap reads (`jcmd GC.run`); one variable per cell.

**B4. Risks and cleanup.** Disk: <= a few hundred MB under a private data dir, deleted afterward; no shared storage. Processes: Cassandra node, jstat, harness; stop all and check with `pgrep -f "CassandraDaemon|jstat|jcmd"`. Never build in the shared source tree; use a private copy.

## C. Sources read

- src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java (lines 150-300, 352-364)
- src/java/org/apache/cassandra/index/sai/plan/QueryController.java (lines 96, 385-460)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 470-480)
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java (lines 503-504 via grep)
- src/java/org/apache/cassandra/index/sai/QueryContext.java (limit(), via grep)
- src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java (MAX_TOP_K, via grep)

## D. Stage-4 feedback

`none yet`

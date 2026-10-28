# Memtable ANN brute-force vs graph-search cutoff (VectorMemoryIndex.orderBy) — verification solution  <!-- file: cases/vector_memory_index_cost_model-orderby-bruteforcerows--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`VectorMemoryIndex.java:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L190) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the check chooses between two search algorithms (cost heuristic); it caps neither memtable memory nor disk. It only bounds a transient per-query list (<= max(LIMIT, graph size) entries) |
| Ground | The compared operands are the number of in-range memtable keys (runtime state) and max(LIMIT, a fitted cost formula); the formula contains hard-coded fitted literals and no byte or row cap. Both branches allocate result objects of similar order (brute force: an ArrayList of up to N scored keys; graph search: a top-K heap), so usage does not follow the threshold. |

**Type:** non-config (runtime-queried: `resultKeys.size()`, `queryContext.limit()` (CQL `LIMIT`), `graph.size()`; plus hard-coded constants/literals in `expectedNodesVisited`: 0.7, 0.33, 0.13, exponent 2). No yaml entry or JVM property takes part.

## A. Constraint trace

**A1. The constraint.** Compared operands of [`if (resultKeys.size() < Math.max(queryContext.limit(), bruteForceRows))`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L190):
- `resultKeys.size()`: count of memtable primary keys in the query token range, a subset view of `primaryKeys` (declared [`VectorMemoryIndex.java:78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L78), a ConcurrentSkipListSet). Runtime-queried; unit: rows; not settable.
- `queryContext.limit()`: [`QueryContext.java:94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/QueryContext.java#L94) returns `readCommand.limits().count()`, the CQL `LIMIT` of the ANN query (query parameter).
- `bruteForceRows` = `maxBruteForceRows(limit, resultKeys.size(), graph.size())` ([`VectorMemoryIndex.java:238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L238)) = max(limit, `expectedNodesVisited(...)`). The latter ([`VectorMemoryIndex.java:275-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L275-L286)) is a curve fitted to observed comparison counts using hard-coded literals (0.7, 0.33, 0.13, squares); a source comment says they were fitted by "Code Interpreter". It is clamped to [min(limit, graphSize), graphSize].
Constant rule applies: literals take part. No yaml/JVM property. Nothing is settable; changing the literals needs a code change.

**A2. What it caps.** No memory or disk cap. It decides whether to score all `resultKeys` exactly (brute force) or run a JVector graph search with a key-range filter. The only memory-relevant effect: brute force builds `ArrayList<PrimaryKeyWithScore>` of size `resultKeys.size()` plus a PriorityQueue (`orderByBruteForce`, `VectorMemoryIndex.java:248-260`), a transient per-query heap allocation that this check keeps below max(LIMIT, ~graphSize) entries.

**A3. Mechanism.** Enclosing method `orderBy(QueryContext, Expression, AbstractBounds)` ([`VectorMemoryIndex.java:162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L162)). If the key range does not cover the full ring (line 168), it builds `resultKeys` (182), returns empty if none (185), computes `bruteForceRows` (188), then at the [`if` on line 190](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L190):
- true: `orderByBruteForce(qv, resultKeys)` (191): scores every in-range key exactly, returns a PriorityQueueIterator.
- false: `bits = new KeyRangeFilteringBits(keyRange, null)` (193) and falls to `graph.search(qv, limit, bits)` (202).
Full-ring queries skip the check (MatchAllBits, graph search). A sibling check in `orderResultsBy` (~line 225, `resultsInRange.size() <= maxBruteForceRows`) uses the same formula. Callers: SAI ANN query path (memtable index view via `MemtableIndexManager`/`StorageAttachedIndexSearcher`; confirm with `grep -rn "\.orderBy(" src/java/org/apache/cassandra/index/sai`). No bypass or overshoot beyond the clamp: if resultKeys.size() is at most max(limit, graphSize) the brute-force list holds at most that many entries; with a very large LIMIT the list is still bounded by resultKeys.size() <= memtable keys.

**A4. Other consumers.** Memtable memory is governed by memtable heap/off-heap space (`memtable_heap_space`, `memtable_offheap_space`) and the JVector graph itself (`graph`, `VectorMemoryIndex.java`), which this check does not touch. Query-time heap also used by the graph-search branch (JVector visited sets, result heap of size LIMIT).

**A5. Evidence beyond the source.** Source comment at `VectorMemoryIndex.java:277-278` (constants fitted empirically). The disk-side twin is `VectorIndexSegmentSearcher.java:355-370`, which multiplies by an observed ratio. `none` otherwise (issue tracker not consulted; CASSANDRA-18715-era SAI vector work, unverified).

## B. Verification solution

**B1. Claim under test.** Peak transient heap of an ANN query on a memtable does not follow the brute-force threshold: moving the threshold (by LIMIT or range size) changes which algorithm runs, but peak query heap stays at the order of `resultKeys.size()` scored entries or LIMIT-sized heap, and not at any configured cap; memtable resident memory is independent of it.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy tag to `~/work/c509` (never build in the shared tree); `ant jar`. Write a JUnit test under `test/unit/org/apache/cassandra/index/sai/memory/` (new file in the copy), run with `ant testsome -Dtest.name=VectorMemoryIndexBruteForceTest`. Add `-Xmx2g`.

**B2b. Knobs.** (1) `LIMIT` in {1, 10, 100, 1000}; (2) token-range width so `resultKeys.size()` in {50, 500, 5000, 50000} out of a 100000-vector memtable index (dimension 8 to keep vectors small, euclidean). Set via the QueryContext limit and a partial key range. Constants not variable; the optional patched arm replaces `Math.max(queryContext.limit(), bruteForceRows)` with `Integer.MAX_VALUE` (always brute force) and with `0` (never brute force) in the copy.

**B2c. Workload.** Insert 100000 random 8-d vectors with distinct partition keys into one `VectorMemoryIndex`. Query ranges covering the fractions above. Arithmetic: with graphSize=100000 `expectedNodesVisited` is clamped to <= 100000, so for every combination the crossover lies between 50 and 100000; the test records on which side each combination falls (via the Tracing message or by wrapping the method).

**B2d. Observables.** Which branch ran (Tracing text "max brute force rows is N", or the type of returned iterator: PriorityQueueIterator vs NodeScoreToScoredPrimaryKeyIterator); bytes allocated by the thread around `orderBy` + full iteration (`com.sun.management.ThreadMXBean.getThreadAllocatedBytes`); retained heap not directly observable per query.

**B2e. Procedure.** Build index; for each (LIMIT, range) pair: warm up 3 runs, then record thread-allocated bytes for 5 runs, and branch taken. Repeat for the two patched arms.

**B2f. Predictions.** Branch flips from brute force to graph as resultKeys grows past roughly max(LIMIT, expectedNodesVisited). Brute-force allocation grows linearly in resultKeys.size() (order of 100-200 bytes per key); graph-search allocation is roughly independent of resultKeys.size() and grows with LIMIT. Always-brute-force arm at 50000 keys allocates >= 5 MB more than the default arm; never-brute-force arm at 50 keys allocates about the same as default or more.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Allocation steps down or up in line with the branch flip at the threshold (a discontinuity at the crossover) | claim refuted: usage follows the threshold |
| Allocation scales smoothly with resultKeys (brute) or LIMIT (graph), no jump at the crossover; positive control (always-brute arm) grows linearly | claim confirmed |
| Crossover never reached (all runs on one branch) or the control allocation does not grow | not confirmed; widen the knobs |

**B2h. Controls.** Fixed seed vectors; same JVM, forced GC before each measurement; patched arms differ in one literal only; positive control is the always-brute-force arm showing allocation moves with a known driver.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, build from the local tag copy (`ant jar`), `-Xms4g -Xmx4g`, data under `~/work/node1` only; SAI enabled (default in 5.0). Default yaml, `memtable_flush_writers` default; raise `memtable_heap_space` so the vectors stay in the memtable (e.g. 2048MiB) and disable auto flush by not reaching it.

**B3b. Knobs.** CQL `LIMIT` {1, 10, 100, 1000} and a `WHERE token(pk) > X AND token(pk) < Y` range width to produce in-range key counts {50, 5000, 50000}. Arms via the patched build as in B2b if the default arm shows no flip.

**B3c. Workload.** Table `(pk int primary key, v vector<float, 8>)` with `CREATE CUSTOM INDEX ... USING 'StorageAttachedIndex'`; insert 100000 rows through the driver (cqlsh COPY or a python loop); no flush. Query `SELECT pk FROM t WHERE token(pk) > X AND token(pk) < Y ORDER BY v ANN OF [..] LIMIT n`, 200 repetitions per cell, single client thread.

**B3d. Observables.** Per-query heap churn via `jcmd <pid> GC.class_histogram` is too coarse, so use GC log allocation rate (`-Xlog:gc*`) and `nodetool tpstats`; Tracing (`TRACING ON`) shows which branch ran; resident memtable size from `nodetool tablestats` ("Memtable data size", "Off heap memory used"). Per-query bytes cannot be read directly; use total allocated bytes (JMX `ThreadAllocatedBytes` of read-stage threads) over each cell.

**B3e. Procedure.** Start node; load data; for each cell: TRACING ON one query to record the branch, then run 200 queries and read JMX allocated bytes and GC log delta; record tablestats memtable size before and after; stop node, delete `~/work/node1`.

**B3f. Predictions.** Memtable data size identical (within 1%) before and after every cell (check does not alter resident memory). Allocated bytes per query track branch and LIMIT, not a cap: brute-force cells grow about linearly with in-range keys, graph cells grow with LIMIT.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Memtable resident size changes with the cell, or per-query allocation jumps at the branch flip beyond the A2 estimate | claim refuted |
| Memtable size flat; allocation smooth in key count/LIMIT; positive control (patched always-brute arm) shows allocation growth with key count | claim confirmed |
| Branch never flips or the control does not move | not confirmed |

**B3h. Controls.** Same dataset and seed, restart between arms, no concurrent flush/compaction (verify with `nodetool compactionstats`), client pinned to one thread.

**B4. Risks and cleanup.** Disk: 100000 8-d rows, a few tens of MB under `~/work/node1`. Kill the node (`pkill -f CassandraDaemon` scoped to your user, then `pgrep -f CassandraDaemon` to confirm none left) and remove `~/work/node1` and `~/work/c509` build output. Never build in the shared tree.

## C. Sources read

- src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java (lines 78, 100-260, 272-286)
- src/java/org/apache/cassandra/index/sai/QueryContext.java (lines 85-100)
- src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java (grep hits, lines 202-370)
- src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java (grep hit, line 107)

## D. Stage-4 feedback

`none yet`

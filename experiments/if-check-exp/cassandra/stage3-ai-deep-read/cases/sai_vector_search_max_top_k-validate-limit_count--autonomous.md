# ANN top-k LIMIT cap (MAX_TOP_K) — verification solution  <!-- file: cases/sai_vector_search_max_top_k-validate-limit_count--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`StorageAttachedIndex.java:503`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L503) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code, 2026-10-27 |
| Estimate | `positive`: a vector `ORDER BY ... ANN OF` query is rejected when its LIMIT exceeds MAX_TOP_K, and the per-query heap structures (top-k priority queue, pending-rows deque, processed-keys set) are sized by that LIMIT, so their entry count (and heap) is capped. Caveat: the cap is on rows, not bytes, so heap also scales with row width. |
| Ground | — |

**Type:** non-config (query parameter). The compared operand is the CQL `LIMIT` (`command.limits().count()`, a query parameter); the bound is the declared constant `MAX_TOP_K` (`public static final int`), whose value is read once at class load from the JVM property `cassandra.sai.vector_search.max_top_k` (default `"1000"`). Constant rule applied: a declared constant (`MAX_TOP_K`) takes part in the check, so this is not a skip, although its value comes only from the JVM property. Both are named here.

> **Link rule.** Constraint declaration: [`IndexWriterConfig.java:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L57). If statement: [`StorageAttachedIndex.java:503`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L503).

## A. Constraint trace

**A1. The constraint.** `MAX_TOP_K`; kind: constant (`public static final int`) initialised from a JVM property; declared at [`IndexWriterConfig.java:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L57) as `SAI_VECTOR_SEARCH_MAX_TOP_K.getInt()`. The property is declared at `CassandraRelevantProperties.java:479` as `SAI_VECTOR_SEARCH_MAX_TOP_K("cassandra.sai.vector_search.max_top_k", "1000")` (doc comment: "Controls the maximum top-k limit for vector search"). Unit: rows (LIMIT count). Default 1000, a literal string in the property declaration. Settable only with `-Dcassandra.sai.vector_search.max_top_k=N` at JVM start (value is frozen into a static final at class load, so a restart is needed); not in yaml, not JMX. No numeric literal appears in the check itself.

**A2. What it caps.** Heap (on-node, coordinator/replica read path). The quantity compared is the LIMIT of an ANN query (`command.limits().count()`) against MAX_TOP_K. The source comment at line 502 gives the purpose: "to avoid overflow of the vector graph internal data structure and avoid OOM when filtering top-k". LIMIT sizes: `PriorityQueue` of top-k rows (`VectorTopKProcessor.java:81,91`), `HashSet(softLimit)` and `ArrayDeque(softLimit)` in the searcher (`StorageAttachedIndexSearcher.java:644-646`), and the number of ANN candidates requested from the graph.

**A3. Mechanism.** Enclosing method `StorageAttachedIndex.validate(ReadCommand)` (`StorageAttachedIndex.java:497`).
1. `if (!indexTermType.isVector()) return;` (line 499-500): non-vector SAI indexes are not checked.
2. The check, [`StorageAttachedIndex.java:503`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L503): `command.limits().count() > MAX_TOP_K`.
3. True: throws `InvalidRequestException(String.format(ANN_LIMIT_ERROR, MAX_TOP_K, count))` (line 504; message at line 141: "Use of ANN OF in an ORDER BY clause requires a LIMIT that is not greater than %s. LIMIT was %s"); the query fails before execution. False: execution proceeds with LIMIT up to and including MAX_TOP_K (so LIMIT == MAX_TOP_K is allowed).
Callers: `Index.QueryPlan.validate(ReadCommand)` (`Index.java:987-989`) runs `getIndexes().forEach(i -> i.validate(command))`; reached from `ReadCommand.maybeValidateIndex()` (`ReadCommand.java:410-416`). Only the validate path enforces it; `MAX_TOP_K` has no other reference in `src/java` besides the import (`StorageAttachedIndex.java:118`).
Separate guard, not this check: `SelectStatement.java:318` rejects ANN queries with no LIMIT (`TOPK_LIMIT_ERROR`, line 116), so unlimited is not a bypass.
Overshoot/bypass: the cap is on row count; row size is unbounded by it (wide rows or large `vector<float, N>` raise bytes per entry). Because the value is static, per-query LIMIT cannot exceed it, but MAX_TOP_K itself can be set arbitrarily high by the operator. Internal batch paths (internal queries that do not call `maybeValidateIndex`) were not traced.

**A4. Other consumers.** Memtable and SAI vector graph (on-heap/off-heap segment builders), key cache, chunk cache, other concurrent queries' PQs, and `cassandra.sai.vector_search.max_materialized_keys` (`CassandraRelevantProperties.java:475`, default 16000) which bounds a different structure. None are controlled by MAX_TOP_K.

**A5. Evidence beyond the source.** Test `VectorInvalidQueryTest.mustHaveLimitSpecifiedAndWithinMaxAllowed` (`test/unit/org/apache/cassandra/index/sai/cql/VectorInvalidQueryTest.java:196-205`) asserts that LIMIT 1001 gives `ANN_LIMIT_ERROR` with default MAX_TOP_K. No docs or CHANGES entry found by grep for `MAX_TOP_K` / `max_top_k` in `doc`, `CHANGES.txt`, `NEWS.txt`.

## B. Verification solution

**B1. Claim under test.** With MAX_TOP_K = K, an ANN query with LIMIT > K is rejected before any top-k structure is allocated, and for accepted LIMIT <= K the heap held by top-k structures grows at most linearly with LIMIT (about LIMIT x per-row bytes), so lowering K lowers the maximum possible per-query heap.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy the tag to a private directory (`rsync -a` of the source to `~/work/cass-unit`), `ant jar` there; tests in the copy under `test/unit/org/apache/cassandra/index/sai/cql/` (a new class modeled on `VectorInvalidQueryTest`, extending the same SAI CQL test base). JVM options through the test config: `-Dcassandra.sai.vector_search.max_top_k=<K>` set per run (the constant is read at class load, so one JVM per K).

**B2b. Knobs.** K in {10, 1000 (default), 5000}, one JVM each, set with the `-D` flag. LIMIT values per K: K-1, K, K+1.

**B2c. Workload.** Table `(k int PRIMARY KEY, v vector<float, 4>)` with SAI index (`similarity_function: euclidean`); insert 6000 rows; run `SELECT k FROM %s ORDER BY v ANN OF [..] LIMIT <n>` through `executeNet`. For the heap measurement, call `VectorTopKProcessor` indirectly by querying with LIMIT = K after a flush of the data (so rows come through the processor).

**B2d. Observables and instruments.** (1) Exception type/message of each query. (2) For accepted queries, heap delta around the query: `Runtime` used memory after forced `System.gc()` is too coarse, so use the JMX/`ThreadMXBean.getThreadAllocatedBytes` of the query thread (`com.sun.management.ThreadMXBean`) before/after, sampled once per query, 5 repeats, median. Cannot directly observe the PQ's retained size; allocated bytes is a proxy.

**B2e. Procedure.** For each K: start JVM with the flag; run the three LIMITs; record outcome and allocated bytes (accepted ones); stop the JVM.

**B2f. Predictions.** Rejected exactly when LIMIT > K, with message `... not greater than K. LIMIT was n`. LIMIT == K accepted. Allocated bytes per accepted query grow roughly linearly with LIMIT (LIMIT 5000 at K=5000 allocates about 5x LIMIT 1000 at K=1000, within a factor of 2 given fixed overhead). LIMIT 1001 accepted at K=5000 and rejected at K=1000.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| LIMIT > K rejected, LIMIT <= K accepted for all three K | check enforces the cap as read (supports claim) |
| LIMIT > K accepted | cap not enforced (claim refuted) |
| allocation grows with LIMIT and scales with K when K is raised | heap bounded by the cap (supports claim) |
| allocation flat across LIMIT 10 / 1000 / 5000 | structures not sized by LIMIT; cap does not bound heap (claim refuted) |
| rejection holds but allocations indistinguishable from noise | inconclusive, enlarge row width/rows |

**B2h. Controls.** Same data and query with a non-vector filter query (no ANN) for the allocation baseline; repeat each measurement after one warm-up query; fix `-Xmx` equal across runs.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional) built from a local copy of the tag with `ant jar`; `-Xms2g -Xmx2g` for a tight heap; `cassandra-env.sh` / `jvm11-server.options` copy edited to add `-Dcassandra.sai.vector_search.max_top_k=<K>`; fresh data directory under a private path; `cassandra-stress` or Python driver as client; GC logging `-Xlog:gc*:file=<private>/gc.log`.

**B3b. Knobs.** K in {1000 (default), 10000} (restart between); LIMIT in {1000, 10000, 10001}. Wide-row variant: vector dimension 1536.

**B3c. Workload.** Table `(k int PRIMARY KEY, v vector<float, 1536>)`, 50,000 rows (about 300 MB of vectors, flushed), SAI index; 32 concurrent client threads issuing ANN queries with the target LIMIT for 5 minutes. Arithmetic: per-row cost about 6 KB (1536 x 4 B), so a top-k queue of 10,000 rows is about 60 MB per query; 32 concurrent is about 1.9 GB, above the 2 GB heap's headroom, so heap pressure is reached at K=10000 and not at K=1000 (about 6 MB per query, 190 MB total).

**B3d. Observables and instruments.** Client-side error rate and message; `jcmd <pid> GC.heap_info` and `jstat -gcutil <pid> 1000` sampled every second; peak old-gen used and GC count from the gc log; `OutOfMemoryError` in `system.log`. Cannot observe PQ size directly.

**B3e. Procedure.** Start node with K=1000; load data and flush (`nodetool flush`); run the three LIMITs for 5 min each with sampling; record; stop node (`nodetool drain`, kill), delete data dir; restart with K=10000 and repeat.

**B3f. Predictions.** K=1000: LIMIT 1000 accepted, heap peak modest (below 50% of heap); LIMIT 10000 and 10001 rejected 100% with `ANN_LIMIT_ERROR`, no extra heap. K=10000: LIMIT 10000 accepted with peak heap at least 3x the K=1000/LIMIT 1000 peak, possible GC storm or OOM; LIMIT 10001 rejected.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| over-K LIMITs rejected, heap peak rises with accepted LIMIT and with K | cap bounds heap (supports claim) |
| over-K LIMIT accepted | cap not enforced (refuted) |
| heap peak same at LIMIT 1000 and 10000 | heap not driven by LIMIT; cap does not bound heap (refuted) |
| no heap rise at any LIMIT, queries fast | workload too small, enlarge rows/concurrency (inconclusive) |

**B3h. Controls.** Run the same concurrency with LIMIT 10 as baseline; keep heap size, data and client identical across K; repeat each configuration twice.

**B4. Risks and cleanup.** Disk: about 300 MB data plus logs under a private directory; delete after runs. A K=10000 run may OOM the JVM; use a private node only. Stop every Cassandra and client process and check with `pgrep -fa CassandraDaemon` and `pgrep -fa cassandra-stress`. Never build in the shared source tree.

## C. Sources read

- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java (lines 118, 141, 470-540)
- src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java (50-60)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (475-481)
- src/java/org/apache/cassandra/db/ReadCommand.java (405-418)
- src/java/org/apache/cassandra/index/Index.java (987-989, grep)
- src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java (grep)
- src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java (640-650)
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (116, 318 grep)
- test/unit/org/apache/cassandra/index/sai/cql/VectorInvalidQueryTest.java (195-207)

## D. Stage-4 feedback

`none yet`
